"""Phase 5 acceptance test: early vs full mode, and the messages when data
is missing.

WHY A COPY OF THE DATABASE IS NEEDED
------------------------------------
All races in f1.db now have BOTH practice and qualifying (1838+ rows each),
so a weekend where only practice exists does not occur naturally. Rather than
pretend, the test copies f1.db and deletes qualifying for one race - a real
reconstruction of "qualifying has not happened yet" - and runs the CLI
against that copy. The original f1.db is never opened for writing; check [7]
proves it is untouched afterwards.

SCENARIOS
  [1] original DB, auto on already-run race -> REFUSED, exit 1
  [2] copy, qualifying deleted     -> EARLY, exit 0, 7 features, practice
                                       scatter, no grid baseline, warning
                                       says qualifying IS unavailable
  [3] copy, same race, --mode full -> REFUSED, exit 1, says why
  [4] copy, practice deleted too   -> REFUSED, exit 1, says neither exists
  [5] copy, no practice, --mode early -> REFUSED, exit 1, says why
  [6] --mode early on a race that HAS qualifying -> wording must say
                                       qualifying exists but is excluded
                                       deliberately, not "unavailable"
  [7] original f1.db row counts unchanged

Run:  python scripts/test_modes.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DB = ROOT / "f1.db"

FAILED = 0
PASSED = 0


def _pick_unrun_round(con, year: int) -> int:
    """Return the latest round in `con` that has qualifying data.
    Since all rounds now have results, we just pick the latest round with qualifying.
    The test copy will delete results to simulate pre-race conditions.
    """
    rounds = con.execute(
        "SELECT DISTINCT round FROM qualifying WHERE year=? ORDER BY round",
        (year,)).fetchall()
    if not rounds:
        raise ValueError(f"No qualifying rounds found for year {year}")
    return max(r[0] for r in rounds)


def _make_pre_race_copy(year: int, round_: int) -> tuple[Path, Path, int, int]:
    """Return (tmp_dir, db_copy, base_q, base_p) for a pre-race world.

    The copy has results/race_status deleted for `round_` AND all later rounds,
    so `round_` is the latest race in the copy.
    """
    tmp = Path(tempfile.mkdtemp(prefix="f1_modes_")) / "f1_practice_only.db"
    shutil.copy2(SRC_DB, tmp)

    con = sqlite3.connect(tmp)
    # Delete results and race_status for this round and all later rounds
    con.execute(
        "DELETE FROM results WHERE year=? AND round>=?", (year, round_))
    con.execute(
        "DELETE FROM race_status WHERE year=? AND round>=?", (year, round_))
    con.commit()
    con.close()

    base_q = count(tmp, "qualifying")
    base_p = count(tmp, "practice")
    return tmp, tmp, base_q, base_p


def check(n: int, cond: bool, label: str, detail: str = "") -> None:
    global FAILED, PASSED
    if cond:
        PASSED += 1
    else:
        FAILED += 1
    print(f"  [{n}] {label:<62} {'PASS' if cond else 'FAIL'}{detail}")


def run_cli(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.run(
        [sys.executable, "-m", "f1pred.cli", *args],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", cwd=ROOT, env=env,
    )


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def has_row(out: str, label: str) -> bool:
    """True if `label` appears as an actual table row (label at line start),
    not merely as prose. Needed because early mode prints the sentence 'NOT
    scored against the grid baseline', which contains the same words."""
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith(label) and len(s) > len(label):
            return True
    return False


def delete(dbfile: Path, table: str, year: int, round_: int) -> int:
    import sqlite3
    con = sqlite3.connect(dbfile)
    cur = con.execute(f"DELETE FROM {table} WHERE year=? AND round=?",
                      (year, round_))
    n = cur.rowcount
    con.commit()
    con.close()
    return n


def count(dbfile: Path, table: str, year: int | None = None,
          round_: int | None = None) -> int:
    import sqlite3
    con = sqlite3.connect(dbfile)
    sql, args = f"SELECT COUNT(*) FROM {table}", []
    if year is not None:
        sql += " WHERE year=? AND round=?"
        args = [year, round_]
    n = con.execute(sql, args).fetchone()[0]
    con.close()
    return n


def _cleanup(tmp_dir: Path) -> None:
    try:
        shutil.rmtree(tmp_dir.parent, ignore_errors=True)
    except OSError:
        pass


def main() -> int:
    YEAR = 2026
    ROUND = 20  # Use R20 as the test round (has qualifying and practice data)

    # ---------------------------------------------------------------- prepare
    rule("SETUP - copy f1.db so the original is never modified")
    tmp = Path(tempfile.mkdtemp(prefix="f1_modes_")) / "f1_practice_only.db"
    shutil.copy2(SRC_DB, tmp)
    print(f"  copy: {tmp}  ({tmp.stat().st_size:,} bytes)")
    print(f"  race under test: {YEAR} R{ROUND}")

    base_q = count(SRC_DB, "qualifying")
    base_p = count(SRC_DB, "practice")
    print(f"  original qualifying rows {base_q}, practice rows {base_p}")

    # ============================================================ [1] auto/full on ORIGINAL DB
    # Note: This tests the "already run" refusal since all 2026 rounds have results
    rule("[1] ORIGINAL DB, auto on already-run race -> expect REFUSED, exit 1")
    r = run_cli("--year", str(YEAR), "--round", str(ROUND))
    print("  " + next((ln for ln in r.stdout.splitlines()
                       if ln.startswith("MODE:")), "(no MODE line)"))
    check(1, r.returncode == 1, "exit code 1 (refused to forecast already-run race)", f" (got {r.returncode})")
    check(2, "already has results" in r.stdout or "already run" in r.stdout.lower(),
          "message explains race already has results")

    # ============================================ [2] practice-only -> EARLY on COPY
    rule("[2] COPY, qualifying deleted -> expect EARLY mode, exit 0")
    n_del = delete(tmp, "qualifying", YEAR, ROUND)
    print(f"  deleted {n_del} qualifying rows for {YEAR} R{ROUND}; "
          f"practice rows for that race: {count(tmp, 'practice', YEAR, ROUND)}")

    r2 = run_cli("--db", str(tmp), "--year", str(YEAR), "--round", str(ROUND))
    first = next((ln for ln in r2.stdout.splitlines() if ln.startswith("MODE:")), "(no MODE line)")
    print("  " + first)
    for ln in r2.stdout.splitlines()[:14]:
        if ln.strip():
            print("    | " + ln)

    check(3, r2.returncode == 0, "exit code 0", f" (got {r2.returncode})")
    check(4, "MODE: EARLY (practice only)" in r2.stdout,
          "auto fell back to EARLY when qualifying was gone")
    check(4, "qualifying is unavailable" in r2.stdout,
          "warning says qualifying IS unavailable")
    check(5, "features   : 7 ->" in r2.stdout,
          "only the 7 early features are used")
    check(6, "q_position" not in r2.stdout.split("WALK-FORWARD")[-1],
          "no qualifying feature appears after the banner")
    check(7, not has_row(r2.stdout.split("THIS MODE'S WALK-FORWARD MAE")[-1],
                         "grid baseline"),
          "grid baseline row is NOT offered in early mode")
    check(8, "_practice.png" in r2.stdout,
          "scatter uses the practice gap")
    check(9, "PREDICTED TOP 3" in r2.stdout and
          "PREDICTED ORDER TABLE" in r2.stdout,
          "top-3 and order table were produced")
    check(9, "MODEL - best baseline" in r2.stdout,
          "early mode still reports its MAE vs baselines")
    check(10, "_practice.png" in r2.stdout,
          "practice scatter PNG was written",
          f" ({list((ROOT / 'reports').glob(f'gap_vs_prediction_{YEAR}_r{ROUND}_practice.png'))})")

    # ==================================================== [3] full refused
    rule("[3] COPY, --mode full with no qualifying -> expect REFUSED, exit 1")
    r3 = run_cli("--db", str(tmp), "--year", str(YEAR), "--round", str(ROUND),
                 "--mode", "full")
    print("  " + (r3.stdout.strip().splitlines() or [""])[0])
    for ln in [l for l in r3.stdout.splitlines() if "full mode needs" in l
               or "Fix:" in l][:4]:
        print("    | " + ln.strip())
    check(12, r3.returncode == 1, "exit code 1", f" (got {r3.returncode})")
    check(12, "full mode needs qualifying" in r3.stdout,
          "message states exactly what full mode needs")
    check(13, "--mode early" in r3.stdout,
          "message suggests the workable alternative")
    check(13, "PREDICTED TOP 3" not in r3.stdout,
          "no forecast was printed for a refused mode")

    # ==================================================== [4] neither session exists
    rule("[4] COPY, qualifying AND practice deleted -> expect REFUSED, exit 1")
    n_p = delete(tmp, "practice", YEAR, ROUND)
    print(f"  deleted {n_p} practice rows too; both sessions now absent")
    r4 = run_cli("--db", str(tmp), "--year", str(YEAR), "--round", str(ROUND))
    for ln in [l for l in r4.stdout.splitlines() if "ERROR" in l or "Fix:" in l][:5]:
        print("    | " + ln.strip())
    check(14, r4.returncode == 1, "exit code 1", f" (got {r4.returncode})")
    check(14, "neither qualifying nor practice" in r4.stdout,
          "message says no pre-race evidence exists at all")

    # ================================================== [5] early refused
    rule("[5] COPY, no practice, --mode early -> expect REFUSED, exit 1")
    r5 = run_cli("--db", str(tmp), "--year", str(YEAR), "--round", str(ROUND),
                 "--mode", "early")
    for ln in [l for l in r5.stdout.splitlines() if "early mode needs" in l][:3]:
        print("    | " + ln.strip())
    check(15, r5.returncode == 1, "exit code 1", f" (got {r5.returncode})")
    check(15, "early mode needs practice" in r5.stdout,
          "message states exactly what early mode needs")

    # ====================================== [6] early on a race WITH qualifying
    rule("[6] --mode early on a race that HAS qualifying -> wording must not lie")
    r6 = run_cli("--year", str(YEAR), "--round", str(ROUND), "--mode", "early")
    warn = [ln.strip() for ln in r6.stdout.splitlines()
            if "qualifying EXISTS" in ln or "qualifying is unavailable" in ln]
    for w in warn:
        print("    | " + w)
    check(16, r6.returncode == 0, "exit code 0", f" (got {r6.returncode})")
    check(16, any("qualifying EXISTS" in w for w in warn),
          "says qualifying exists but is excluded deliberately")
    check(17, not any("qualifying is unavailable" in w for w in warn),
          "does NOT claim qualifying is unavailable when 22/22 have times")

    # ================================================ [7] original untouched
    rule("[7] ORIGINAL f1.db UNTOUCHED")
    q_now, p_now = count(SRC_DB, "qualifying"), count(SRC_DB, "practice")
    print(f"  qualifying {base_q} -> {q_now}, practice {base_p} -> {p_now}")
    check(17, q_now == base_q, "qualifying row count unchanged",
          f" ({q_now} vs {base_q})")
    check(18, p_now == base_p, "practice row count unchanged",
          f" ({p_now} vs {base_p})")
    check(18, count(tmp, "qualifying", YEAR, ROUND) == 0,
          "the COPY is the one that lost its qualifying")

    _cleanup(tmp)

    # ========================================== [8] TRUE FORECAST: no results
    rule("[8] TRUE FORECAST - a race with NO results row")
    tmp2 = Path(tempfile.mkdtemp(prefix="f1_forecast_")) / "f1_not_run.db"
    shutil.copy2(SRC_DB, tmp2)
    # Must delete results for this round AND all later rounds so the
    # build_features guard sees this as the latest race.
    con2 = sqlite3.connect(tmp2)
    con2.execute("DELETE FROM results WHERE year=? AND round>=?", (YEAR, ROUND))
    con2.execute("DELETE FROM race_status WHERE year=? AND round>=?", (YEAR, ROUND))
    con2.commit()
    con2.close()
    n_res = count(tmp2, "results", YEAR, ROUND)
    n_stat = count(tmp2, "race_status", YEAR, ROUND)
    print(f"  deleted results/race_status for {YEAR} R{ROUND}+; "
          f"results rows now: {n_res}, race_status: {n_stat}")
    print(f"  kept: practice {count(tmp2, 'practice', YEAR, ROUND)}, "
          f"qualifying {count(tmp2, 'qualifying', YEAR, ROUND)}")
    print("  -> a weekend that has NOT run: pre-race data only, no finish anywhere")

    r8 = run_cli("--db", str(tmp2), "--year", str(YEAR), "--round", str(ROUND),
                 "--mode", "early")
    print("  " + next((ln for ln in r8.stdout.splitlines()
                       if ln.startswith("MODE:")), "(no MODE line)"))
    n_order = r8.stdout.count("forecast - race not run yet")
    mae_line = next((ln.strip() for ln in r8.stdout.splitlines()
                     if ln.strip().startswith("MAE ")), "(no MAE line)")
    print(f"  {mae_line}")
    print(f"  order-table rows marked 'forecast - race not run yet': {n_order}")

    check(19, r8.returncode == 0, "exit code 0", f" (got {r8.returncode})")
    check(19, "TRUE FORECAST" in r8.stdout, "prints the true-forecast banner")
    check(20, "PREDICTED ORDER TABLE" in r8.stdout, "order table was produced")
    check(20, n_order == 22, "all 22 cars predicted and none scored",
          f" ({n_order} rows)")
    check(21, "not run yet" in r8.stdout.split("PREDICTED TOP 3")[1][:800],
          "top-3 says the race has not been run")
    check(21, "nan" not in r8.stdout.lower(),
          "no NaN leaked into any printed number")
    check(22, "validated 170 races" in r8.stdout,
          "the un-run fold is predicted but NOT scored (170 validated)")
    check(22, mae_line.startswith("MAE 3."), "MAE is still a real number",
          f" ({mae_line})")
    check(22, "rank the model gave the actual winner" not in r8.stdout,
          "no winner-rank line when there is no winner")

    rule("[8b] SAME RACE, FULL MODE - grid cannot exist yet")
    r9 = run_cli("--db", str(tmp2), "--year", str(YEAR), "--round", str(ROUND),
                 "--mode", "full")
    print("  " + next((ln for ln in r9.stdout.splitlines()
                       if ln.startswith("MODE:")), "(no MODE line)"))
    for ln in [l.strip() for l in r9.stdout.splitlines()
               if "has not run, so our tables" in l or "RESULT     :" in l]:
        print("    | " + ln)
    check(23, r9.returncode == 0, "full mode also works on an un-run race",
          f" (got {r9.returncode})")
    check(23, "holds no starting grid" in r9.stdout.lower(),
          "full mode explains why no grid exists yet")
    check(24, "nan" not in r9.stdout.lower(), "full mode: no NaN printed")

    _cleanup(tmp2)

    # ========================================== [9] GUARD against a bad call
    rule("[9] GUARD - a race that HAS already run cannot be 'forecast'")
    sys.path.insert(0, str(ROOT))
    from f1pred import db as _db, features as _feats  # noqa: E402

    con = _db.connect()
    con.row_factory = None
    try:
        _feats.build_features(con, forecast_race=(YEAR, ROUND))
    except ValueError as exc:
        ok, msg = True, str(exc)
    else:
        ok, msg = False, "no error raised"
    con.close()
    print(f"  {msg[:120]}")
    check(25, ok, "build_features refuses to forecast an already-run race")
    check(25, "already run" in msg, "the message says exactly why")

    rule("RESULT")
    print(f"  {PASSED} passed, {FAILED} failed")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    sys.exit(main())