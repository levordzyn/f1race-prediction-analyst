"""Report what the database already knows about races AFTER the last scored one.

WHY THIS SCRIPT EXISTS
  The São Paulo forecast flow needs three things to be true, and none of them
  may be assumed:
    1. a target race that is NOT in `results` (otherwise there is nothing to
       forecast - the answer would already be in the table);
    2. enough sessions already fetched for that race to build features
       (a forecast made before qualifying exists is a different, much weaker
       forecast, so the script must say which it is);
    3. no weather columns for a date that has not passed, because build_features
       deliberately omits them rather than inventing a value.

  Everything here is READ-ONLY against f1.db. It prints facts; it fetches
  nothing and writes nothing.

Run:  python scripts/probe_next_race.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db

FAILS: list[str] = []


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def chk(n: int, cond: bool, msg: str) -> None:
    print(f"  [{n:>2}] {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        FAILS.append(msg)


def main() -> int:
    con = db.connect()
    con.row_factory = None

    rule("[1] RACES THAT ALREADY HAVE RESULTS  (these are DONE, not forecasts)")
    rows = con.execute(
        "SELECT year, round, COUNT(*) n FROM results "
        "GROUP BY year, round ORDER BY year, round").fetchall()
    scored = {(y, r) for y, r, _ in rows}
    print(f"  races with results : {len(scored)}")
    print(f"  last scored race   : {max(scored)}")

    rule("[2] EVERY RACE THE CALENDAR KNOWS ABOUT")
    ses = con.execute(
        "SELECT year, round, event, event_format, event_date, expected_size "
        "FROM sessions ORDER BY year, round").fetchall()
    print(f"  {'year':<6}{'rd':<4}{'event':<32}{'format':<13}{'date':<12}"
          f"{'size':<6}{'results':<9}")
    print("  " + "-" * 76)
    for y, r, ev, fmt, d, sz in ses:
        has = "YES" if (y, r) in scored else "no"
        print(f"  {y:<6}{r:<4}{str(ev)[:31]:<32}{str(fmt)[:12]:<13}"
              f"{str(d):<12}{str(sz):<6}{has:<9}")

    rule("[3] RACES IN THE CALENDAR WITH NO RESULTS YET  (forecast candidates)")
    pending = [(y, r, ev, fmt, d) for y, r, ev, fmt, d, _ in ses
               if (y, r) not in scored]
    if not pending:
        print("  none - every race in the calendar has results, so the "
              "forecast flow needs a new race fetched first")
    for y, r, ev, fmt, d in pending:
        print(f"  {y} R{r}  {ev}  ({fmt})  {d}")

    rule("[4] HOW MUCH SESSION DATA EACH PENDING RACE HAS")
    for y, r, ev, fmt, d in pending:
        q = con.execute(
            "SELECT COUNT(*) FROM qualifying WHERE year=? AND round=?",
            (y, r)).fetchone()[0]
        p = con.execute(
            "SELECT COUNT(DISTINCT driver_number) FROM practice "
            "WHERE year=? AND round=?", (y, r)).fetchone()[0]
        s = con.execute(
            "SELECT COUNT(DISTINCT driver_number) FROM sprint "
            "WHERE year=? AND round=?", (y, r)).fetchone()[0]
        sq = con.execute(
            "SELECT COUNT(DISTINCT driver_number) FROM sprint_qualifying "
            "WHERE year=? AND round=?", (y, r)).fetchone()[0]
        w = con.execute(
            "SELECT COUNT(*) FROM weather WHERE year=? AND round=?",
            (y, r)).fetchone()[0]
        print(f"  {y} R{r}  qualifying={q}  practice_drivers={p}  "
              f"sprint={s}  sprint_q={sq}  weather={w}")
        stage = ("ready (grid known)"
                 if q > 0 else
                 "pre-qualifying (early mode only)")
        print(f"           -> {stage}")

    rule("[5] WEATHER COVERAGE  (observed weather cannot exist for a future date)")
    w = con.execute("SELECT COUNT(*), MIN(year||'-'||round), "
                    "MAX(year||'-'||round) FROM weather").fetchone()
    print(f"  weather rows       : {w[0]}")
    missing = [(y, r) for y, r, _, _, _, _ in ses if (y, r) not in
               {(a, b) for a, b in
                [(x[0], x[1]) for x in
                 con.execute("SELECT year, round FROM weather").fetchall()]}]
    print(f"  calendar races with no weather row: {len(missing)}")
    for y, r in missing:
        print(f"    {y} R{r}")

    rule("[6] WHAT A FORECAST RUN MUST NOT DO")
    print("  * write to results - the scoring table stays the authority and")
    print("    the 7-column contract in db.py must hold")
    print("  * fill weather for an unpassed date - build_features omits the")
    print("    columns instead, so a conventional weekend with no weather row")
    print("    simply runs on the 12 production features")
    print("  * reuse a forecast for a different race - predictions are keyed")
    print("    by (year, round, mode) so a re-run is auditable")

    con.close()
    rule("RESULT")
    if FAILS:
        for f in FAILS:
            print(f"  FAIL - {f}")
        return 1
    print(f"  {len(pending)} pending race(s) found; probe completed without "
          "writing anything")
    return 0


if __name__ == "__main__":
    sys.exit(main())
