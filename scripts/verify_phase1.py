"""Pre-build verification for Phase 1 (your four checks).

  1. match OpenF1 sessions to FastF1 races by date + session type,
     and check driver counts (22 for 2026, 20 for 2023-2025)
  2. map driver_number -> name_acronym via /drivers and confirm it equals
     FastF1's Abbreviation (FastF1: DriverNumber -> Abbreviation)
  3. best practice lap per driver from lap_duration, excluding null laps and
     is_pit_out_lap; also count laps per driver
  4. sprint weekends: confirm only one practice session (Practice 1) and that
     sprint qualifying exists; record where practice data is absent

Run:  python scripts/verify_phase1.py            (all four)
      python scripts/verify_phase1.py --check 2  (one check)

Nothing here writes to f1.db - this is read-only reconnaissance.
"""
from __future__ import annotations

import argparse
import logging
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import fastf1
from f1pred import httpcache, openf1 as o1

YEARS = (2023, 2024, 2025, 2026)
EXPECTED_FIELD_SIZE = {2026: 22, 2025: 20, 2024: 20, 2023: 20}
SPRINT_FORMAT = "sprint_qualifying"

Path("f1_cache").mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logging.getLogger("fastf1").setLevel(logging.ERROR)
pd.set_option("display.width", 220)


def _d(value) -> datetime:
    """Session date_start / EventDate -> naive UTC date."""
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.to_pydatetime()


def load_fastf1_races(year: int) -> dict[int, dict]:
    """{round: info} for races already run, with loaded race results."""
    sched = fastf1.get_event_schedule(year, include_testing=False)
    out: dict[int, dict] = {}
    for _, ev in sched.iterrows():
        rnd = int(ev["RoundNumber"])
        if _d(ev["EventDate"]) > datetime.now(timezone.utc).replace(tzinfo=None):
            continue
        try:
            ses = fastf1.get_session(year, rnd, "R")
            ses.load(laps=False, telemetry=False, weather=False, messages=False)
            res = ses.results
        except Exception as exc:                       # noqa: BLE001 - log & skip
            print(f"  [FastF1] skip {year} R{rnd}: {type(exc).__name__}: {exc}")
            continue
        out[rnd] = {
            "event": str(ev["EventName"]),
            "format": str(ev["EventFormat"]),
            "date": _d(ev["EventDate"]),
            "results": res,
            "sched_row": ev,
        }
    return out


def fastf1_sessions_of(ev_row) -> list[str]:
    """Session1..Session5 names from the schedule row (order preserved)."""
    return [str(ev_row[f"Session{i}"]) for i in range(1, 6)
            if f"Session{i}" in ev_row and pd.notna(ev_row[f"Session{i}"])]


# --------------------------------------------------------------------- check 1
def check1(years, verbose: bool = True) -> dict[tuple[int, int], dict]:
    """Match OpenF1 race sessions to FastF1 races by date; verify driver counts.

    Always loads the data - checks 2-4 need ``matched`` - but only reports
    when ``verbose`` is set.
    """
    print("=" * 78)
    print("CHECK 1  OpenF1 <-> FastF1 race matching, by date and session type")
    print("=" * 78)
    if not verbose:
        print("(quiet: loading matched races for checks 2-4)")

    matched: dict[tuple[int, int], dict] = {}
    problems: list[str] = []

    def say(*args) -> None:
        if verbose:
            print(*args)

    for year in years:
        f1 = load_fastf1_races(year)
        sessions = [s for s in o1.get_sessions(year)
                    if s.get("session_type") == "Race" and s.get("session_name") == "Race"]
        say(f"\n{year}: FastF1 races={len(f1)}  OpenF1 race sessions={len(sessions)}")

        used: set[int] = set()
        for rnd, info in sorted(f1.items()):
            # match on race date, allowing +-1 day for local/UTC date shift
            cands = [s for s in sessions
                     if id(s) not in used
                     and abs((_d(s["date_start"]).date() - info["date"].date()).days) <= 1]
            if not cands:
                problems.append(f"{year} R{rnd} {info['event']}: NO OpenF1 race session "
                                f"(FastF1 date {info['date'].date()})")
                continue
            ses = min(cands, key=lambda s: abs(
                (_d(s["date_start"]).date() - info["date"].date()).days))
            used.add(id(ses))

            o1_drivers = o1.get_drivers(ses["session_key"])
            f1_res = info["results"]
            n_o1, n_f1 = len(o1_drivers), len(f1_res)
            expected = EXPECTED_FIELD_SIZE[year]

            flag = ""
            if n_o1 != n_f1:
                flag = f"  <-- COUNT MISMATCH (OpenF1 {n_o1} vs FastF1 {n_f1})"
                problems.append(f"{year} R{rnd}: driver count OpenF1={n_o1} FastF1={n_f1} "
                                f"(expected {expected})")
            elif n_o1 != expected:
                flag = f"  <-- FIELD SIZE {n_o1} != {expected}"
                problems.append(f"{year} R{rnd}: field size {n_o1} != expected {expected}")

            matched[(year, rnd)] = {
                "event": info["event"], "format": info["format"],
                "session_key": ses["session_key"], "meeting_key": ses["meeting_key"],
                "o1_date": _d(ses["date_start"]), "f1_date": info["date"],
                "o1_drivers": o1_drivers, "f1_results": f1_res,
                "n_o1": n_o1, "n_f1": n_f1, "expected": expected,
                "sessions": fastf1_sessions_of(info["sched_row"]),
            }
            if flag:
                say(f"  R{rnd:<3} {info['event'][:34]:<34} O1={n_o1:<3} F1={n_f1:<3}{flag}")

        matched_this = sum(1 for k in matched if k[0] == year)
        unmatched = len(f1) - matched_this
        say(f"  -> {matched_this}/{len(f1)} matched, {unmatched} unmatched, "
            f"{len(sessions) - len(used)} OpenF1 race sessions unused")

    # date agreement summary
    deltas = [(k, abs((m["o1_date"].date() - m["f1_date"].date()).days))
              for k, m in matched.items()]
    exact = sum(1 for _, dd in deltas if dd == 0)
    say(f"\n  date agreement: {exact}/{len(deltas)} exact, "
        f"{len(deltas) - exact} within +-1 day")
    say(f"  driver counts: {sum(1 for m in matched.values() if m['n_o1'] == m['n_f1'])}"
        f"/{len(matched)} OpenF1 == FastF1")

    if not verbose:
        return matched

    if problems:
        print(f"\n  !! {len(problems)} problem(s):")
        for p in problems:
            print("     -", p)
    else:
        print("\n  OK: every race matched, every driver count as expected")
    return matched


# --------------------------------------------------------------------- check 2
def check2(matched) -> None:
    print("\n" + "=" * 78)
    print("CHECK 2  driver_number -> name_acronym vs FastF1 Abbreviation")
    print("=" * 78)

    total_pairs = 0
    mismatches: list[str] = []
    missing_in_o1: list[str] = []
    missing_in_f1: list[str] = []
    unknown_numbers: list[str] = []

    for (year, rnd), m in sorted(matched.items()):
        # OpenF1: driver_number -> name_acronym
        o1_map = {d["driver_number"]: d.get("name_acronym")
                  for d in m["o1_drivers"] if d.get("driver_number") is not None}
        # FastF1: DriverNumber -> Abbreviation
        res = m["f1_results"]
        if "DriverNumber" not in res.columns:
            unknown_numbers.append(f"{year} R{rnd}: FastF1 results have no DriverNumber")
            continue
        f1_map = {}
        for _, r in res.iterrows():
            num = r.get("DriverNumber")
            if pd.isna(num):
                continue
            f1_map[int(num)] = str(r["Abbreviation"])

        for num, f1_abbr in f1_map.items():
            total_pairs += 1
            o1_abbr = o1_map.get(num)
            if o1_abbr is None:
                missing_in_o1.append(f"{year} R{rnd}: FastF1 {f1_abbr}(#{num}) not in OpenF1 /drivers")
            elif o1_abbr != f1_abbr:
                mismatches.append(f"{year} R{rnd}: #{num} OpenF1={o1_abbr} FastF1={f1_abbr}")

        for num, o1_abbr in o1_map.items():
            if num not in f1_map:
                missing_in_f1.append(f"{year} R{rnd}: OpenF1 {o1_abbr}(#{num}) not in FastF1 results")

    print(f"  compared {total_pairs} driver/race pairs across {len(matched)} races")
    print(f"  abbreviation mismatches : {len(mismatches)}")
    print(f"  in FastF1 not in OpenF1  : {len(missing_in_o1)}")
    print(f"  in OpenF1 not in FastF1  : {len(missing_in_f1)}")
    print(f"  FastF1 lacks DriverNumber: {len(unknown_numbers)}")

    for label, items in (("MISMATCH", mismatches),
                         ("missing in OpenF1", missing_in_o1),
                         ("missing in FastF1", missing_in_f1),
                         ("no DriverNumber", unknown_numbers)):
        if items:
            print(f"\n  {label} ({len(items)}), first 12:")
            for it in items[:12]:
                print("     -", it)

    if not (mismatches or missing_in_o1 or missing_in_f1 or unknown_numbers):
        print("\n  OK: driver_number -> name_acronym matches FastF1 Abbreviation everywhere")
    else:
        print("\n  => join on driver_number is NOT safe by itself; "
              "verify the exceptions above before relying on it")


# --------------------------------------------------------------------- check 3
def check3(matched) -> dict:
    print("\n" + "=" * 78)
    print("CHECK 3  best practice lap (lap_duration, excl. null + pit-out) + lap counts")
    print("=" * 78)

    per_race = {}
    no_practice: list[str] = []
    drivers_without_best: list[str] = []
    lap_counts: list[int] = []
    all_have = 0

    for (year, rnd), m in sorted(matched.items()):
        sessions = m["sessions"]
        # last practice of the weekend: FP3 if present, else FP1 (sprint weekend)
        practice_names = [s for s in sessions if s in o1.PRACTICE_SESSION_NAMES]
        if not practice_names:
            no_practice.append(f"{year} R{rnd} {m['event']}: FastF1 schedule has no practice")
            continue
        chosen_name = practice_names[-1]     # FP3 for conventional, FP1 for sprint
        o1_sessions = o1.get_sessions(year)
        cand = [s for s in o1_sessions
                if s.get("meeting_key") == m["meeting_key"]
                and s.get("session_name") == chosen_name
                and s.get("session_type") == "Practice"]
        if not cand:
            no_practice.append(f"{year} R{rnd} {m['event']}: OpenF1 has no '{chosen_name}'")
            continue

        laps = o1.get_laps(cand[0]["session_key"])
        best = o1.best_practice_laps(laps)

        # every driver who raced should be considered
        raced = [int(r["DriverNumber"]) for _, r in m["f1_results"].iterrows()
                 if pd.notna(r.get("DriverNumber"))]
        without = [n for n in raced
                   if n not in best or best[n]["best_lap_s"] is None]
        if without:
            abbr = {int(r["DriverNumber"]): str(r["Abbreviation"])
                    for _, r in m["f1_results"].iterrows() if pd.notna(r.get("DriverNumber"))}
            drivers_without_best.append(
                f"{year} R{rnd} {chosen_name}: no valid practice lap for "
                + ", ".join(abbr.get(n, f"#{n}") for n in without))

        counts = [v["lap_count"] for v in best.values()]
        lap_counts.extend(counts)
        if not without:
            all_have += 1

        per_race[(year, rnd)] = {
            "session_name": chosen_name, "session_key": cand[0]["session_key"],
            "best": best, "raced": raced, "without": without,
            "n_laps_rows": len(laps),
        }

    print(f"  practice sessions resolved: {len(per_race)}/{len(matched)}")
    print(f"  races where every racer has a valid best lap: {all_have}/{len(per_race)}")
    if lap_counts:
        print(f"  laps per driver: min={min(lap_counts)} median={statistics.median(lap_counts):.0f} "
              f"max={max(lap_counts)} (n={len(lap_counts)} drivers)")
    print(f"  drivers with NO valid practice lap: {len(drivers_without_best)} "
          f"across {len(per_race) - all_have} races -> missing flag is required")

    if no_practice:
        print(f"\n  practice session not found ({len(no_practice)}):")
        for it in no_practice:
            print("     -", it)
    if drivers_without_best:
        print(f"\n  drivers missing a practice time ({len(drivers_without_best)} races), first 15:")
        for it in drivers_without_best[:15]:
            print("     -", it)
    if not no_practice and not drivers_without_best:
        print("\n  OK: practice data present for every driver in every race")
    return per_race


# --------------------------------------------------------------------- check 4
def check4(matched) -> None:
    print("\n" + "=" * 78)
    print("CHECK 4  sprint weekends: single practice + sprint qualifying present")
    print("=" * 78)

    sprint = {k: m for k, m in matched.items() if m["format"] == SPRINT_FORMAT}
    conv = {k: m for k, m in matched.items() if m["format"] != SPRINT_FORMAT}
    print(f"  sprint weekends: {len(sprint)}   conventional: {len(conv)}")

    problems: list[str] = []
    practice_counts: dict[int, int] = defaultdict(int)
    sq_present = 0
    sq_missing: list[str] = []

    for (year, rnd), m in sorted(sprint.items()):
        names = m["sessions"]
        pr = [n for n in names if n in o1.PRACTICE_SESSION_NAMES]
        practice_counts[len(pr)] += 1
        if len(pr) != 1:
            problems.append(f"{year} R{rnd}: {len(pr)} practice sessions {pr} (expected 1)")

        # sprint qualifying appears in FastF1 schedule slots?
        has_sq = any("Sprint Qualifying" in n or n == "Sprint Shootout" for n in names)
        if has_sq:
            sq_present += 1
        else:
            sq_missing.append(f"{year} R{rnd} {m['event']}: schedule slots={names}")

        # and does OpenF1 actually carry it?
        o1_names = {s.get("session_name")
                    for s in o1.get_sessions(year)
                    if s.get("meeting_key") == m["meeting_key"]}
        if not any(n in o1_names for n in ("Sprint Qualifying", "Sprint Shootout")):
            problems.append(f"{year} R{rnd}: OpenF1 meeting lacks Sprint Qualifying "
                            f"(has {sorted(o1_names)})")
        if "Sprint" not in o1_names:
            problems.append(f"{year} R{rnd}: OpenF1 meeting lacks Sprint race session")

    print(f"  practice-session counts on sprint weekends: {dict(practice_counts)}")
    print(f"  sprint qualifying in FastF1 schedule: {sq_present}/{len(sprint)}")

    # conventional weekends should have 3 practices
    conv_counts: dict[int, int] = defaultdict(int)
    for (year, rnd), m in conv.items():
        conv_counts[len([n for n in m["sessions"] if n in o1.PRACTICE_SESSION_NAMES])] += 1
    print(f"  practice-session counts on conventional weekends: {dict(conv_counts)}")

    # one worked example
    if sprint:
        (year, rnd), m = sorted(sprint.items())[0]
        print(f"\n  example sprint weekend {year} R{rnd} {m['event']}:")
        print(f"    FastF1 schedule slots: {m['sessions']}")
        rows = [(s.get("session_name"), s.get("session_type"), s["session_key"])
                for s in o1.get_sessions(year) if s.get("meeting_key") == m["meeting_key"]]
        for nm, ty, key in sorted(rows):
            print(f"    OpenF1: {nm:<20} type={ty:<12} key={key}")

    for label, items in (("PROBLEM", problems), ("no sprint qualifying", sq_missing)):
        if items:
            print(f"\n  {label} ({len(items)}):")
            for it in items[:20]:
                print("     -", it)
    if not problems and not sq_missing:
        print("\n  OK: every sprint weekend has exactly one practice and a sprint qualifying")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", type=int, choices=(1, 2, 3, 4), default=0)
    ap.add_argument("--years", type=int, nargs="+", default=list(YEARS))
    args = ap.parse_args()

    print(f"OpenF1 base       : {httpcache.BASE_URL}")
    print(f"OpenF1 cache      : {httpcache.DEFAULT_CACHE_DIR} "
          f"({len(list(httpcache.DEFAULT_CACHE_DIR.glob('*.json')))} entries before run)")
    print(f"rate spacing      : {httpcache.current_spacing()}s "
          f"(raises automatically on first HTTP 429)")
    print(f"years             : {args.years}\n")

    matched = check1(args.years, verbose=(args.check in (0, 1)))
    if args.check in (0, 2):
        check2(matched)
    if args.check in (0, 3):
        check3(matched)
    if args.check in (0, 4):
        check4(matched)

    print(f"\nrate spacing at end: {httpcache.current_spacing()}s")
    print(f"OpenF1 cache now   : {len(list(httpcache.DEFAULT_CACHE_DIR.glob('*.json')))} entries")
    print("NOTE: no HTTP 429 observed" if httpcache.current_spacing() == httpcache.MIN_INTERVAL_S
          else "NOTE: HTTP 429 observed, spacing was raised (backoff works)")


if __name__ == "__main__":
    main()
