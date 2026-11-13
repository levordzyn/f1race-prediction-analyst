"""Probe the pre-race data sources for an upcoming race (2026 R20 Sao Paulo).

WHY THIS SCRIPT EXISTS
  Before writing the upcoming-race fetch path, three things must be observed
  rather than guessed:

  1. WHICH FastF1 sessions already exist for R20, and what their ``results``
     carry (Abbreviation / TeamName / DriverNumber) - that triple is the
     driver identifier the whole database uses, so it must come from FastF1
     and not from a second source that could disagree.
  2. WHOSE drivers are in them - FastF1 practice sessions can contain reserve
     and test drivers who will not start the race (seen before: practice_rank
     27 in a 22-car field). The entrant list for a forecast has to be the
     real field, so the overlap with drivers who have already raced in 2026
     is printed.
  3. WHETHER OpenF1 has a Race session for the weekend yet - practice.py
     resolves the meeting by matching an OpenF1 Race session to
     sessions.event_date, and that session cannot exist before the race.

  READ-ONLY. Nothing is written to f1.db.

Run:  python scripts/probe_upcoming.py [year] [round]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import fastf1

from f1pred import db, fetch, openf1 as o1

FAILS: list[str] = []

IDENTS = ("FP1", "FP2", "FP3", "Q")


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
    rnd = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    fetch.enable_cache()
    con = db.connect()
    con.row_factory = None

    # ---- season drivers already in results (the "has raced" set) ----------
    season = con.execute(
        "SELECT DISTINCT driver FROM results WHERE year=?", (year,)
    ).fetchall()
    season_drivers = {r[0] for r in season}
    print(f"  {year} drivers who have already started a race: "
          f"{len(season_drivers)}")

    rule("[1] WHICH FASTF1 SESSIONS EXIST FOR THIS ROUND")
    found: dict[str, pd.DataFrame] = {}
    for ident in IDENTS:
        try:
            ses = fastf1.get_session(year, rnd, ident)
            ses.load(laps=False, telemetry=False, weather=False,
                     messages=False)
            res = ses.results
        except Exception as exc:                       # noqa: BLE001
            print(f"  {ident:<5} unavailable: {type(exc).__name__}: {exc}")
            continue
        n = len(res)
        found[ident] = res
        print(f"  {ident:<5} OK - {n} rows, columns={list(res.columns)}")

    chk(1, len(found) > 0, "at least one pre-race session is available")

    rule("[2] DRIVER TRIPLE FROM EACH AVAILABLE SESSION  "
         "(the identifier the DB uses)")
    for ident, res in found.items():
        cols = {c.lower(): c for c in res.columns}
        need = ["abbreviation", "teamname", "drivernumber"]
        if not all(k in cols for k in need):
            print(f"  {ident}: missing one of {need} -> columns "
                  f"{list(res.columns)}")
            continue
        ab = res[cols["abbreviation"]]
        # FastF1 writes the STRING 'nan' for drivers who took no part; the
        # same test fetch.py uses.
        mask = ab.apply(lambda v: not fetch._nullish(v))
        sub = res[mask]
        print(f"  {ident}: {len(sub)} real entries "
              f"(dropped {len(res) - len(sub)} placeholder rows)")
        print(f"    drivers: "
              f"{sorted(str(v) for v in sub[cols['abbreviation']])}")
        in_season = sorted(
            str(v) for v in sub[cols["abbreviation"]]
            if str(v) in season_drivers)
        not_in_season = sorted(
            str(v) for v in sub[cols["abbreviation"]]
            if str(v) not in season_drivers)
        print(f"    already raced in {year}: {len(in_season)}")
        print(f"    NOT yet raced in {year}: {not_in_season or 'none'}")

    rule("[3] DOES THE FIELD MATCH expected_size?")
    row = con.execute(
        "SELECT expected_size, event_date, event_format FROM sessions "
        "WHERE year=? AND round=?", (year, rnd)).fetchone()
    if row is None:
        print("  no sessions row yet (expected - the fetch path creates it)")
        expected, e_date, fmt = None, None, None
    else:
        expected, e_date, fmt = row
        print(f"  expected_size={expected} event_date={e_date} "
              f"format={fmt}")
    for ident, res in found.items():
        cols = {c.lower(): c for c in res.columns}
        if "abbreviation" not in cols:
            continue
        real = [v for v in res[cols["abbreviation"]]
                if not fetch._nullish(v)]
        print(f"  {ident}: {len(real)} real entries"
              + (f" vs expected_size {expected}"
                 if expected is not None else ""))

    rule("[4] OPENF1 SESSIONS FOR THE WEEKEND  "
         "(resolve_meeting matches on the RACE session)")
    all_ses = o1.get_sessions(year)
    if not all_ses:
        print("  no OpenF1 sessions returned for this year")
    # Sessions near this race's date, whichever meeting owns them.
    target = None
    if e_date:
        target = pd.Timestamp(e_date).date()
        print(f"  sessions.event_date = {target}")
    near = []
    for s in all_ses:
        try:
            d = o1._date(s["date_start"]) if hasattr(o1, "_date") else None
        except Exception:                              # noqa: BLE001
            d = None
        if d is None:
            try:
                d = pd.Timestamp(s["date_start"]).tz_convert("UTC") \
                    .tz_localize(None).date()
            except Exception:                          # noqa: BLE001
                continue
        if target is not None and abs((d - target).days) <= 3:
            near.append((d, s))
    for d, s in sorted(near, key=lambda x: x[0]):
        print(f"  {d}  meeting_key={s.get('meeting_key')!s:<8} "
              f"type={s.get('session_type')!s:<12} "
              f"name={s.get('session_name')!s:<20} "
              f"key={s.get('session_key')}")

    races = [s for s in all_ses
             if s.get("session_type") == "Race"
             and s.get("session_name") == "Race"]
    race_near = []
    for s in races:
        try:
            d = pd.Timestamp(s["date_start"]).tz_convert("UTC") \
                .tz_localize(None).date()
        except Exception:                              # noqa: BLE001
            continue
        if target is not None and abs((d - target).days) <= 1:
            race_near.append((d, s))
    print(f"\n  OpenF1 Race sessions within +-1 day of the event date: "
          f"{len(race_near)}")
    if race_near:
        for d, s in race_near:
            print(f"    {d} meeting_key={s.get('meeting_key')} "
                  f"session_key={s.get('session_key')}")
    chk(2, True,
        "recorded: resolve_meeting needs a Race session that may not exist yet"
        if not race_near else "a Race session exists for this weekend")

    rule("[5] WHAT THE FETCH PATH WILL HAVE TO SOLVE")
    print("  blocker A  _starters() reads `results`; empty before the race,")
    print("             so fetch_qualifying and compute_practice both bail")
    print("             out with 'no starters'.")
    print("  blocker B  resolve_meeting() matches an OpenF1 RACE session to")
    print("             sessions.event_date within +-1 day; with no race yet")
    print("             there is nothing to match, so practice_sessions()")
    print("             returns [] and no laps are read.")
    print("  blocker C  the entrant list must be the real field, not every")
    print("             driver who appears in a practice session.")
    print("  Nothing has been written to f1.db.")

    con.close()
    rule("RESULT")
    if FAILS:
        for f in FAILS:
            print(f"  FAIL - {f}")
        return 1
    print(f"  probe complete - {len(found)} session(s) available for "
          f"{year} R{rnd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
