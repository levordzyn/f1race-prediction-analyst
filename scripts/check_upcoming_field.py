"""Derive the starting field of a race that has not run, and prove it is 22.

WHY THIS SCRIPT EXISTS
  A forecast needs the list of drivers who will START. Before the race that
  list is not in `results`, so it has to come from the weekend's sessions -
  and a naive reading gets it wrong twice over:

    * FP1 of 2026 R20 contains SIX F2 rookies (BEG, BRO, FOR, HER, MIN, SLA)
      who are running the mandatory young-driver FP1 test. They will not race.
    * HIR has been REPLACED by CAM (Camara), who makes his full F1 weekend
      debut alongside Oliver Bearman. So filtering to "drivers who have
      already started a 2026 race" would drop the man who is actually racing
      and would have left the field one car short.

  The rule that gets both right, and is checked here:

    entrant  =  has raced this season
             OR appears in a practice session AFTER FP1 (a full-weekend entry)

  A young-driver test driver appears only in FP1 and has never raced, so he
  is dropped. A debutant who is actually racing appears in FP2, so he is kept.

  READ-ONLY. Nothing is written to f1.db.

Run:  python scripts/check_upcoming_field.py [year] [round]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fastf1

from f1pred import db, fetch

FAILS: list[str] = []

# The sessions worth loading: FP1..FP3 plus qualifying. A session that has
# not run yet comes back with 0 rows and contributes nothing.
PRE_RACE_IDENTS = ("FP1", "FP2", "FP3", "Q")


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def chk(n: int, cond: bool, msg: str) -> None:
    print(f"  [{n:>2}] {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        FAILS.append(msg)


def drivers_of(res) -> dict[str, str]:
    """{Abbreviation: TeamName} for rows that really took part.

    Uses fetch._nullish, not pandas.isna: FastF1 writes the STRING 'nan' for
    entries that did not take part and pandas.isna() does not catch it.
    """
    out: dict[str, str] = {}
    if res is None or len(res) == 0 or "Abbreviation" not in getattr(
            res, "columns", []):
        return out
    for _, r in res.iterrows():
        ab = r.get("Abbreviation")
        if fetch._nullish(ab):
            continue
        team = r.get("TeamName")
        out[str(ab)] = "" if fetch._nullish(team) else str(team)
    return out


def main() -> int:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    rnd = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    fetch.enable_cache()
    con = db.connect()
    con.row_factory = None

    raced_rows = con.execute(
        "SELECT DISTINCT driver FROM results WHERE year=?", (year,)).fetchall()
    raced = {r[0] for r in raced_rows}

    # Season field size, taken the way fetch.py does for a completed race.
    row = con.execute(
        "SELECT expected_size FROM sessions WHERE year=? ORDER BY round "
        "DESC LIMIT 1", (year,)).fetchone()
    expected = row[0] if row else None
    print(f"  {year} drivers who have already started a race: {len(raced)}")
    print(f"  season field size (expected_size): {expected}")

    rule("[1] WHICH PRE-RACE SESSIONS HAVE RUN")
    per_session: dict[str, dict[str, str]] = {}
    for ident in PRE_RACE_IDENTS:
        try:
            ses = fastf1.get_session(year, rnd, ident)
            ses.load(laps=False, telemetry=False, weather=False,
                     messages=False)
            dmap = drivers_of(ses.results)
        except Exception as exc:                       # noqa: BLE001
            print(f"  {ident:<4} unavailable ({type(exc).__name__}: {exc})")
            dmap = {}
        per_session[ident] = dmap
        state = "RUN" if dmap else "not run yet"
        print(f"  {ident:<4} {len(dmap):>2} drivers  [{state}]")

    run = {k: v for k, v in per_session.items() if v}
    chk(1, bool(run), "at least one pre-race session has run")

    rule("[2] THE RULE, APPLIED")
    # Drivers seen AFTER FP1 are in the weekend proper, not a one-off test.
    late: set[str] = set()
    for ident, dmap in per_session.items():
        if ident != "FP1":
            late |= set(dmap)
    in_fp1 = set(per_session.get("FP1", {}))

    entrants: dict[str, str] = {}
    dropped_test: dict[str, str] = {}
    for ident in PRE_RACE_IDENTS:
        for d, team in per_session[ident].items():
            if d in raced or d in late:
                entrants.setdefault(d, team or entrants.get(d, ""))
            else:
                dropped_test.setdefault(d, team)

    print(f"  raced this season          : "
          f"{len([d for d in entrants if d in raced])}")
    print(f"  kept, in a session past FP1: "
          f"{sorted(d for d in entrants if d not in raced)}")
    print(f"  dropped (FP1-only test)    : {sorted(dropped_test)}")
    print()
    print(f"  ENTRANTS ({len(entrants)}): {sorted(entrants)}")

    chk(2, expected is not None and len(entrants) == expected,
        f"entrant count {len(entrants)} equals expected_size {expected}")

    rule("[3] FIELD COMPOSITION - 11 TEAMS x 2 CARS")
    teams: dict[str, list[str]] = {}
    for d, team in entrants.items():
        teams.setdefault(team, []).append(d)
    for team in sorted(teams):
        cars = sorted(teams[team])
        flag = "" if len(cars) == 2 else "   <-- NOT A PAIR"
        print(f"  {team:<24} {len(cars)} car(s): {cars}{flag}")
    pairs = sum(1 for v in teams.values() if len(v) == 2)
    print(f"\n  teams with exactly 2 cars: {pairs} of {len(teams)}")
    chk(3, pairs == len(teams) == 11,
        "every team fields exactly 2 cars (11 teams)")

    rule("[4] CROSS-CHECK AGAINST THE STATED DRIVER CHANGES")
    cam_team = entrants.get("CAM")
    print(f"  CAM  team = {cam_team!r}   "
          f"(expected Haas, replacing HIR)")
    print(f"  HIR  in any pre-race session? "
          f"{'YES' if any('HIR' in v for v in per_session.values()) else 'no'}")
    print(f"  HIR  in entrants? "
          f"{'YES' if 'HIR' in entrants else 'no'}")
    print(f"  BEA  in entrants? "
          f"{'YES' if 'BEA' in entrants else 'no'}  "
          f"(team {entrants.get('BEA')!r})")
    print(f"  the six F2 test drivers excluded: "
          f"{sorted(d for d in dropped_test if d != 'CAM')}")

    chk(4, cam_team is not None and "Haas" in cam_team,
        "CAM is entered with Haas")
    chk(5, "HIR" not in entrants and "HIR" not in
        {d for v in per_session.values() for d in v},
        "HIR is gone - replaced, and absent from every practice session")
    chk(6, "BEA" in entrants and entrants.get("BEA") == cam_team,
        "BEA and CAM are team-mates at Haas")

    rule("[5] WHY THE NAIVE FILTER WOULD HAVE FAILED")
    naive = sorted(d for d in
                   {d for v in per_session.values() for d in v} & raced)
    print(f"  'only drivers who already raced this season' -> "
          f"{len(naive)} cars (short by {expected - len(naive)})")
    print(f"  it drops CAM, who IS racing, and keeps nobody who left.")
    print(f"  'every driver in FP1' -> "
          f"{len(per_session.get('FP1', {}))} cars, of which "
          f"{len(per_session.get('FP1', {})) - len([d for d in per_session.get('FP1', {}) if d in raced or d in late])} "
          f"are F2 rookies who will not race.")
    print(f"  The rule above gets {len(entrants)} because a full-weekend")
    print(f"  entry shows up in FP2, and a one-off test does not.")
    print("  Nothing has been written to f1.db.")

    con.close()
    rule("RESULT")
    if FAILS:
        print(f"  {len(FAILS)} FAILED:")
        for f in FAILS:
            print(f"    - {f}")
        return 1
    print(f"  6 of 6 PASS  - field derived: {len(entrants)} cars, "
          f"{len(teams)} teams")
    return 0


if __name__ == "__main__":
    sys.exit(main())
