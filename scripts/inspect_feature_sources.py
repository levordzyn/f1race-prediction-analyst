"""Print one real sample of every column Phase 3 will read.

Rule: never guess field names or semantics. This shows the actual values so
the feature formulas in f1pred/features.py are written against observed data.

Questions answered:
  1. Is practice_rank a WITHIN-RACE rank (1..N) or a season-long rank?
  2. Is gap_to_best_pct a percentage (0 = fastest) and what is its range?
  3. What are laps_completed / has_practice_lap / n_sessions?
  4. Is gap_to_pole_pct a percentage, and what is its range?
  5. What does has_qualifying_time mean in practice?
  6. Is grid ever 0 or missing (pit-lane starts)?
  7. Do the three tables join cleanly on (year, round, driver)?

Run:  python scripts/inspect_feature_sources.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

SAMPLE = (2025, 6)   # Miami - now has qualifying times after the fix


def q(sql, *args):
    return con.execute(sql, args).fetchall()


def section(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


section("1. PRACTICE - is practice_rank within a race?")
rows = q(
    "SELECT year, round, driver, practice_rank, best_practice_s, "
    "       gap_to_best_pct, laps_completed, n_sessions, has_practice_lap "
    "FROM practice WHERE year=? AND round=? ORDER BY practice_rank LIMIT 8",
    *SAMPLE)
print(f"  {'drv':<5} {'rank':>5} {'best_s':>9} {'gap%':>8} {'laps':>5} "
      f"{'n_ses':>5} {'has_lap':>7}")
for r in rows:
    print(f"  {r['driver']:<5} {str(r['practice_rank']):>5} "
          f"{str(round(r['best_practice_s'],3) if r['best_practice_s'] else '-'):>9} "
          f"{str(round(r['gap_to_best_pct'],3) if r['gap_to_best_pct'] is not None else '-'):>8} "
          f"{str(r['laps_completed']):>5} {str(r['n_sessions']):>5} "
          f"{r['has_practice_lap']:>7}")

print()
print("  ranks across MULTIPLE races (must restart at 1 each race):")
for r in q("SELECT year, round, MIN(practice_rank) mn, MAX(practice_rank) mx, "
           "COUNT(*) n FROM practice GROUP BY year, round ORDER BY year, round "
           "LIMIT 6"):
    print(f"      {r['year']} R{r['round']:>2}: min={r['mn']} max={r['mx']} "
          f"rows={r['n']}")
mx = q("SELECT MAX(practice_rank) m FROM practice")[0]["mn" if False else "m"]
tot_races = q("SELECT COUNT(DISTINCT year||'-'||round) c FROM practice")[0]["c"]
print(f"  global MAX(practice_rank) across all races: {mx}")
print(f"  races: {tot_races}  -> if max equals the largest field size, "
      f"rank is WITHIN RACE")

section("2. gap_to_best_pct - units and range")
for r in q("SELECT MIN(gap_to_best_pct) lo, MAX(gap_to_best_pct) hi, "
           "AVG(gap_to_best_pct) avg FROM practice WHERE gap_to_best_pct IS NOT NULL"):
    print(f"  practice gap: min={r['lo']:.3f}  max={r['hi']:.3f}  "
          f"mean={r['avg']:.3f}")
for r in q("SELECT MIN(gap_to_pole_pct) lo, MAX(gap_to_pole_pct) hi, "
           "AVG(gap_to_pole_pct) avg FROM qualifying WHERE gap_to_pole_pct IS NOT NULL"):
    print(f"  qualifying gap: min={r['lo']:.3f}  max={r['hi']:.3f}  "
          f"mean={r['avg']:.3f}")
print("  (both are percentages: 0.0 = fastest in that session)")

section("3. practice laps / flags / sessions")
for r in q("SELECT MIN(laps_completed) lo, MAX(laps_completed) hi, "
           "AVG(laps_completed) avg FROM practice"):
    print(f"  laps_completed: min={r['lo']} max={r['hi']} mean={r['avg']:.1f}")
for r in q("SELECT n_sessions, COUNT(*) n, SUM(has_practice_lap) with_lap "
           "FROM practice GROUP BY n_sessions ORDER BY n_sessions"):
    print(f"  n_sessions={r['n_sessions']}: rows={r['n']} "
          f"with a lap={r['with_lap']}")
print("  -> practice laps/30: sprint weekends have only FP1 (n_sessions=1),")
print("     so this feature is structurally smaller there.")

section("4. QUALIFYING flags and gaps")
for r in q("SELECT has_qualifying_time, COUNT(*) n FROM qualifying "
           "GROUP BY has_qualifying_time"):
    print(f"  has_qualifying_time={r['has_qualifying_time']}: {r['n']} rows")
print(f"  -> the missing flag = 1 - has_qualifying_time")
for r in q("SELECT COUNT(*) n FROM qualifying WHERE q_position=1"):
    print(f"  drivers with q_position=1 (pole): {r['n']}  "
          f"(= races with a pole-sitter)")

section("5. GRID - zeros, missing, range")
for r in q("SELECT year, MIN(grid) lo, MAX(grid) hi, SUM(grid IS NULL) nulls, "
           "SUM(grid<=0) zeros FROM results GROUP BY year ORDER BY year"):
    print(f"  {r['year']}: min={r['lo']} max={r['hi']} "
          f"NULL={r['nulls']} <=0={r['zeros']}")
print("  -> grid<=0 means pit-lane/no-grid; features.py must clean it")
print("     BEFORE the model sees it (treat as last on the grid).")

section("6. JOIN: do the three tables share keys?")
j = q(
    "SELECT COUNT(*) n FROM results r "
    "LEFT JOIN qualifying q ON q.year=r.year AND q.round=r.round "
    "AND q.driver=r.driver "
    "LEFT JOIN practice p ON p.year=r.year AND p.round=r.round "
    "AND p.driver=r.driver "
    "WHERE q.driver IS NULL OR p.driver IS NULL")
print(f"  results rows missing a qualifying OR practice row: {j[0]['n']}")
j2 = q("SELECT COUNT(*) n FROM results WHERE finish IS NULL")
print(f"  results rows with finish IS NULL (did not classify): {j2[0]['n']}")
j3 = q("SELECT COUNT(*) n FROM results")
print(f"  results rows total: {j3[0]['n']}")

section("7. TARGET sanity: finish positions")
for r in q("SELECT year, MIN(finish) lo, MAX(finish) hi, "
           "COUNT(DISTINCT round) races FROM results GROUP BY year "
           "ORDER BY year"):
    print(f"  {r['year']}: finish {r['lo']}..{r['hi']} "
          f"across {r['races']} races")
print("  -> target is finish position; lower is better")

section("8. SAMPLE ROW: one race, all sources joined")
rows = q(
    "SELECT r.driver, r.grid, r.finish, r.team, "
    "       q.q_position, q.gap_to_pole_pct, q.has_qualifying_time, "
    "       p.practice_rank, p.gap_to_best_pct, p.laps_completed, "
    "       p.has_practice_lap "
    "FROM results r "
    "LEFT JOIN qualifying q ON q.year=r.year AND q.round=r.round AND q.driver=r.driver "
    "LEFT JOIN practice p ON p.year=r.year AND p.round=r.round AND p.driver=r.driver "
    "WHERE r.year=? AND r.round=? ORDER BY r.finish LIMIT 6", *SAMPLE)
print(f"  {'drv':<5} {'team':<16} {'grid':>5} {'finish':>6} {'q_pos':>6} "
      f"{'q_gap%':>7} {'q_ok':>4} {'prac':>5} {'p_gap%':>7} {'laps':>5} {'p_ok':>4}")
for r in rows:
    print(f"  {r['driver']:<5} {r['team'][:16]:<16} {str(r['grid']):>5} "
          f"{str(r['finish']):>6} {str(r['q_position']):>6} "
          f"{str(round(r['gap_to_pole_pct'],3) if r['gap_to_pole_pct'] is not None else '-'):>7} "
          f"{str(r['has_qualifying_time']):>4} "
          f"{str(r['practice_rank']):>5} "
          f"{str(round(r['gap_to_best_pct'],3) if r['gap_to_best_pct'] is not None else '-'):>7} "
          f"{str(r['laps_completed']):>5} {str(r['has_practice_lap']):>4}")

con.close()
