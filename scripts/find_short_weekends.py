"""Which conventional weekends expose only 1 practice slot, and why?

Run:  python scripts/find_short_weekends.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import fastf1
from f1pred import openf1 as o1

Path("f1_cache").mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))
pd.set_option("display.width", 240)

PRACTICE = set(o1.PRACTICE_SESSION_NAMES)

for year in (2023, 2024, 2025, 2026):
    sched = fastf1.get_event_schedule(year, include_testing=False)
    for _, ev in sched.iterrows():
        if str(ev["EventFormat"]) == "sprint_qualifying":
            continue
        slots = [str(ev[f"Session{i}"]) for i in range(1, 6)
                 if f"Session{i}" in ev and pd.notna(ev[f"Session{i}"])]
        pr = [s for s in slots if s in PRACTICE]
        if len(pr) == 3:
            continue

        rnd = int(ev["RoundNumber"])
        print(f"\n{year} R{rnd} {ev['EventName']}  format={ev['EventFormat']}")
        print(f"   FastF1 slots : {slots}")
        print(f"   practices    : {pr}")
        print(f"   Session5 raw : {ev.get('Session5')!r}")

        # what does OpenF1 actually have for this meeting?
        def _utc_date(value):
            ts = pd.Timestamp(value)
            if ts.tzinfo is not None:
                ts = ts.tz_convert("UTC").tz_localize(None)
            return ts.date()

        rows = [(s["session_name"], s["session_type"], s["session_key"])
                for s in o1.get_sessions(year)
                if _utc_date(s["date_start"]) == _utc_date(ev["EventDate"])]
        print(f"   OpenF1 that day ({len(rows)}): {sorted(rows)}")
