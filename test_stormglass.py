"""
Quick Stormglass API key validation.
Usage: STORMGLASS_KEY=your_key python test_stormglass.py
"""
import os
import sys
import requests
from datetime import datetime, timezone, timedelta

key = os.environ.get("STORMGLASS_KEY", "")
if not key:
    print("ERROR: STORMGLASS_KEY env var not set.")
    print("Usage: STORMGLASS_KEY=your_key python test_stormglass.py")
    sys.exit(1)

israel_tz = timezone(timedelta(hours=3))
now = datetime.now(israel_tz)
start = now.replace(hour=6, minute=0, second=0, microsecond=0)
end = now.replace(hour=8, minute=0, second=0, microsecond=0)

print(f"Testing Stormglass API key...")
print(f"Spot: דרומי (32.158, 34.7965)")
print(f"Window: {start.strftime('%Y-%m-%d %H:%M')} – {end.strftime('%H:%M')} Israel time\n")

resp = requests.get(
    "https://api.stormglass.io/v2/weather/point",
    params={
        "lat": 32.158,
        "lng": 34.7965,
        "params": "waveHeight,wavePeriod,windSpeed,windDirection",
        "start": start.isoformat(),
        "end": end.isoformat(),
    },
    headers={"Authorization": key},
    timeout=20,
)

print(f"HTTP status: {resp.status_code}")

if resp.status_code == 401:
    print("FAIL: Invalid API key.")
    sys.exit(1)
if resp.status_code == 402:
    print("FAIL: Daily quota exceeded (10 requests/day on free tier).")
    sys.exit(1)
if not resp.ok:
    print(f"FAIL: {resp.text}")
    sys.exit(1)

data = resp.json()
meta = data.get("meta", {})
hours = data.get("hours", [])

print(f"Requests used today: {meta.get('requestCount', '?')} / {meta.get('dailyQuota', '?')}")
print(f"Hours returned: {len(hours)}\n")

if not hours:
    print("WARNING: No hourly data returned.")
    sys.exit(1)

# Show the first hour's values
h = hours[0]
def pick(d):
    for src in ("sg", "noaa", "icon", "meto"):
        v = d.get(src)
        if v is not None:
            return round(v, 2)
    return None

print(f"Sample data ({h['time']}):")
print(f"  waveHeight:  {pick(h.get('waveHeight', {}))} m")
print(f"  wavePeriod:  {pick(h.get('wavePeriod', {}))} s")
print(f"  windSpeed:   {pick(h.get('windSpeed', {}))} m/s  ({round((pick(h.get('windSpeed', {})) or 0)*3.6,1)} km/h)")
print(f"  windDir:     {pick(h.get('windDirection', {}))}°")

print("\nSUCCESS: Stormglass key is valid and returning data.")
