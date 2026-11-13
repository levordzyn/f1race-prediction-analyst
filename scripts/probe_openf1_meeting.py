"""Does OpenF1 already know about the upcoming race weekend?

WHY THIS SCRIPT EXISTS
  f1pred.practice.resolve_meeting() finds the weekend by matching an OpenF1
  **Race** session to sessions.event_date within +-1 day. For a race that has
  not run, that Race session does not exist yet - so the meeting cannot be
  resolved, practice_sessions() returns [], and no practice laps are read even
  though OpenF1 already has them.

  This probe prints what OpenF1 actually holds around the event date so the
  fallback can be designed against real rows instead of a guess:
    * every session within +-4 days of the event date,
    * its meeting_key / session_key / session_type / session_name,
    * whether any of them is a Race session (the current code's requirement).

  READ-ONLY. Nothing is written to f1.db.

Run:  python scripts/probe_openf1_meeting.py [year] [round]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from f1pred import db, openf1 as o1, practice

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


def utc_date(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def main() -> int:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    rnd = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    con = db.connect()
    con.row_factory = None

    row = con.execute(
        "SELECT event_date, meeting_key FROM sessions WHERE year=? "
        "AND round=?", (year, rnd)).fetchone()
    if row is None:
        print(f"  no sessions row for {year} R{rnd} yet - using the FastF1 "
              "schedule date instead")
        from f1pred import fetch
        import fastf1
        fetch.enable_cache()
        sched = fastf1.get_event_schedule(year, include_testing=False)
        ev = sched[sched["RoundNumber"] == rnd].iloc[0]
        target = utc_date(ev["EventDate"]).date()
        stored_key = None
        print(f"  FastF1 EventDate = {target}  "
              f"EventName = {ev['EventName']!r}  "
              f"EventFormat = {ev['EventFormat']!r}")
    else:
        target = datetime_date(row[0])
        stored_key = row[1]
        print(f"  sessions.event_date = {target}, meeting_key = {stored_key}")

    rule("[1] EVERY OPENF1 SESSION WITHIN +-4 DAYS")
    all_ses = o1.get_sessions(year)
    print(f"  OpenF1 sessions returned for {year}: {len(all_ses)}")
    near = []
    for s in all_ses:
        try:
            d = utc_date(s["date_start"]).date()
        except Exception:                              # noqa: BLE001
            continue
        if abs((d - target).days) <= 4:
            near.append((d, s))
    near.sort(key=lambda x: (x[0], str(x[1].get("session_name"))))
    print(f"  {'date':<12}{'meeting':<10}{'key':<10}{'type':<14}"
          f"{'name':<22}delta")
    print("  " + "-" * 74)
    for d, s in near:
        delta = (d - target).days
        print(f"  {str(d):<12}{str(s.get('meeting_key')):<10}"
              f"{str(s.get('session_key')):<10}"
              f"{str(s.get('session_type')):<14}"
              f"{str(s.get('session_name')):<22}{delta:+d}")

    rule("[2] WHAT THE CURRENT resolve_meeting() REQUIRES")
    races = [s for s in all_ses
             if s.get("session_type") == "Race"
             and s.get("session_name") == "Race"]
    hit = []
    for s in races:
        try:
            d = utc_date(s["date_start"]).date()
        except Exception:                              # noqa: BLE001
            continue
        if abs((d - target).days) <= practice.DATE_TOLERANCE_DAYS:
            hit.append((d, s))
    print(f"  Race sessions within "
          f"+-{practice.DATE_TOLERANCE_DAYS} day of {target}: {len(hit)}")
    for d, s in hit:
        print(f"    {d} meeting_key={s.get('meeting_key')} "
              f"session_key={s.get('session_key')}")
    chk(1, True,
        "NO Race session exists -> resolve_meeting returns None"
        if not hit else "a Race session exists -> current code works")

    rule("[3] WHAT A FALLBACK COULD MATCH ON")
    meetings = sorted({s.get("meeting_key") for d, s in near
                       if s.get("meeting_key") is not None})
    print(f"  distinct meeting_keys near the date: {meetings}")
    for mk in meetings:
        sess = [s for d, s in near if s.get("meeting_key") == mk]
        names = [str(s.get("session_name")) for s in sess]
        dates = sorted({str(utc_date(s["date_start"]).date()) for s in sess})
        print(f"    meeting {mk}: {len(sess)} session(s) on {dates}")
        print(f"      names: {names}")
        practice_here = [n for n in names if n in practice.PRACTICE_NAMES]
        print(f"      practice sessions usable: {practice_here}")
    chk(2, len(meetings) >= 1,
        "at least one meeting owns sessions in this window")

    rule("[4] IMPLICATION")
    print("  resolve_meeting() needs a Race session that cannot exist before")
    print("  the race. Without a fallback the upcoming-race fetch would store")
    print("  a sessions row and then read ZERO practice laps, silently")
    print("  producing a forecast built on missing-flag features only.")
    print("  The fallback must match on the meeting that owns the weekend's")
    print("  practice sessions, and must never fire for a completed race")
    print("  (those always have a Race session, so path 1 still runs first).")
    print("  Nothing has been written to f1.db.")

    con.close()
    rule("RESULT")
    if FAILS:
        for f in FAILS:
            print(f"  FAIL - {f}")
        return 1
    print("  2 of 2 PASS")
    return 0


def datetime_date(value):
    return pd.Timestamp(value).date()


if __name__ == "__main__":
    sys.exit(main())
