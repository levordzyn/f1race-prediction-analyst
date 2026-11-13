"""Re-fetch ONLY Miami 2025 (2025 R6) qualifying with the ses.laps fallback.

Before this runs, every driver in that race has has_qualifying_time=0 because
results.Q1/Q2/Q3 are all NaT, even though FastF1's laps hold their times.

What it guarantees:
  * only 2025 R6 qualifying is re-fetched (fetch_log entry deleted, then the
    real fetch_qualifying runs against real FastF1 data);
  * every OTHER race's qualifying rows are byte-identical afterwards;
  * q_position / q_position_official are untouched (official Position, not
    lap-derived) - only best_q_s, gap_to_pole_pct and has_qualifying_time move;
  * total qualifying rows stay at 1,816;
  * a timestamped backup is taken first.

Run:  python scripts/refetch_miami_q.py
"""
from __future__ import annotations

import logging
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import credentials  # noqa: E402

credentials.load()
from f1pred import db, fetch  # noqa: E402

YEAR, RND = 2025, 6
DB = Path("f1.db")
COLS = ("driver", "q_position", "q_position_official", "q1_s", "q2_s",
        "q3_s", "best_q_s", "gap_to_pole_pct", "has_qualifying_time")

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)-7s %(name)s: %(message)s")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row


def snapshot() -> dict[tuple, tuple]:
    """Every qualifying row keyed by (year, round, driver)."""
    return {
        (r["year"], r["round"], r["driver"]): tuple(r[c] for c in COLS)
        for r in con.execute(
            "SELECT year, round, driver, q_position, q_position_official, "
            "       q1_s, q2_s, q3_s, best_q_s, gap_to_pole_pct, "
            "       has_qualifying_time FROM qualifying"
        )
    }


def counts() -> tuple[int, int, int]:
    """(missing qualifying time, fully unknown, total rows)."""
    miss = con.execute(
        "SELECT COUNT(*) FROM qualifying WHERE has_qualifying_time = 0"
    ).fetchone()[0]
    unknown = con.execute(
        "SELECT COUNT(*) FROM qualifying WHERE has_qualifying_time = 0 "
        "AND q_position IS NULL"
    ).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM qualifying").fetchone()[0]
    return miss, unknown, total


before = snapshot()
b_miss, b_unknown, b_total = counts()

print("=" * 78)
print("BEFORE")
print("=" * 78)
print(f"  qualifying rows total            : {b_total}")
print(f"  rows with no qualifying time     : {b_miss}")
print(f"  fully unknown (no time, no pos)  : {b_unknown}")
print(f"  {YEAR} R{RND} rows in snapshot          : "
      f"{sum(1 for k in before if k[0] == YEAR and k[1] == RND)}")

print()
print(f"  fully unknown drivers (must stay {b_unknown}):")
for (y, r, d), v in sorted(before.items()):
    # COLS index: 1=q_position, 8=has_qualifying_time (7 is gap_to_pole_pct)
    if v[8] == 0 and v[1] is None:
        print(f"      {y} R{r}  {d}")

# ---- backup -------------------------------------------------------------
stamp = time.strftime("%Y%m%d_%H%M%S")
backup = Path(f"f1_backup_before_miami_refetch_{stamp}.db")
shutil.copy(DB, backup)
print(f"\n  backup written: {backup.name} ({backup.stat().st_size:,} bytes)")

# ---- re-fetch only this race -------------------------------------------
n_log = con.execute(
    "SELECT COUNT(*) FROM fetch_log WHERE year=? AND round=? AND step='qualifying'",
    (YEAR, RND)).fetchone()[0]
if n_log:
    con.execute("DELETE FROM fetch_log WHERE year=? AND round=? "
                "AND step='qualifying'", (YEAR, RND))
    con.commit()
    print(f"  fetch_log entry for {YEAR} R{RND} deleted so the fetch runs")

print()
print("=" * 78)
print(f"RUNNING fetch_qualifying({YEAR}, {RND}) - real FastF1 call")
print("=" * 78)
try:
    fetch.fetch_qualifying(con, YEAR, RND)
except Exception as exc:                          # noqa: BLE001
    print(f"  FAILED: {type(exc).__name__}: {exc}")
    sys.exit(1)

after = snapshot()
a_miss, a_unknown, a_total = counts()

print()
print("=" * 78)
print(f"AFTER {YEAR} R{RND}")
print("=" * 78)
print(f"  {'drv':<5} {'q_pos':>6} {'best_q_s':>10} {'gap%':>8} {'has_time':>9}")
for (y, r, d), v in sorted(after.items(), key=lambda x: (x[0][0], x[0][1],
                                                         x[1][1] is None,
                                                         x[1][1])):
    if y == YEAR and r == RND:
        best = f"{v[6]:.3f}" if v[6] is not None else "-"
        gap = f"{v[7]:.3f}" if v[7] is not None else "-"
        print(f"  {d:<5} {str(v[1]):>6} {best:>10} {gap:>8} {v[8]:>9}")

print()
print("=" * 78)
print("COUNTS: before -> after")
print("=" * 78)
print(f"  qualifying rows total           : {b_total} -> {a_total}   "
      f"{'OK' if a_total == 1816 else 'FAIL (expected 1816)'}")
print(f"  rows with no qualifying time    : {b_miss} -> {a_miss}   "
      f"(expect ~42 -> ~22)")
print(f"  fully unknown (no time, no pos) : {b_unknown} -> {a_unknown}   "
      f"(expect {b_unknown} -> {b_unknown})")

print()
print("=" * 78)
print("INVARIANTS")
print("=" * 78)
ok = True

# 1. total rows unchanged
c1 = a_total == 1816 == b_total
print(f"  [1] total qualifying rows still 1816          "
      f"{'PASS' if c1 else 'FAIL'}")
ok &= c1

# 2. exactly the 20 Miami rows changed
changed = [k for k in before if before[k] != after.get(k)]
miami = {(YEAR, RND, d) for (y, r, d) in before if y == YEAR and r == RND}
c2 = set(changed) == miami and len(changed) == 20
print(f"  [2] exactly the {len(miami)} Miami rows changed "
      f"({len(changed)})   {'PASS' if c2 else 'FAIL'}")
if set(changed) != miami:
    print(f"        unexpected: {sorted(set(changed) - miami)[:10]}")
    print(f"        missing   : {sorted(miami - set(changed))[:10]}")
ok &= c2

# 3. no OTHER race touched
others = [k for k in changed if not (k[0] == YEAR and k[1] == RND)]
c3 = not others
print(f"  [3] no other race touched ({len(others)})              "
      f"{'PASS' if c3 else 'FAIL'}")
ok &= c3

# 4. only the three intended fields moved on Miami rows
allowed = {"best_q_s", "gap_to_pole_pct", "has_qualifying_time"}
bad_fields = set()
for k in changed:
    for i, col in enumerate(COLS):
        if before[k][i] != after[k][i]:
            if col not in allowed:
                bad_fields.add(col)
c4 = not bad_fields
print(f"  [4] only best_q_s/gap/has_time changed           "
      f"{'PASS' if c4 else 'FAIL ' + str(bad_fields)}")
ok &= c4

# 5. every Miami driver now has a time, and positions are untouched
miami_now = {k: v for k, v in after.items() if k[0] == YEAR and k[1] == RND}
c5 = (len(miami_now) == 20
      and all(v[8] == 1 and v[6] is not None for v in miami_now.values())
      and all(before[k][1] == after[k][1]
              and before[k][2] == after[k][2] for k in miami_now))
print(f"  [5] all 20 have a time; q_position unchanged     "
      f"{'PASS' if c5 else 'FAIL'}")
ok &= c5

# 6. missing-count dropped by exactly the 20 recovered
c6 = (b_miss - a_miss) == 20
print(f"  [6] missing-time count fell by exactly 20 "
      f"({b_miss - a_miss})  {'PASS' if c6 else 'FAIL'}")
ok &= c6

# 7. the 6 fully unknown survived untouched
c7 = a_unknown == b_unknown == 6
print(f"  [7] still exactly 6 fully unknown drivers        "
      f"{'PASS' if c7 else 'FAIL'}")
ok &= c7

# 8. fetch_log restored
n_after_log = con.execute(
    "SELECT COUNT(*) FROM fetch_log WHERE year=? AND round=? "
    "AND step='qualifying'", (YEAR, RND)).fetchone()[0]
c8 = n_after_log == 1
print(f"  [8] fetch_log entry restored (={n_after_log})            "
      f"{'PASS' if c8 else 'FAIL'}")
ok &= c8

# 9. no fully-unknown row gained a time
regressed = [
    k for k in before
    if before[k][1] is None and (after.get(k) or before[k])[8] != 0
]
c9 = not regressed
print(f"  [9] no fully-unknown driver gained a time        "
      f"{'PASS' if c9 else 'FAIL ' + str(regressed)}")
ok &= c9

print()
print("=" * 78)
print("REMAINING rows with no qualifying time (expect 22)")
print("=" * 78)
for (y, r, d), v in sorted(after.items()):
    if v[8] == 0:
        tag = "  <-- fully unknown" if v[1] is None else ""
        print(f"  {y} R{r:>2}  {d:<5} q_pos={str(v[1]):>5}{tag}")

con.close()
print()
print("=" * 78)
print("MIAMI RE-FETCH PASSED" if ok else "MIAMI RE-FETCH FAILED")
print("=" * 78)
sys.exit(0 if ok else 1)
