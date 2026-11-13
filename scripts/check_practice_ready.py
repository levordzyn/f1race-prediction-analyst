"""Pre-flight for the practice module: does it import, and are there edge cases?

Checks:
  1. f1pred.practice imports without error (syntax/name resolution).
  2. How many starters have driver_number = NULL? Those take the "no data"
     fallback path in _write_rows, so we need to know if it is reachable.
  3. Do the new tables exist with the expected columns?
  4. Is every sprint weekend distinguishable from a conventional one?

Run:  python scripts/check_practice_ready.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

print("=" * 70)
print("1. IMPORT f1pred.practice")
print("=" * 70)
try:
    from f1pred import practice  # noqa: F401
    print("  OK imported")
    for name in ("fetch_practice", "fetch_sprint_qualifying",
                 "resolve_meeting", "practice_sessions",
                 "sprint_qualifying_session", "_merge_sessions",
                 "_write_rows", "_starters"):
        print(f"    {name:26} {'OK' if hasattr(practice, name) else 'MISSING'}")
except Exception as exc:  # noqa: BLE001
    print(f"  FAILED: {type(exc).__name__}: {exc}")
    raise

print()
print("=" * 70)
print("2. STARTERS WITH NULL driver_number (fallback path reachability)")
print("=" * 70)
con = sqlite3.connect("f1.db")
n_null = con.execute(
    "SELECT COUNT(*) FROM results r LEFT JOIN driver_numbers d "
    "ON d.year=r.year AND d.round=r.round AND d.driver=r.driver "
    "WHERE d.driver_number IS NULL"
).fetchone()[0]
n_all = con.execute("SELECT COUNT(*) FROM results").fetchone()[0]
print(f"  results rows                : {n_all}")
print(f"  with driver_number NULL      : {n_null}")
if n_null:
    rows = con.execute(
        "SELECT r.year, r.round, r.driver FROM results r "
        "LEFT JOIN driver_numbers d ON d.year=r.year AND d.round=r.round "
        "AND d.driver=r.driver WHERE d.driver_number IS NULL LIMIT 10"
    ).fetchall()
    print("  examples:", rows)

print()
print("=" * 70)
print("3. NEW TABLES + COLUMNS")
print("=" * 70)
# db.connect() runs SCHEMA + _migrate, which is what actually creates the
# tables - a raw sqlite3.connect() would see an empty database.
from f1pred import db as f1db  # noqa: E402

f1db.connect()
con = sqlite3.connect("f1.db")
for t in ("practice", "sprint_qualifying"):
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t:20} rows={n:<5} cols={len(cols)}")
    print(f"      {cols}")

print()
print("=" * 70)
print("4. SPRINT vs CONVENTIONAL WEEKENDS")
print("=" * 70)
rows = con.execute(
    "SELECT event_format, COUNT(*) FROM sessions GROUP BY event_format"
).fetchall()
for fmt, n in rows:
    print(f"  {fmt:22} {n} races")

# meeting_key currently NULL everywhere (practice step fills it)
n_mk = con.execute(
    "SELECT COUNT(*) FROM sessions WHERE meeting_key IS NOT NULL"
).fetchone()[0]
n_sess = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
print(f"\n  sessions with meeting_key set: {n_mk}/{n_sess} "
      f"(practice step fills this)")

print()
print("=" * 70)
print("5. httpcache / openf1 functions practice.py depends on")
print("=" * 70)
from f1pred import openf1 as o1  # noqa: E402

for name in ("get_sessions", "get_drivers", "get_laps",
             "best_practice_laps", "PRACTICE_SESSION_NAMES"):
    obj = getattr(o1, name, None)
    print(f"  {name:24} {'OK' if obj is not None else 'MISSING'}")
print(f"  PRACTICE_SESSION_NAMES = {o1.PRACTICE_SESSION_NAMES}")
