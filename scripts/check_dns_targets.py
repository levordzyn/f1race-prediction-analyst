"""Do 'Did not start' drivers occupy a finish position in results?

A driver who never started the race is not classified in F1, so if FastF1
lists them with a Position anyway, results.finish would be a wrong TARGET for
those rows - a model would be trained to predict a result that never happened.

This was already true before race_status existed; race_status just makes it
visible for the first time.

Run:  python scripts/check_dns_targets.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 78)
print("EVERY 'Did not start' ROW, WITH ITS STORED FINISH POSITION")
print("=" * 78)
rows = con.execute("""
    SELECT rs.year, rs.round, rs.driver, rs.status,
           res.finish, res.grid, res.event
    FROM race_status rs
    JOIN results res ON res.year=rs.year AND res.round=rs.round
                    AND res.driver=rs.driver
    WHERE rs.status = 'Did not start'
    ORDER BY rs.year, rs.round, res.finish""").fetchall()

print(f"  {'year':>5} {'rnd':>4} {'drv':<5} {'grid':>5} {'finish':>6}  event")
for r in rows:
    g = int(r["grid"]) if r["grid"] is not None else "-"
    f = int(r["finish"]) if r["finish"] is not None else "NULL"
    print(f"  {r['year']:>5} {r['round']:>4} {r['driver']:<5} {str(g):>5} "
          f"{str(f):>6}  {r['event']}")

print()
print("=" * 78)
print("WHAT POSITION DO THEY OCCUPY RELATIVE TO THE FIELD?")
print("=" * 78)
# If DNS drivers were unclassified they should be at the very back; if they
# sit mid-field they are displacing a driver who actually raced.
mid = 0
for r in rows:
    field = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?",
        (r["year"], r["round"])).fetchone()[0]
    if r["finish"] is not None and int(r["finish"]) <= field - 2:
        mid += 1
        print(f"    {r['year']} R{r['round']} {r['driver']}: finish "
              f"{int(r['finish'])} of {field} - mid-field, not last")
print(f"    DNS drivers not classified at the very back: {mid} of {len(rows)}")
if mid == 0:
    print("    -> all DNS drivers occupy the last positions (expected).")

print()
print("=" * 78)
print("IS finish CONTIGUOUS 1..N EVEN WHEN A DNS DRIVER IS PRESENT?")
print("=" * 78)
bad = con.execute("""
    SELECT COUNT(*) FROM (
      SELECT year, round, MIN(finish) lo, MAX(finish) hi, COUNT(*) n,
             COUNT(DISTINCT finish) d
      FROM results GROUP BY year, round
      HAVING MIN(finish) != 1 OR MAX(finish) != COUNT(*)
          OR COUNT(DISTINCT finish) != COUNT(*))""").fetchone()[0]
print(f"  races NOT exactly 1..N : {bad} of 89")
print("  -> FastF1 gives DNS drivers a position, so there is no gap to reveal it.")

print()
print("=" * 78)
print("CROSS-CHECK: are DNS rows the same drivers flagged in qualifying?")
print("=" * 78)
q = con.execute("""
    SELECT rs.year, rs.round, rs.driver,
           q.q_position, q.has_qualifying_time, rs.status
    FROM race_status rs
    LEFT JOIN qualifying q ON q.year=rs.year AND q.round=rs.round
                          AND q.driver=rs.driver
    WHERE rs.status = 'Did not start'
    ORDER BY rs.year, rs.round""").fetchall()
print(f"  {'year':>5} {'rnd':>4} {'drv':<5} {'q_pos':>6} {'q_time':>7}")
for r in q:
    print(f"  {r['year']:>5} {r['round']:>4} {r['driver']:<5} "
          f"{str(r['q_position']):>6} {str(r['has_qualifying_time']):>7}")

print()
print("=" * 78)
print("CROSS-CHECK: the 6 'fully unknown' qualifying rows vs their status")
print("=" * 78)
unk = con.execute("""
    SELECT q.year, q.round, q.driver, q.q_position, q.has_qualifying_time,
           rs.status, res.finish
    FROM qualifying q
    LEFT JOIN race_status rs ON rs.year=q.year AND rs.round=q.round
                            AND rs.driver=q.driver
    LEFT JOIN results res ON res.year=q.year AND res.round=q.round
                         AND res.driver=q.driver
    WHERE q.q_position IS NULL AND q.has_qualifying_time = 0
    ORDER BY q.year, q.round, q.driver""").fetchall()
print(f"  {'year':>5} {'rnd':>4} {'drv':<5} {'finish':>7}  status")
for r in unk:
    f = int(r["finish"]) if r["finish"] is not None else "NULL"
    print(f"  {r['year']:>5} {r['round']:>4} {r['driver']:<5} {str(f):>7}  "
          f"{r['status']}")
print(f"  ({len(unk)} rows; expected 6)")

con.close()
