"""List every table in f1.db with its row count and a per-year breakdown.

Quick integrity check after edits: confirms nothing was dropped, and that the
practice / sprint_qualifying tables from Phase 1 step 2 are still populated
(coverage.py predates them and does not list them).

Run:  python scripts/list_tables.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")

tables = [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
)]

print("=" * 60)
print("TABLES AND ROW COUNTS")
print("=" * 60)
for t in tables:
    n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f"  {t:<22} {n:>6}")

print()
print("=" * 60)
print("PRACTICE / SPRINT_QUALIFYING (Phase 1 step 2)")
print("=" * 60)
for t in ("practice", "sprint_qualifying"):
    if t not in tables:
        print(f"  {t}: MISSING")
        continue
    cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
    print(f"  {t}: {cols}")
    year_col = "year" if "year" in cols else None
    if year_col:
        for y, n in con.execute(
                f'SELECT {year_col}, COUNT(*) FROM "{t}" GROUP BY {year_col} '
                f"ORDER BY {year_col}"):
            print(f"      {y}: {n} rows")
    # does practice record how many sessions were aggregated?
    if "n_sessions" in cols:
        dist = con.execute(
            f'SELECT n_sessions, COUNT(*) FROM "{t}" GROUP BY n_sessions '
            f"ORDER BY n_sessions"
        ).fetchall()
        print(f"      n_sessions distribution: {dist}")
    if "has_practice_lap" in cols:
        no_lap = con.execute(
            f'SELECT COUNT(*) FROM "{t}" WHERE has_practice_lap = 0'
        ).fetchone()[0]
        print(f"      rows with no practice lap: {no_lap}")

print()
print("=" * 60)
print("FETCH_LOG: which steps ran")
print("=" * 60)
for step, n in con.execute(
        "SELECT step, COUNT(*) FROM fetch_log GROUP BY step ORDER BY step"):
    print(f"  {step:<22} {n:>6}")

con.close()
