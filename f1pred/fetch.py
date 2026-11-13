"""Phase 1 step 1: fetch results, grid, qualifying and sprint from FastF1.

Verified against FastF1 3.9.0 (see scripts/verify_identifiers.py):

  identifier   conventional   sprint weekend
  -----------  ------------   --------------
  R            ok             ok
  Q            ok             ok
  S            rejected       ok          <- sprint RACE result
  SQ           rejected       resolves but ALWAYS returns 0 rows
  FP1/FP2/FP3  ok             FP1 only

Sprint QUALIFYING therefore comes from OpenF1 (scripts/verify_sprint.py:
18/18 empty via FastF1), and is added in the practice step.

Accepted identifiers are taken from FastF1's own schedule slots where
possible; a wrong identifier raises ValueError, which we log and skip
rather than guess.

Idempotency: a step is only recorded in fetch_log when it stored real rows.
A race that has not run yet (0 results) is retried next time instead of
being remembered as done - the bug Appendix A had with Mexico City 2026.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import fastf1

from . import clean, credentials, db, practice

log = logging.getLogger(__name__)

CACHE_DIR = Path("f1_cache")
SPRINT_FORMATS = {"sprint_shootout", "sprint_qualifying"}

# session name as it appears in FastF1's schedule -> accepted identifier
SLOT_IDENTIFIER = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",
    "Sprint": "S",
    "Race": "R",
}


def enable_cache() -> None:
    # Load F1 account credentials FIRST: FastF1 reads F1_USERNAME/F1_PASSWORD
    # at import/use time, and lap data (practices, qualifying lap times) needs
    # an authenticated session. The values are never logged.
    credentials.load()
    CACHE_DIR.mkdir(exist_ok=True)
    fastf1.Cache.configure(cache_dir=str(CACHE_DIR))


def _naive_utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


def _td_seconds(value) -> float | None:
    """Timedelta/NaT -> float seconds, or None."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    return float(pd.Timedelta(value).total_seconds())


def _season_field_size(counts: list[int]) -> int:
    """Most common cars-per-race for the season (20 or 22), never hard-coded."""
    if not counts:
        raise clean.DataValidationError("no races to size the field from")
    return max(set(counts), key=counts.count)


def _nullish(value) -> bool:
    """True for None/NaN **and** for FastF1's stringified NaN.

    FastF1 renders missing fields as the literal strings ``'nan'`` / ``'None'``
    on an object column, so ``pd.isna()`` alone reports False for them. That
    is what let 10 placeholder entrants and one non-starter through into
    2026 R19 - see ``fetch_race``.
    """
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):          # array-likes: not a scalar
        return False
    return str(value).strip().lower() in ("", "nan", "none")


def _float_or_none(value) -> float | None:
    """Numeric field -> float, or None when absent/unparseable."""
    if _nullish(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value) -> int | None:
    """Positive integer, else None.

    Rejects ``'nan'``, the letter codes FastF1 puts in ClassifiedPosition
    (``'R'`` retired, ``'N'`` not classified) and non-integral values, so it
    can be used to read a position without ever inventing one.
    """
    if _nullish(value):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not f.is_integer() or f <= 0:
        return None
    return int(f)


def _load(year: int, rnd: int, ident: str):
    ses = fastf1.get_session(year, rnd, ident)
    ses.load(laps=False, telemetry=False, weather=False, messages=False)
    return ses, ses.results


# ------------------------------------------------------------------- step: race
def fetch_race(con, year: int, rnd: int, ev) -> bool:
    """Store results + grid + driver numbers for one race.

    Returns True when real rows were stored (i.e. the race has run).
    """
    race_already_done = db.step_done(con, year, rnd, "race")
    
    event_name = str(ev["EventName"])
    try:
        _, res = _load(year, rnd, "R")
    except Exception as exc:                       # noqa: BLE001 - log & skip
        log.warning("race %d R%d unavailable: %s: %s",
                    year, rnd, type(exc).__name__, exc)
        return False

    if len(res) == 0:
        log.warning("%d R%d %s: no results yet (not run, or data missing) "
                    "- will retry next run", year, rnd, event_name)
        return False

    # For 2018-2022, ensure meeting_key is populated in sessions table
    if year < 2023:
        row = con.execute("SELECT meeting_key FROM sessions WHERE year=? AND round=?", (year, rnd)).fetchone()
        existing_meeting_key = row[0] if row else None
        if existing_meeting_key is None:
            try:
                import fastf1
                ses = fastf1.get_session(year, rnd, "R")
                ses.load(laps=False, telemetry=False, weather=False, messages=False)
                meeting_key = ses.session_info["Meeting"]["Key"]
                con.execute(
                    "UPDATE sessions SET meeting_key=? WHERE year=? AND round=?",
                    (meeting_key, year, rnd))
                con.commit()
                log.info("%d R%d: updated meeting_key to %s", year, rnd, meeting_key)
            except Exception as exc:
                log.warning("%d R%d: failed to get meeting_key from FastF1: %s", year, rnd, exc)
    elif not db.step_done(con, year, rnd, "race"):
        # For 2023+, only create sessions row if race step not done yet
        # (meeting_key will be populated by OpenF1 fetch)
        pass

    if race_already_done:
        return True

    event_name = str(ev["EventName"])
    try:
        _, res = _load(year, rnd, "R")
    except Exception as exc:                       # noqa: BLE001 - log & skip
        log.warning("race %d R%d unavailable: %s: %s",
                    year, rnd, type(exc).__name__, exc)
        return False

    if len(res) == 0:
        log.warning("%d R%d %s: no results yet (not run, or data missing) "
                    "- will retry next run", year, rnd, event_name)
        return False

    rows, num_rows = [], []
    pending: list[tuple[int, object]] = []     # (row index, ClassifiedPosition)
    n_classified = 0
    n_not_started = 0
    for _, r in res.iterrows():
        abbr = r.get("Abbreviation")
        if _nullish(abbr):
            log.warning("%d R%d: row without an abbreviation, skipped", year, rnd)
            continue
        abbr = str(abbr)
        grid = _float_or_none(r.get("GridPosition"))
        finish = _float_or_none(r.get("Position"))
        status = r.get("Status")

        # FastF1 lists entries that took NO part in the session: placeholder
        # codes (FM*/MC*/SC*, numbers 236-247) and drivers who were replaced
        # - seen for 2026 R19, where OCO has a name and team but no Status,
        # no Position and no GridPosition. They are not starters. A driver
        # who DID race always carries a real Status (HIR: 'Finished'), even
        # when FastF1 omits his Position, so "no finish AND no real Status"
        # is the reliable "did not take part" test. _nullish is essential:
        # FastF1 writes the STRING 'nan' here, which pd.isna() misses.
        if finish is None and _nullish(status):
            n_not_started += 1
            continue

        team_raw = r.get("TeamName")
        team = "" if _nullish(team_raw) else str(team_raw)
        rows.append((year, rnd, event_name, abbr, team, grid, finish))
        num_rows.append((year, rnd, abbr, _int_or_none(r.get("DriverNumber"))))
        if finish is None:
            pending.append((len(rows) - 1, r.get("ClassifiedPosition")))
        else:
            n_classified += 1

    # FastF1 sometimes leaves Position null for a driver it DID classify:
    # 2026 R19 HIR has ClassifiedPosition='10', Status='Finished', Points=1.0
    # (exactly what P10 scores) and 10 is the sole gap in an otherwise
    # complete 1..22 run. ClassifiedPosition also carries letter codes
    # ('R' retired), so _int_or_none only accepts a positive integer, and
    # the value is discarded if it would collide with a position someone
    # else already holds - we never invent a duplicate classification.
    taken = {row[6] for row in rows if row[6] is not None}
    for idx, cp in pending:
        pos = _int_or_none(cp)
        if pos is None or float(pos) in taken:
            continue
        old = rows[idx]
        rows[idx] = old[:6] + (float(pos),)
        taken.add(float(pos))
        n_classified += 1
        log.info("%d R%d: Position null for %s; used ClassifiedPosition=%d",
                 year, rnd, old[3], pos)

    if n_not_started:
        log.info("%d R%d %s: ignored %d entrant(s) that took no part",
                 year, rnd, event_name, n_not_started)

    # A session FastF1 has no result for YET (fetched before the race ran)
    # comes back as an entry list with every Position null. Storing that and
    # logging the step would freeze the bad data forever - which is exactly
    # what happened to 2026 R19. Refuse instead, so the next run retries.
    if n_classified == 0:
        log.warning("%d R%d %s: no classified finishers - race not run yet, "
                    "or FastF1 has no result. Nothing stored; will retry.",
                    year, rnd, event_name)
        return False

    # EXPLICIT column names, as in fetch_qualifying: a positional VALUES list
    # breaks silently the moment db._migrate appends a column (it corrupted
    # 48 qualifying rounds once). Name the columns and the order can never
    # drift away from the schema.
    con.executemany(
        "INSERT OR REPLACE INTO results (year, round, event, driver, team,"
        " grid, finish) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    con.executemany(
        "INSERT OR REPLACE INTO driver_numbers (year, round, driver,"
        " driver_number) VALUES (?,?,?,?)",
        num_rows,
    )
    con.execute(
        "INSERT OR REPLACE INTO sessions "
        "(year, round, event, event_format, event_date, meeting_key, "
        " expected_size, n_starters) VALUES (?,?,?,?,?,NULL,NULL,?)",
        (year, rnd, event_name, str(ev["EventFormat"]),
         _naive_utc(ev["EventDate"]).strftime("%Y-%m-%d"), len(rows)),
    )
    con.commit()
    db.log_step(con, year, rnd, "race", len(rows))
    log.info("%d R%d %-34s stored %d results", year, rnd, event_name, len(rows))
    return True


# ---------------------------------------------------------- step: race status
def fetch_race_status(con, year: int, rnd: int, ev) -> None:
    """Store FastF1's race Status for every starter, one row per driver.

    Why a separate table and a separate load: ``results`` must stay exactly
    the 7 columns f1_baseline.py depends on (asserted by check [3] in
    scripts/test_baseline_fetch.py), so Status cannot go there. Keeping the
    write isolated also means this step cannot alter the target variable even
    in principle - it only ever INSERTs into race_status.

    Status is the only way to tell a retirement from a finish: FastF1 gives
    retirees a real position (all 54 non-'Finished' sprint rows carry one),
    so results.finish alone can never express a DNF. Feature 7 of the 12
    ("recent non-finish rate") is built from this.
    """
    if db.step_done(con, year, rnd, "race_status"):
        return
    if not db.step_done(con, year, rnd, "race"):
        # race has not run / produced no results - retry on the next run
        return

    event_name = str(ev["EventName"])
    try:
        _, res = _load(year, rnd, "R")
    except Exception as exc:                       # noqa: BLE001 - log & skip
        log.warning("race status %d R%d unavailable: %s: %s",
                    year, rnd, type(exc).__name__, exc)
        return

    if len(res) == 0:
        log.warning("%d R%d %s: race status has no rows yet - will retry",
                    year, rnd, event_name)
        return

    out = []
    for _, r in res.iterrows():
        abbr = r.get("Abbreviation")
        if _nullish(abbr):
            continue
        # Same "did this driver take part" test fetch_race uses, so the row
        # set matches results exactly and the two join 1:1. A driver who raced
        # always carries a real Status even when FastF1 omits Position, so
        # "no Position AND no real Status" is the reliable not-a-starter test.
        # _nullish is essential: FastF1 writes the STRING 'nan', which
        # pd.isna() misses.
        finish = _float_or_none(r.get("Position"))
        status = r.get("Status")
        if finish is None and _nullish(status):
            continue
        out.append((year, rnd, str(abbr),
                    None if _nullish(status) else str(status)))

    if not out:
        # Zero rows means we learned nothing - do NOT log the step, so the
        # next run retries instead of freezing an empty table.
        log.warning("%d R%d %s: no race status rows - will retry",
                    year, rnd, event_name)
        return

    con.executemany(
        "INSERT OR REPLACE INTO race_status (year, round, driver, status)"
        " VALUES (?,?,?,?)",
        out,
    )
    con.commit()
    db.log_step(con, year, rnd, "race_status", len(out))
    log.info("%d R%d %s: race status stored for %d drivers",
             year, rnd, event_name, len(out))


# -------------------------------------------------------------- step: field size
def assign_field_sizes(con, year: int, rounds: set[int] | None = None) -> int:
    """Set sessions.expected_size from the season's modal car count, and validate.

    Returns the number of hard validation failures (0 in a healthy season).
    """
    where = "year=?" if rounds is None else None
    params = (year,) if rounds is None else None
    rows = con.execute(
        "SELECT round, n_starters FROM sessions WHERE year=?", (year,)
    ).fetchall()
    if rounds is not None:
        rows = [r for r in rows if r[0] in rounds]
    if not rows:
        return 0

    # A race that has NOT run yet still has a sessions row (the forecast path
    # inserts one) but no results, so its n_starters is NULL. There is no
    # grid size to check until it finishes, and validate_field_size(None, ...)
    # would raise a TypeError comparing None with an int - so those rows get
    # expected_size like every other row but are never validated.
    ran = [(r, n) for r, n in rows if n is not None]
    if not ran:
        log.info("%d: no completed race in scope - field size left as-is",
                 year)
        return 0

    expected = _season_field_size([n for _, n in ran])
    failures = 0
    for rnd, n in rows:
        con.execute("UPDATE sessions SET expected_size=? WHERE year=? AND round=?",
                    (expected, year, rnd))
        if n is None:
            continue                      # race still to come: nothing to check
        try:
            clean.validate_field_size(n, expected, f"{year} R{rnd} results")
        except clean.DataValidationError as exc:
            log.error("VALIDATION FAILED - %s", exc)
            failures += 1
    con.commit()
    log.info("%d: field size set to %d cars over %d races",
             year, expected, len(ran))
    return failures


# ------------------------------------------------------------ step: qualifying
def _starters(con, year: int, rnd: int) -> list[tuple]:
    """(driver, team_raw, driver_number) for every driver in results."""
    rows = con.execute(
        "SELECT r.driver, r.team, d.driver_number FROM results r "
        "LEFT JOIN driver_numbers d ON d.year=r.year AND d.round=r.round "
        "AND d.driver=r.driver WHERE r.year=? AND r.round=? ORDER BY r.finish",
        (year, rnd),
    ).fetchall()
    return rows


def _recover_best_from_laps(ses, by_abbr: dict[str, dict]) -> int:
    """Fill a missing qualifying best lap from the session's lap data.

    FastF1's results.Q1/Q2/Q3 are NaT for a whole session while the laps still
    carry the times - 2025 R6 Miami is the known case, where all 20 drivers
    stored has_qualifying_time=0 despite having real laps. A driver is flagged
    "no qualifying time" ONLY when BOTH sources are empty.

    Returns the number of drivers whose best lap was recovered.
    """
    try:
        # _load() calls ses.load(laps=False), and ses.laps then RAISES
        # DataNotLoadedError rather than returning an empty frame - so laps
        # must be requested explicitly, and only when they are actually needed.
        ses.load(laps=True, telemetry=False, weather=False, messages=False)
        laps = ses.laps
    except Exception as exc:                       # noqa: BLE001 - log & continue
        log.warning("lap fallback unavailable: %s: %s", type(exc).__name__, exc)
        return 0

    if laps is None or len(laps) == 0:
        return 0

    # A lap that can count toward qualifying is a FLYING lap. FastF1 stamps the
    # lap on which the car leaves or enters the pits with PitOutTime/PitInTime;
    # those are not flying laps (208 of Miami's 314 laps). Verified on this
    # session that this filter, IsAccurate==True and a Deleted filter all
    # produce byte-identical best laps, so the simplest self-documenting one
    # is used. Deleted laps never count either.
    valid = laps[
        laps["LapTime"].notna()
        & laps["PitOutTime"].isna()
        & laps["PitInTime"].isna()
    ]
    if "Deleted" in valid.columns:
        valid = valid[~valid["Deleted"].fillna(False).astype(bool)]
    if len(valid) == 0:
        return 0

    bests = (
        valid.assign(_s=valid["LapTime"].dt.total_seconds())
        .groupby("Driver")["_s"]
        .min()
    )

    n = 0
    for abbr, rec in by_abbr.items():
        if rec["best"] is not None:
            continue                              # results already had a time
        t = bests.get(abbr)
        if t is None or pd.isna(t):
            continue                              # lap data has nothing either
        rec["best"] = float(t)
        n += 1
    return n


def fetch_qualifying(con, year: int, rnd: int, entrants=None) -> None:
    """One row per starter; has_qualifying_time=0 only when NEITHER
    results.Q1/Q2/Q3 NOR the session's laps carry a time for that driver.

    ``entrants`` supplies the field for a race that has not run yet, where
    ``_starters`` reads an empty ``results`` table - see fetch_upcoming.
    None for every completed race, so the fallback is never reached there.
    """
    if db.step_done(con, year, rnd, "qualifying"):
        return

    starters = _starters(con, year, rnd)
    if not starters and entrants:
        starters = entrants
    if not starters:
        log.warning("%d R%d: no starters, qualifying skipped", year, rnd)
        return
    expected = con.execute(
        "SELECT expected_size FROM sessions WHERE year=? AND round=?",
        (year, rnd),
    ).fetchone()[0]

    try:
        ses, res = _load(year, rnd, "Q")
    except Exception as exc:                       # noqa: BLE001 - log & skip
        log.warning("qualifying %d R%d unavailable: %s: %s",
                    year, rnd, type(exc).__name__, exc)
        return

    if len(res) == 0:
        log.warning("%d R%d: qualifying has no rows yet - will retry", year, rnd)
        return

    try:
        clean.validate_field_size(len(res), expected, f"{year} R{rnd} qualifying")
    except clean.DataValidationError as exc:
        log.error("VALIDATION FAILED - %s (qualifying for %d R%d not stored)",
                  exc, year, rnd)
        return

    by_abbr: dict[str, dict] = {}
    for _, r in res.iterrows():
        abbr = r.get("Abbreviation")
        if pd.isna(abbr):
            continue
        q1, q2, q3 = _td_seconds(r.get("Q1")), _td_seconds(r.get("Q2")), _td_seconds(r.get("Q3"))
        segs = [v for v in (q1, q2, q3) if v is not None]
        by_abbr[str(abbr)] = {
            "pos": float(r["Position"]) if pd.notna(r.get("Position")) else None,
            "q1": q1, "q2": q2, "q3": q3,
            "best": min(segs) if segs else None,
        }

    # A starter FastF1 omits from the qualifying table gets the same
    # placeholder the output loop writes, so the lap fallback below can check
    # them too: has_qualifying_time must stay 0 only when BOTH sources are
    # empty, not merely because results omitted the driver.
    for driver, _team, _number in starters:
        if driver not in by_abbr:
            by_abbr[driver] = {"pos": None, "q1": None, "q2": None,
                               "q3": None, "best": None}

    # results.Q1/Q2/Q3 can be NaT for an entire session while the laps still
    # hold the times - 2025 R6 Miami, where all 20 drivers were flagged
    # has_qualifying_time=0 despite having real laps. Recover those BEFORE
    # pole is computed, so any_times/pole/gap all see the recovered times.
    # Laps are requested only when a driver is actually missing a time, so a
    # normal session never pays for them.
    if any(v["best"] is None for v in by_abbr.values()):
        n_rec = _recover_best_from_laps(ses, by_abbr)
        if n_rec:
            log.info("%d R%d: recovered %d qualifying time(s) from lap data",
                     year, rnd, n_rec)

    # FastF1's own Position column: validate leniently, because we verified it
    # can contain ties (2023 R10 -> Position 15.0 for both PER and BOT).
    positions = [int(v["pos"]) for v in by_abbr.values() if v["pos"] is not None]
    try:
        clean.validate_positions(positions, expected, f"{year} R{rnd} qualifying",
                                 allow_ties=True)
    except clean.DataValidationError as exc:
        log.error("VALIDATION FAILED - %s (qualifying for %d R%d not stored)",
                  exc, year, rnd)
        return

    bests = {d: v["best"] for d, v in by_abbr.items()}
    any_times = any(t is not None for t in bests.values())

    if any_times:
        pole = min(t for t in bests.values() if t is not None)
    else:
        # Both sources are empty: results.Q1/Q2/Q3 are NaT for every driver
        # AND the lap fallback above found no flying lap for anyone. This used
        # to be reachable via 2025 R6 Miami, but Miami's laps are recoverable
        # and now are - so only a session where nobody set a lap reaches here.
        # Leave best/gap NULL and keep has_qualifying_time=0 so the model sees
        # the missing-pace flag instead of a fabricated number. q_position
        # below still carries the official Position, which FastF1 returns even
        # for a session with no times.
        pole = None
        log.warning("%d R%d: qualifying has NO lap times in results or laps - "
                    "leaving best/gap NULL with has_qualifying_time=0",
                    year, rnd)

    # q_position IS FastF1's official Position.
    #
    # It used to be derive_rank(min(Q1,Q2,Q3)) - a rank of lap times - because
    # official Position can contain ties. That was WRONG, and three independent
    # checks agree:
    #   * against results.grid, which the race session records separately from
    #     the qualifying session, official wins 277 to 14 on the rows where the
    #     two definitions disagree;
    #   * 2025 R17: official says SAI P2 / ANT P4, but ANT's published Q2
    #     (101.464s) is faster than SAI's best (101.595s), so a lap rank puts
    #     ANT ahead - while Wikipedia's classification agrees with official
    #     ("Antonelli qualified in fourth... the first time he out-qualified
    #     Russell"; the lap rank has Russell P4, Antonelli P6);
    #   * no lap in that session is flagged Deleted, so the Q1/Q2/Q3 columns
    #     carry laps that never counted toward classification without marking
    #     them - ranking them ranks invalid laps.
    # Ties (2023 R10: PER and BOT both 15) and gaps when a qualifier does not
    # start are real features of the official classification and are kept as-is;
    # validate_positions(allow_ties=True) above already downgrades them to
    # warnings instead of failing the race.
    ranks = {d: (int(v["pos"]) if v["pos"] is not None else None)
             for d, v in by_abbr.items()}

    out = []
    for driver, team, number in starters:
        rec = by_abbr.get(driver)
        if rec is None:
            # starter absent from the qualifying table: no time set
            out.append((year, rnd, driver, number, team,
                        None, None, None, None, None, None, None, 0))
            continue
        best = rec["best"]
        gap = None if (best is None or pole is None) else (best - pole) / pole * 100.0
        out.append((year, rnd, driver, number, team,
                    ranks.get(driver), rec["pos"], rec["q1"], rec["q2"], rec["q3"],
                    best, gap, 1 if best is not None else 0))

    # EXPLICIT column names: the physical column order is NOT reliable here.
    # _migrate() appends new columns at the end, while this tuple is built in
    # the logical schema order - a positional VALUES(...) list silently shifts
    # every column after the first divergence (this corrupted 48 rounds once).
    con.executemany(
        "INSERT OR REPLACE INTO qualifying (year, round, driver, driver_number,"
        " team, q_position, q_position_official, q1_s, q2_s, q3_s, best_q_s,"
        " gap_to_pole_pct, has_qualifying_time)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        out,
    )
    con.commit()
    db.log_step(con, year, rnd, "qualifying", len(out))
    n_no_time = sum(1 for row in out if row[12] == 0)
    log.info("%d R%d qualifying stored for %d starters (%d without a lap time)",
             year, rnd, len(out), n_no_time)


# ---------------------------------------------------------------- step: sprint
def fetch_sprint(con, year: int, rnd: int) -> None:
    """Sprint RACE result via FastF1 'S'. Sprint weekends only."""
    if db.step_done(con, year, rnd, "sprint"):
        return

    starters = _starters(con, year, rnd)
    if not starters:
        return
    expected = con.execute(
        "SELECT expected_size FROM sessions WHERE year=? AND round=?",
        (year, rnd),
    ).fetchone()[0]

    try:
        _, res = _load(year, rnd, "S")
    except Exception as exc:                       # noqa: BLE001 - log & skip
        log.warning("sprint %d R%d unavailable: %s: %s",
                    year, rnd, type(exc).__name__, exc)
        return

    if len(res) == 0:
        log.warning("%d R%d: sprint has no rows yet - will retry", year, rnd)
        return

    try:
        clean.validate_field_size(len(res), expected, f"{year} R{rnd} sprint")
    except clean.DataValidationError as exc:
        log.error("VALIDATION FAILED - %s (sprint for %d R%d not stored)",
                  exc, year, rnd)
        return

    by_abbr: dict[str, dict] = {}
    for _, r in res.iterrows():
        abbr = r.get("Abbreviation")
        if pd.isna(abbr):
            continue
        by_abbr[str(abbr)] = {
            "pos": float(r["Position"]) if pd.notna(r.get("Position")) else None,
            "status": str(r["Status"]) if pd.notna(r.get("Status")) else None,
            "grid": float(r["GridPosition"]) if pd.notna(r.get("GridPosition")) else None,
            "points": float(r["Points"]) if pd.notna(r.get("Points")) else None,
        }

    positions = [int(v["pos"]) for v in by_abbr.values() if v["pos"] is not None]
    try:
        # allow_ties=True: a sprint is a race, and classified positions can be
        # shared by drivers who retired on the same lap - same reason as qualifying.
        clean.validate_positions(positions, expected, f"{year} R{rnd} sprint",
                                 allow_ties=True)
    except clean.DataValidationError as exc:
        log.error("VALIDATION FAILED - %s (sprint for %d R%d not stored)",
                  exc, year, rnd)
        return

    if positions and all(v["grid"] is None for v in by_abbr.values()):
        log.warning("%d R%d: sprint grid positions absent from FastF1 "
                    "(stored as NULL)", year, rnd)

    out = []
    for driver, team, number in starters:
        rec = by_abbr.get(driver)
        if rec is None:
            out.append((year, rnd, driver, number, team, None, None, None, None, 0))
        else:
            out.append((year, rnd, driver, number, team,
                        rec["pos"], rec["status"], rec["grid"],
                        rec["points"], 1))

    con.executemany(
        "INSERT OR REPLACE INTO sprint (year, round, driver, driver_number,"
        " team, sprint_position, sprint_status, sprint_grid, sprint_points,"
        " has_sprint_result) VALUES (?,?,?,?,?,?,?,?,?,?)",
        out,
    )
    con.commit()
    db.log_step(con, year, rnd, "sprint", len(out))
    log.info("%d R%d sprint stored for %d starters", year, rnd, len(out))


# ---------------------------------------------------------------------- driver
# ------------------------------------------------------- step: upcoming race
# FastF1 schedule session name -> the identifier fastf1.get_session accepts.
# Verified against the live API by scripts/probe_schedule.py: Session1..3 are
# "Practice 1..3", Session4 is "Qualifying", Session5 is "Race".
PRE_RACE_IDENTS: dict[str, str] = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
}


def _session_started(ev, ident: str, now: pd.Timestamp) -> bool:
    """Has this session's scheduled start time passed?

    Guards the entry-list load: asking FastF1 for FP3 or qualifying hours
    before they start costs rate-limit budget and returns nothing. A session
    with no published time counts as started, so the fetch is attempted and
    reports honestly if the data is not there.
    """
    for i in range(1, 6):
        name = str(ev.get(f"Session{i}", "") or "")
        if PRE_RACE_IDENTS.get(name) != ident:
            continue
        when = ev.get(f"Session{i}DateUtc")
        if when is None or pd.isna(when):
            return True
        try:
            return _naive_utc(when) <= now
        except (TypeError, ValueError):
            return True
    return False                      # not on this calendar entry at all


def upcoming_entrants(con, year: int, rnd: int,
                      ev) -> list[tuple[str, str, int | None]]:
    """(driver, team, driver_number) for a race that has NOT run yet.

    WHY IT EXISTS
      ``_starters()`` in both this module and ``practice`` reads the field out
      of ``results``. Before the race that table is empty, so ``fetch_race``'s
      siblings would each bail out with "no starters" and the forecast would
      silently be built on missing-flag features alone.

    WHERE THE FIELD COMES FROM
      FastF1's own pre-race session results - the same ``Abbreviation`` /
      ``TeamName`` / ``DriverNumber`` triple ``fetch_race`` stores, so there
      is one identifier in the database and no chance of a cross-source
      mismatch.

    WHY IT IS NOT "EVERYONE WHO APPEARS"
      Two opposite mistakes are both real, and both were seen on 2026 R20:

        * FP1 contains SIX F2 rookies (BEG, BRO, FOR, HER, MIN, SLA) running
          the mandatory young-driver test. They will not race.
        * Filtering instead to "drivers who have already started a race this
          season" drops CAM (Camara), who replaces HIR and makes his full
          weekend debut - that yields 21 cars in a 22-car field.

      The rule applied here::

          entrant = has raced this season OR appears in a session after FP1

      A one-off test driver shows up only in FP1 and has never raced, so he
      is dropped; a full-weekend entry shows up in FP2, so he is kept. On
      2026 R20 that produces exactly 22 cars in 11 teams of 2, with CAM at
      Haas alongside BEA and HIR absent entirely - checked by
      scripts/check_upcoming_field.py (6 of 6 PASS).

    WHAT IT NEVER DOES
      Never invents a driver who is in no session, and never quietly accepts
      a shortfall: the count is returned so the caller can compare it with
      ``sessions.expected_size`` and say so out loud.
    """
    raced = {d for (d,) in con.execute(
        "SELECT DISTINCT driver FROM results WHERE year=?", (year,))}

    now = _naive_utc(datetime.now(timezone.utc))
    # ident -> {abbreviation: (team, driver_number)}
    seen: dict[str, dict[str, tuple[str, int | None]]] = {}
    for ident in ("FP1", "FP2", "FP3", "Q"):
        if not _session_started(ev, ident, now):
            continue
        try:
            _, res = _load(year, rnd, ident)
        except Exception as exc:                        # noqa: BLE001
            log.info("%d R%d %s not usable for the entry list: %s: %s",
                     year, rnd, ident, type(exc).__name__, exc)
            continue
        dmap: dict[str, tuple[str, int | None]] = {}
        for _, r in (res if res is not None else []).iterrows():
            ab = r.get("Abbreviation")
            if _nullish(ab):        # FastF1's stringified NaN, not pd.isna
                continue
            team = r.get("TeamName")
            dmap[str(ab)] = ("" if _nullish(team) else str(team),
                             _int_or_none(r.get("DriverNumber")))
        if dmap:
            seen[ident] = dmap

    if not seen:
        return []

    # Drivers seen in any session other than FP1 are in the weekend proper.
    late: set[str] = set()
    for ident, dmap in seen.items():
        if ident != "FP1":
            late |= set(dmap)

    entrants: dict[str, tuple[str, int | None]] = {}
    dropped: list[str] = []
    for ident in ("FP1", "FP2", "FP3", "Q"):
        for d, rec in seen.get(ident, {}).items():
            if d in raced or d in late:
                entrants.setdefault(d, rec)   # first session seen wins the team
            elif d not in dropped:
                dropped.append(d)

    if dropped:
        log.info("%d R%d: excluded %d driver(s) who appear only in FP1 and "
                 "have not raced this season (young-driver test): %s",
                 year, rnd, len(dropped), ", ".join(sorted(dropped)))
    no_number = sorted(d for d, (_t, n) in entrants.items() if n is None)
    if no_number:
        log.warning("%d R%d: entry list has no driver number for %s - they "
                    "cannot be matched to lap data", year, rnd,
                    ", ".join(no_number))

    return [(d, team, num) for d, (team, num) in sorted(entrants.items())]


def fetch_upcoming(con, year: int, rnd: int) -> dict:
    """Fetch the pre-race sessions of a race that has NOT happened yet.

    WHY A SEPARATE ENTRY POINT
      ``fetch_year`` deliberately skips any race whose ``EventDate`` is in the
      future, and gates practice and qualifying behind
      ``step_done(..., "race")`` - because both read the field out of
      ``results``. A forecast needs those sessions BEFORE the race, so this
      path creates the ``sessions`` row, derives the entry list from the
      weekend's own sessions and passes it down instead.

    IT NEVER WRITES ``results``
      That table stays the authority for what happened, so the 7-column
      contract asserted by test [3] of scripts/test_baseline_fetch.py cannot
      be affected from here. ``n_starters`` is left NULL for exactly the same
      reason: no race has produced starters yet.

    Returns a summary dict. Raises only when the round is not on the calendar.
    """
    enable_cache()
    sched = fastf1.get_event_schedule(year, include_testing=False)
    hit = sched[sched["RoundNumber"] == rnd]
    if hit.empty:
        raise ValueError(f"{year} round {rnd} is not on FastF1's {year} "
                         "schedule")
    ev = hit.iloc[0]
    event_name = str(ev["EventName"])

    already = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?",
        (year, rnd)).fetchone()[0]
    if already:
        log.info("%d R%d already has %d results row(s) - the normal fetch "
                 "path owns it, nothing to do", year, rnd, already)
        return {"year": year, "round": rnd, "event": event_name,
                "status": "already-raced", "entrants": 0,
                "practice_rows": 0, "qualifying_rows": 0,
                "expected_size": None}

    now = _naive_utc(datetime.now(timezone.utc))

    # 1. sessions row - resolve_meeting() reads event_date from it, and for an
    #    unrun race fetch_race is not the one that creates it.
    row = con.execute("SELECT meeting_key FROM sessions WHERE year=? AND round=?",
                      (year, rnd)).fetchone()
    row_exists = row is not None
    existing_meeting_key = row[0] if row else None
    
    counts = [n for (n,) in con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? GROUP BY round",
        (year,))]
    expected = _season_field_size(counts) if counts else None
    
    # For 2018-2022, fetch meeting_key from FastF1 since OpenF1 not available
    meeting_key = existing_meeting_key
    if year < 2023 and existing_meeting_key is None:
        try:
            ses = fastf1.get_session(year, rnd, "R")
            ses.load(laps=False, telemetry=False, weather=False, messages=False)
            meeting_key = ses.session_info["Meeting"]["Key"]
        except Exception as exc:
            log.warning("%d R%d: failed to get meeting_key from FastF1: %s", year, rnd, exc)
    
    if row_exists:
        # Update existing row, preserving meeting_key
        con.execute(
            "UPDATE sessions SET event=?, event_format=?, event_date=?, meeting_key=?, expected_size=? "
            "WHERE year=? AND round=?",
            (event_name, str(ev["EventFormat"]),
             _naive_utc(ev["EventDate"]).strftime("%Y-%m-%d"), meeting_key, expected,
             year, rnd))
        log.info("%d R%d %s: sessions row updated (expected_size=%s, meeting_key=%s)",
                 year, rnd, event_name, expected, meeting_key)
    else:
        con.execute(
            "INSERT INTO sessions (year, round, event, event_format, event_date, meeting_key, expected_size, n_starters) "
            "VALUES (?,?,?,?,?,?,?,NULL)",
            (year, rnd, event_name, str(ev["EventFormat"]),
             _naive_utc(ev["EventDate"]).strftime("%Y-%m-%d"), meeting_key, expected))
        con.commit()
        log.info("%d R%d %s: sessions row created (expected_size=%s, meeting_key=%s, n_starters NULL)",
                 year, rnd, event_name, expected, meeting_key)

    # 2. entry list, then the sessions themselves.
    entrants = upcoming_entrants(con, year, rnd, ev)
    if not entrants:
        log.warning("%d R%d: no pre-race session has produced a driver list "
                    "yet - nothing to fetch", year, rnd)
        return {"year": year, "round": rnd, "event": event_name,
                "status": "no-sessions", "entrants": 0,
                "practice_rows": 0, "qualifying_rows": 0,
                "expected_size": _expected_size(con, year, rnd)}

    practice.fetch_practice(con, year, rnd, entrants=entrants)

    # 3. qualifying, but only once its scheduled start has passed - asking
    #    FastF1 for a session that has not begun costs calls and yields rows
    #    of zero, which fetch_qualifying would then log as "will retry".
    q_started = _session_started(ev, "Q", now)
    if q_started:
        fetch_qualifying(con, year, rnd, entrants=entrants)
    else:
        log.info("%d R%d: qualifying has not started yet (%s UTC) - "
                 "early-mode only for now", year, rnd,
                 _session_start(ev, "Q"))

    n_p = con.execute("SELECT COUNT(*) FROM practice WHERE year=? AND round=?",
                      (year, rnd)).fetchone()[0]
    n_q = con.execute(
        "SELECT COUNT(*) FROM qualifying WHERE year=? AND round=?",
        (year, rnd)).fetchone()[0]
    expected = _expected_size(con, year, rnd)
    if expected is not None and len(entrants) != expected:
        log.warning("%d R%d: entry list has %d cars against an expected %d - "
                    "the field is only final once qualifying has run",
                    year, rnd, len(entrants), expected)

    log.info("%d R%d %s (upcoming): %d entrants, %d practice rows, "
             "%d qualifying rows", year, rnd, event_name, len(entrants),
             n_p, n_q)
    return {"year": year, "round": rnd, "event": event_name,
            "status": "fetched", "entrants": len(entrants),
            "practice_rows": n_p, "qualifying_rows": n_q,
            "expected_size": expected, "qualifying_started": q_started}


def _expected_size(con, year: int, rnd: int) -> int | None:
    row = con.execute(
        "SELECT expected_size FROM sessions WHERE year=? AND round=?",
        (year, rnd)).fetchone()
    if row is not None and row[0] is not None:
        return int(row[0])
    counts = [n for (n,) in con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? GROUP BY round", (year,))]
    return _season_field_size(counts) if counts else None


def _session_start(ev, ident: str) -> str:
    """Scheduled UTC start of a session as 'YYYY-MM-DD HH:MM', or '?'."""
    for i in range(1, 6):
        if PRE_RACE_IDENTS.get(str(ev.get(f"Session{i}", "") or "")) != ident:
            continue
        when = ev.get(f"Session{i}DateUtc")
        if when is None or pd.isna(when):
            return "?"
        return _naive_utc(when).strftime("%Y-%m-%d %H:%M")
    return "?"


def fetch_year(con, year: int, rounds: set[int] | None = None) -> dict:
    enable_cache()
    sched = fastf1.get_event_schedule(year, include_testing=False)
    today = _naive_utc(datetime.now(timezone.utc).date())

    # ---- pass 1: results + grid
    candidates = []
    for _, ev in sched.iterrows():
        rnd = int(ev["RoundNumber"])
        if rounds is not None and rnd not in rounds:
            continue
        if _naive_utc(ev["EventDate"]) > today:
            log.info("%d R%d %s is in the future - skipped",
                     year, rnd, ev["EventName"])
            continue
        candidates.append((rnd, ev))

    n_race = sum(1 for rnd, ev in candidates if fetch_race(con, year, rnd, ev))

    # ---- pass 1b: race Status (feature 7, "recent non-finish rate").
    #      Own table, own load, own fetch_log step: this never writes results,
    #      so the 7-column contract f1_baseline.py relies on cannot break.
    for rnd, ev in candidates:
        fetch_race_status(con, year, rnd, ev)

    # ---- pass 2: field size + validation (needs all races of the season)
    failures = assign_field_sizes(con, year, rounds)

    # ---- pass 3: qualifying + sprint
    n_q = n_s = 0
    for rnd, ev in candidates:
        if not db.step_done(con, year, rnd, "race"):
            continue                              # race had no data
        fetch_qualifying(con, year, rnd)
        if str(ev["EventFormat"]) in SPRINT_FORMATS:
            fetch_sprint(con, year, rnd)

    # ---- pass 4: practice + sprint qualifying
    # For 2018-2022: FastF1 practice (OpenF1 starts at 2023)
    # For 2023+: OpenF1 practice + sprint qualifying
    from . import practice_fastf1
    for rnd, ev in candidates:
        if not db.step_done(con, year, rnd, "race"):
            continue
        if year < 2023:
            practice_fastf1.fetch_practice_fastf1(con, year, rnd)
        else:
            practice.fetch_practice(con, year, rnd)
            if str(ev["EventFormat"]) in SPRINT_FORMATS:
                practice.fetch_sprint_qualifying(con, year, rnd)

    counts = con.execute(
        "SELECT (SELECT COUNT(*) FROM results WHERE year=?), "
        "(SELECT COUNT(*) FROM qualifying WHERE year=?), "
        "(SELECT COUNT(*) FROM sprint WHERE year=?), "
        "(SELECT COUNT(*) FROM sessions WHERE year=?), "
        "(SELECT COUNT(*) FROM practice WHERE year=?), "
        "(SELECT COUNT(*) FROM sprint_qualifying WHERE year=?), "
        "(SELECT COUNT(*) FROM race_status WHERE year=?)",
        (year, year, year, year, year, year, year),
    ).fetchone()
    return {"year": year, "results": counts[0], "qualifying": counts[1],
            "sprint": counts[2], "sessions": counts[3],
            "practice": counts[4], "sprint_qualifying": counts[5],
            "race_status": counts[6],
            "races_with_results": n_race, "validation_failures": failures}


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="python -m f1pred.fetch",
        description="Phase 1: fetch results/grid/qualifying/sprint from FastF1")
    ap.add_argument("--years", type=int, nargs="+", required=True)
    ap.add_argument("--rounds", type=int, nargs="+", default=None,
                    help="only these round numbers (for quick tests)")
    ap.add_argument("--db", type=Path, default=db.DB_PATH)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("fastf1").setLevel(logging.ERROR)

    rounds = set(args.rounds) if args.rounds else None
    con = db.connect(args.db)
    total_failures = 0
    try:
        for year in args.years:
            print(f"\n=== {year} ===", flush=True)
            summary = fetch_year(con, year, rounds)
            total_failures += summary["validation_failures"]
            print(f"    results={summary['results']} "
                  f"qualifying={summary['qualifying']} sprint={summary['sprint']} "
                  f"practice={summary.get('practice', 0)} "
                  f"sq={summary.get('sprint_qualifying', 0)} "
                  f"status={summary.get('race_status', 0)} "
                  f"sessions={summary['sessions']} "
                  f"races={summary['races_with_results']} "
                  f"validation_failures={summary['validation_failures']}")
    finally:
        con.close()

    print(f"\nvalidation failures: {total_failures}")
    return 1 if total_failures else 0


if __name__ == "__main__":
    sys.exit(main())
