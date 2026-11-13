"""Phase 6b step 1: verify a weather provider with ONE real sample.

The project rules are explicit: before any parsing code exists, fetch one real
response and print its actual keys. Do not guess variable names.

Questions answered here, from the network rather than from memory:
  1. Which circuit/date keys do we have to look up? (sessions table)
  2. Does Open-Meteo's historical archive serve temperature, humidity, rain
     and wind for a race weekend, and under exactly which daily keys?
  3. Are the units what we expect?

This script WRITES NOTHING and parses nothing - it only prints what came back.

Run:  python scripts/probe_weather_provider.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db  # noqa: E402

# Monza - one real race weekend, chosen before looking at any result.
LAT, LON = 45.6159, 9.2817
START, END = "2024-08-30", "2024-09-01"
RACE_DATE = "2024-09-01"

# Candidate daily keys for the four quantities the spec asks for. Whatever
# the API does not accept comes back as an error, which is exactly what this
# probe is for - no name here is trusted until the response proves it.
DAILY = ",".join([
    "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
    "relative_humidity_2m_mean", "relative_humidity_2m_max",
    "precipitation_sum", "rain_sum", "precipitation_hours",
    "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant",
])

URL = ("https://archive-api.open-meteo.com/v1/archive"
       f"?latitude={LAT}&longitude={LON}"
       f"&start_date={START}&end_date={END}"
       f"&daily={DAILY}&timezone=auto")


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


# ------------------------------------------------------- [1] what we hold
rule("[1] WHAT THIS PROJECT ALREADY KNOWS ABOUT VENUES AND DATES")
con = db.connect()
con.row_factory = None
cols = [c[1] for c in con.execute("PRAGMA table_info(sessions)").fetchall()]
print(f"  sessions columns: {', '.join(cols)}")
row = con.execute("SELECT * FROM sessions LIMIT 1").fetchone()
print(f"  sample row      : {dict(zip(cols, row))}")
print()
print("  distinct event names (a weather lookup needs a venue, and the only")
print("  venue-ish field we hold is `event`):")
events = [r[0] for r in con.execute(
    "SELECT DISTINCT event FROM sessions ORDER BY event").fetchall()]
n_sessions = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
for e in events:
    print(f"    {e}")
print(f"  -> {len(events)} distinct venues for {n_sessions} session rows")
print()
print("  any coordinate column at all?",
      any(k in " ".join(cols).lower() for k in
          ("lat", "lon", "coord", "circuit")))
sq0 = con.execute("SELECT COUNT(*) FROM sprint_qualifying WHERE has_sq_lap=0"
                  ).fetchone()[0]
print(f"  sprint_qualifying rows with has_sq_lap = 0 : {sq0}")
con.close()

# ------------------------------------------------ [2] the real sample
rule("[2] ONE REAL SAMPLE FROM OPEN-METEO HISTORICAL ARCHIVE")
print(f"  GET {URL[:110]}...")
print()
try:
    req = urllib.request.Request(URL, headers={"User-Agent": "f1-pred/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        status = resp.status
        raw = resp.read().decode("utf-8")
except urllib.error.HTTPError as exc:
    status = exc.code
    raw = exc.read().decode("utf-8")
except Exception as exc:                      # noqa: BLE001 - report, don't hide
    status, raw = 0, repr(exc)

print(f"  HTTP {status}")
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("  NOT JSON - full body:")
    print("  " + raw[:800])
    sys.exit(1)

print(f"  top-level keys: {sorted(data.keys())}")
if "error" in data or status != 200:
    print(f"  API SAID: {json.dumps(data)[:600]}")
    sys.exit(1)

print(f"  units        : {json.dumps(data.get('daily_units', {}), indent=4)}")
daily = data["daily"]
print(f"  daily keys   : {sorted(daily.keys())}")
print()
print(f"  the actual row for {RACE_DATE}:")
for k, v in sorted(daily.items()):
    if k == "time":
        continue
    print(f"    {k:<30} {v[daily['time'].index(RACE_DATE)]}")
print()
print(f"  full time axis: {daily['time']}")

# ------------------------------------------------- [3] verdict
rule("[3] VERDICT - which of the four required quantities are proven to exist")
have = set(daily.keys())
wanted = {
    "temperature": ["temperature_2m_mean", "temperature_2m_max"],
    "humidity": ["relative_humidity_2m_mean", "relative_humidity_2m_max"],
    "rain": ["rain_sum", "precipitation_sum", "precipitation_hours"],
    "wind": ["wind_speed_10m_max", "wind_gusts_10m_max"],
}
ok = True
for name, cands in wanted.items():
    got = [c for c in cands if c in have]
    print(f"  {name:<12} -> {got if got else 'MISSING'}")
    ok = ok and bool(got)
print()
print(f"  provider: Open-Meteo historical archive "
      f"(archive-api.open-meteo.com)")
print(f"  verdict : {'ALL FOUR CONFIRMED - safe to write the fetcher' if ok else 'INCOMPLETE - pick another provider or variable set'}")
sys.exit(0 if ok else 1)
