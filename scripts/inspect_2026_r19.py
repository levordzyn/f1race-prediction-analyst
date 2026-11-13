"""Investigate 2026 R19: why 32 rows in a 22-car grid?

Run:  python scripts/inspect_2026_r19.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 74)
print("2026 R19 - rows in every table")
print("=" * 74)
for t in ("results", "qualifying", "practice", "sprint",
          "sprint_qualifying", "driver_numbers"):
    n = con.execute(
        f"SELECT COUNT(*) FROM {t} WHERE year=2026 AND round=19"
    ).fetchone()[0]
    print(f"  {t:20} {n}")

print()
print("=" * 74)
print("results rows for 2026 R19")
print("=" * 74)
rows = con.execute(
    "SELECT driver, team, grid, finish FROM results "
    "WHERE year=2026 AND round=19 ORDER BY finish"
).fetchall()
for r in rows:
    print(f"  {r['driver']:>4}  team={str(r['team'])[:26]:26} "
          f"grid={str(r['grid']):>5} finish={str(r['finish']):>5}")

print()
print(f"distinct drivers : {len({r['driver'] for r in rows})}")
print(f"distinct teams   : {len({r['team'] for r in rows})}")
print(f"rows             : {len(rows)}")

# duplicate drivers?
from collections import Counter
dup = [d for d, c in Counter(r["driver"] for r in rows).items() if c > 1]
print(f"duplicate drivers: {dup}")
dup_t = [d for d, c in Counter(r["team"] for r in rows).items() if c > 1]
print(f"duplicate teams  : {dup_t}")

print()
print("=" * 74)
print("session row for 2026 R19")
print("=" * 74)
s = con.execute(
    "SELECT * FROM sessions WHERE year=2026 AND round=19"
).fetchone()
for k in s.keys():
    print(f"  {k:16} = {s[k]}")

print()
print("=" * 74)
print("fetch_log for 2026 R19")
print("=" * 74)
for r in con.execute(
    "SELECT step, nrows, run_at FROM fetch_log "
    "WHERE year=2026 AND round=19"
):
    print(f"  {r['step']:20} nrows={r['nrows']:<4} {r['run_at']}")

print()
print("=" * 74)
print("2026 schedule - what is round 19 and are there more rounds?")
print("=" * 74)
for r in con.execute(
    "SELECT round, event, event_format, event_date FROM sessions "
    "WHERE year=2026 ORDER BY round"
):
    print(f"  R{r['round']:<3} {str(r['event'])[:34]:34} "
          f"{str(r['event_format']):18} {r['event_date']}")
