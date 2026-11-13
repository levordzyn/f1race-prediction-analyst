"""Confirm practice_rank counts non-starters: look for GAPS in the rank sequence.

If derive_rank ran over everyone who drove in practice (including reserve
drivers who never started the race), then for a 22-starter race whose table
holds 22 rows the ranks would span 1..27 with five values MISSING - those
missing values are the dropped non-starters whose ranks still consumed
numbers.

Run:  python scripts/prove_rank_gap.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

RACES = [(2023, 13), (2024, 2), (2025, 3), (2025, 9), (2026, 7),
         (2026, 8), (2026, 11), (2026, 13), (2026, 19)]

print("=" * 78)
print("RANK GAPS: ranks present vs the span they cover")
print("=" * 78)
print(f"  {'race':<12} {'rows':>5} {'min':>5} {'max':>5} "
      f"{'missing ranks in 1..max':<24} {'field':>6}")
for y, r in RACES:
    rows = con.execute(
        "SELECT practice_rank FROM practice WHERE year=? AND round=? "
        "AND practice_rank IS NOT NULL ORDER BY practice_rank", (y, r)
    ).fetchall()
    ranks = sorted(int(x["practice_rank"]) for x in rows)
    field = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?", (y, r)
    ).fetchone()[0]
    lo, hi = min(ranks), max(ranks)
    missing = [i for i in range(lo, hi + 1) if i not in ranks]
    print(f"  {y} R{r:<7} {len(ranks):>5} {lo:>5} {hi:>5} "
          f"{str(missing):<24} {field:>6}")

print()
print("=" * 78)
print("DOES THE NUMBER OF MISSING RANKS EQUAL (max - field)?")
print("=" * 78)
print("  If yes, derive_rank ranked MORE drivers than started the race,")
print("  and those extra drivers are exactly the missing ranks.")
all_ok = True
for y, r in RACES:
    ranks = sorted(int(x["practice_rank"]) for x in con.execute(
        "SELECT practice_rank FROM practice WHERE year=? AND round=? "
        "AND practice_rank IS NOT NULL", (y, r)))
    field = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?", (y, r)
    ).fetchone()[0]
    missing = [i for i in range(1, max(ranks) + 1) if i not in ranks]
    expected = max(ranks) - field
    ok = len(missing) == expected
    all_ok &= ok
    print(f"  {y} R{r:<3}: max={max(ranks)} field={field} "
          f"missing={len(missing)} expected={expected}  "
          f"{'OK' if ok else 'MISMATCH'}")

print()
print("=" * 78)
print("SQUAD RANK: does sprint_qualifying have the same problem?")
print("=" * 78)
bad = con.execute(
    """
    SELECT year, round, MAX(sq_rank) mx, COUNT(*) n
    FROM sprint_qualifying
    GROUP BY year, round
    HAVING MAX(sq_rank) > COUNT(*)
    ORDER BY year, round
    """
).fetchall()
print(f"  races where sq_rank exceeds their row count: {len(bad)}")
for b in bad:
    print(f"      {b['year']} R{b['round']}: max={b['mx']} rows={b['n']}")

print()
print("=" * 78)
print("HOW MANY STARTERS ARE AFFECTED?")
print("=" * 78)
n_bad = con.execute(
    """
    SELECT COUNT(*) FROM practice p
    WHERE p.practice_rank > (SELECT COUNT(*) FROM results r
                              WHERE r.year=p.year AND r.round=p.round)
    """
).fetchone()[0]
n_total = con.execute("SELECT COUNT(*) FROM practice").fetchone()[0]
print(f"  rows whose rank exceeds their own field size: {n_bad}/{n_total} "
      f"({100*n_bad/n_total:.2f}%)")
print(f"  races affected: {len(RACES)}/89")

print()
print("=" * 78)
print("WHAT THE CORRECT RANK WOULD BE (re-ranked among starters only)")
print("=" * 78)
print("  Only drivers WITH a lap time can be re-ranked; drivers without one")
print("  keep rank None. Showing 2026 R7 as the clearest case:")
rows = con.execute(
    """
    SELECT driver, practice_rank, best_practice_s
    FROM practice WHERE year=2026 AND round=7
    ORDER BY best_practice_s
    """
).fetchall()
timed = [x for x in rows if x["best_practice_s"] is not None]
print(f"  {'drv':<5} {'stored':>7} {'correct':>8} {'best_s':>9}  verdict")
for i, x in enumerate(timed, start=1):
    stored = int(x["practice_rank"])
    verdict = "ok" if stored == i else f"WRONG by {stored - i:+d}"
    print(f"  {x['driver']:<5} {stored:>7} {i:>8} "
          f"{x['best_practice_s']:>9.3f}  {verdict}")

con.close()
