# 🏄 Wave Alert Bot — Israel

Sends a Telegram alert every morning when waves at **Herzliya Dromi** and **Tel Baruch** look good for surfing. Includes a Telegram bot for live control, a 5-day forecast, weekly recap, and a composite scoring system.

Uses the [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api) (free, no API key needed).

---

## How it works

Three GitHub Actions workflows run automatically:

| Workflow | Schedule | What it does |
|---|---|---|
| **Wave Alert** | 08:00 Israel time daily | Checks today's conditions and sends an alert if threshold is met |
| **Weekly Forecast** | Sunday 08:00 Israel time | Sends last week's recap then a 5-day forecast |
| **Bot Command Handler** | Every 10 min, 08:00–01:59 | Polls Telegram for commands and updates settings |

The daily alert:
1. Fetches hourly wave height, period, and wind for both spots via Open-Meteo.
2. Scores each hour on a 1–10 scale (wave height 50%, period 28%, wind 22%).
3. Finds the best consecutive window where conditions are above your threshold (e.g. `07:00–10:00`).
4. Sends a Hebrew Telegram message if at least one spot scores above `min_score`.

---

## Scoring

Each hour is scored out of 10 based on three factors:

| Factor | Weight | Details |
|---|---|---|
| Wave height | 50% | Scales from `min_wave_height` upward |
| Wave period | 28% | <6s choppy → 1.0 for 12s+ clean groundswell |
| Wind | 22% | Offshore = 1.0, cross = 0.5, onshore = 0.0 |

---

## Example Telegram messages

**Daily alert:**
```
🏄 התראת גלים!

📍 דרומי
   🌊 1.2m | ⏱ 10s | 💨 אוף 🟢
   🕗 07:00–10:00 (שיא 09:00)  ⭐ 6.8/10

📍 תל ברוך
   🌊 1.1m | ⏱ 9s | 💨 קרוס 🟡
   🕗 שיא 09:00  ⭐ 5.2/10

🏆 דרומי עדיף היום (+1.6)

⚡ סף: 0.8m | ⭐ 4.0/10
🗓️ יום: שישי
צא לגלוש! 🤙
```

**5-day forecast:**
```
📅 תחזית גלים — 5 ימים קרובים

✅ ראשון 05/11  🌊1.0m ⏱9s 💨אוף 🟢  ⭐5.4
🔥 שני 05/12   🌊1.5m ⏱11s 💨אוף 🟢  ⭐7.2
➖ שלישי 05/13 🌊0.4m ⏱7s 💨און 🔴  ⭐2.1
...

🏆 הכי טוב: שני — ⭐7.2/10
```

**Weekly recap:**
```
📊 סיכום שבוע שעבר

✅ חמישי 04/30  🌊1.1m ⏱9s 💨אוף 🟢  ⭐5.9
🔥 שישי 05/01  🌊1.4m ⏱11s 💨אוף 🟢  ⭐7.1
✅ שבת 05/02   🌊1.0m ⏱8s 💨קרוס 🟡  ⭐5.2

📈 ממוצע: ⭐6.1/10
🏆 יום הכי טוב: שישי 05/01 — ⭐7.1
🏄 ימים שהיו שווים לגלוש: 3/3
```

---

## Telegram bot commands

| Command | Example | Description |
|---|---|---|
| `/setthreshold` | `/setthreshold 1.2` | Set minimum wave height (0.1–5.0m) |
| `/setscore` | `/setscore 5.0` | Set minimum composite score to trigger alert (1–10) |
| `/forecast` | `/forecast` | Get the 5-day forecast now |
| `/history` | `/history` | Show last 7 days of conditions |
| `/status` | `/status` | Show current settings |
| `/help` | `/help` | List all commands |

Settings changed via bot are committed back to `config.json` in the repo and take effect on the next run.

---

## Setup

### 1. Create a Telegram bot

1. Message **@BotFather** on Telegram.
2. Send `/newbot` and follow the prompts → copy the **bot token**.
3. Start a chat with your bot.
4. Get your **chat ID**: message `@userinfobot` for a personal chat, or add `@RawDataBot` to a group and copy the `chat.id` (negative number for groups).

### 2. Create a GitHub repository

```bash
git init
git add .
git commit -m "Initial wave alert bot"
git remote add origin https://github.com/YOUR_USERNAME/wave-alert.git
git branch -M main
git push -u origin main
```

### 3. Add GitHub Secrets

**Settings → Secrets and variables → Actions → Secrets → New repository secret:**

| Name | Value |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from BotFather (e.g. `123456:ABC-DEF...`) |
| `TELEGRAM_CHAT_ID` | Your chat or group ID (e.g. `123456789` or `-987654321`) |
| `GH_PAT` | A GitHub personal access token with `repo` scope (needed for the bot to commit config changes) |

### 4. Add GitHub Variables

**Same page → Variables tab → New repository variable:**

| Name | Default | Description |
|---|---|---|
| `MIN_WAVE_HEIGHT` | `0.8` | Minimum wave height in meters |
| `MIN_SCORE` | `4.0` | Minimum composite score (1–10) to send alert |
| `CHECK_DAYS` | `thursday,friday,saturday` | Comma-separated days to check |

If a variable is not set the script falls back to the defaults above. Settings changed via `/setthreshold` or `/setscore` in Telegram override these at runtime.

### 5. Test

1. Go to the **Actions** tab → **Wave Alert → Run workflow** and tick **"Send alert even if today is not a surf day"**.
2. Confirm the Telegram message arrives.
3. The workflows will run automatically from then on.

---

## Files

| File | Purpose |
|---|---|
| `wave_checker.py` | Fetching, scoring, message building, all run modes |
| `bot_handler.py` | Telegram command polling and config updates |
| `config.json` | Live settings (`min_wave_height`, `min_score`, `last_update_id`) |
| `history.json` | Rolling 90-day log of daily conditions |
| `test_stormglass.py` | Quick script to validate a Stormglass API key |
| `.github/workflows/wave_alert.yml` | Daily alert workflow |
| `.github/workflows/bot_handler.yml` | Bot command handler workflow |
| `.github/workflows/weekly_forecast.yml` | Sunday recap + forecast workflow |

---

## Notes

- **DST:** Two cron lines (`0 5` and `0 6`) ensure the alert fires at 08:00 Israel time in both winter (UTC+2) and summer DST (UTC+3).
- **Spots:** Dromi `32.1580°N 34.7965°E` (offshore wind ~100°), Tel Baruch `32.1220°N 34.7900°E` (offshore wind ~90°).
- **Mediterranean tides** are negligible (~20cm range) so tide scoring is disabled for both spots.
- **Bot polling** runs every 10 minutes between 08:00–01:59 Israel time only, to save GitHub Actions minutes.
