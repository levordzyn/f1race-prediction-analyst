"""Prove the practice_rank source fix by re-fetching one affected race.

The repair (scripts/repair_practice_rank.py) and the fixed practice.py now
compute the same thing: rank starters only. If both are correct they must
agree exactly, so re-fetching 2026 R7 - the worst case, where STR was stored
P27 in a 22-car field - should reproduce the repaired rows with ZERO
differences.

What it guarantees:
  * only 2026 R7 practice is re-fetched (fetch_log entry deleted, then the
    real fetch_practice runs against real OpenF1 data);
  * every OTHER race's practice rows are byte-identical afterwards;
  * row counts stay at 1816 and sprint_qualifying is untouched;
  * fetch_log entry is restored.

Run:  python scripts/verify_practice_rank_fix.py
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, practice  # noqa: E402

YEAR, RND = 2026, 7
DB = "f1.db"
COLS = ("driver", "driver_number", "team", "n_sessions", "best_practice_s",
        "practice_rank", "laps_completed", "pit_out_laps", "gap_to_best_pct",
        "has_practice_lap")

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)-7s %(name)s: %(message)s")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row


def snapshot() -> dict[tuple, tuple]:
    """Every practice row keyed by (year, round, driver)."""
    cols = ", ".join(COLS)
    return {
        (r["year"], r["round"], r["driver"]): tuple(r[c] for c in COLS)
        for r in con.execute(f"SELECT year, round, {cols} FROM practice")
    }


before = snapshot()
b_total = con.execute("SELECT COUNT(*) FROM practice").fetchone()[0]

print("=" * 78)
print("BEFORE")
print("=" * 78)
print(f"  practice rows total : {b_total}")
print(f"  {YEAR} R{RND} rows      : "
      f"{sum(1 for k in before if k[0] == YEAR and k[1] == RND)}")

# Show the worst row so the fix is visible, not just asserted.
print(f"\n  {YEAR} R{RND} stored ranks BEFORE re-fetch:")
for r in con.execute(
        "SELECT driver, practice_rank, best_practice_s FROM practice "
        "WHERE year=? AND round=? ORDER BY practice_rank", (YEAR, RND)):
    flag = "   <-- was P27, outside a 22-car field" \
        if (r["practice_rank"] or 0) > 22 else ""
    print(f"    P{int(r['practice_rank']):>2}  {r['driver']:<5} "
          f"{r['best_practice_s']:.3f}{flag}")

# ---- re-fetch only this race --------------------------------------------
n_log = con.execute(
    "SELECT COUNT(*) FROM fetch_log WHERE year=? AND round=? "
    "AND step='practice'", (YEAR, RND)).fetchone()[0]
if n_log:
    con.execute("DELETE FROM fetch_log WHERE year=? AND round=? "
                "AND step='practice'", (YEAR, RND))
    con.commit()
    print(f"\n  fetch_log entry for {YEAR} R{RND} deleted so the fetch runs")

print()
print("=" * 78)
print(f"RUNNING fetch_practice({YEAR}, {RND}) - real OpenF1 call")
print("=" * 78)
try:
    practice.fetch_practice(con, YEAR, RND)
except Exception as exc:                          # noqa: BLE001
    print(f"  FAILED: {type(exc).__name__}: {exc}")
    sys.exit(1)

after = snapshot()
a_total = con.execute("SELECT COUNT(*) FROM practice").fetchone()[0]

print()
print("=" * 78)
print("AFTER re-fetch")
print("=" * 78)
print(f"  practice rows total : {a_total}")

# ---- diff ---------------------------------------------------------------
changed = [k for k in before if before[k] != after.get(k)]
miami = {(YEAR, RND, d) for (y, r, d) in before if y == YEAR and r == RND}
others = [k for k in changed if not (k[0] == YEAR and k[1] == RND)]

print()
print("=" * 78)
print("INVARIANTS")
print("=" * 78)
ok = True

c1 = a_total == 1816 == b_total
print(f"  [1] practice rows still 1816                 "
      f"{'PASS' if c1 else 'FAIL'}")
ok &= c1

c2 = not others
print(f"  [2] no other race touched ({len(others)})                 "
      f"{'PASS' if c2 else 'FAIL'}")
ok &= c2

# The real assertion: repaired data == what correct code produces.
c3 = not changed
print(f"  [3] re-fetch reproduced the repaired rows exactly "
      f"({len(changed)} diffs)  {'PASS' if c3 else 'FAIL'}")
if changed:
    print(f"        differences in {len(changed)} row(s):")
    for k in sorted(changed)[:20]:
        b, a = before[k], after.get(k)
        diffs = [f"{COLS[i]}: {b[i]!r} -> {a[i]!r}"
                 for i in range(len(COLS)) if b[i] != a[i]]
        print(f"          {k} :: {'; '.join(diffs)}")
ok &= c3

# The specific bug: no rank outside the field, and STR is 22nd not 27th.
field = con.execute(
    "SELECT COUNT(*) FROM results WHERE year=? AND round=?",
    (YEAR, RND)).fetchone()[0]
over = con.execute(
    "SELECT COUNT(*) FROM practice WHERE practice_rank > "
    "(SELECT COUNT(*) FROM results r WHERE r.year=practice.year "
    " AND r.round=practice.round)").fetchone()[0]
str_rank = con.execute(
    "SELECT practice_rank FROM practice WHERE year=? AND round=? "
    "AND driver='STR'", (YEAR, RND)).fetchone()[0]
c4 = over == 0 and int(str_rank) == field
print(f"  [4] STR is P{int(str_rank)} of {field}, none outside the field "
      f"({over})  {'PASS' if c4 else 'FAIL'}")
ok &= c4

# MIN=1, unique, contiguous within this race.
ranks = sorted(int(r["practice_rank"]) for r in con.execute(
    "SELECT practice_rank FROM practice WHERE year=? AND round=? "
    "AND practice_rank IS NOT NULL", (YEAR, RND)))
c5 = ranks == list(range(1, field + 1))
print(f"  [5] ranks are exactly 1..{field} contiguous         "
      f"{'PASS' if c5 else 'FAIL'}")
ok &= c5

# fetch_log restored
n_after_log = con.execute(
    "SELECT COUNT(*) FROM fetch_log WHERE year=? AND round=? "
    "AND step='practice'", (YEAR, RND)).fetchone()[0]
c6 = n_after_log == 1
print(f"  [6] fetch_log entry restored (={n_after_log})             "
      f"{'PASS' if c6 else 'FAIL'}")
ok &= c6

# sprint_qualifying untouched
sq_changed = con.execute(
    "SELECT COUNT(*) FROM sprint_qualifying").fetchone()[0]
c7 = sq_changed == 492
print(f"  [7] sprint_qualifying still 492 rows ({sq_changed})       "
      f"{'PASS' if c7 else 'FAIL'}")
ok &= c7

# DB-wide: no rank anywhere exceeds its field.
over_all = con.execute(
    "SELECT COUNT(*) FROM practice WHERE practice_rank > "
    "(SELECT COUNT(*) FROM results r WHERE r.year=practice.year "
    " AND r.round=practice.round)").fetchone()[0]
c8 = over_all == 0
print(f"  [8] DB-wide, no practice_rank exceeds its field "
      f"({over_all})     {'PASS' if c8 else 'FAIL'}")
ok &= c8

print()
print("=" * 78)
print("AFTER re-fetch - 2026 R7 ranks")
print("=" * 78)
for r in con.execute(
        "SELECT driver, practice_rank FROM practice "
        "WHERE year=? AND round=? ORDER BY practice_rank", (YEAR, RND)):
    print(f"    P{int(r['practice_rank']):>2}  {r['driver']}")

con.close()
print()
print("=" * 78)
print("PRACTICE_RANK SOURCE FIX VERIFIED" if ok
      else "PRACTICE_RANK SOURCE FIX FAILED")
print("=" * 78)
sys.exit(0 if ok else 1)
