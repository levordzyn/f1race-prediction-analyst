"""Why does practice_rank reach 27 when the largest field is 22?

If practice_rank were a clean within-race rank it could never exceed the
number of starters in that race. Finding the races where max rank exceeds
their own field size tells us whether practice.py has a bug - and the
practice-order baseline and practice-position feature both depend on it.

Run:  python scripts/check_practice_rank.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 78)
print("RACES WHERE max(practice_rank) EXCEEDS THEIR STARTER COUNT")
print("=" * 78)
rows = con.execute(
    """
    SELECT p.year, p.round,
           MAX(p.practice_rank) AS max_rank,
           COUNT(*)            AS n_practice,
           (SELECT COUNT(*) FROM results r
             WHERE r.year = p.year AND r.round = p.round) AS n_results
    FROM practice p
    GROUP BY p.year, p.round
    HAVING MAX(p.practice_rank) > COUNT(*)
       OR MAX(p.practice_rank) > (SELECT COUNT(*) FROM results r
                                   WHERE r.year = p.year AND r.round = p.round)
    ORDER BY p.year, p.round
    """
).fetchall()

print(f"  races where rank exceeds the field: {len(rows)}")
for r in rows:
    print(f"    {r['year']} R{r['round']:>2}: max_rank={r['max_rank']}  "
          f"practice_rows={r['n_practice']}  results_rows={r['n_results']}")

print()
print("=" * 78)
print("GLOBAL DISTRIBUTION OF practice_rank")
print("=" * 78)
for r in con.execute(
        "SELECT practice_rank, COUNT(*) n FROM practice "
        "WHERE practice_rank > 22 GROUP BY practice_rank "
        "ORDER BY practice_rank"):
    print(f"  rank {r['practice_rank']}: {r['n']} rows")

print()
print("=" * 78)
print("THE ROWS WITH rank > 22 - WHICH DRIVERS?")
print("=" * 78)
rows = con.execute(
    """
    SELECT p.year, p.round, p.driver, p.practice_rank, p.best_practice_s,
           p.n_sessions, p.has_practice_lap,
           (SELECT COUNT(*) FROM results r
             WHERE r.year = p.year AND r.round = p.round) AS field
    FROM practice p
    WHERE p.practice_rank > 22
    ORDER BY p.year, p.round, p.practice_rank
    """
).fetchall()
print(f"  {'year':>5} {'rnd':>4} {'drv':>5} {'rank':>6} {'best_s':>9} "
      f"{'n_ses':>5} {'lap':>4} {'field':>6}")
for r in rows:
    best = (f"{r['best_practice_s']:.3f}"
            if r["best_practice_s"] is not None else "-")
    print(f"  {r['year']:>5} {r['round']:>4} {r['driver']:>5} "
          f"{r['practice_rank']:>6} {best:>9} {r['n_sessions']:>5} "
          f"{r['has_practice_lap']:>4} {r['field']:>6}")

print()
print("=" * 78)
print("HOW MANY RACES HAVE ANY rank > field SIZE?")
print("=" * 78)
n = con.execute(
    """
    SELECT COUNT(*) FROM (
      SELECT year, round FROM practice
      GROUP BY year, round
      HAVING MAX(practice_rank) > (SELECT COUNT(*) FROM results r
                                    WHERE r.year = practice.year
                                      AND r.round = practice.round)
    )
    """
).fetchone()[0]
print(f"  {n} of 89 races")

print()
print("=" * 78)
print("IS practice_rank GLOBALLY RANKED INSTEAD OF PER RACE?")
print("=" * 78)
# A within-race rank restarts at 1 every race: MIN must be 1 for all 89.
bad_min = con.execute(
    """
    SELECT COUNT(*) FROM (
      SELECT year, round, MIN(practice_rank) m FROM practice
      GROUP BY year, round HAVING MIN(practice_rank) != 1
    )
    """
).fetchone()[0]
print(f"  races whose MIN(practice_rank) != 1 : {bad_min}  (0 = restarts at 1)")
dup = con.execute(
    """
    SELECT COUNT(*) FROM (
      SELECT year, round, practice_rank FROM practice
      WHERE practice_rank IS NOT NULL
      GROUP BY year, round, practice_rank HAVING COUNT(*) > 1
    )
    """
).fetchone()[0]
print(f"  duplicated rank within a race       : {dup}  "
      f"(0 = ranks are unique per race)")
tot = con.execute(
    "SELECT COUNT(*) FROM practice WHERE practice_rank IS NULL"
).fetchone()[0]
print(f"  NULL practice_rank                  : {tot}")

print()
print("=" * 78)
print("RACES WITH rank > 22: are their drivers present in results?")
print("=" * 78)
missing = con.execute(
    """
    SELECT p.year, p.round, p.driver, p.practice_rank
    FROM practice p
    LEFT JOIN results r ON r.year=p.year AND r.round=p.round
                       AND r.driver=p.driver
    WHERE p.practice_rank > 22 AND r.driver IS NULL
    """
).fetchall()
print(f"  practice rows with rank>22 but NO results row: {len(missing)}")
for r in missing:
    print(f"      {r['year']} R{r['round']} {r['driver']} "
          f"rank={r['practice_rank']}")

con.close()
