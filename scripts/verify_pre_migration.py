"""Do the 40 pre-migration races hold OFFICIAL positions or LAP-derived ones?

WHY THIS MATTERS
----------------
q_position currently means two different things:

  * 40 races (inserted before db._migrate added q_position_official):
        q_position = FastF1 raw Position        (q_position_official IS NULL)
  * 49 races (inserted after):
        q_position = derive_rank(best_q_s)     (q_position_official populated)

Wikipedia + the race grid proved OFFICIAL is the correct definition (277:14).
So the 49 post-migration races need q_position := q_position_official.

But the 40 pre-migration races have q_position_official = NULL, so we cannot
copy from it. We must know what is already in q_position there. If it is
official, those rows need no change (only a backfill of the reference column).
If it is lap-derived, they need repairing too.

THE TEST (no FastF1 calls - uses data already in the DB)
--------------------------------------------------------
grid = official qualifying position + penalties, so it matches official ~76%
of the time and matches a LAP-derived rank only ~61% of the time. Those two
rates are far enough apart to tell the two definitions apart.

Cross-checks also run:
  * does pre-migration q_position ever differ from derive_rank(best_q_s)?
    (if it were lap-derived it would match by construction)
  * do pre-migration races contain duplicate/gap patterns that only official
    Position produces?  (derive_rank always yields unique 1..k)

Run:  python scripts/verify_pre_migration.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import clean  # noqa: E402

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

pre = [tuple(r) for r in con.execute(
    "SELECT DISTINCT year, round FROM qualifying "
    "WHERE q_position_official IS NULL ORDER BY year, round")]
post = [tuple(r) for r in con.execute(
    "SELECT DISTINCT year, round FROM qualifying "
    "WHERE q_position_official IS NOT NULL ORDER BY year, round")]

print("=" * 78)
print("HOW MANY RACES IN EACH GROUP?")
print("=" * 78)
print(f"  pre-migration  (q_position_official NULL) : {len(pre)}")
print(f"  post-migration (q_position_official set)  : {len(post)}")


def grid_agreement(races, label):
    """How often does q_position equal results.grid in these races?"""
    match = total = 0
    for y, r in races:
        for row in con.execute(
            "SELECT q.q_position, x.grid FROM qualifying q "
            "JOIN results x ON x.year=q.year AND x.round=q.round "
            "                        AND x.driver=q.driver "
            "WHERE q.year=? AND q.round=? "
            "AND q.q_position IS NOT NULL AND x.grid IS NOT NULL",
            (y, r),
        ):
            total += 1
            if float(row["q_position"]) == float(row["grid"]):
                match += 1
    pct = 100.0 * match / total if total else 0.0
    print(f"  {label:34} : {match:4}/{total:4}  ({pct:5.2f}%)")
    return pct


print()
print("=" * 78)
print("TEST 1 - q_position vs results.grid  (official~76%, laprank~61%)")
print("=" * 78)
p_pre = grid_agreement(pre, "PRE-migration q_position")
p_post = grid_agreement(post, "POST-migration q_position")

print()
print("  Reference points measured earlier on the whole DB:")
print("    official definition vs grid : 76.12%")
print("    lap-rank definition vs grid : 61.31%")
print()
if p_pre >= 72.0:
    print(f"  -> PRE-migration ({p_pre:.1f}%) is close to official 76%:")
    print("     these rows already hold OFFICIAL. No q_position change needed.")
elif p_pre <= 65.0:
    print(f"  -> PRE-migration ({p_pre:.1f}%) is close to lap-rank 61%:")
    print("     these rows hold LAP-DERIVED ranks and need repairing too.")
else:
    print(f"  -> PRE-migration ({p_pre:.1f}%) sits between the two anchors;")
    print("     inconclusive from this test alone, see tests 2 and 3.")

print()
print("=" * 78)
print("TEST 2 - does pre-migration q_position differ from derive_rank?")
print("=" * 78)
same = diff = norank = 0
examples = []
for y, r in pre:
    rows = con.execute(
        "SELECT driver, q_position, best_q_s FROM qualifying "
        "WHERE year=? AND round=?", (y, r)).fetchall()
    bests = {x["driver"]: x["best_q_s"] for x in rows}
    if not any(v is not None for v in bests.values()):
        norank += 1
        continue
    d = clean.derive_rank(bests)
    for x in rows:
        if x["q_position"] is None:
            continue
        if d.get(x["driver"]) == x["q_position"]:
            same += 1
        else:
            diff += 1
            if len(examples) < 10:
                examples.append((y, r, x["driver"], x["q_position"],
                                 d.get(x["driver"])))
print(f"  rows where stored == derive_rank : {same}")
print(f"  rows where stored != derive_rank : {diff}")
print(f"  races with no lap times at all   : {norank}")
if examples:
    print("  examples of stored != derive_rank (stored is what we keep):")
    for y, r, drv, st, dv in examples:
        print(f"      {y} R{r:<3} {drv:>4} stored={st}  derive_rank would say {dv}")
print()
if diff > same:
    print("  -> stored does NOT follow derive_rank, so it is not lap-derived.")
else:
    print("  -> stored follows derive_rank in most rows; see tests 1 and 3.")

print()
print("=" * 78)
print("TEST 3 - duplicate / gap patterns in pre-migration q_position")
print("=" * 78)
print("  derive_rank always yields unique 1..k with no gaps.")
print("  official Position can contain ties (2023 R10: PER and BOT both 15)")
print("  and gaps (2025 R9: position 14 absent).")
print()
dup_races = 0
gap_races = 0
for y, r in pre:
    vals = [int(x[0]) for x in con.execute(
        "SELECT q_position FROM qualifying "
        "WHERE year=? AND round=? AND q_position IS NOT NULL", (y, r))]
    if not vals:
        continue
    if len(vals) != len(set(vals)):
        dup_races += 1
        print(f"    DUPLICATE in {y} R{r}: {sorted(vals)}")
    expected = list(range(min(vals), max(vals) + 1))
    if sorted(set(vals)) != expected:
        gap_races += 1
        print(f"    GAP in {y} R{r}: {sorted(vals)}")
print()
print(f"  pre-migration races with duplicate q_position : {dup_races}")
print(f"  pre-migration races with a gap in q_position : {gap_races}")
if dup_races or gap_races:
    print("  -> these patterns are IMPOSSIBLE from derive_rank, so those")
    print("     rows hold official Position. Strong evidence for all races.")
else:
    print("  -> no duplicates or gaps found; inconclusive on its own.")

print()
print("=" * 78)
print("SIDE EFFECT - how many duplicates would the fix introduce?")
print("=" * 78)
rows = con.execute(
    "SELECT year, round, q_position_official, COUNT(*) c, "
    "GROUP_CONCAT(driver) drivers "
    "FROM qualifying WHERE q_position_official IS NOT NULL "
    "GROUP BY year, round, q_position_official HAVING COUNT(*) > 1").fetchall()
print(f"  (race, official) groups tied in the POST-migration set: {len(rows)}")
for x in rows:
    print(f"    {x['year']} R{x['round']:<3} official={x['q_position_official']} "
          f"n={x['c']}  {x['drivers']}")

print()
print("=" * 78)
print("SIDE EFFECT - starters with NULL q_position (model impact)")
print("=" * 78)
n = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position IS NULL").fetchone()[0]
print(f"  qualifying rows with q_position NULL : {n}")
for x in con.execute(
    "SELECT year, round, driver, has_qualifying_time, best_q_s "
    "FROM qualifying WHERE q_position IS NULL "
    "ORDER BY year, round LIMIT 15"):
    print(f"    {x['year']} R{x['round']:<3} {x['driver']:>4} "
          f"has_time={x['has_qualifying_time']} best={x['best_q_s']}")
if n == 0:
    print("  -> none; every starter has a q_position. No missing-value work.")
