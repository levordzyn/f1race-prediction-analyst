"""What are the 42 qualifying rows with no lap time?

sanity.py reports: 1816 rows, 1774 with a lap time, 42 without, across
14 races. Phase 3 needs to know whether these are (a) real - a driver who
never set a time, or (b) recoverable - FastF1's results.Q1/Q2/Q3 are NaT
while the laps themselves exist (the known Miami 2025 case).

Run:  python scripts/list_missing_q_times.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

rows = con.execute(
    """
    SELECT year, round, driver, team, q_position, has_qualifying_time
    FROM qualifying
    WHERE has_qualifying_time = 0
    ORDER BY year, round, q_position, driver
    """
).fetchall()

print("=" * 78)
print(f"ROWS WITH NO QUALIFYING TIME: {len(rows)}")
print("=" * 78)
print(f"{'year':>5} {'round':>5} {'driver':>7} {'team':>16} "
      f"{'q_pos':>6} {'has_time':>8}")
for r in rows:
    print(f"{r['year']:>5} {r['round']:>5} {r['driver']:>7} "
          f"{(r['team'] or ''):>16} {str(r['q_position']):>6} "
          f"{r['has_qualifying_time']:>8}")

print()
print("=" * 78)
print("GROUPED BY RACE")
print("=" * 78)
for r in con.execute(
        "SELECT year, round, COUNT(*) n FROM qualifying "
        "WHERE has_qualifying_time = 0 GROUP BY year, round "
        "ORDER BY year, round"):
    print(f"  {r['year']} R{r['round']:>2}: {r['n']} drivers")

print()
print("=" * 78)
print("SPLIT: is a position still known? (position without time)")
print("=" * 78)
both_null = con.execute(
    "SELECT COUNT(*) FROM qualifying "
    "WHERE has_qualifying_time = 0 AND q_position IS NULL"
).fetchone()[0]
pos_only = con.execute(
    "SELECT COUNT(*) FROM qualifying "
    "WHERE has_qualifying_time = 0 AND q_position IS NOT NULL"
).fetchone()[0]
print(f"  no time AND no position (fully unknown) : {both_null}")
print(f"  no time but position IS known           : {pos_only}")
print()
print("  Fully-unknown rows are faithful to FastF1: it returns")
print("  Position=nan with Q1..Q3=NaT for a driver who never set a")
print("  classified time. Those are kept, with has_qualifying_time=0 as")
print("  the missing flag Phase 3 must use (never 0 as a lap time).")
print()
print("  The position-known/time-missing rows come from sessions where")
print("  results.Q1/Q2/Q3 are all NaT. Known recoverable case: Miami 2025.")
print("  Optional fix - fetch_qualifying would fall back to ses.laps.")

print()
print("=" * 78)
print("WHAT PHASE 3 MUST DO")
print("=" * 78)
print("  - never impute a missing qualifying time as 0")
print("  - use has_qualifying_time as the missingness flag")
print("  - decide explicitly: drop, or fill with a sentinel + indicator")

con.close()
