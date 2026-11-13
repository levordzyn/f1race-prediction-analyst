"""Verify specific bug hypotheses in Appendix A against real data.

Run:  python scripts/check_appendix_a.py
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import fastf1

Path("f1_cache").mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))
pd.set_option("display.width", 200)

# ---- H1: EventDate tz handling (line: pd.Timestamp(ev["EventDate"]).tz_localize(None))
print("=== H1: EventDate tz behaviour ===")
for year in (2025, 2026):
    sched = fastf1.get_event_schedule(year, include_testing=False)
    raw = sched["EventDate"].iloc[0]
    print(f"  {year} raw type={type(raw).__name__} value={raw!r} dtype={sched['EventDate'].dtype}")
    ts = pd.Timestamp(raw)
    print(f"    pd.Timestamp -> tz={ts.tz} ; tz_localize(None) -> {ts.tz_localize(None)!r}")

print("\n=== H1b: datetime.utcnow() under Python 3.14 ===")
try:
    today = pd.Timestamp(datetime.utcnow().date())
    print("  utcnow() ok, no exception; today =", today)
except Exception as exc:
    print("  RAISED:", type(exc).__name__, exc)

print("\n=== H2: comparing EventDate(tz-aware) vs naive today ===")
sched = fastf1.get_event_schedule(2026, include_testing=False)
ts = pd.Timestamp(sched["EventDate"].iloc[0])
today = pd.Timestamp(datetime.now(timezone.utc).date())   # tz-aware today
try:
    _ = ts.tz_localize(None) > today
    print("  comparison ok (no TypeError)")
except Exception as exc:
    print("  RAISED:", type(exc).__name__, exc)

# ---- H3: qualifying completeness (Q rows vs race rows)
print("\n=== H3: qualifying completeness 2026 R1 ===")
race = fastf1.get_session(2026, 1, "R")
race.load(laps=False, telemetry=False, weather=False, messages=False)
q = fastf1.get_session(2026, 1, "Q")
q.load(laps=False, telemetry=False, weather=False, messages=False)
r_abbr = set(race.results["Abbreviation"])
q_abbr = set(q.results["Abbreviation"])
print("  race drivers:", len(r_abbr), "| Q drivers:", len(q_abbr))
print("  in race but NOT in Q:", sorted(r_abbr - q_abbr))
print("  in Q but not in race:", sorted(q_abbr - r_abbr))

# ---- H4: GridPosition missing / zero (pit-lane) in a real race
print("\n=== H4: GridPosition oddities (2026 R1) ===")
cols = ["Abbreviation", "GridPosition", "Position", "ClassifiedPosition", "Status"]
print(race.results[cols].sort_values("GridPosition", na_position="first").to_string(index=False))
print("  GridPosition NaN count:", int(race.results["GridPosition"].isna().sum()),
      "| <=0 count:", int((race.results["GridPosition"] <= 0).sum()))

# ---- H5: is `finish` ever NaN for a classified driver? (dropna effect)
print("\n=== H5: Position NaN in race results 2026 R1 ===")
print("  Position NaN:", int(race.results["Position"].isna().sum()), "/", len(race.results))

# ---- H6: event schedule row count vs 'done' idempotency assumption
print("\n=== H6: schedule size / duplicate rounds ===")
print("  2026 rows:", len(sched), "| unique RoundNumber:", sched["RoundNumber"].nunique())
