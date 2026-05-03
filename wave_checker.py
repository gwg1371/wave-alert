import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import requests

SPOTS = [
    {
        "name": "דרומי",
        "lat": 32.1580,
        "lon": 34.7965,
        "offshore_dir": 100,  # wind from ~east is offshore for this west-facing beach
        "best_tide": None,    # Mediterranean tidal range is tiny; no strong preference
    },
    {
        "name": "תל ברוך",
        "lat": 32.1220,
        "lon": 34.7900,
        "offshore_dir": 90,
        "best_tide": None,
    },
]

DAYS_HE = {
    "monday": "שני",
    "tuesday": "שלישי",
    "wednesday": "רביעי",
    "thursday": "חמישי",
    "friday": "שישי",
    "saturday": "שבת",
    "sunday": "ראשון",
}

SURF_START_HOUR = 6
SURF_END_HOUR = 18
FORECAST_DAYS = 5
HISTORY_FILE = "history.json"
MAX_HISTORY = 90

ISRAEL_TZ = timezone(timedelta(hours=3))


def get_israel_now() -> datetime:
    return datetime.now(ISRAEL_TZ)


def today_name(now: datetime) -> str:
    return now.strftime("%A").lower()


# ---------------------------------------------------------------------------
# Data fetching — unified hourly format
# ---------------------------------------------------------------------------
# Every fetch function returns list[dict] where each dict is:
#   {date: "YYYY-MM-DD", hour: int, wave_height: float|None,
#    wave_period: float|None, wind_speed_kmh: float|None,
#    wind_dir: float|None, tide_height: float|None}

def _pick(sources: dict) -> float | None:
    """Pick best available value from a Stormglass multi-source dict."""
    for src in ("sg", "noaa", "icon", "meto", "dwd", "fcoo", "fmi", "yr", "smhi"):
        val = sources.get(src)
        if val is not None:
            return float(val)
    for val in sources.values():
        if val is not None:
            return float(val)
    return None


def fetch_stormglass(
    lat: float, lon: float, start_date: str, end_date: str, key: str
) -> list[dict] | None:
    """
    Single Stormglass call covering wave height+period, wind, and tide.
    Returns unified hourly list in Israel local time, or None on failure.
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=ISRAEL_TZ)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=ISRAEL_TZ)

    params = {
        "lat": lat,
        "lng": lon,
        "params": "waveHeight,wavePeriod,windSpeed,windDirection",
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
    }
    try:
        resp = requests.get(
            "https://api.stormglass.io/v2/weather/point",
            params=params,
            headers={"Authorization": key},
            timeout=20,
        )
        if not resp.ok:
            body = resp.text[:300]
            print(
                f"Stormglass HTTP {resp.status_code} for ({lat}, {lon}): {body}",
                file=sys.stderr,
            )
            return None
        data = resp.json()
    except requests.RequestException as e:
        print(f"Stormglass error for ({lat}, {lon}): {e}", file=sys.stderr)
        return None

    result = []
    for entry in data.get("hours", []):
        try:
            local_dt = datetime.fromisoformat(
                entry["time"].replace("Z", "+00:00")
            ).astimezone(ISRAEL_TZ)
        except (KeyError, ValueError):
            continue

        wind_ms = _pick(entry.get("windSpeed", {}))
        result.append({
            "date": local_dt.strftime("%Y-%m-%d"),
            "hour": local_dt.hour,
            "wave_height": _pick(entry.get("waveHeight", {})),
            "wave_period": _pick(entry.get("wavePeriod", {})),
            "wind_speed_kmh": round(wind_ms * 3.6, 1) if wind_ms is not None else None,
            "wind_dir": _pick(entry.get("windDirection", {})),
            "tide_height": _pick(entry.get("seaLevel", {})),
        })

    return result or None


def fetch_open_meteo(
    lat: float, lon: float, start_date: str, end_date: str
) -> list[dict] | None:
    """
    Fallback when no Stormglass key. Calls Open-Meteo marine + forecast APIs.
    Returns unified hourly list (tide_height is always None).
    """
    marine_params = {
        "latitude": lat, "longitude": lon,
        "hourly": "wave_height,wave_period",
        "start_date": start_date, "end_date": end_date,
        "timezone": "Asia/Jerusalem",
    }
    wind_params = {
        "latitude": lat, "longitude": lon,
        "hourly": "wind_speed_10m,wind_direction_10m",
        "start_date": start_date, "end_date": end_date,
        "timezone": "Asia/Jerusalem",
        "wind_speed_unit": "kmh",
    }
    try:
        marine_resp = requests.get(
            "https://marine-api.open-meteo.com/v1/marine",
            params=marine_params, timeout=15,
        )
        marine_resp.raise_for_status()
        marine = marine_resp.json()
    except requests.RequestException as e:
        print(f"Marine API error for ({lat}, {lon}): {e}", file=sys.stderr)
        return None

    wind_by_time: dict[str, tuple[float, float]] = {}
    try:
        wind_resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=wind_params, timeout=15,
        )
        wind_resp.raise_for_status()
        wind = wind_resp.json()
        for t, spd, drn in zip(
            wind["hourly"]["time"],
            wind["hourly"]["wind_speed_10m"],
            wind["hourly"]["wind_direction_10m"],
        ):
            if spd is not None and drn is not None:
                wind_by_time[t] = (spd, drn)
    except requests.RequestException as e:
        print(f"Wind API error for ({lat}, {lon}): {e}", file=sys.stderr)

    try:
        times = marine["hourly"]["time"]
        heights = marine["hourly"]["wave_height"]
        periods = marine["hourly"].get("wave_period", [None] * len(times))
    except KeyError:
        return None

    result = []
    for t, h, p in zip(times, heights, periods):
        w = wind_by_time.get(t)
        result.append({
            "date": t[:10],
            "hour": int(t[11:13]),
            "wave_height": h,
            "wave_period": p,
            "wind_speed_kmh": w[0] if w else None,
            "wind_dir": w[1] if w else None,
            "tide_height": None,
        })

    return result or None


def _fetch_spot_data(
    spot: dict, start_date: str, end_date: str, stormglass_key: str
) -> list[dict] | None:
    """Try Stormglass first; fall back to Open-Meteo if no key or failure."""
    if stormglass_key:
        data = fetch_stormglass(spot["lat"], spot["lon"], start_date, end_date, stormglass_key)
        if data is not None:
            return data
        print(f"Stormglass failed for {spot['name']}, falling back to Open-Meteo.", file=sys.stderr)
    return fetch_open_meteo(spot["lat"], spot["lon"], start_date, end_date)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _angle_diff(a: float, b: float) -> float:
    """Smallest angular difference between two compass bearings (0–180)."""
    diff = abs(a - b) % 360
    return diff if diff <= 180 else 360 - diff


def height_score(height: float, min_height: float) -> float:
    if height < min_height:
        return 0.0
    ratio = (height - min_height) / max(min_height, 0.01)
    return min(1.0, 0.3 + ratio * 0.7)


def period_score(period: float | None) -> float:
    if period is None:
        return 0.5
    if period < 6:
        return 0.1
    if period < 8:
        return 0.3 + (period - 6) / 2 * 0.2   # 0.3 → 0.5
    if period < 12:
        return 0.5 + (period - 8) / 4 * 0.4   # 0.5 → 0.9
    return 1.0


def wind_score(wind_speed_kmh: float | None, wind_dir: float | None, offshore_dir: float) -> float:
    if wind_speed_kmh is None or wind_dir is None:
        return 0.5
    if wind_speed_kmh < 10:
        return 0.9  # glassy — good regardless of direction
    diff = _angle_diff(wind_dir, offshore_dir)
    if diff <= 30:
        return 1.0
    if diff <= 90:
        return 1.0 - (diff - 30) / 60 * 0.7   # 1.0 → 0.3
    return max(0.0, 0.3 - (diff - 90) / 90 * 0.3)


def tide_phase(tide_heights: dict[int, float], hour: int) -> str | None:
    h = tide_heights.get(hour)
    h_prev = tide_heights.get(hour - 1)
    h_next = tide_heights.get(hour + 1)
    if h is None:
        return None
    if h_prev is not None and h_next is not None:
        if h >= h_prev and h >= h_next:
            return "high"
        if h <= h_prev and h <= h_next:
            return "low"
    if h_prev is not None:
        return "rising" if h > h_prev else "falling"
    if h_next is not None:
        return "rising" if h_next > h else "falling"
    return None


def tide_score(tide_heights: dict[int, float] | None, hour: int, best_tide: str | None) -> float:
    if not tide_heights or best_tide is None:
        return 0.5
    phase = tide_phase(tide_heights, hour)
    if phase is None:
        return 0.5
    if phase == best_tide:
        return 1.0
    opposites = {"rising": "falling", "falling": "rising", "high": "low", "low": "high"}
    if opposites.get(best_tide) == phase:
        return 0.2
    return 0.5


def tide_label(tide_heights: dict[int, float] | None, hour: int) -> str | None:
    if not tide_heights:
        return None
    phase = tide_phase(tide_heights, hour)
    return {"high": "גאות ▲", "low": "שפל ▼", "rising": "עולה ↑", "falling": "יורד ↓"}.get(phase)


def wind_label(wind_speed_kmh: float | None, wind_dir: float | None, offshore_dir: float) -> str:
    if wind_speed_kmh is None or wind_dir is None:
        return "?"
    if wind_speed_kmh < 10:
        return "גלאסי 🪟"
    diff = _angle_diff(wind_dir, offshore_dir)
    if diff <= 45:
        return "אוף 🟢"
    if diff <= 90:
        return "קרוס 🟡"
    return "און 🔴"


def composite_score(
    h_score: float, p_score: float, w_score: float, t_score: float | None = None
) -> float:
    if t_score is not None:
        raw = h_score * 0.45 + p_score * 0.25 + w_score * 0.20 + t_score * 0.10
    else:
        raw = h_score * 0.50 + p_score * 0.28 + w_score * 0.22
    return round(raw * 10, 1)


# ---------------------------------------------------------------------------
# Conditions extraction
# ---------------------------------------------------------------------------

def best_conditions_in_window(
    hours: list[dict], spot: dict, min_height: float, date_str: str
) -> dict | None:
    """Return the highest-scoring hour in the surf window for the given date."""
    surf_hours = [
        h for h in hours
        if h["date"] == date_str
        and SURF_START_HOUR <= h["hour"] < SURF_END_HOUR
        and h["wave_height"] is not None
    ]
    if not surf_hours:
        return None

    # Build tide heights across the full day (not just surf window) for phase detection
    tide_heights: dict[int, float] = {
        h["hour"]: h["tide_height"]
        for h in hours
        if h["date"] == date_str and h["tide_height"] is not None
    }
    has_tide = bool(tide_heights)

    best: dict | None = None
    best_score = -1.0

    for h in surf_hours:
        hs = height_score(h["wave_height"], min_height)
        ps = period_score(h["wave_period"])
        wsc = wind_score(h["wind_speed_kmh"], h["wind_dir"], spot["offshore_dir"])
        ts = tide_score(tide_heights, h["hour"], spot.get("best_tide")) if has_tide else None
        cs = composite_score(hs, ps, wsc, ts)

        if cs > best_score:
            best_score = cs
            best = {
                "name": spot["name"],
                "hour": h["hour"],
                "height": h["wave_height"],
                "period": h["wave_period"],
                "wind_speed": h["wind_speed_kmh"],
                "wind_dir": h["wind_dir"],
                "wind_label": wind_label(h["wind_speed_kmh"], h["wind_dir"], spot["offshore_dir"]),
                "tide_label": tide_label(tide_heights, h["hour"]) if has_tide else None,
                "score": cs,
                "height_score": hs,
            }

    return best


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def build_today_message(
    results: list[dict], min_height: float, min_score: float, day_he: str
) -> str:
    lines = ["🏄 התראת גלים!\n"]
    for r in results:
        good = r["height_score"] > 0 and r["score"] >= min_score
        icon = "📍" if good else "❌"
        period_str = f"{r['period']:.0f}s" if r["period"] is not None else "—"
        tide_str = f" | {r['tide_label']}" if r.get("tide_label") else ""
        lines.append(
            f"{icon} {r['name']}\n"
            f"   🌊 {r['height']:.1f}m | ⏱ {period_str} | 💨 {r['wind_label']}{tide_str}\n"
            f"   ⭐ {r['score']:.1f}/10 — שיא בשעה {r['hour']:02d}:00"
        )
    lines.append(f"\n⚡ סף: {min_height:.1f}m | ⭐ {min_score:.1f}/10")
    lines.append(f"🗓️ יום: {day_he}")
    lines.append("\nצא לגלוש! 🤙")
    return "\n".join(lines)


def build_forecast_message(forecast: list[dict]) -> str:
    lines = ["📅 תחזית גלים — 5 ימים קרובים\n"]
    best_day = max(forecast, key=lambda d: d["score"])

    for day in forecast:
        score = day["score"]
        star = "🔥" if score >= 7 else ("✅" if score >= 5 else "➖")
        period_str = f"{day['period']:.0f}s" if day["period"] is not None else "—"
        lines.append(
            f"{star} {day['day_he']} {day['date'][5:]}  "
            f"🌊{day['height']:.1f}m ⏱{period_str} 💨{day['wind_label']}  ⭐{score:.1f}"
        )

    lines.append(f"\n🏆 הכי טוב: {best_day['day_he']} — ⭐{best_day['score']:.1f}/10")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    print("Telegram message sent.")


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def load_history() -> list:
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def append_history(entry: dict) -> None:
    history = load_history()
    history = [h for h in history if h["date"] != entry["date"]]
    history.append(entry)
    history = sorted(history, key=lambda x: x["date"])[-MAX_HISTORY:]
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"History updated: {entry['date']}")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config_file() -> dict:
    try:
        with open("config.json") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

def run_today(
    token: str,
    chat_id: str,
    min_height: float,
    min_score: float,
    check_days: list[str],
    stormglass_key: str = "",
    force: bool = False,
) -> None:
    now = get_israel_now()
    today = today_name(now)

    if today not in check_days:
        if not force:
            print(f"Today is {today}, not in check days {check_days}. Exiting.")
            return
        print(f"Today is {today} (not a surf day) — running anyway due to --force.")

    date_str = now.strftime("%Y-%m-%d")
    day_he = DAYS_HE.get(today, today)

    results = []
    for spot in SPOTS:
        hours = _fetch_spot_data(spot, date_str, date_str, stormglass_key)
        if hours is None:
            print(f"Skipping {spot['name']} — all fetches failed.", file=sys.stderr)
            continue
        best = best_conditions_in_window(hours, spot, min_height, date_str)
        if best is None:
            print(f"No data in surf window for {spot['name']}.", file=sys.stderr)
            continue
        results.append(best)
        print(
            f"{spot['name']}: {best['height']:.1f}m "
            f"period={best['period']}s wind={best['wind_label']} "
            f"tide={best.get('tide_label')} score={best['score']}"
        )

    if not results:
        print("No wave data retrieved. Exiting.")
        return

    any_good = any(r["score"] >= min_score and r["height_score"] > 0 for r in results)

    append_history({
        "date": date_str,
        "day_he": day_he,
        "spots": [
            {
                "name": r["name"],
                "height": r["height"],
                "period": r["period"],
                "wind_label": r["wind_label"],
                "tide_label": r.get("tide_label"),
                "score": r["score"],
                "hour": r["hour"],
            }
            for r in results
        ],
        "best_score": max(r["score"] for r in results),
        "alert_sent": any_good,
    })

    if not any_good:
        print(f"No spot meets minimum score {min_score}. No alert sent.")
        return

    if not token or not chat_id:
        print("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set.", file=sys.stderr)
        sys.exit(1)

    message = build_today_message(results, min_height, min_score, day_he)
    print("Message:\n" + message)
    send_telegram(token, chat_id, message)


def run_forecast(
    token: str, chat_id: str, min_height: float, stormglass_key: str = ""
) -> None:
    now = get_israel_now()
    start_date = now.strftime("%Y-%m-%d")
    end_date = (now + timedelta(days=FORECAST_DAYS - 1)).strftime("%Y-%m-%d")
    dates = [
        (now + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(FORECAST_DAYS)
    ]

    # One call per spot covers all 5 days
    all_hours: dict[str, list[dict] | None] = {
        spot["name"]: _fetch_spot_data(spot, start_date, end_date, stormglass_key)
        for spot in SPOTS
    }

    forecast_days = []
    for date_str in dates:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_he = DAYS_HE.get(dt.strftime("%A").lower(), dt.strftime("%A"))

        best_for_day: dict | None = None
        for spot in SPOTS:
            hours = all_hours.get(spot["name"])
            if hours is None:
                continue
            cond = best_conditions_in_window(hours, spot, min_height, date_str)
            if cond is None:
                continue
            if best_for_day is None or cond["score"] > best_for_day["score"]:
                best_for_day = cond

        if best_for_day is None:
            forecast_days.append(
                {"date": date_str, "day_he": day_he, "score": 0.0,
                 "height": 0.0, "period": None, "wind_label": "—"}
            )
        else:
            forecast_days.append(
                {
                    "date": date_str,
                    "day_he": day_he,
                    "score": best_for_day["score"],
                    "height": best_for_day["height"],
                    "period": best_for_day["period"],
                    "wind_label": best_for_day["wind_label"],
                }
            )

    if not token or not chat_id:
        print("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set.", file=sys.stderr)
        sys.exit(1)

    message = build_forecast_message(forecast_days)
    print("Forecast:\n" + message)
    send_telegram(token, chat_id, message)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["today", "forecast"], default="today")
    parser.add_argument("--force", action="store_true", help="Skip day-of-week check and always send alert")
    args = parser.parse_args()

    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    stormglass_key = os.environ.get("STORMGLASS_KEY", "")

    file_config = load_config_file()
    env_min = float(os.environ.get("MIN_WAVE_HEIGHT") or "0.8")
    min_height = float(file_config.get("min_wave_height") or env_min)
    min_score = float(file_config.get("min_score") or os.environ.get("MIN_SCORE") or "4.0")

    if args.mode == "forecast":
        run_forecast(token, chat_id, min_height, stormglass_key)
    else:
        check_days_raw = os.environ.get("CHECK_DAYS", "thursday,friday,saturday")
        check_days = [d.strip().lower() for d in check_days_raw.split(",")]
        run_today(token, chat_id, min_height, min_score, check_days, stormglass_key, force=args.force)


if __name__ == "__main__":
    main()
