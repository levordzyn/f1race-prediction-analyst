"""2025 R6 (Miami): FastF1's Q1/Q2/Q3 are all NaT, but OpenF1 has 314 laps.

Before deciding whether OpenF1 is a safe fallback for this one race, check that
OpenF1's best-lap ranking agrees with FastF1's official Position column.

Run:  python scripts/verify_2025_r6_fallback.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import openf1

YEAR, RND = 2025, 6

con = sqlite3.connect("f1.db")

# FastF1 official qualifying positions (these ARE present and clean 1..20)
official = dict(con.execute(
    "SELECT driver, grid FROM results WHERE year=? AND round=?", (YEAR, RND)
).fetchall())

# driver_number -> abbreviation for this race
num2ab = {
    int(n): d for d, n in con.execute(
        "SELECT driver, driver_number FROM driver_numbers "
        "WHERE year=? AND round=?",
        (YEAR, RND),
    ).fetchall()
}

# OpenF1 qualifying session for Miami 2025
sess = openf1.get_sessions(year=YEAR)
miami = [s for s in sess if str(s.get("location", "")).lower() == "miami gardens"]
qual = [s for s in miami if s.get("session_name") == "Qualifying"]
assert len(qual) == 1, f"expected 1 qualifying session, got {len(qual)}"
key = qual[0]["session_key"]
print(f"OpenF1 qualifying session_key={key} "
      f"start={qual[0]['date_start']}")

laps = openf1.get_laps(session_key=key)
print(f"lap rows: {len(laps)}  (type={type(laps).__name__})")

best = openf1.best_practice_laps(laps)
print(f"drivers with lap rows: {len(best)}")

timed = {d: r["best_lap_s"] for d, r in best.items() if r["best_lap_s"]}
print(f"drivers with a valid best lap: {len(timed)}")

order = sorted(timed.items(), key=lambda kv: (kv[1], kv[0]))

print("\n pace rank  driver   best_s   official_grid  agree?")
print("-" * 60)
prev_ab = None
disagree = 0
for rank, (num, t) in enumerate(order, start=1):
    ab = num2ab.get(int(num), f"#{num}")
    off = official.get(ab)
    # pace rank should equal official grid when FastF1's data is complete
    ok = (off is not None and int(off) == rank)
    if not ok:
        disagree += 1
    print(f"   {rank:2}     {ab:4}   {t:7.3f}   {off!s:>8}      "
          f"{'OK' if ok else 'DIFF'}")
    prev_ab = ab

print(f"\nmismatches: {disagree} of {len(order)}")
print("drivers in FastF1 results but missing from OpenF1 laps:",
      sorted(set(official) - {num2ab.get(int(n)) for n in timed}))
