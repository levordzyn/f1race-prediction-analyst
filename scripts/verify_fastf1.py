"""VERIFY ONE REAL SAMPLE - prints actual FastF1 fields, never guesses.

Run:  python scripts/verify_fastf1.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

import fastf1

CACHE_DIR = Path("f1_cache")
CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

print("fastf1 version:", fastf1.__version__)

# ---------------------------------------------------------------- schedule
for year in (2026, 2025):
    try:
        sched = fastf1.get_event_schedule(year, include_testing=False)
    except Exception as exc:
        print(f"schedule {year}: FAILED {exc}")
        continue
    print(f"\n=== SCHEDULE {year} : {len(sched)} events ===")
    print("schedule columns:", list(sched.columns))
    print(
        sched[["RoundNumber", "EventName", "EventDate", "EventFormat"]]
        .head(8)
        .to_string(index=False)
    )
    print("EventFormat values:", sorted(sched["EventFormat"].unique().tolist()))
    today = pd.Timestamp(datetime.utcnow().date())
    future = sched[pd.to_datetime(sched["EventDate"]).dt.tz_localize(None) > today]
    print(f"events still in the future for {year}: {len(future)}")

# --------------------------------------------------------- one race result
YEAR, RND = 2025, 1
print(f"\n=== SESSION {YEAR} R{RND} 'R' ===")
ses = fastf1.get_session(YEAR, RND, "R")
ses.load(laps=False, telemetry=False, weather=False, messages=False)
print("session type:", type(ses).__name__)
res = ses.results
print("results type:", type(res).__name__)
print("results columns:", list(res.columns))
print("results rows:", len(res))
cols = [
    c
    for c in [
        "Position", "Abbreviation", "TeamName", "GridPosition", "ClassifiedPosition",
        "Status", "Number", "FirstName", "LastName", "Q1", "Q2", "Q3",
    ]
    if c in res.columns
]
print(res[cols].head(25).to_string(index=False))
print("\nDtypes:")
print(res[cols].dtypes.to_string())
