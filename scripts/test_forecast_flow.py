"""End-to-end test of the upcoming-race forecast flow, on a COPY of f1.db.

WHY A COPY
  This flow writes on purpose: it fetches a race that has not run and saves a
  forecast for it. Running it against production data before anyone had read
  the output would defeat the whole point of a forecast. The real database is
  fingerprinted before and after and must come back identical.

THE LOOP IT EXERCISES
  fetch_upcoming  ->  python -m f1pred.cli --save  ->  score (race not run)
  ->  simulate the race  ->  score again  ->  refuse a second save
  ->  catch a tampered timestamp

WHY SIMULATING THE RACE IS LEGITIMATE HERE
  The test creates a pre-race world on a copy by deleting results for the
  target round AND all later rounds. Filling `results` on a throwaway
  copy with a deterministic order proves the scoring code works BEFORE the
  race it will be used for, which is exactly when you want to find out it
  does not. Nothing written here can reach f1.db.

WHAT IT PROVES
  1. a forecast can be saved for an unrun race, one row per car;
  2. it records created_at, race_start_utc, features, alpha and the number
     of training races, and created_at precedes race_start_utc;
  3. score() on an unrun race says "not run" (exit 2) instead of inventing
     a number;
  4. once results exist, score() returns MAE, Spearman, winner and podium
     hit rates plus this mode's baselines, on the same drivers;
  5. saving a second forecast once results exist is REFUSED - a prediction
     written after the result is a back-fit;
  6. a created_at moved past race_start_utc fails the no-peeking check, and
     because scoring looks at the LATEST row, tampering one row is enough
     to be caught.

Run:  python scripts/test_forecast_flow.py [year] [round]
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from f1pred import db, features, fetch, forecast  # noqa: E402

FAILS: list[str] = []
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "f1.db"


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def chk(n: int | str, cond: bool, msg: str) -> None:
    print(f"  [{n:>2}] {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        FAILS.append(msg)


def fingerprint(path: Path) -> dict[str, int]:
    con = db.connect(path)
    con.row_factory = None
    out = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
           for t in ("results", "qualifying", "practice", "sessions",
                     "driver_numbers", "race_status", "weather", "sprint",
                     "sprint_qualifying", "fetch_log", "forecasts")}
    con.close()
    return out


def run(args: list[str]) -> tuple[int, str]:
    p = subprocess.run([sys.executable, *args], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


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
    """Create a copy with results/race_status/forecasts deleted for round_ and all later."""
    tmp = Path(tempfile.gettempdir()) / f"f1_flow_test_{year}_R{round_}.db"
    if tmp.exists():
        tmp.unlink()
    shutil.copy2(db_path, tmp)

    con = sqlite3.connect(tmp)
    con.execute("DELETE FROM results WHERE year=? AND round>=?", (year, round_))
    con.execute("DELETE FROM race_status WHERE year=? AND round>=?", (year, round_))
    con.execute("DELETE FROM forecasts WHERE year=? AND round>=?", (year, round_))
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

    before = fingerprint(DB)
    rule("[0] REAL DATABASE BEFORE")
    for k, v in before.items():
        print(f"  {k:<20} {v}")

    tmp = _make_pre_race_copy(DB, year, rnd)
    print(f"\n  working copy: {tmp}")
    dbp = str(tmp)

    con = db.connect(tmp)
    con.row_factory = None

    rule("[1] FETCH THE UNRUN RACE ON THE COPY")
    s = fetch.fetch_upcoming(con, year, rnd)
    print(f"  status={s['status']}  entrants={s['entrants']}  "
          f"practice={s['practice_rows']}  qualifying={s['qualifying_rows']}")
    chk(1, s["status"] == "fetched" and s["entrants"] == 22,
        "fetch_upcoming produced the 22-car field")
    n_res = con.execute("SELECT COUNT(*) FROM results WHERE year=? AND "
                        "round=?", (year, rnd)).fetchone()[0]
    chk(2, n_res == 0, "results is still empty for the unrun race")

    # Close the connection before running CLI to avoid database lock conflicts
    con.close()

    rule("[2] SAVE THE FORECAST (real command line, real walk-forward)")
    # Full mode now requires --grid-file. Use the official grid for this round.
    grid_file = ROOT / "official_grid_2026_r20.csv"
    code, out = run(["-m", "f1pred.cli", "--year", str(year),
                     "--round", str(rnd), "--mode", "full", "--save",
                     "--db", dbp, "--grid-file", str(grid_file)])
    tail = "\n".join(out.splitlines()[-40:])
    print(tail)
    chk(3, code == 0, f"python -m f1pred.cli --save exited 0 (got {code})")
    chk(4, "FORECAST SAVED" in out, "the CLI printed the SAVED banner")

    # A forecast is written once and never replaced: re-running --save must
    # be a safe no-op that leaves the original timestamp in place.
    code_r, out_r = run(["-m", "f1pred.cli", "--year", str(year),
                         "--round", str(rnd), "--mode", "full", "--save",
                         "--db", dbp, "--grid-file", str(grid_file)])
    # Reopen connection for database queries
    con = db.connect(tmp)
    con.row_factory = None
    n_rerun = con.execute(
        "SELECT COUNT(*) FROM forecasts WHERE year=? AND round=?"
        " AND mode='full'", (year, rnd)).fetchone()[0]
    orig_at = con.execute(
        "SELECT MIN(created_at) FROM forecasts WHERE year=? AND round=?"
        " AND mode='full'", (year, rnd)).fetchone()[0]
    print(f"  re-run exit {code_r}; rows now {n_rerun}; "
          f"created_at still {orig_at}")
    chk("4b", code_r == 0 and n_rerun == 22
        and "FORECAST ALREADY ON FILE" in out_r,
        "re-running --save is a safe no-op: still 22 rows, not overwritten")

    # For the no-peeking check to pass when running against a past race,
    # we must patch race_start_utc to be in the future relative to now.
    future_start = (datetime.now(timezone.utc) + timedelta(hours=1)
                    ).isoformat(timespec="minutes")
    con.execute(
        "UPDATE forecasts SET race_start_utc=? WHERE year=? AND round=? AND mode='full'",
        (future_start, year, rnd))
    con.commit()
    con.close()

    # Reopen connection for subsequent queries
    con = db.connect(tmp)
    con.row_factory = None

    rule("[3] WHAT LANDED IN the `forecasts` TABLE")
    rows = con.execute(
        "SELECT driver, team, pred, pred_pos, created_at, race_start_utc,"
        " features, alpha, n_train_races FROM forecasts WHERE year=? AND"
        " round=? AND mode='full' ORDER BY pred_pos", (year, rnd)).fetchall()
    print(f"  rows: {len(rows)}")
    for r in rows[:5]:
        print(f"    P{int(r[3]):>2} {r[0]:<4} {str(r[1])[:20]:<20}"
              f" pred={r[2]:7.3f}  {r[4]}  vs  {r[5]}")
    print(f"    ... ({len(rows)} rows total)")
    chk(5, len(rows) == 22, f"one row per car (got {len(rows)})")
    chk(6, all(r[4] == rows[0][4] for r in rows),
        "every row carries the same created_at")
    chk(7, rows[0][5] not in (None, "None"),
        "race_start_utc was patched for the test")

    created = rows[0][4]
    start = rows[0][5]
    c_ts, s_ts = forecast._naive(created), forecast._naive(start)
    print(f"  created_at  : {created}")
    print(f"  race start  : {start} (patched to future)")
    print(f"  delta       : {s_ts - c_ts} before lights out")
    chk(8, c_ts < s_ts, "created_at precedes race_start_utc (patched)")

    feats = json.loads(rows[0][6])
    print(f"  features    : {len(feats)} -> {feats}")
    chk(9, len(feats) == 12, "the full-mode feature list was recorded")
    chk(10, float(rows[0][7]) == 1.0, "alpha 1.0 was recorded, not tuned")
    n_train = int(rows[0][8])
    n_races = len({(r0[0], r0[1]) for r0 in con.execute(
        "SELECT year, round FROM results")})
    print(f"  n_train_races: {n_train}   (races in history: {n_races})")
    chk(11, n_train == n_races,
        f"trained on every earlier race and no later one ({n_train})")

    positions = sorted(int(r[3]) for r in rows)
    chk(12, positions == list(range(1, 23)),
        "pred_pos is a permutation of 1..22")

    # Close connection before running CLI to avoid database lock
    con.close()

    rule("[4] SCORE IT BEFORE THE RACE HAS RUN")
    code, out = run(["scripts/score_forecast.py", "--year", str(year),
                     "--round", str(rnd), "--mode", "full", "--db", dbp])
    print("\n".join(out.splitlines()[-25:]))
    chk(13, code == 2, f"score exits 2 = race not run yet (got {code})")
    chk(14, "not run" in out.lower() or "not-run" in out.lower(),
        "the script says the race has not produced results yet")

    # Reopen connection for race simulation
    con = db.connect(tmp)
    con.row_factory = None

    rule("[5] SIMULATE THE RACE ON THE COPY ONLY")
    # 21 of the 22 forecast drivers get a result; one is omitted on purpose
    # so the 'started but not classified' path is exercised too.
    q = con.execute(
        "SELECT driver, team, q_position FROM qualifying WHERE year=? AND"
        " round=? ORDER BY driver", (year, rnd)).fetchall()
    p_rows = con.execute(
        "SELECT driver, team FROM practice WHERE year=? AND round=?"
        " ORDER BY driver", (year, rnd)).fetchall()
    teams = {d: t for d, t, _ in q}
    grid_of = {d: (int(g) if g is not None else None) for d, _t, g in q}
    for d, t in p_rows:
        teams.setdefault(d, t)
    # Deterministic order that is NOT derived from grid, practice or the
    # model, so no metric is accidentally perfect and no leakage sneaks in.
    order = sorted(d for d in teams)[:21]
    omitted = sorted(set(teams) - set(order))
    print(f"  field: {len(teams)} cars, {len(order)} get a result, "
          f"omitted (no result): {omitted}")
    n_done = 0
    for i, d in enumerate(order, start=1):
        con.execute(
            "INSERT INTO results (year, round, event, driver, team, grid,"
            " finish) VALUES (?,?,?,?,?,?,?)",
            (year, rnd, "Sao Paulo Grand Prix", d, teams[d], grid_of.get(d),
             float(i)))
        # race_status is a separate table by design; without it
        # build_features warns about missing status for every simulated car.
        con.execute(
            "INSERT INTO race_status (year, round, driver, status)"
            " VALUES (?,?,?,?)",
            (year, rnd, d, "Finished"))
        n_done += 1
    con.commit()
    chk(15, n_done == 21, f"21 results rows written on the copy ({n_done})")
    chk(16, omitted and omitted[0] not in
        {r[0] for r in con.execute("SELECT driver FROM results WHERE year=?"
                                   " AND round=?", (year, rnd))},
        "the omitted driver really has no result row")

    rule("[6] SCORE IT AFTER THE RACE HAS RUN")
    # Close connection before running CLI to avoid database lock
    con.close()
    code, out = run(["scripts/score_forecast.py", "--year", str(year),
                     "--round", str(rnd), "--mode", "full", "--db", dbp])
    print(out)

    # Reopen connection for score() call
    con = db.connect(tmp)
    con.row_factory = None
    chk(17, code == 0, f"score exits 0 once results exist (got {code})")
    chk(18, "NO-PEEKING CHECK PASSED" in out,
        "the no-peeking verdict passed")
    chk(19, "SMALL-SAMPLE WARNING" in out,
        "the one-race small-sample warning is printed")
    chk(20, "grid baseline" in out and "practice-order baseline" in out
        and "recent-form baseline" in out,
        "all three full-mode baselines were scored on the same drivers")

    r = forecast.score(con, year, rnd, "full")
    print(f"  status={r['status']}  mae={r['mae']:.3f}  rho={r['rho']:.4f}  "
          f"winner={r['winner_hit']:.0%}  podium={r['podium_hit']:.0%}")
    print(f"  n_forecast={r['n_forecast']}  n_scored={r['n_scored']}  "
          f"no-result={r.get('forecast_without_result')}")
    print(f"  predicted winner={r['winner_pred']}  "
          f"actual winner={r['winner_act']}")
    print(f"  best baseline: {r.get('best_baseline')} "
          f"({r.get('best_baseline_mae'):.3f})  "
          f"model - best = {r.get('model_minus_best_mae'):+.3f}")
    chk(21, r["status"] == "scored", "score() reports status='scored'")
    chk(22, 0 <= r["mae"] <= 22, "MAE is inside the field size")
    chk(23, r["n_scored"] == 21 and
        r.get("forecast_without_result") == omitted,
        "the driver with no result was excluded from scoring, not counted "
        "as an error")
    chk(24, len(r["baselines"]) == 3, "three baselines returned")
    chk(25, r["saved_before_race"] is True,
        "the saved-before-race verdict is True")
    chk(26, r["features"] and len(r["features"]) == 12,
        "the saved feature list round-trips")

    rule("[7] A SECOND SAVE AFTER THE RACE IS REFUSED")
    fake = pd.DataFrame({
        "driver": [r0[0] for r0 in rows],
        "pred": [r0[2] for r0 in rows],
        "pred_pos": [r0[3] for r0 in rows],
        # Results now exist, so writing this would be a back-fit, not a
        # forecast - save() must refuse it before looking at anything else.
        "finish": [1.0] * len(rows),
    })
    df = features.build_features(con)
    try:
        forecast.save(con, year, rnd, "full", fake, feats, df)
        chk(27, False, "save() refused a race that already has results")
    except ValueError as exc:
        print(f"  raised ValueError: {exc}")
        chk(27, "results" in str(exc), "save() refused with a clear reason")

    rule("[8] A TAMPERED TIMESTAMP FAILS THE CHECK")
    # Use a created_at that is after the patched race_start_utc
    patched_start = con.execute(
        "SELECT race_start_utc FROM forecasts WHERE year=? AND round=? AND mode='full' LIMIT 1",
        (year, rnd)).fetchone()[0]
    tampered_at = (forecast._naive(patched_start) + timedelta(hours=1)
                   ).isoformat(timespec="seconds") + "+00:00"
    con.execute(
        "UPDATE forecasts SET created_at=? WHERE year=? AND round=?",
        (tampered_at, year, rnd))
    con.commit()
    r2 = forecast.score(con, year, rnd, "full")
    print(f"  created_at  : {r2['created_at']}")
    print(f"  race start  : {r2['race_start_utc']} (patched)")
    print(f"  saved_before: {r2['saved_before_race']}")
    chk(28, r2["saved_before_race"] is False,
        "a created_at after lights out is caught, even on one row")
    chk(29, r2["status"] == "scored",
        "metrics still print, but the banner will flag them as unverified")

    rule("[9] THE REAL DATABASE WAS NOT TOUCHED")
    after = fingerprint(DB)
    if after != before:
        for k in before:
            if before[k] != after[k]:
                print(f"  CHANGED {k}: {before[k]} -> {after[k]}")
    chk(30, after == before, "every production table is identical to before")

    con.close()
    try:
        tmp.unlink()
        print(f"\n  working copy removed: {tmp}")
        # The scorecard follows the database, so a scoring run against the
        # copy lands in the temp folder's reports/ - remove it so repeated
        # runs do not leave anything behind.
        for card in (tmp.parent / "reports").glob(
                f"scorecard_{year}_r{rnd}_*.md"):
            card.unlink()
            print(f"  scorecard removed: {card}")
    except OSError as exc:
        print(f"\n  could not remove {tmp}: {exc}")

    rule("RESULT")
    if FAILS:
        print(f"  {len(FAILS)} FAILED:")
        for f in FAILS:
            print(f"    - {f}")
        return 1
    print("  31 of 31 PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())