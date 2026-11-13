"""Audit: did we store any race that had not actually run?

Two failure modes:

  A. A race stored with ZERO classified finishers (every finish IS NULL) but
     still marked done in fetch_log -> it will never be retried.
  B. Placeholder rows leaking in: driver codes with no team and no status
     (FastF1 emits FM*/SC*/MC* with driver numbers 236-247 for entries it has
     no data for).

Run:  python scripts/audit_unrun_races.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 78)
print("(A) RACES WITH NO CLASSIFIED FINISHER")
print("=" * 78)
rows = con.execute(
    """SELECT year, round, event, COUNT(*) AS n,
              SUM(finish IS NULL) AS no_finish,
              SUM(grid IS NULL)   AS no_grid
       FROM results GROUP BY year, round
       HAVING no_finish = n
       ORDER BY year, round"""
).fetchall()
print(f"{'year':>6} {'R':>4} {'rows':>6} {'no_finish':>10} {'no_grid':>8}  event")
for r in rows:
    print(f"{r['year']:>6} {r['round']:>4} {r['n']:>6} {r['no_finish']:>10} "
          f"{r['no_grid']:>8}  {r['event']}")
print(f"\nraces affected: {len(rows)}")

print()
print("=" * 78)
print("(A2) same races: are they marked done in fetch_log?")
print("=" * 78)
for r in rows:
    log = con.execute(
        "SELECT step, nrows, run_at FROM fetch_log "
        "WHERE year=? AND round=? ORDER BY step", (r["year"], r["round"])
    ).fetchall()
    print(f"  {r['year']} R{r['round']} {r['event']}:")
    for l in log:
        print(f"      {l['step']:20} nrows={l['nrows']:<4} {l['run_at']}")

print()
print("=" * 78)
print("(B) PLACEHOLDER / NAMELESS ROWS IN EVERY TABLE")
print("=" * 78)
# team IS NULL is the signature FastF1's placeholders carry
for t in ("results", "qualifying", "practice", "sprint",
          "sprint_qualifying", "driver_numbers"):
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
    if "team" not in cols:
        continue
    n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE team IS NULL").fetchone()[0]
    print(f"  {t:20} team IS NULL: {n}")
    if n:
        for r in con.execute(
            f"SELECT year, round, driver, driver_number FROM {t} "
            f"WHERE team IS NULL ORDER BY year, round, driver"
        ):
            print(f"      {r['year']} R{r['round']:>3} {r['driver']:>4} "
                  f"num={r['driver_number']}")

print()
print("=" * 78)
print("(B2) driver numbers outside the normal 1-100 range")
print("=" * 78)
for r in con.execute(
    """SELECT year, round, driver, driver_number FROM driver_numbers
       WHERE driver_number IS NOT NULL AND driver_number > 100
       ORDER BY year, round, driver"""
):
    print(f"  {r['year']} R{r['round']:>3} {r['driver']:>4} "
          f"num={r['driver_number']}")

print()
print("=" * 78)
print("(C) RACES WHERE finish IS NULL FOR SOME DRIVERS (partial data)")
print("=" * 78)
rows2 = con.execute(
    """SELECT year, round, event, COUNT(*) AS n, SUM(finish IS NULL) AS nf
       FROM results GROUP BY year, round
       HAVING nf > 0 AND nf < n ORDER BY year, round"""
).fetchall()
for r in rows2:
    print(f"  {r['year']} R{r['round']:>3} {r['event'][:34]:34} "
          f"rows={r['n']} finish_null={r['nf']}")
print(f"\nraces with partial null finishes: {len(rows2)}")

print()
print("=" * 78)
print("(D) sessions.n_starters vs actual row counts (R19 should be 22)")
print("=" * 78)
bad = con.execute(
    """SELECT s.year, s.round, s.event, s.n_starters,
              (SELECT COUNT(*) FROM results r
               WHERE r.year=s.year AND r.round=s.round) AS actual
       FROM sessions s
       WHERE s.n_starters IS NOT NULL
         AND s.n_starters != (SELECT COUNT(*) FROM results r
                              WHERE r.year=s.year AND r.round=s.round)
       ORDER BY s.year, s.round"""
).fetchall()
for r in bad:
    print(f"  {r['year']} R{r['round']:>3} {r['event'][:32]:32} "
          f"n_starters={r['n_starters']} actual={r['actual']}")
print(f"\nmismatches: {len(bad)}")
