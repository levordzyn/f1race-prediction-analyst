"""Inspect the two remaining repair failures to decide if they are real
corruption or legitimate F1 data.

  1. gap_to_pole_pct outside [0, 6]  -> 46 rows
  2. q_position not 1..n             -> 2025 R9 (19 drivers, max rank 20)

Run:  python scripts/inspect_repair_failures.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 74)
print("(1) gap_to_pole_pct outside [0,6]")
print("=" * 74)
rows = con.execute(
    """SELECT year, round, driver, q_position, best_q_s, gap_to_pole_pct,
              has_qualifying_time
       FROM qualifying
       WHERE gap_to_pole_pct IS NOT NULL
         AND (gap_to_pole_pct < 0 OR gap_to_pole_pct > 6.0)
       ORDER BY gap_to_pole_pct DESC"""
).fetchall()
print(f"count: {len(rows)}")
print(f"{'year':>5} {'R':>3} {'drv':>4} {'pos':>4} {'best_s':>9} "
      f"{'gap%':>8} {'flag':>4}")
for r in rows:
    print(f"{r['year']:>5} {r['round']:>3} {r['driver']:>4} "
          f"{r['q_position']:>4} {r['best_q_s']:>9.3f} "
          f"{r['gap_to_pole_pct']:>8.3f} {r['has_qualifying_time']:>4}")

# Is gap consistent with the formula for these rows? (it passed the check,
# so recompute the pole for their race to show WHY it is large)
print()
print("pole lap for each affected race (explains large gaps):")
for y, rd in sorted({(r["year"], r["round"]) for r in rows}):
    pole = con.execute(
        "SELECT MIN(best_q_s) FROM qualifying "
        "WHERE year=? AND round=? AND best_q_s IS NOT NULL",
        (y, rd),
    ).fetchone()[0]
    worst = con.execute(
        "SELECT driver, best_q_s, gap_to_pole_pct FROM qualifying "
        "WHERE year=? AND round=? AND gap_to_pole_pct > 6.0 "
        "ORDER BY gap_to_pole_pct DESC LIMIT 1",
        (y, rd),
    ).fetchone()
    print(f"  {y} R{rd}: pole={pole:.3f}s  "
          f"worst={worst['driver']} {worst['best_q_s']:.3f}s "
          f"gap={worst['gap_to_pole_pct']:.3f}%")

# sanity: how many TOTAL rows have gap > 4%? (what is normal here)
allg = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE gap_to_pole_pct IS NOT NULL"
).fetchone()[0]
gt4 = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE gap_to_pole_pct > 4.0"
).fetchone()[0]
gt6 = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE gap_to_pole_pct > 6.0"
).fetchone()[0]
mx = con.execute(
    "SELECT MAX(gap_to_pole_pct) FROM qualifying"
).fetchone()[0]
print(f"\nrows with a gap: {allg}")
print(f"  > 4.0%: {gt4}")
print(f"  > 6.0%: {gt6}")
print(f"  max   : {mx:.3f}%")

print()
print("=" * 74)
print("(2) 2025 R9 q_position not 1..n")
print("=" * 74)
r9 = con.execute(
    """SELECT driver, driver_number, q_position, q_position_official,
              best_q_s, has_qualifying_time
       FROM qualifying WHERE year=2025 AND round=9
       ORDER BY q_position"""
).fetchall()
print(f"rows in qualifying table: {len(r9)}")
print(f"{'drv':>4} {'num':>4} {'q_pos':>6} {'off':>5} {'best_s':>9} {'flag':>4}")
for r in r9:
    print(f"{r['driver']:>4} {r['driver_number']:>4} "
          f"{str(r['q_position']):>6} {str(r['q_position_official']):>5} "
          f"{str(round(r['best_q_s'],3) if r['best_q_s'] else None):>9} "
          f"{r['has_qualifying_time']:>4}")

ranks = sorted(int(r["q_position"]) for r in r9 if r["q_position"])
print(f"\nranks present: {ranks}")
missing = sorted(set(range(1, max(ranks) + 1)) - set(ranks))
print(f"missing rank : {missing}")

# how many drivers does results have for that race?
res = con.execute(
    "SELECT driver, grid, finish FROM results WHERE year=2025 AND round=9 "
    "ORDER BY grid"
).fetchall()
print(f"\nresults rows for 2025 R9: {len(res)}")
for r in res:
    print(f"   {r['driver']:>4} grid={r['grid']} finish={r['finish']}")

# and how many did FastF1 list in qualifying?
print()
print("=> if results has 19 but qualifying had 20 starters, the missing")
print("   rank belongs to a driver absent from results (did not start).")
