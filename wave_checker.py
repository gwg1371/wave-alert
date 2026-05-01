import os
import sys
from datetime import datetime, timezone, timedelta

import requests

SPOTS = [
    {
        "name": "דרומי",
        "lat": 32.1580,
        "lon": 34.7965,
    },
    {
        "name": "תל ברוך",
        "lat": 32.1220,
        "lon": 34.7900,
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


def get_israel_now() -> datetime:
    israel_tz = timezone(timedelta(hours=3))
    return datetime.now(israel_tz)


def today_name(now: datetime) -> str:
    return now.strftime("%A").lower()


def fetch_wave_data(lat: float, lon: float, date_str: str) -> dict | None:
    url = "https://marine-api.open-meteo.com/v1/marine"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "wave_height",
        "start_date": date_str,
        "end_date": date_str,
        "timezone": "Asia/Jerusalem",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        print(f"Error fetching data for ({lat}, {lon}): {e}", file=sys.stderr)
        return None


def peak_in_window(data: dict) -> tuple[float, int] | None:
    """Return (peak_height, peak_hour) for surfing hours, or None on error."""
    try:
        times = data["hourly"]["time"]
        heights = data["hourly"]["wave_height"]
    except KeyError:
        return None

    best_height = -1.0
    best_hour = -1

    for time_str, height in zip(times, heights):
        if height is None:
            continue
        hour = int(time_str[11:13])
        if SURF_START_HOUR <= hour < SURF_END_HOUR:
            if height > best_height:
                best_height = height
                best_hour = hour

    if best_hour == -1:
        return None
    return best_height, best_hour


def build_message(results: list[dict], min_height: float, day_he: str) -> str:
    lines = ["🏄 התראת גלים!\n"]
    for r in results:
        icon = "📍" if r["peak"] >= min_height else "❌"
        lines.append(f"{icon} {r['name']}: {r['peak']:.1f}m (שיא בשעה {r['hour']:02d}:00)")
    lines.append(f"\n⚡ סף מינימום: {min_height:.1f}m")
    lines.append(f"🗓️ יום: {day_he}")
    lines.append("\nצא לגלוש! 🤙")
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    print("Telegram message sent.")


def main() -> None:
    token = os.environ.get("TELEGRAM_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    min_height = float(os.environ.get("MIN_WAVE_HEIGHT", "0.8"))
    check_days_raw = os.environ.get("CHECK_DAYS", "friday,saturday")
    check_days = [d.strip().lower() for d in check_days_raw.split(",")]

    now = get_israel_now()
    today = today_name(now)

    if today not in check_days:
        print(f"Today is {today}, not in check days {check_days}. Exiting.")
        return

    date_str = now.strftime("%Y-%m-%d")
    day_he = DAYS_HE.get(today, today)

    results = []
    for spot in SPOTS:
        data = fetch_wave_data(spot["lat"], spot["lon"], date_str)
        if data is None:
            print(f"Skipping {spot['name']} due to fetch error.", file=sys.stderr)
            continue
        peak = peak_in_window(data)
        if peak is None:
            print(f"No data in surf window for {spot['name']}.", file=sys.stderr)
            continue
        peak_height, peak_hour = peak
        results.append({"name": spot["name"], "peak": peak_height, "hour": peak_hour})
        print(f"{spot['name']}: {peak_height:.1f}m at {peak_hour:02d}:00")

    if not results:
        print("No wave data retrieved. Exiting.")
        return

    any_good = any(r["peak"] >= min_height for r in results)
    if not any_good:
        print(f"No spot exceeds minimum {min_height}m. No alert sent.")
        return

    if not token or not chat_id:
        print("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set.", file=sys.stderr)
        sys.exit(1)

    message = build_message(results, min_height, day_he)
    print("Message:\n" + message)
    send_telegram(token, chat_id, message)


if __name__ == "__main__":
    main()
