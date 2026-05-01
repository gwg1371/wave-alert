# 🏄 Wave Alert Bot — Israel

Sends a Telegram alert every morning when waves at **Herzliya Dromi** and **Tel Aviv Tel Baruch** look good for surfing.

Uses the [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api) (free, no API key needed).

---

## How it works

1. GitHub Actions runs every day at **08:00 Israel time** (06:00 UTC).
2. The script checks whether today is one of the configured `CHECK_DAYS`.
3. It fetches hourly wave height for both spots and finds the peak between 06:00–18:00.
4. If at least one spot exceeds `MIN_WAVE_HEIGHT`, a Hebrew Telegram message is sent.

---

## Setup steps

### 1. Create a Telegram bot

1. Open Telegram and message **@BotFather**.
2. Send `/newbot` and follow the prompts → copy the **bot token**.
3. Start a chat with your new bot (or add it to a group).
4. Get your **chat ID**:
   - For a personal chat: message `@userinfobot`.
   - For a group: add `@RawDataBot` to the group, send any message, copy the `chat.id` value (it will be negative for groups).

### 2. Create a GitHub repository

```bash
# On your machine, inside the wave-alert folder:
git init
git add .
git commit -m "Initial wave alert bot"

# Create a new repo on GitHub (github.com → New repository → e.g. "wave-alert")
git remote add origin https://github.com/YOUR_USERNAME/wave-alert.git
git branch -M main
git push -u origin main
```

### 3. Add GitHub Secrets (sensitive values)

Go to your repository → **Settings → Secrets and variables → Actions → Secrets tab** → **New repository secret**:

| Name | Value |
|---|---|
| `TELEGRAM_TOKEN` | The bot token from BotFather (e.g. `123456:ABC-DEF...`) |
| `TELEGRAM_CHAT_ID` | Your chat or group ID (e.g. `123456789` or `-987654321`) |

### 4. Add GitHub Variables (non-sensitive settings)

Same page → **Variables tab** → **New repository variable**:

| Name | Default | Description |
|---|---|---|
| `MIN_WAVE_HEIGHT` | `0.8` | Minimum wave height in meters to trigger alert |
| `CHECK_DAYS` | `friday,saturday` | Comma-separated English day names to check |

If a variable is not set, the script falls back to the defaults above.

### 5. Enable GitHub Actions & test

1. Go to the **Actions** tab in your repo — the workflow should already be listed.
2. Click **Wave Alert → Run workflow** to trigger a manual run and verify the Telegram message arrives.
3. After confirmation, the workflow will run automatically every morning at 08:00 Israel time.

---

## Example Telegram message

```
🏄 התראת גלים!

📍 דרומי: 1.2m (שיא בשעה 10:00)
❌ תל ברוך: 0.5m (שיא בשעה 11:00)

⚡ סף מינימום: 0.8m
🗓️ יום: שישי

צא לגלוש! 🤙
```

---

## Files

| File | Purpose |
|---|---|
| `wave_checker.py` | Main Python script |
| `.github/workflows/wave_alert.yml` | GitHub Actions workflow (cron + manual trigger) |
| `README.md` | This file |

---

## Notes

- The cron time `0 6 * * *` is **06:00 UTC**, which equals **08:00 Israel Standard Time** (UTC+2) and **09:00 Israel Daylight Time** (UTC+3, April–October). Adjust to `0 5 * * *` during summer if you prefer 08:00 DST.
- Coordinates used: Dromi Beach `32.1580°N 34.7965°E`, Tel Baruch `32.1220°N 34.7900°E`.
