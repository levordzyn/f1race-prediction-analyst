"""Verify 2026 R19 after the fetch_race fix.

Expected: 22 rows, positions 1..22 complete (HIR filled from
ClassifiedPosition=10), no placeholder driver numbers, grid complete.

Run:  python scripts/verify_r19.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 74)
print("2026 R19 - results")
print("=" * 74)
rows = con.execute(
    "SELECT driver, team, grid, finish FROM results "
    "WHERE year=2026 AND round=19 ORDER BY finish"
).fetchall()
print(f"{'drv':>4} {'team':22} {'grid':>5} {'finish':>6}")
for r in rows:
    print(f"{r['driver']:>4} {str(r['team']):22} "
          f"{str(r['grid']):>5} {str(r['finish']):>6}")

finishes = sorted(int(r["finish"]) for r in rows if r["finish"] is not None)
grids = sorted(int(r["grid"]) for r in rows if r["grid"] is not None)
print(f"\nrows              : {len(rows)}")
print(f"finish values     : {finishes}")
print(f"complete 1..22    : {finishes == list(range(1, 23))}")
print(f"grid values       : {grids}")
print(f"grid complete     : {grids == list(range(1, 23))}")
print(f"finish NULL rows  : "
      f"{[r['driver'] for r in rows if r['finish'] is None]}")
print(f"grid NULL rows    : "
      f"{[r['driver'] for r in rows if r['grid'] is None]}")

print()
print("=" * 74)
print("NO PLACEHOLDERS ANYWHERE")
print("=" * 74)
bad = con.execute(
    "SELECT COUNT(*) FROM driver_numbers WHERE driver_number > 100"
).fetchall()
print(f"  driver_number > 100 in whole DB: {sum(b[0] for b in bad)}")
bad2 = con.execute(
    "SELECT year, round, driver FROM results "
    "WHERE team IS NULL OR team IN ('', 'None') "
    "AND year=2026 AND round=19"
).fetchall()
print(f"  nameless teams in R19: {len(bad2)}")
n_all = con.execute(
    "SELECT COUNT(*) FROM results WHERE year=2026 AND round=19 "
    "AND (team IS NULL OR team IN ('','None'))"
).fetchone()[0]
print(f"  (recheck, correct precedence) nameless teams: {n_all}")

print()
print("=" * 74)
print("PER-RACE ROW COUNTS FOR 2026 (all should be 22)")
print("=" * 74)
for r in con.execute(
    "SELECT round, COUNT(*) AS n, SUM(finish IS NULL) AS nf, "
    "SUM(grid IS NULL) AS ng FROM results WHERE year=2026 "
    "GROUP BY round ORDER BY round"
):
    flag = "" if r["n"] == 22 else "   <-- WRONG SIZE"
    print(f"  R{r['round']:>3} n={r['n']:>3} finish_null={r['nf']} "
          f"grid_null={r['ng']}{flag}")

print()
print("=" * 74)
print("RACE INTEGRITY ACROSS ALL YEARS")
print("=" * 74)
n_bad = con.execute(
    """SELECT COUNT(*) FROM (
         SELECT year, round FROM results
         WHERE finish IS NULL OR grid IS NULL
         GROUP BY year, round)"""
).fetchone()[0]
print(f"  races with any NULL finish/grid: {n_bad}")
dupes = con.execute(
    """SELECT year, round, COUNT(*) FROM results
       GROUP BY year, round, finish
       HAVING COUNT(*) > 1 AND finish IS NOT NULL"""
).fetchall()
print(f"  duplicate finish positions in a race: {len(dupes)}")
for d in dupes:
    print(f"      {d}")

print()
print("=" * 74)
print("fetch_log FOR R19")
print("=" * 74)
for l in con.execute(
    "SELECT step, nrows, run_at FROM fetch_log "
    "WHERE year=2026 AND round=19 ORDER BY step"
):
    print(f"  {l['step']:20} nrows={l['nrows']:<4} {l['run_at']}")
s = con.execute(
    "SELECT n_starters, expected_size, meeting_key FROM sessions "
    "WHERE year=2026 AND round=19"
).fetchone()
print(f"  sessions: n_starters={s['n_starters']} "
      f"expected_size={s['expected_size']} meeting_key={s['meeting_key']}")

print()
print("=" * 74)
print("WHOLE-DATABASE TOTALS")
print("=" * 74)
for t in ("results", "qualifying", "practice", "sprint",
          "sprint_qualifying", "driver_numbers", "sessions", "fetch_log"):
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t:20} {n}")
