"""Print per-year coverage of every Phase 1 table plus gaps in fetch_log.

Run:  python scripts/coverage.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")

YEARS = [2023, 2024, 2025, 2026]

print("=" * 74)
print("PER-YEAR COVERAGE")
print("=" * 74)
for t in ["sessions", "qualifying", "sprint", "driver_numbers"]:
    print(f"\n{t}:")
    for y in YEARS:
        n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE year=?", (y,)).fetchone()[0]
        r = con.execute(
            f"SELECT COUNT(DISTINCT round) FROM {t} WHERE year=?", (y,)
        ).fetchone()[0]
        print(f"  {y}: {n:5} rows  {r:3} rounds")

print("\n" + "=" * 74)
print("FETCH_LOG ROUNDS PER STEP")
print("=" * 74)
for y in YEARS:
    print(f"\n{y}:")
    for step in ["race", "qualifying", "sprint"]:
        rows = [
            r[0]
            for r in con.execute(
                "SELECT round FROM fetch_log WHERE year=? AND step=? ORDER BY round",
                (y, step),
            )
        ]
        print(f"  {step:12}: {rows}")

print("\n" + "=" * 74)
print("GAPS: rounds present in results but missing from a step")
print("=" * 74)
for y in YEARS:
    all_r = {
        r[0] for r in con.execute("SELECT DISTINCT round FROM results WHERE year=?", (y,))
    }
    for step in ["qualifying", "sprint"]:
        done = {
            r[0]
            for r in con.execute(
                "SELECT round FROM fetch_log WHERE year=? AND step=?", (y, step)
            )
        }
        # sprint gaps only matter for sprint weekends; report raw and let the
        # caller compare against the sprint calendar
        missing = sorted(all_r - done)
        print(f"{y} {step:12}: missing {missing}")

print("\n" + "=" * 74)
print("TABLE TOTALS")
print("=" * 74)
for t in ["results", "sessions", "qualifying", "sprint", "driver_numbers", "fetch_log"]:
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t:16} {n:6}")

# races with zero qualifying rows at all
print("\nRounds with 0 qualifying rows:")
for y in YEARS:
    rows = con.execute(
        """SELECT r.round FROM results r
           WHERE r.year=?
           AND (SELECT COUNT(*) FROM qualifying q
                WHERE q.year=r.year AND q.round=r.round) = 0
           GROUP BY r.round""",
        (y,),
    ).fetchall()
    if rows:
        print(f"  {y}: {[x[0] for x in rows]}")
