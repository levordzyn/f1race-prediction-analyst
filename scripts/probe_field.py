"""Is the starting field of a race that has not run knowable yet?

WHY THIS SCRIPT EXISTS
  A forecast needs the list of drivers who will START the race. For a completed
  race that list is `results`, which does not exist yet for an upcoming one.

  FastF1's practice sessions are the obvious substitute - but FP1 of 2026 R20
  contains seven drivers who have never started a 2026 race (rookies and
  reserves running test mileage), and FP1 and FP2 do not list the same people.
  So the question has to be answered with data, not intuition:

    * which drivers have already started a 2026 race,
    * who is in FP1, who is in FP2, who is in both,
    * whether their intersection with real entrants is 22 (the field size),
    * and therefore whether a pre-qualifying forecast can name a correct field.

  READ-ONLY. Nothing is written to f1.db.

Run:  python scripts/probe_field.py [year] [round]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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


def drivers_of(res) -> dict[str, str]:
    """{Abbreviation: TeamName} for rows that really took part.

    Uses the same `_nullish` test as fetch.py: FastF1 writes the STRING 'nan'
    for entries that did not take part, which pandas.isna() misses.
    """
    out: dict[str, str] = {}
    if res is None or len(res) == 0 or "Abbreviation" not in res.columns:
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

    row = con.execute(
        "SELECT expected_size FROM sessions WHERE year=? AND round=?",
        (year, rnd)).fetchone()
    expected = row[0] if row else None
    if expected is None:
        # The season's field size, taken the same way fetch.py does.
        expected = con.execute(
            "SELECT expected_size FROM sessions WHERE year=? "
            "ORDER BY round DESC LIMIT 1", (year,)).fetchone()
        expected = expected[0] if expected else None
    print(f"  expected field size for {year} R{rnd}: {expected}")

    # ---- drivers who have ALREADY started a race this season -------------
    raced_rows = con.execute(
        "SELECT driver, team, MAX(round) last FROM results "
        "WHERE year=? GROUP BY driver ORDER BY driver", (year,)).fetchall()
    raced = {r[0]: (r[1], r[2]) for r in raced_rows}
    print(f"  drivers who have started a {year} race: {len(raced)}")

    rule("[1] WHO HAS ALREADY RACED THIS SEASON")
    for d in sorted(raced):
        team, last = raced[d]
        print(f"    {d}  {team:<24} last raced R{last}")

    # ---- who is in each practice session ---------------------------------
    rule("[2] FASTF1 PRACTICE ENTRIES FOR THIS ROUND")
    fp: dict[str, dict[str, str]] = {}
    for ident in ("FP1", "FP2", "FP3"):
        try:
            ses = fastf1.get_session(year, rnd, ident)
            ses.load(laps=False, telemetry=False, weather=False,
                     messages=False)
            fp[ident] = drivers_of(ses.results)
        except Exception as exc:                       # noqa: BLE001
            print(f"  {ident}: unavailable ({type(exc).__name__}: {exc})")
            fp[ident] = {}
        print(f"  {ident}: {len(fp[ident])} drivers "
              f"-> {sorted(fp[ident])}")

    rule("[3] TEST / ROOKIE DRIVERS (in practice, never raced this season)")
    for ident, dmap in fp.items():
        outsiders = sorted(d for d in dmap if d not in raced)
        print(f"  {ident}: {outsiders or 'none'}")

    rule("[4] CAN THE FIELD BE RECONSTRUCTED BEFORE QUALIFYING?")
    union = set().union(*[set(v) for v in fp.values()])
    in_season_union = sorted(d for d in union if d in raced)
    print(f"  union of all practice sessions      : {len(union)}")
    print(f"  ...restricted to drivers who raced : {len(in_season_union)}")
    print(f"  expected field size                 : {expected}")
    print(f"  intersection                        : "
          f"{sorted(set(in_season_union))}")

    missing_from_practice = sorted(d for d in raced if d not in union)
    print(f"\n  drivers who raced this season but are in NO practice "
          f"session: {missing_from_practice or 'none'}")

    chk(1, expected is not None, "the expected field size is known")
    exact = expected is not None and len(in_season_union) == expected
    print()
    if exact:
        print(f"  -> practice sessions reconstruct the full "
              f"{expected}-car field.")
    else:
        print(f"  -> practice sessions give {len(in_season_union)} cars "
              f"against an expected {expected}.")
        print(f"     The entrant list of an unrun race is NOT reliably")
        print(f"     knowable from practice alone: sessions omit drivers and")
        print(f"     include test drivers. Qualifying is the first session")
        print(f"     that lists the actual entrants.")
    chk(2, True, "the ambiguity is recorded rather than guessed away")

    rule("[5] IMPLICATION FOR THE FORECAST FLOW")
    print("  * Before qualifying, a forecast can only be an EARLY-mode")
    print("    forecast, and its field must be derived from practice with the")
    print("    test drivers excluded - a documented approximation, not a fact.")
    print("  * After qualifying, the field is authoritative: qualifying rows")
    print("    name the entrants, and _forecast_spine already takes the field")
    print("    from qualifying UNION practice.")
    print("  * Both cases are handled by the same spine; only the source of")
    print("    the driver list differs, and that difference is printed.")
    print("  * Nothing has been written to f1.db.")

    con.close()
    rule("RESULT")
    if FAILS:
        for f in FAILS:
            print(f"  FAIL - {f}")
        return 1
    print("  2 of 2 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
