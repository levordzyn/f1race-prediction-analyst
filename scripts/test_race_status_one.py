"""Test fetch_race_status on ONE race before fetching all 89.

Guarantees checked:
  1. race_status row set for the race == results row set for the race (1:1);
  2. results is byte-identical afterwards (the step never writes it);
  3. all 1816 results rows unchanged;
  4. the fetch_log step is recorded, and a second call is a no-op;
  5. every stored status is a real string, never FastF1's 'nan'.

Run:  python scripts/test_race_status_one.py
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import credentials  # noqa: E402

credentials.load()
from f1pred import db, fetch  # noqa: E402

YEAR, RND = 2023, 1

logging.basicConfig(level=logging.INFO,
                    format="%(levelname)-7s %(name)s: %(message)s")

con = db.connect()
# db.connect() does not set a row_factory; db.starters() does it as a side
# effect. Set it here so the snapshot can index rows by column name.
con.row_factory = sqlite3.Row

RES_COLS = ["year", "round", "event", "driver", "team", "grid", "finish"]


def results_snapshot():
    cols = ", ".join(RES_COLS)
    return {
        (r["year"], r["round"], r["driver"]): tuple(r[c] for c in RES_COLS)
        for r in con.execute(f"SELECT {cols} FROM results")
    }


before = results_snapshot()
b_total = len(before)
print("=" * 78)
print(f"BEFORE  results={b_total}  "
      f"race_status={con.execute('SELECT COUNT(*) FROM race_status').fetchone()[0]}")
print("=" * 78)

ev = con.execute(
    "SELECT event, event_format, event_date FROM sessions "
    "WHERE year=? AND round=?", (YEAR, RND)).fetchone()
print(f"  target: {YEAR} R{RND} {ev['event']} ({ev['event_format']})")

# fetch_race_status needs the `ev` row FastF1-style (EventName/EventFormat/
# EventDate). Build the minimal duck-typed object it reads.
class _Ev(dict):
    def __getitem__(self, k):
        return dict.__getitem__(self, k)


fastf1_ev = _Ev({"EventName": ev["event"],
                 "EventFormat": ev["event_format"],
                 "EventDate": ev["event_date"]})

print()
print("=" * 78)
print(f"RUNNING fetch_race_status({YEAR}, {RND}) - real FastF1 call")
print("=" * 78)
try:
    fetch.fetch_race_status(con, YEAR, RND, fastf1_ev)
except Exception as exc:                          # noqa: BLE001
    print(f"  FAILED: {type(exc).__name__}: {exc}")
    sys.exit(1)

after = results_snapshot()
a_total = len(after)

# ---- the row-set parity assertion ---------------------------------------
rs = {r["driver"] for r in con.execute(
    "SELECT driver FROM race_status WHERE year=? AND round=?", (YEAR, RND))}
rr = {r["driver"] for r in con.execute(
    "SELECT driver FROM results WHERE year=? AND round=?", (YEAR, RND))}

print()
print("=" * 78)
print("INVARIANTS")
print("=" * 78)
ok = True

c1 = rs == rr
print(f"  [1] race_status drivers == results drivers       "
      f"{'PASS' if c1 else 'FAIL'}")
if not c1:
    print(f"        only in status: {sorted(rs - rr)}")
    print(f"        only in results: {sorted(rr - rs)}")
ok &= c1

c2 = after == before
print(f"  [2] results byte-identical ({b_total} -> {a_total})   "
      f"{'PASS' if c2 else 'FAIL'}")
ok &= c2

c3 = a_total == 1816
print(f"  [3] results still 1816 rows                     "
      f"{'PASS' if c3 else 'FAIL'}")
ok &= c3

# second call must be a no-op (fetch_log guard)
n_before = con.execute("SELECT COUNT(*) FROM race_status").fetchone()[0]
fetch.fetch_race_status(con, YEAR, RND, fastf1_ev)
n_after = con.execute("SELECT COUNT(*) FROM race_status").fetchone()[0]
c4 = n_before == n_after and n_before == len(rr)
print(f"  [4] second call is a no-op ({n_before} -> {n_after})        "
      f"{'PASS' if c4 else 'FAIL'}")
ok &= c4

# no FastF1 'nan' strings leaked through
bad = con.execute(
    "SELECT COUNT(*) FROM race_status WHERE status IS NOT NULL "
    "AND (status = 'nan' OR status = '' OR status = 'None')").fetchone()[0]
c5 = bad == 0
print(f"  [5] no 'nan'/empty status strings ({bad})          "
      f"{'PASS' if c5 else 'FAIL'}")
ok &= c5

# fetch_log recorded
n_log = con.execute(
    "SELECT COUNT(*) FROM fetch_log WHERE year=? AND round=? "
    "AND step='race_status'", (YEAR, RND)).fetchone()[0]
c6 = n_log == 1
print(f"  [6] fetch_log step recorded (={n_log})                "
      f"{'PASS' if c6 else 'FAIL'}")
ok &= c6

# other steps untouched
other = con.execute(
    "SELECT step, COUNT(*) n FROM fetch_log GROUP BY step ORDER BY step"
).fetchall()
print()
print("  fetch_log steps now:")
for r in other:
    print(f"      {r['step']:<20} {r['n']}")

# results columns still exactly 7
cols = [r[1] for r in con.execute("PRAGMA table_info(results)")]
c7 = cols == RES_COLS
print()
print(f"  [7] results still exactly the 7 columns          "
      f"{'PASS' if c7 else 'FAIL ' + str(cols)}")
ok &= c7

print()
print("=" * 78)
print(f"STATUSES STORED FOR {YEAR} R{RND}")
print("=" * 78)
# 'Lapped' is a FINISH: the driver reached the chequered flag and is
# classified, just a lap down. Only genuine retirements/exclusions count as
# non-finishes - this is the definition feature 7 will use.
FINISHING = {"Finished", "Lapped"}
for r in con.execute(
        "SELECT rs.driver, rs.status, r.finish, r.grid FROM race_status rs "
        "JOIN results r ON r.year=rs.year AND r.round=rs.round "
        "AND r.driver=rs.driver "
        "WHERE rs.year=? AND rs.round=? ORDER BY r.finish", (YEAR, RND)):
    if r["status"] in FINISHING:
        note = "" if r["status"] == "Finished" else "   (finished, a lap down)"
    else:
        note = "   <-- NON-FINISH"
    print(f"    P{int(r['finish']):>2}  {r['driver']:<5} "
          f"grid={str(int(r['grid']) if r['grid'] else '-'):>3}  "
          f"{r['status']:<22}{note}")

con.close()
print()
print("=" * 78)
print("ONE-RACE TEST PASSED" if ok else "ONE-RACE TEST FAILED")
print("=" * 78)
sys.exit(0 if ok else 1)
