"""Print FastF1's real 2026 event schedule so the upcoming-race path can be
written against verified field names instead of guesses.

WHY THIS SCRIPT EXISTS
  The database calendar stops at 2026 R19 because f1_baseline.py skips any
  race whose EventDate is in the future. Before building a forecast flow for
  Sao Paulo, the exact schedule row has to be seen once:
    * which RoundNumber Sao Paulo is,
    * what EventDate FastF1 reports,
    * what the session date columns are actually called,
    * which rounds are still in the future as of today.

  FastF1 field names are never assumed - every column name printed here comes
  from the response itself.

  READ-ONLY: prints the schedule, writes nothing to f1.db.

Run:  python scripts/probe_schedule.py [year]
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import fastf1

from f1pred import db, fetch

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
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026

    rule(f"[0] FASTF1 EVENT SCHEDULE {year} - COLUMNS THE API ACTUALLY RETURNS")
    # Same cache configuration every other FastF1 script uses, so this shares
    # its rate-limit budget and does not re-download what is already on disk.
    fetch.enable_cache()
    sched = fastf1.get_event_schedule(year, include_testing=False)
    print(f"  rows returned : {len(sched)}")
    print(f"  columns       : {list(sched.columns)}")

    rule("[1] EVERY ROUND, WITH THE FUTURE FLAG AS f1_baseline.py SEES IT")
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    print(f"  today (UTC date) : {today.date()}")
    print(f"  {'rd':<4}{'event':<32}{'EventDate':<22}{'future?':<9}in_db")
    print("  " + "-" * 74)

    con = db.connect()
    con.row_factory = None
    in_db = {(y, r) for y, r in con.execute(
        "SELECT DISTINCT year, round FROM results")}
    ses = {(y, r) for y, r in con.execute(
        "SELECT DISTINCT year, round FROM sessions")}
    con.close()

    future: list[tuple[int, str, str]] = []
    for _, ev in sched.iterrows():
        rnd = int(ev["RoundNumber"])
        d = pd.Timestamp(ev["EventDate"]).tz_localize(None)
        is_future = d > today
        name = str(ev["EventName"])
        if is_future:
            future.append((rnd, name, str(d.date())))
        mark = "YES" if is_future else "no"
        print(f"  {rnd:<4}{name[:31]:<32}{str(d.date()):<22}{mark:<9}"
              f"{'results' if (year, rnd) in in_db else '':<9}"
              f"{'sessions' if (year, rnd) in ses else ''}")

    rule("[2] ROUNDS f1_baseline.py WOULD SKIP TODAY")
    print(f"  future rounds: {len(future)}")
    for rnd, name, d in future:
        print(f"    R{rnd}  {name}  {d}")
    chk(1, len(future) > 0,
        "at least one round is still in the future (a forecast target exists)")

    rule("[3] THE SAO PAULO ROW, UNMODIFIED")
    sp = sched[sched["EventName"].astype(str).str.contains("Paulo", na=False)]
    chk(2, len(sp) == 1, "exactly one Sao Paulo event in the schedule")
    if len(sp) == 1:
        r = sp.iloc[0]
        print(f"  RoundNumber : {r['RoundNumber']!r}")
        print(f"  EventName   : {r['EventName']!r}")
        print(f"  EventDate   : {r['EventDate']!r}")
        print(f"  location    : "
              f"{r.get('Location', '<no Location column>')!r}")
        # Session date columns are printed verbatim so the fetch path can
        # rely on their real names.
        sess_cols = [c for c in sched.columns if "Session" in c]
        print(f"  session date columns present: {sess_cols}")
        for c in sess_cols:
            print(f"    {c:<26} = {r[c]!r}")

    rule("[4] WHAT THIS MEANS FOR THE FORECAST FLOW")
    print("  * f1_baseline.py line 80 skips future races, so the calendar in")
    print("    f1.db stops at the last completed round by design.")
    print("  * The upcoming-race path must therefore CREATE the session row,")
    print("    not merely find it.")
    print("  * It must fetch pre-race sessions (practice, qualifying) - there")
    print("    is no results row yet, which is the definition of a forecast.")
    print("  * Nothing here has been written to f1.db.")

    rule("RESULT")
    if FAILS:
        for f in FAILS:
            print(f"  FAIL - {f}")
        return 1
    print("  2 of 2 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
