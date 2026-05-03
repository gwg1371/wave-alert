"""
Polls Telegram for bot commands and updates config.json in the repo.

Supported commands (from the authorized chat only):
  /setthreshold 1.2  — set minimum wave height alert threshold
  /setscore 5.0      — set minimum composite surf score (1–10)
  /forecast          — send the 5-day surf forecast now
  /history           — show last 7 days of conditions
  /status            — show current settings
  /help              — show available commands
"""

import base64
import json
import os
import sys

import requests

from wave_checker import run_forecast, load_config_file as load_wave_config, load_history

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GH_PAT = os.environ.get("GH_PAT", "")
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "")  # e.g. "gwg1371/wave-alert"
WORLDTIDES_KEY = os.environ.get("WORLDTIDES_KEY", "")

CONFIG_FILE = "config.json"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {"min_wave_height": 0.8, "min_score": 4.0, "last_update_id": 0}


def push_config(config: dict) -> None:
    """Commit updated config.json back to GitHub via the Contents API."""
    api_url = f"https://api.github.com/repos/{GH_REPO}/contents/{CONFIG_FILE}"
    headers = {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
    }

    # Fetch current SHA so we can update (not create) the file.
    resp = requests.get(api_url, headers=headers, timeout=15)
    sha = resp.json().get("sha") if resp.ok else None

    content_b64 = base64.b64encode(
        json.dumps(config, indent=2, ensure_ascii=False).encode()
    ).decode()

    payload: dict = {
        "message": f"bot: update config (threshold={config['min_wave_height']}, score={config.get('min_score', 4.0)})",
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(api_url, headers=headers, json=payload, timeout=15)
    resp.raise_for_status()
    print(f"config.json pushed: {config}")


# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------

def get_updates(offset: int) -> list[dict]:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 0, "offset": offset}
    resp = requests.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json().get("result", [])


def send_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def handle_setthreshold(parts: list[str], config: dict) -> tuple[str, bool]:
    """Returns (reply_text, config_changed)."""
    if len(parts) != 2:
        return "❌ פורמט שגוי.\nדוגמה: /setthreshold 0.8", False
    try:
        value = float(parts[1])
    except ValueError:
        return "❌ הכנס מספר תקין.\nדוגמה: /setthreshold 0.8", False

    if not (0.1 <= value <= 5.0):
        return "❌ ערך חייב להיות בין 0.1 ל-5.0 מטר.", False

    config["min_wave_height"] = round(value, 2)
    reply = (
        f"✅ סף גלים עודכן!\n"
        f"⚡ סף חדש: {value:.1f}m\n"
        f"ההגדרה תיכנס לתוקף בבדיקה הבאה 🏄"
    )
    return reply, True


def handle_setscore(parts: list[str], config: dict) -> tuple[str, bool]:
    if len(parts) != 2:
        return "❌ פורמט שגוי.\nדוגמה: /setscore 5.0", False
    try:
        value = float(parts[1])
    except ValueError:
        return "❌ הכנס מספר תקין.\nדוגמה: /setscore 5.0", False

    if not (1.0 <= value <= 10.0):
        return "❌ ציון חייב להיות בין 1.0 ל-10.0.", False

    config["min_score"] = round(value, 1)
    reply = (
        f"✅ סף ציון עודכן!\n"
        f"⭐ ציון מינימום חדש: {value:.1f}/10\n"
        f"ההגדרה תיכנס לתוקף בבדיקה הבאה 🏄"
    )
    return reply, True


def handle_status(config: dict) -> str:
    min_score = config.get("min_score", 4.0)
    return (
        f"📊 הגדרות נוכחיות:\n"
        f"⚡ סף גלים: {config['min_wave_height']:.1f}m\n"
        f"⭐ ציון מינימום: {min_score:.1f}/10\n"
        f"לשינוי: /setthreshold [גובה] | /setscore [ציון]"
    )


def handle_history() -> str:
    history = load_history()
    if not history:
        return "📜 אין היסטוריה זמינה עדיין."

    recent = history[-7:]
    lines = ["📜 היסטוריית גלים — 7 ימים אחרונים\n"]
    for entry in reversed(recent):
        date_short = entry["date"][5:]
        day_he = entry["day_he"]
        alert_icon = "✅" if entry.get("alert_sent") else "➖"
        spots = entry.get("spots", [])
        if spots:
            best = max(spots, key=lambda s: s["score"])
            period_str = f"{best['period']:.0f}s" if best.get("period") else "—"
            tide_str = f" | {best['tide_label']}" if best.get("tide_label") else ""
            lines.append(
                f"{alert_icon} {day_he} {date_short}  "
                f"🌊{best['height']:.1f}m ⏱{period_str} 💨{best['wind_label']}{tide_str}  "
                f"⭐{entry['best_score']:.1f}"
            )
        else:
            lines.append(f"➖ {day_he} {date_short}  אין נתונים")
    return "\n".join(lines)


HELP_TEXT = (
    "🏄 Wave Alert Bot — פקודות זמינות:\n\n"
    "/setthreshold [מטר] — שנה סף גלים מינימלי\n"
    "  דוגמה: /setthreshold 1.2\n\n"
    "/setscore [1-10] — שנה ציון מינימום לקבלת התראה\n"
    "  דוגמה: /setscore 5.0\n\n"
    "/forecast — קבל תחזית 5 ימים עכשיו\n\n"
    "/history — היסטוריית תנאים — 7 ימים אחרונים\n\n"
    "/status — הצג הגדרות נוכחיות\n\n"
    "/help — הצג הודעה זו"
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("TELEGRAM_TOKEN or TELEGRAM_CHAT_ID not set.", file=sys.stderr)
        sys.exit(1)

    if not GH_PAT or not GH_REPO:
        print("GH_PAT or GITHUB_REPOSITORY not set.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    last_update_id: int = config.get("last_update_id", 0)

    updates = get_updates(offset=last_update_id + 1)

    if not updates:
        print("No new updates.")
        return

    config_changed = False
    new_last_id = last_update_id

    for update in updates:
        update_id: int = update.get("update_id", 0)
        new_last_id = max(new_last_id, update_id)

        message = update.get("message") or update.get("edited_message", {})
        if not message:
            continue

        chat_id = str(message.get("chat", {}).get("id", ""))
        text: str = (message.get("text") or "").strip()

        print(f"Update {update_id} from chat {chat_id}: {text!r}")

        # Only respond to the authorised chat.
        if chat_id != str(TELEGRAM_CHAT_ID):
            print(f"  Ignoring — not from authorized chat ({TELEGRAM_CHAT_ID}).")
            continue

        if not text.startswith("/"):
            continue

        parts = text.split()
        command = parts[0].lower().split("@")[0]  # strip @botname suffix

        if command == "/setthreshold":
            reply, changed = handle_setthreshold(parts, config)
            if changed:
                config_changed = True
            send_message(reply)

        elif command == "/setscore":
            reply, changed = handle_setscore(parts, config)
            if changed:
                config_changed = True
            send_message(reply)

        elif command == "/forecast":
            send_message("⏳ מביא תחזית 5 ימים...")
            try:
                wave_config = load_wave_config()
                env_min = float(os.environ.get("MIN_WAVE_HEIGHT", "0.8"))
                min_height = float(wave_config.get("min_wave_height", env_min))
                run_forecast(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, min_height, WORLDTIDES_KEY)
            except Exception as e:
                send_message(f"❌ שגיאה בטעינת תחזית: {e}")

        elif command == "/history":
            send_message(handle_history())

        elif command == "/status":
            send_message(handle_status(config))

        elif command == "/help":
            send_message(HELP_TEXT)

        else:
            send_message(f"❓ פקודה לא מוכרת: {command}\nשלח /help לרשימת פקודות.")

    # Always update last_update_id so we don't re-process old messages.
    if new_last_id != last_update_id or config_changed:
        config["last_update_id"] = new_last_id
        push_config(config)


if __name__ == "__main__":
    main()
