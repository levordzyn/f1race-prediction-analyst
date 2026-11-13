"""Phase 1 integrity: does q_position mean official Position on every row?

q_position used to mean two different things:

  * 42 races inserted before db._migrate added q_position_official held
    FastF1's raw Position;
  * 49 races inserted after held derive_rank(best_q_s).

Three independent checks proved the official value is the correct definition
and the lap-derived rank was wrong:

  * against results.grid - which the race session records separately from the
    qualifying session - official wins 277 to 14 on rows where they disagree;
  * 2025 R17: official says SAI P2 / ANT P4, but ANT's published Q2
    (101.464s) is faster than SAI's best (101.595s), so a lap rank puts ANT
    ahead - while Wikipedia's classification agrees with official
    ("Antonelli qualified in fourth... the first time he out-qualified
    Russell"; the lap rank has Russell P4, Antonelli P6);
  * no lap in that session is flagged Deleted, so the Q1/Q2/Q3 columns carry
    laps that never counted toward classification without marking them.

scripts/repair_q_position.py applied the fix. This script checks the
invariant it established:

  1. q_position == q_position_official for every row (or both NULL);
  2. q_position_official is now populated everywhere it can be;
  3. ties and gaps are present and legal - they are real features of the
     official classification, not corruption;
  4. no position falls outside 1..22 (the 22-car 2026 grid ceiling).

Run:  python scripts/verify_q_position.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 78)
print("(1) q_position == q_position_official on EVERY row?")
print("=" * 78)

n_rows = con.execute("SELECT COUNT(*) FROM qualifying").fetchone()[0]
n_diff = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE "
    "(q_position IS NULL) != (q_position_official IS NULL) "
    "OR (q_position IS NOT NULL AND q_position_official IS NOT NULL "
    "    AND q_position != q_position_official)"
).fetchone()[0]
n_both_null = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position IS NULL "
    "AND q_position_official IS NULL"
).fetchone()[0]
n_ok = n_rows - n_diff - n_both_null

print(f"  rows total                                   : {n_rows}")
print(f"  rows where both are set and equal            : {n_ok}")
print(f"  rows where they DIFFER (must be 0)           : {n_diff}")
print(f"  rows where both are NULL (see section 3)     : {n_both_null}")
for r in con.execute(
        "SELECT year, round, driver, has_qualifying_time FROM qualifying "
        "WHERE q_position IS NULL AND q_position_official IS NULL "
        "ORDER BY year, round"):
    print(f"      {r['year']} R{r['round']:<3} {r['driver']:>4} "
          f"has_time={r['has_qualifying_time']}")

print()
print("=" * 78)
print("(2) q_position_official coverage")
print("=" * 78)
have = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position_official IS NOT NULL"
).fetchone()[0]
print(f"  rows WITH official      : {have}/{n_rows}  "
      f"({100.0 * have / n_rows:.1f}%)")
print(f"  rows WITHOUT official   : {n_rows - have}  "
      f"({100.0 * (n_rows - have) / n_rows:.1f}%)")

missing = con.execute(
    """SELECT year, round, COUNT(*) AS n,
              SUM(q_position_official IS NULL) AS n_null,
              SUM(has_qualifying_time=1) AS with_time
       FROM qualifying GROUP BY year, round
       HAVING n_null = n ORDER BY year, round"""
).fetchall()
partial = con.execute(
    """SELECT year, round, COUNT(*) AS n,
              SUM(q_position_official IS NULL) AS n_null
       FROM qualifying GROUP BY year, round
       HAVING n_null > 0 AND n_null < n ORDER BY year, round"""
).fetchall()
print(f"  races entirely missing it : {len(missing)}")
for m in missing:
    print(f"      {m['year']} R{m['round']:>3} rows={m['n']} "
          f"with_lap_time={m['with_time']}")
print(f"  races PARTIALLY missing it: {len(partial)}")
for m in partial:
    print(f"      {m['year']} R{m['round']:>3} rows={m['n']} null={m['n_null']}")

print()
print("=" * 78)
print("(3) the 6 both-NULL rows: are they honest?")
print("=" * 78)
print("  Drivers FastF1 never classified in qualifying. They still have")
print("  has_qualifying_time=0 as the model's missing flag, so Phase 3 sees")
print("  'no qualifying data' rather than a fabricated position.")
for r in con.execute(
        "SELECT q.year, q.round, q.driver, x.grid, q.has_qualifying_time, "
        "       q.best_q_s "
        "FROM qualifying q "
        "JOIN results x ON x.year=q.year AND x.round=q.round "
        "                        AND x.driver=q.driver "
        "WHERE q.q_position IS NULL AND q.q_position_official IS NULL "
        "ORDER BY q.year, q.round"):
    print(f"      {r['year']} R{r['round']:<3} {r['driver']:>4} "
          f"grid={r['grid']} has_time={r['has_qualifying_time']} "
          f"best={r['best_q_s']}")

print()
print("=" * 78)
print("(4) ties and gaps - legal features, not corruption")
print("=" * 78)
print("  official Position can contain ties (2023 R10: PER and BOT both 15)")
print("  and gaps when a qualifier does not start (2025 R9: no position 14).")
print("  Both are kept as-is; derive_rank would have hidden them.")
print()
print("  KNOWN SOURCE DEFECT (see scripts/explain_ties.py): F1 times are")
print("  recorded to 0.001s, so two drivers CANNOT genuinely tie. In 6 of")
print("  the 7 groups the race grid puts the SLOWER driver ahead, which is")
print("  what a grid penalty on the faster driver looks like - FastF1's")
print("  Position then carries grid order for the shifted drivers while the")
print("  penalized driver keeps his raw qualifying spot, creating a")
print("  duplicate. 2023 R10 proves it: lap order BOT15/PER16/TSU17/...")
print("  plus BOT's +5 penalty reproduces the observed grid exactly.")
print("  Those rows are off by ONE position. We keep official anyway:")
print("  its errors are rarer and smaller than the lap rank's (which is off")
print("  by up to six in 2025 R17, confirmed against Wikipedia), and one")
print("  definition everywhere beats mixing rules per race.")
dupes = con.execute(
    """SELECT year, round, q_position, COUNT(*) AS n,
              GROUP_CONCAT(driver) AS drivers
       FROM qualifying WHERE q_position IS NOT NULL
       GROUP BY year, round, q_position HAVING COUNT(*) > 1"""
).fetchall()
print(f"  tied (race, q_position) groups: {len(dupes)}")
for d in dupes:
    print(f"      {d['year']} R{d['round']} pos={d['q_position']} "
          f"n={d['n']} drivers={d['drivers']}")

gaps = 0
for r in con.execute(
        "SELECT DISTINCT year, round FROM qualifying ORDER BY year, round"):
    vals = sorted({int(x[0]) for x in con.execute(
        "SELECT q_position FROM qualifying WHERE year=? AND round=? "
        "AND q_position IS NOT NULL", (r["year"], r["round"]))})
    if vals and vals != list(range(min(vals), max(vals) + 1)):
        gaps += 1
        print(f"      GAP {r['year']} R{r['round']:<3} {vals}")
print(f"  races with a gap in q_position: {gaps}")

print()
print("=" * 78)
print("(5) range check: 1..22 (22-car 2026 grid)")
print("=" * 78)
n_bad = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position IS NOT NULL "
    "AND (q_position < 1 OR q_position > 22)"
).fetchone()[0]
bad_races = con.execute(
    "SELECT year, round, MAX(q_position) AS mx FROM qualifying "
    "WHERE q_position IS NOT NULL GROUP BY year, round "
    "HAVING MAX(q_position) > 22"
).fetchall()
print(f"  rows outside 1..22              : {n_bad}   (expect 0)")
print(f"  races whose max exceeds 22      : {len(bad_races)}   (expect 0)")

print()
print("=" * 78)
print("(6) sanity: q_position still tracks the grid")
print("=" * 78)
match = total = 0
for r in con.execute(
        "SELECT q.q_position, x.grid FROM qualifying q "
        "JOIN results x ON x.year=q.year AND x.round=q.round "
        "                        AND x.driver=q.driver "
        "WHERE q.q_position IS NOT NULL AND x.grid IS NOT NULL"):
    total += 1
    if float(r["q_position"]) == float(r["grid"]):
        match += 1
print(f"  q_position == results.grid : {match}/{total}  "
      f"({100.0 * match / total:.2f}%)")
print("  (reference: official vs grid measured 76.12% before the fix;")
print("   the remainder is penalties and pit-lane starts, which is expected)")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
if n_diff == 0 and n_bad == 0 and not bad_races:
    print("  q_position means official Position on every row.")
    print("  One definition, no drift between insert eras, ties and gaps")
    print("  preserved. Phase 3 can read the column as-is.")
else:
    print("  PROBLEM: see the counts above - must be fixed before Phase 3.")
    con.close()
    sys.exit(1)

con.close()
