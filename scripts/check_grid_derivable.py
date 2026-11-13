"""Is results.grid derivable from qualifying.q_position?

HIR (2026 R19) has grid=NULL because FastF1's race GridPosition is NaN for
him. Before considering a fill, check the two facts that would justify it:

  1. HIR's own qualifying position in our DB.
  2. Whether grid == q_position for the OTHER drivers in R19.
  3. Whether grid == q_position holds dataset-wide - if penalties/pit-lane
     starts make them differ often, grid is NOT derivable and must stay NULL.

Run:  python scripts/check_grid_derivable.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 78)
print("(1) 2026 R19 qualifying - HIR's position")
print("=" * 78)
for r in con.execute(
    "SELECT driver, q_position, q_position_official, best_q_s, "
    "has_qualifying_time FROM qualifying "
    "WHERE year=2026 AND round=19 ORDER BY q_position"
):
    mark = "   <-- the grid-less driver" if r["driver"] == "HIR" else ""
    print(f"  {r['driver']:>4} q_position={r['q_position']} "
          f"official={r['q_position_official']} "
          f"best={r['best_q_s']} flag={r['has_qualifying_time']}{mark}")

print()
print("=" * 78)
print("(2) R19: does grid == q_position for the 21 drivers that have a grid?")
print("=" * 78)
rows = con.execute(
    """SELECT r.driver, r.grid, q.q_position
       FROM results r
       JOIN qualifying q ON q.year=r.year AND q.round=r.round
                         AND q.driver=r.driver
       WHERE r.year=2026 AND r.round=19
       ORDER BY r.grid"""
).fetchall()
same = diff = 0
for r in rows:
    ok = r["grid"] is not None and r["q_position"] is not None \
        and float(r["grid"]) == float(r["q_position"])
    same += ok
    diff += not ok
    if not ok:
        print(f"  {r['driver']:>4} grid={r['grid']} q_position="
              f"{r['q_position']}  <-- DIFFERS")
print(f"  identical: {same}   differing: {diff}")

print()
print("=" * 78)
print("(3) DATASET-WIDE: grid vs q_position")
print("=" * 78)
tot = con.execute(
    """SELECT COUNT(*) FROM results r
       JOIN qualifying q ON q.year=r.year AND q.round=r.round
                         AND q.driver=r.driver
       WHERE r.grid IS NOT NULL AND q.q_position IS NOT NULL"""
).fetchone()[0]
match = con.execute(
    """SELECT COUNT(*) FROM results r
       JOIN qualifying q ON q.year=r.year AND q.round=r.round
                         AND q.driver=r.driver
       WHERE r.grid IS NOT NULL AND q.q_position IS NOT NULL
         AND r.grid = q.q_position"""
).fetchone()[0]
print(f"  comparable rows : {tot}")
print(f"  grid == q_pos   : {match}  ({100.0 * match / tot:.2f}%)")
print(f"  grid != q_pos   : {tot - match}  ({100.0 * (tot - match) / tot:.2f}%)")

print()
print("  sample of the differing rows (these are penalties / pit-lane starts):")
for r in con.execute(
    """SELECT r.year, r.round, r.driver, r.grid, q.q_position
       FROM results r
       JOIN qualifying q ON q.year=r.year AND q.round=r.round
                         AND q.driver=r.driver
       WHERE r.grid IS NOT NULL AND q.q_position IS NOT NULL
         AND r.grid != q.q_position
       ORDER BY r.year, r.round LIMIT 15"""
):
    print(f"      {r['year']} R{r['round']:>3} {r['driver']:>4} "
          f"grid={r['grid']:>5} q_pos={r['q_position']:>5}")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
pct = 100.0 * match / tot
if pct >= 99.0:
    print(f"  grid matches qualifying in {pct:.2f}% of rows.")
    print("  -> derivable IN PRACTICE, but the exceptions prove grid carries")
    print("     information qualifying does not (penalties, pit-lane starts).")
    print("     Filling HIR would be a guess, not a read from the source.")
else:
    print(f"  grid matches qualifying in only {pct:.2f}% of rows.")
    print("  -> NOT derivable. Leave HIR's grid NULL and document it as a")
    print("     missing-value edge case for Phase 3 to handle.")
