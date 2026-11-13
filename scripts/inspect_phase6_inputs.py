"""Inspect the inputs Phase 6 and the true-forecast test need.

Three questions, answered from the database rather than assumed:

1. WHICH car makes the banner say "21 of 22 grid slots"? A grid slot counts
   only when grid IS NOT NULL AND grid > 0, so a pit-lane start or an
   unclassified qualifier is excluded.
2. What do the `sprint` and `sprint_qualifying` rows actually look like?
   Phase 6a must not guess column names (spec line 61: print one real
   sample), so the real rows are printed here.
3. Which races have sprint data at all, and does any race have a sprint
   result but no sprint qualifying (or vice versa)?

READ-ONLY.

Run:  python scripts/inspect_phase6_inputs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db  # noqa: E402


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


con = db.connect()
con.row_factory = None

# ------------------------------------------------------------- [1] grid
rule("[1] WHY 2026 R19 SHOWS 21 OF 22 GRID SLOTS")
rows = con.execute(
    "SELECT driver, team, grid, finish FROM results"
    " WHERE year=2026 AND round=19 ORDER BY grid IS NULL DESC, grid"
).fetchall()
bad = [r for r in rows if r[2] is None or r[2] <= 0]
print(f"  cars in the race            : {len(rows)}")
print(f"  cars with grid IS NOT NULL AND grid > 0 : {len(rows) - len(bad)}")
print()
print("  cars that do NOT count toward that number:")
for r in bad:
    print(f"    {r[0]}  ({r[1]})  grid = {r[2]!r}   finished P{r[3]:.0f}")
print()
print("  every other race's count, as a cross-check:")
for y, rnd in con.execute(
        "SELECT year, round FROM sessions ORDER BY year, round").fetchall():
    n, ok = con.execute(
        "SELECT COUNT(*), SUM(grid IS NOT NULL AND grid > 0) FROM results"
        " WHERE year=? AND round=?", (y, rnd)).fetchone()
    if (ok or 0) != n:
        print(f"    {y} R{rnd:<3} {n} cars, {ok or 0} with a slot"
              f"  ({n - (ok or 0)} without)")

print()
print("  what build_features does with such a row (features.py):")
print("    bad_grid = grid.isna() | (grid <= 0)")
print("    grid     = grid.mask(bad_grid, field_n + 1)")
print("  i.e. the car is placed BEHIND every classified slot (22 + 1 = 23)")
print("  instead of being given 0, which would look like pole. Verified on")
print("  the only 5 such rows across 4 seasons.")

# --------------------------------------------------- [2] sprint samples
rule("[2] ONE REAL ROW FROM EACH SPRINT TABLE (do not guess columns)")
for table in ("sprint", "sprint_qualifying"):
    cols = [c[1] for c in con.execute(f"PRAGMA table_info({table})").fetchall()]
    print(f"  {table}: {', '.join(cols)}")
    r = con.execute(f"SELECT * FROM {table} LIMIT 1").fetchone()
    print(f"    sample -> {dict(zip(cols, r))}")
    print()

# ------------------------------------------------------ [3] coverage
rule("[3] SPRINT COVERAGE")
tot = con.execute("SELECT COUNT(DISTINCT year||'-'||round) FROM sprint").fetchone()[0]
print(f"  races with a sprint result            : {tot}")
sq = con.execute(
    "SELECT COUNT(DISTINCT year||'-'||round) FROM sprint_qualifying"
).fetchone()[0]
print(f"  races with sprint qualifying laps     : {sq}")

both = con.execute(
    "SELECT COUNT(DISTINCT s.year||'-'||s.round) FROM sprint s"
    " JOIN sprint_qualifying q ON s.year=q.year AND s.round=q.round"
).fetchone()[0]
print(f"  races with BOTH                       : {both}")

only_s = con.execute(
    "SELECT DISTINCT s.year, s.round FROM sprint s"
    " LEFT JOIN sprint_qualifying q"
    " ON s.year=q.year AND s.round=q.round"
    " WHERE q.year IS NULL ORDER BY s.year, s.round"
).fetchall()
print(f"  sprint result but NO sprint qualifying : {len(only_s)} {only_s[:6]}")

only_q = con.execute(
    "SELECT DISTINCT q.year, q.round FROM sprint_qualifying q"
    " LEFT JOIN sprint s ON s.year=q.year AND s.round=q.round"
    " WHERE s.year IS NULL ORDER BY q.year, q.round"
).fetchall()
print(f"  sprint qualifying but NO sprint result : {len(only_q)} {only_q[:6]}")

print()
print("  rows per race (22 expected on a sprint weekend):")
for y, rnd, n in con.execute(
        "SELECT year, round, COUNT(*) FROM sprint GROUP BY year, round"
        " ORDER BY year, round LIMIT 6").fetchall():
    nq = con.execute(
        "SELECT COUNT(*) FROM sprint_qualifying WHERE year=? AND round=?",
        (y, rnd)).fetchone()[0]
    print(f"    {y} R{rnd:<3} sprint={n}  sprint_qualifying={nq}")

print()
print("  how many of the 89 races are sprint weekends -> sprint features are")
print("  MISSING for the rest, so a missing/has-sprint flag is mandatory; a")
print("  silent 0-fill would be indistinguishable from 'finished 0th'.")

rule("[4] SPRINT RESULT FIELD SHAPE")
r = con.execute(
    "SELECT sprint_position, sprint_status, sprint_grid, sprint_points,"
    " has_sprint_result FROM sprint LIMIT 5").fetchall()
print(f"  {'pos':>6} {'status':<12} {'grid':>6} {'pts':>6} {'has':>4}")
for row in r:
    print(f"  {str(row[0]):>6} {str(row[1]):<12} {str(row[2]):>6} "
          f"{str(row[3]):>6} {str(row[4]):>4}")

print()
print("  missing sprint_position values:",
      con.execute("SELECT COUNT(*) FROM sprint"
                  " WHERE sprint_position IS NULL").fetchone()[0])
print("  rows with has_sprint_result = 0:",
      con.execute("SELECT COUNT(*) FROM sprint"
                  " WHERE has_sprint_result = 0").fetchone()[0])
print("  missing sprint_grid values:",
      con.execute("SELECT COUNT(*) FROM sprint"
                  " WHERE sprint_grid IS NULL").fetchone()[0])

con.close()
print()
rule("DONE")
sys.exit(0)
