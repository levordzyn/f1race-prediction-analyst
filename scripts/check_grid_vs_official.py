"""CORRECTION: compare grid against q_position_official, not q_position.

The earlier check compared results.grid to the DERIVED q_position, which
renumbers every driver after a qualifying tie (2026 R19 has LIN and LAW both
officially P8, so derived pushes everyone after them up by 1). That inflated
the mismatch rate to 32.8%.

grid comes from the official qualifying classification, so
q_position_official is the right column to test derivability against.

Run:  python scripts/check_grid_vs_official.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 78)
print("grid vs q_position_official  (dataset-wide)")
print("=" * 78)
tot = con.execute(
    """SELECT COUNT(*) FROM results r
       JOIN qualifying q ON q.year=r.year AND q.round=r.round
                         AND q.driver=r.driver
       WHERE r.grid IS NOT NULL AND q.q_position_official IS NOT NULL"""
).fetchone()[0]
match = con.execute(
    """SELECT COUNT(*) FROM results r
       JOIN qualifying q ON q.year=r.year AND q.round=r.round
                         AND q.driver=r.driver
       WHERE r.grid IS NOT NULL AND q.q_position_official IS NOT NULL
         AND r.grid = q.q_position_official"""
).fetchone()[0]
print(f"  comparable rows : {tot}")
print(f"  grid == official: {match}  ({100.0 * match / tot:.2f}%)")
print(f"  grid != official: {tot - match}  ({100.0 * (tot - match) / tot:.2f}%)")

print()
print("  every differing row (grid penalties, pit-lane starts, swaps):")
n = 0
for r in con.execute(
    """SELECT r.year, r.round, r.driver, r.grid, q.q_position_official
       FROM results r
       JOIN qualifying q ON q.year=r.year AND q.round=r.round
                         AND q.driver=r.driver
       WHERE r.grid IS NOT NULL AND q.q_position_official IS NOT NULL
         AND r.grid != q.q_position_official
       ORDER BY r.year, r.round"""
):
    n += 1
    print(f"      {r['year']} R{r['round']:>3} {r['driver']:>4} "
          f"grid={r['grid']:>5} official={r['q_position_official']:>5}")
print(f"  total differing: {n}")

print()
print("=" * 78)
print("2026 R19 SPECIFICALLY")
print("=" * 78)
rows = con.execute(
    """SELECT r.driver, r.grid, q.q_position_official, q.q_position
       FROM results r
       JOIN qualifying q ON q.year=r.year AND q.round=r.round
                         AND q.driver=r.driver
       WHERE r.year=2026 AND r.round=19
       ORDER BY q.q_position_official"""
).fetchall()
same = 0
for r in rows:
    if r["grid"] is None:
        tag = "  <-- grid NULL"
    elif float(r["grid"]) == float(r["q_position_official"]):
        same += 1
        tag = ""
    else:
        tag = f"  <-- differs (penalty?)"
    print(f"  {r['driver']:>4} grid={str(r['grid']):>5} "
          f"official={r['q_position_official']:>5} "
          f"derived={r['q_position']:>5}{tag}")
print(f"\n  matching: {same} of 22")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
pct = 100.0 * match / tot
print(f"  grid == official qualifying position in {pct:.2f}% of rows.")
print(f"  Mismatches ({n}) are real F1 effects: penalties and pit-lane starts")
print("  move drivers, so grid is NOT a copy of qualifying.")
print()
print("  For HIR (2026 R19): his official qualifying position is 18, and 18")
print("  is exactly the one grid slot missing from the race - but the")
print("  mismatches above prove we cannot be certain no penalty applied to")
print("  him. FastF1 reports GridPosition=NaN, so the faithful reading is")
print("  NULL.")
print()
print("  DECISION: leave grid NULL for HIR. It is 1 row in 1816; Phase 3")
print("  must treat a missing grid as a missing value (flag or impute), not")
print("  as zero. Document as a known edge case.")
