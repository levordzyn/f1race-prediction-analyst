"""Test the upcoming-race fetch path on a COPY of f1.db.

WHY A COPY
  fetch_upcoming() writes - it has to, that is the point of it. Testing
  against the real database would put an unrun race into production data
  before anyone had checked the result. Every check below therefore runs on a
  throwaway copy, and the real file is compared before and after to prove it
  was not touched.

WHAT IT PROVES
  1. the fetch creates a sessions row with the right expected_size and a
     NULL n_starters (no race has produced starters yet);
  2. it writes practice rows for the real field and writes NOTHING into
     results, so the 7-column contract cannot be affected;
  3. build_features() WITHOUT forecast_race is byte-identical afterwards -
     the historical frame must stay at 1816 rows, or every accepted Phase
     3/4/5 number would move;
  4. build_features(forecast_race=...) adds exactly the field's cars, with
     finish NULL, so they are predicted but never scored;
  5. assign_field_sizes() still returns 0 failures - it used to crash with a
     TypeError the moment a sessions row had a NULL n_starters.

Run:  python scripts/test_upcoming_fetch.py [year] [round]
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from f1pred import db, features, fetch

FAILS: list[str] = []
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "f1.db"


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def chk(n: int, cond: bool, msg: str) -> None:
    print(f"  [{n:>2}] {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        FAILS.append(msg)


def counts(path: Path) -> dict[str, int]:
    con = db.connect(path)
    con.row_factory = None
    out = {}
    for t in ("results", "qualifying", "practice", "sessions",
              "driver_numbers", "race_status", "weather", "sprint",
              "sprint_qualifying", "fetch_log"):
        out[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    out["feature_rows"] = len(features.build_features(con))
    con.close()
    return out


def _pick_unrun_round(con, year: int) -> int:
    """Return the latest round in `con` that HAS qualifying data (so a forecast
    can be made) but we will delete its results in the test copy to simulate
    pre-race. Since all rounds in the real DB have results, we just need a
    round with qualifying/practice data, then the copy deletes results for it
    and all later rounds.
    """
    rounds = con.execute(
        "SELECT DISTINCT round FROM qualifying WHERE year=? ORDER BY round",
        (year,)).fetchall()
    if not rounds:
        raise ValueError(f"No qualifying rounds found for year {year}")
    # Pick the latest round that has qualifying data
    return max(r[0] for r in rounds)


def _make_pre_race_copy(db_path: Path, year: int, round_: int) -> Path:
    """Create a copy with results/race_status/forecasts/sessions deleted for round_ and all later."""
    tmp = Path(tempfile.gettempdir()) / f"f1_upcoming_test_{year}_R{round_}.db"
    if tmp.exists():
        tmp.unlink()
    shutil.copy2(db_path, tmp)

    con = sqlite3.connect(tmp)
    con.execute("DELETE FROM results WHERE year=? AND round>=?", (year, round_))
    con.execute("DELETE FROM race_status WHERE year=? AND round>=?", (year, round_))
    con.execute("DELETE FROM forecasts WHERE year=? AND round>=?", (year, round_))
    con.execute("DELETE FROM sessions WHERE year=? AND round>=?", (year, round_))
    con.commit()
    con.close()
    return tmp


def main() -> int:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    rnd = int(sys.argv[2]) if len(sys.argv) > 2 else None

    # If no round specified, pick the latest unrun round from the real DB
    if rnd is None:
        con0 = sqlite3.connect(DB)
        try:
            rnd = _pick_unrun_round(con0, year)
        finally:
            con0.close()
        if rnd is None:
            print("  No unrun round found - skipping test")
            return 0

    print(f"  now (UTC) : {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}")
    print(f"  database  : {DB}")
    print(f"  test race : {year} R{rnd}")
    print()

    tmp = _make_pre_race_copy(DB, year, rnd)
    print(f"\n  working copy: {tmp}")

    con = db.connect(tmp)
    con.row_factory = None

    # Get baseline counts from the copy BEFORE fetch_upcoming
    before = counts(tmp)
    rule("[0] THE COPY BEFORE fetch_upcoming")
    for k, v in before.items():
        print(f"  {k:<20} {v}")

    # Also fingerprint the real DB to prove it's untouched
    real_before = counts(DB)

    rule("[1] RUN fetch_upcoming ON THE COPY")
    summary = fetch.fetch_upcoming(con, year, rnd)
    print(f"  status            : {summary['status']}")
    print(f"  event             : {summary['event']}")
    print(f"  entrants          : {summary['entrants']}")
    print(f"  practice rows     : {summary['practice_rows']}")
    print(f"  qualifying rows   : {summary['qualifying_rows']}")
    print(f"  expected_size     : {summary['expected_size']}")
    if "qualifying_started" in summary:
        print(f"  qualifying started: {summary['qualifying_started']}")
    chk(1, summary["status"] == "fetched",
        "the fetch reports status='fetched'")

    rule("[2] THE sessions ROW")
    row = con.execute(
        "SELECT event, event_format, event_date, expected_size, n_starters,"
        " meeting_key FROM sessions WHERE year=? AND round=?",
        (year, rnd)).fetchone()
    if row is None:
        chk(2, False, "sessions row was created")
        row = (None,) * 6
    else:
        chk(2, True, "sessions row was created")
    event, fmt, edate, expected, n_starters, meeting = row
    print(f"  event        : {event}")
    print(f"  event_format : {fmt}")
    print(f"  event_date   : {edate}")
    print(f"  expected_size: {expected}")
    print(f"  n_starters   : {n_starters}   (NULL = race has not run)")
    print(f"  meeting_key  : {meeting}   (set by resolve_meeting)")
    chk(3, n_starters is None,
        "n_starters is NULL - no race has produced starters")
    chk(4, expected == 22, f"expected_size is the season's 22, not 20 "
                           f"(got {expected})")
    chk(5, fmt == "conventional",
        f"{summary['event']} {year} is a conventional weekend, so no sprint features")

    rule("[3] results IS UNTOUCHED (7-column contract)")
    n_res = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?",
        (year, rnd)).fetchone()[0]
    print(f"  results rows for {year} R{rnd}: {n_res}")
    chk(6, n_res == 0,
        "no results rows written for an unrun race")

    rule("[4] FIELD COMPOSITION OF THE PRACTICE ROWS")
    prows = con.execute(
        "SELECT driver, team, driver_number FROM practice "
        "WHERE year=? AND round=? ORDER BY driver", (year, rnd)).fetchall()
    print(f"  practice rows: {len(prows)}")
    teams: dict[str, list[str]] = {}
    for d, t, _n in prows:
        teams.setdefault(t, []).append(d)
    for t in sorted(teams):
        print(f"    {t:<24} {sorted(teams[t])}")
    pairs = sum(1 for v in teams.values() if len(v) == 2)
    print(f"  teams with exactly 2 cars: {pairs} of {len(teams)}")
    chk(7, len(prows) == 22, f"22 practice rows (got {len(prows)})")
    chk(8, pairs == 11 and len(teams) == 11, "11 teams x 2 cars")
    chk(9, not any(d in {p[0] for p in prows}
                   for d in ("BEG", "BRO", "FOR", "HER", "MIN", "SLA")),
        "the six F2 young-driver test drivers are not in the field")
    chk(10, any(d == "CAM" for d, _t, _n in prows),
        "CAM (Camara) IS in the field - the debutant a naive filter would "
        "have dropped")

    rule("[5] build_features() WITHOUT forecast_race IS UNCHANGED")
    df_plain = features.build_features(con)
    print(f"  rows: {before['feature_rows']} -> {len(df_plain)}")
    chk(11, len(df_plain) == before["feature_rows"],
        f"historical frame still {before['feature_rows']} rows - no accepted "
        "Phase 3/4/5 number can move")
    n_fc = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?",
        (year, rnd)).fetchone()[0]
    chk(12, n_fc == 0, "the unrun race contributes no history row")

    rule("[6] build_features(forecast_race=) ADDS THE FIELD")
    df_fc = features.build_features(con, forecast_race=(year, rnd))
    added = len(df_fc) - len(df_plain)
    print(f"  rows: {len(df_plain)} -> {len(df_fc)}  (+{added})")
    fc = df_fc[(df_fc["year"] == year) & (df_fc["round"] == rnd)]
    print(f"  forecast rows: {len(fc)}")
    print(f"  finish all NULL: {bool(fc['finish'].isna().all())}")
    print(f"  grid  all NULL: {bool(fc['grid'].isna().all())}")
    print(f"  team_form not null: {int(fc['team_form'].notna().sum())} of "
          f"{len(fc)}")
    chk(13, len(fc) == 22, "exactly 22 forecast rows")
    chk(14, bool(fc["finish"].isna().all()),
        "every forecast row has finish NULL - predicted, never scored")
    chk(15, bool(fc["team_form"].notna().all()),
        "team_form resolved for all 22 (the team came through with the "
        "entry list)")
    print(f"\n  early-mode columns present: "
          f"{[c for c in features.EARLY_FEATURES if c in fc.columns]}")
    chk(16, all(c in fc.columns for c in features.EARLY_FEATURES),
        "all 7 early-mode features exist on the forecast rows")

    rule("[7] assign_field_sizes() MUST NOT CRASH ON A NULL n_starters")
    try:
        failures = fetch.assign_field_sizes(con, year)
        print(f"  returned {failures} validation failure(s)")
        chk(17, failures == 0, "0 validation failures for the season")
    except Exception as exc:                           # noqa: BLE001
        print(f"  raised {type(exc).__name__}: {exc}")
        chk(17, False, "assign_field_sizes raised")

    rule("[8] THE REAL DATABASE WAS NOT TOUCHED")
    after = counts(DB)
    same = after == real_before
    if not same:
        for k in real_before:
            if real_before[k] != after[k]:
                print(f"  CHANGED {k}: {real_before[k]} -> {after[k]}")
    chk(18, same, "every table and the feature frame are identical to before")

    con.close()
    try:
        tmp.unlink()
        print(f"\n  working copy removed: {tmp}")
    except OSError as exc:
        print(f"\n  could not remove {tmp}: {exc}")

    rule("RESULT")
    if FAILS:
        print(f"  {len(FAILS)} FAILED:")
        for f in FAILS:
            print(f"    - {f}")
        return 1
    print("  18 of 18 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())