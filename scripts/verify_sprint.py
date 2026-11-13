"""Do sprint + sprint-qualifying results actually load? Across all sprint weekends.

The identifier probe returned rows=0 for SQ on 2026 R2. This checks every
sprint weekend 2023-2026 so we know whether sprint data is usable at all.

Run:  python scripts/verify_sprint.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import fastf1

Path("f1_cache").mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))
pd.set_option("display.width", 240)

SPRINT_FORMATS = {"sprint_shootout", "sprint_qualifying"}


def utc_date(v):
    ts = pd.Timestamp(v)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.to_pydatetime()


def load(year: int, rnd: int, ident: str):
    ses = fastf1.get_session(year, rnd, ident)
    ses.load(laps=False, telemetry=False, weather=False, messages=False)
    return ses, ses.results


summary = {"SQ": {"ok": 0, "empty": 0, "fail": 0},
           "S": {"ok": 0, "empty": 0, "fail": 0}}
rows_report = []

for year in (2023, 2024, 2025, 2026):
    sched = fastf1.get_event_schedule(year, include_testing=False)
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    for _, ev in sched.iterrows():
        if str(ev["EventFormat"]) not in SPRINT_FORMATS:
            continue
        rnd = int(ev["RoundNumber"])
        if utc_date(ev["EventDate"]) > today:
            continue

        rec = {"year": year, "round": rnd, "event": str(ev["EventName"]),
               "format": str(ev["EventFormat"])}

        for label, ident in (("SQ", "SQ"), ("S", "S")):
            try:
                ses, res = load(year, rnd, ident)
                n = len(res)
                rec[label] = n
                rec[f"{label}_name"] = ses.name
                if n == 0:
                    summary[label]["empty"] += 1
                else:
                    summary[label]["ok"] += 1
            except Exception as exc:           # noqa: BLE001
                rec[label] = f"ERR {type(exc).__name__}"
                summary[label]["fail"] += 1

        # Q and R for contrast
        for label, ident in (("Q", "Q"), ("R", "R")):
            try:
                _, res = load(year, rnd, ident)
                rec[label] = len(res)
            except Exception as exc:           # noqa: BLE001
                rec[label] = f"ERR {type(exc).__name__}"

        rows_report.append(rec)

df = pd.DataFrame(rows_report)
print("=" * 100)
print("SPRINT RESULT AVAILABILITY (all sprint weekends, completed races)")
print("=" * 100)
print(df.to_string(index=False))

print("\n=== totals ===")
for k, v in summary.items():
    print(f"  {k}: {v['ok']} populated, {v['empty']} EMPTY, {v['fail']} raised")

# Where SQ is empty, does FastF1 expose another route?
print("\n=== if SQ empty, what does FastF1 say? (2026 R2 detail) ===")
try:
    ses, res = load(2026, 2, "SQ")
    print("  session.name:", ses.name, "| rows:", len(res))
    print("  f1_api_support:", ses.f1_api_support)
    print("  results type:", type(res).__name__)
except Exception as exc:                       # noqa: BLE001
    print("  ", type(exc).__name__, exc)

# Cross-check: does OpenF1 have sprint qualifying laps for 2026 R2?
from f1pred import openf1 as o1
print("\n=== OpenF1 sprint sessions for 2026 (China R2) ===")
for s in o1.get_sessions(2026):
    if "Sprint" in str(s.get("session_name")):
        laps = o1.get_laps(s["session_key"])
        best = o1.best_practice_laps(laps)
        with_time = sum(1 for v in best.values() if v["best_lap_s"] is not None)
        print(f"  {s['session_name']:<20} key={s['session_key']} "
              f"date={str(s['date_start'])[:10]} lap_rows={len(laps)} drivers_with_time={with_time}")
