"""Quick sanity check: every Phase 1 table's row count and coverage.

Run:  python scripts/sanity.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")

print("=" * 60)
print("TABLE ROW COUNTS")
print("=" * 60)
for t in ["results", "sessions", "qualifying", "sprint",
          "driver_numbers", "fetch_log"]:
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t:16} {n:6} rows")

print()
print("=" * 60)
print("results SCHEMA (f1_baseline.py depends on these 7 columns)")
print("=" * 60)
cols = [r[1] for r in con.execute("PRAGMA table_info(results)")]
print(f"  {cols}")

print()
print("=" * 60)
print("PER-YEAR COVERAGE")
print("=" * 60)
print(f"  {'year':>6} {'results':>9} {'qual':>7} {'sprint':>8} "
      f"{'sess':>6} {'q_rounds':>9}")
for y in (2023, 2024, 2025, 2026):
    res = con.execute("SELECT COUNT(*) FROM results WHERE year=?",
                      (y,)).fetchone()[0]
    qual = con.execute("SELECT COUNT(*) FROM qualifying WHERE year=?",
                       (y,)).fetchone()[0]
    spr = con.execute("SELECT COUNT(*) FROM sprint WHERE year=?",
                      (y,)).fetchone()[0]
    sess = con.execute("SELECT COUNT(*) FROM sessions WHERE year=?",
                       (y,)).fetchone()[0]
    qr = con.execute(
        "SELECT COUNT(DISTINCT round) FROM qualifying WHERE year=?", (y,)
    ).fetchone()[0]
    print(f"  {y:>6} {res:>9} {qual:>7} {spr:>8} {sess:>6} {qr:>9}")

print()
print("=" * 60)
print("QUALIFYING INTEGRITY")
print("=" * 60)
n_total = con.execute("SELECT COUNT(*) FROM qualifying").fetchone()[0]
n_time = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE has_qualifying_time=1"
).fetchone()[0]
n_noq = con.execute(
    "SELECT COUNT(DISTINCT round) FROM qualifying "
    "WHERE has_qualifying_time=0"
).fetchone()[0]
print(f"  rows                  : {n_total}")
print(f"  with a lap time       : {n_time}")
print(f"  missing a lap time    : {n_total - n_time}")
print(f"  races with >=1 missing: {n_noq}")

# every race in results should have qualifying rows
orphan = con.execute(
    """SELECT r.year, r.round FROM results r
       WHERE (SELECT COUNT(*) FROM qualifying q
              WHERE q.year=r.year AND q.round=r.round) = 0
       GROUP BY r.year, r.round"""
).fetchall()
print(f"  races with NO qualifying rows: {len(orphan)} {orphan}")

print()
print("=" * 60)
print("SPRINT COVERAGE (sprint weekends only)")
print("=" * 60)
sp = con.execute(
    """SELECT s.year, COUNT(DISTINCT s.round)
       FROM sessions s WHERE s.event_format IN
       ('sprint_qualifying','sprint_shootout')
       GROUP BY s.year"""
).fetchall()
for y, n in sp:
    have = con.execute(
        "SELECT COUNT(DISTINCT round) FROM sprint WHERE year=?", (y,)
    ).fetchone()[0]
    print(f"  {y}: {n} sprint weekends, {have} with sprint rows")
