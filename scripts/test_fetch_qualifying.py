"""End-to-end test of the changed fetch_qualifying on a REAL session.

Picks 2023 R10 because official Position has a genuine tie there (PER and BOT
both 15), so it exercises the allow_ties=True path that the old derive_rank
code never hit.

What it does:
  1. snapshot the qualifying rows for the race;
  2. delete the fetch_log entry so fetch_qualifying is not skipped;
  3. call fetch_qualifying (the real code path, real FastF1 data);
  4. diff the rows before vs after;
  5. confirm q_position == q_position_official on every row.

Nothing is written unless the fetch succeeds - validation failures return
before the INSERT.

Run:  python scripts/test_fetch_qualifying.py
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.ERROR)

from f1pred import credentials  # noqa: E402

credentials.load()
from f1pred import db, fetch  # noqa: E402

YEAR, RND = 2023, 10
COLS = ("driver", "q_position", "q_position_official", "q1_s", "q2_s",
        "q3_s", "best_q_s", "gap_to_pole_pct", "has_qualifying_time")

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row


def snapshot() -> dict[str, tuple]:
    return {
        r["driver"]: tuple(r[c] for c in COLS)
        for r in con.execute(
            "SELECT driver, q_position, q_position_official, q1_s, q2_s, "
            "       q3_s, best_q_s, gap_to_pole_pct, has_qualifying_time "
            "FROM qualifying WHERE year=? AND round=? ORDER BY driver",
            (YEAR, RND))
    }


before = snapshot()
print("=" * 78)
print(f"BEFORE: {YEAR} R{RND} qualifying - {len(before)} rows")
print("=" * 78)
for d, v in sorted(before.items(), key=lambda x: (x[1][1] is None, x[1][1])):
    print(f"  {d:>4}  q_position={v[1]}  official={v[2]}  best={v[6]}")

n_log = con.execute(
    "SELECT COUNT(*) FROM fetch_log WHERE year=? AND round=? "
    "AND step='qualifying'", (YEAR, RND)).fetchone()[0]
print(f"\n  fetch_log entries for this step: {n_log} "
      f"({'would be skipped' if n_log else 'will run'})")

if n_log:
    con.execute("DELETE FROM fetch_log WHERE year=? AND round=? "
                "AND step='qualifying'", (YEAR, RND))
    con.commit()
    print("  -> deleted so the fetch actually runs")

print()
print("=" * 78)
print("RUNNING fetch_qualifying (real FastF1 call)")
print("=" * 78)
try:
    fetch.fetch_qualifying(con, YEAR, RND)
except Exception as exc:                      # noqa: BLE001
    print(f"  FAILED: {type(exc).__name__}: {exc}")
    sys.exit(1)

after = snapshot()

print()
print("=" * 78)
print("DIFF: before vs after")
print("=" * 78)
print(f"  rows before : {len(before)}")
print(f"  rows after  : {len(after)}")
missing = sorted(set(before) - set(after))
added = sorted(set(after) - set(before))
print(f"  rows lost   : {missing or 'none'}")
print(f"  rows added  : {added or 'none'}")

changed = []
for d in sorted(set(before) & set(after)):
    if before[d] != after[d]:
        changed.append(d)
print(f"  rows changed: {len(changed)}")
for d in changed:
    for i, c in enumerate(COLS):
        if before[d][i] != after[d][i]:
            print(f"      {d:>4} {c}: {before[d][i]} -> {after[d][i]}")

if not missing and not added and not changed:
    print("  -> byte-identical. The new code produces exactly what the")
    print("     repaired data already holds.")

print()
print("=" * 78)
print("AFTER: q_position vs official (tie must survive)")
print("=" * 78)
for d, v in sorted(after.items(), key=lambda x: (x[1][1] is None, x[1][1])):
    mark = "  <-- TIE" if v[1] == 15 else ""
    print(f"  {d:>4}  q_position={v[1]}  official={v[2]}{mark}")

n_diff = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE year=? AND round=? AND "
    "((q_position IS NULL) != (q_position_official IS NULL) OR "
    "(q_position IS NOT NULL AND q_position_official IS NOT NULL "
    " AND q_position != q_position_official))", (YEAR, RND)).fetchone()[0]
n_tie = con.execute(
    "SELECT COUNT(*) FROM (SELECT q_position FROM qualifying "
    "WHERE year=? AND round=? AND q_position IS NOT NULL "
    "GROUP BY q_position HAVING COUNT(*) > 1)", (YEAR, RND)).fetchone()[0]

print()
print(f"  rows where q_position != official : {n_diff}   (expect 0)")
print(f"  tie groups preserved              : {n_tie}   (expect 1)")
print(f"  fetch_log restored                : "
      f"{con.execute('SELECT COUNT(*) FROM fetch_log WHERE year=? AND round=? AND step=?', (YEAR, RND, 'qualifying')).fetchone()[0]}"
      f"   (expect 1)")

ok = (not missing and not added and not changed
      and n_diff == 0 and n_tie == 1)
print()
print("TEST PASSED" if ok else "TEST FAILED")
con.close()
sys.exit(0 if ok else 1)
