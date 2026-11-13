"""Practice + sprint-qualifying pace from OpenF1.

Kept in its own module (per your instruction) so the practice data source can
be swapped later without touching the rest of the pipeline. FastF1 stays the
primary source for qualifying/grid/race/sprint - see ``f1pred.fetch``.

WHY OPenF1 FOR PRACTICE
-----------------------
FastF1's lap data sits behind F1-account auth; before credentials were
available it failed silently (``Failed to load timing data!``), so practice
laps were unreachable. OpenF1 needs no auth and carries the same sessions.

FIELDS RELIED ON (verified against the live API - scripts/verify_phase1.py
checks 1-4, all 89/89 races matched):
  /v1/sessions   session_key, meeting_key, session_name, session_type,
                 date_start, year, location
  /v1/drivers    driver_number, name_acronym, team_name
  /v1/laps       driver_number, lap_duration, is_pit_out_lap, lap_number

MATCHING RULE
-------------
OpenF1 Race session date <-> FastF1 ``sessions.event_date``, within +-1 day
(86/89 exact, rest local/UTC shifts). That yields the meeting_key, and every
practice session of the weekend hangs off that meeting.

SPRINT WEEKENDS (verified: 18 sprint_qualifying + 6 sprint_shootout)
--------------------------------------------------------------------
* exactly ONE practice session (FP1) - so ``n_sessions = 1``;
* FastF1's own ``SQ`` session is always EMPTY (18/18) or raises ValueError
  (6 shootouts), because Ergast has no sprint-qualifying data. The sprint
  one-lap-speed feature therefore comes from OpenF1's ``Sprint Qualifying``.
* when a race has no practice at all, rows are still written with
  ``n_sessions = 0`` and ``has_practice_lap = 0`` - a missing flag, never a
  fabricated number.

MISSING DATA
------------
12 races have at least one driver with no valid practice lap (verified).
Those drivers keep their row with ``best_practice_s = NULL`` and
``has_practice_lap = 0`` so the model sees the gap instead of a zero.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from . import clean, db, openf1 as o1

log = logging.getLogger(__name__)

# FastF1 schedule slot name -> what we ask OpenF1 for
PRACTICE_NAMES = o1.PRACTICE_SESSION_NAMES          # ("Practice 1/2/3")
SQ_NAMES = ("Sprint Qualifying", "Sprint Shootout")
DATE_TOLERANCE_DAYS = 1


def _utc_date(value) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.to_pydatetime()


# ------------------------------------------------------------- session lookup
def resolve_meeting(con, year: int, rnd: int, sessions_by_year=None) -> int | None:
    """Match OpenF1's Race session to this FastF1 race by date -> meeting_key.

    Stores the result in ``sessions.meeting_key`` so it is only computed once.
    Returns None when no OpenF1 race session is within tolerance.
    """
    row = con.execute(
        "SELECT event_date, meeting_key FROM sessions WHERE year=? AND round=?",
        (year, rnd),
    ).fetchone()
    if row is None:
        return None
    if row[1] is not None:
        return row[1]

    if not row[0]:
        log.warning("%d R%d: no event_date in sessions, cannot match OpenF1",
                    year, rnd)
        return None
    target = datetime.fromisoformat(row[0]).date()

    all_sessions = sessions_by_year or o1.get_sessions(year)
    races = [s for s in all_sessions
             if s.get("session_type") == "Race"
             and s.get("session_name") == "Race"]
    best, best_delta = None, None
    for s in races:
        try:
            d = _utc_date(s["date_start"]).date()
        except (KeyError, TypeError, ValueError):
            continue
        delta = abs((d - target).days)
        if delta <= DATE_TOLERANCE_DAYS and (best_delta is None or delta < best_delta):
            best, best_delta = s, delta

    if best is None:
        log.warning("%d R%d: no OpenF1 race session within %d day(s) of %s",
                    year, rnd, DATE_TOLERANCE_DAYS, target)
        return None

    meeting = best.get("meeting_key")
    con.execute(
        "UPDATE sessions SET meeting_key=? WHERE year=? AND round=?",
        (meeting, year, rnd),
    )
    con.commit()
    log.debug("%d R%d matched OpenF1 meeting_key=%s (delta=%d day)",
              year, rnd, meeting, best_delta)
    return meeting


def _meeting_sessions(year: int, meeting_key: int) -> list[dict]:
    """Every OpenF1 session belonging to one meeting."""
    return [s for s in o1.get_sessions(year)
            if s.get("meeting_key") == meeting_key]


def practice_sessions(con, year: int, rnd: int) -> list[dict]:
    """Practice sessions of the weekend, in schedule order.

    Conventional weekends have FP1/FP2/FP3; sprint weekends have exactly one
    (FP1). Returns [] when the meeting cannot be resolved - callers write a
    missing-data row rather than skipping the race.
    """
    meeting = resolve_meeting(con, year, rnd)
    if meeting is None:
        return []
    sess = [s for s in _meeting_sessions(year, meeting)
            if s.get("session_type") == "Practice"
            and s.get("session_name") in PRACTICE_NAMES]
    return sorted(sess, key=lambda s: str(s.get("date_start", "")))


def sprint_qualifying_session(con, year: int, rnd: int) -> dict | None:
    """OpenF1 'Sprint Qualifying' session, or None on a conventional weekend."""
    meeting = resolve_meeting(con, year, rnd)
    if meeting is None:
        return None
    sess = [s for s in _meeting_sessions(year, meeting)
            if s.get("session_name") in SQ_NAMES]
    return sess[0] if sess else None


# ------------------------------------------------------------------- helpers
def _starters(con, year: int, rnd: int) -> list[tuple]:
    """(driver, team, driver_number) for every driver in results."""
    return con.execute(
        "SELECT r.driver, r.team, d.driver_number FROM results r "
        "LEFT JOIN driver_numbers d ON d.year=r.year AND d.round=r.round "
        "AND d.driver=r.driver WHERE r.year=? AND r.round=? ORDER BY r.finish",
        (year, rnd),
    ).fetchall()


def _merge_sessions(session_results: list[dict[int, dict]]) -> dict[int, dict]:
    """Merge per-session best-lap dicts into one weekend-long view.

    ``lap_count`` is summed (laps completed across the weekend); the best lap
    is the minimum over sessions, ignoring sessions where the driver set none.
    """
    merged: dict[int, dict] = {}
    for lap_dict in session_results:
        for driver, rec in lap_dict.items():
            m = merged.setdefault(driver, {
                "best_lap_s": None, "lap_count": 0, "is_pit_out_laps": 0})
            m["lap_count"] += rec["lap_count"]
            m["is_pit_out_laps"] += rec["is_pit_out_laps"]
            b = rec["best_lap_s"]
            if b is not None and (m["best_lap_s"] is None or b < m["best_lap_s"]):
                m["best_lap_s"] = b
    return merged


def _write_rows(con, table: str, year: int, rnd: int, step: str,
                starters, values: dict[int, dict],
                columns: list[str]) -> None:
    """Write one row per starter into ``table`` with EXPLICIT column names.

    Explicit columns matter: ``db._migrate`` appends new columns at the end,
    so a positional VALUES(...) list silently shifts data (that bug hit
    qualifying once already).
    """
    if not starters:
        log.warning("%d R%d: no starters, %s skipped", year, rnd, step)
        return

    out = []
    for driver, team, number in starters:
        rec = values.get(number) if number is not None else None
        if rec is None:
            # driver has no data at all: NULLs + missing flag, never a 0
            out.append([year, rnd, driver, number, team]
                       + [None] * (len(columns) - 6) + [0])
        else:
            out.append([year, rnd, driver, number, team] + rec)

    ph = ",".join("?" * len(columns))
    con.executemany(
        f"INSERT OR REPLACE INTO {table} ({', '.join(columns)}) VALUES ({ph})",
        out,
    )
    con.commit()
    db.log_step(con, year, rnd, step, len(out))


# ------------------------------------------------------------ step: practice
def compute_practice(con, year: int, rnd: int, entrants=None):
    """Pure recomputation of what ``fetch_practice`` would store - writes nothing.

    Returns ``(starters, values, columns, session_names)``.

    Extracted from ``fetch_practice`` so the cross-check validator can recompute
    every one of the 89 races through the IDENTICAL production code path, rather
    than through a parallel reimplementation that could silently drift from it.
    The only side effect left is ``resolve_meeting`` populating
    ``sessions.meeting_key``, which is already populated for all 89 races and is
    idempotent.

    ``entrants`` is how a race that has NOT run yet supplies its field:
    ``_starters`` reads ``results``, and there is no results row before the
    race, so ``fetch_upcoming`` passes the entry list it derived from the
    weekend's own sessions. For all 89 completed races ``_starters`` returns
    rows and this fallback is never reached - behaviour there is unchanged.
    """
    starters = _starters(con, year, rnd)
    if not starters and entrants:
        starters = entrants
    if not starters:
        return starters, {}, [], []

    sessions = practice_sessions(con, year, rnd)
    # aggregate every practice of the weekend (FP1+FP2+FP3, or FP1 alone)
    per_session = [o1.best_practice_laps(o1.get_laps(s["session_key"]))
                   for s in sessions]
    merged = _merge_sessions(per_session)

    bests = {num: rec["best_lap_s"] for num, rec in merged.items()}
    timed = [t for t in bests.values() if t is not None]
    session_best = min(timed) if timed else None

    all_numbers = {n for _, _, n in starters if n is not None}

    # RANK STARTERS ONLY. OpenF1's practice sessions also contain reserve and
    # test drivers who never start the race. Ranking `merged` counted those
    # phantom drivers, so their ranks consumed numbers and real starters were
    # pushed as high as P27 in a 22-car field - 9 of 89 races affected, e.g.
    # STR 2026 R7 stored practice_rank 27 when he was 22nd of 22. _write_rows
    # below writes starters only, so the ranking universe must match the rows
    # actually stored.
    # session_best deliberately stays over EVERYONE: in every affected race
    # rank 1 is present, i.e. no non-starter was ever fastest, so
    # gap_to_best_pct was never wrong and needs no change.
    starter_bests = {num: bests[num] for num in bests if num in all_numbers}
    timed_starters = [t for t in starter_bests.values() if t is not None]
    # derive_rank keys are driver_numbers here; sort key is (time, key) so
    # integer keys are fine and the result is duplicate-free by construction.
    ranks = (clean.derive_rank(starter_bests) if timed_starters
             else {k: None for k in starter_bests})

    values: dict[int, list] = {}
    for num in all_numbers | set(merged):
        rec = merged.get(num)
        best = rec["best_lap_s"] if rec else None
        gap = (None if (best is None or session_best is None)
               else (best - session_best) / session_best * 100.0)
        values[num] = [
            len(sessions),
            best,
            ranks.get(num),
            rec["lap_count"] if rec else 0,
            rec["is_pit_out_laps"] if rec else 0,
            gap,
            1 if best is not None else 0,
        ]

    columns = ["year", "round", "driver", "driver_number", "team",
               "n_sessions", "best_practice_s", "practice_rank",
               "laps_completed", "pit_out_laps", "gap_to_best_pct",
               "has_practice_lap"]
    names = [s["session_name"] for s in sessions]
    return starters, values, columns, names


def fetch_practice(con, year: int, rnd: int, entrants=None) -> None:
    """One row per starter: weekend best practice lap, laps, missing flag.

    ``entrants`` is passed straight through to ``compute_practice`` - see the
    note there. It is None for every completed race, which is why the call
    below is byte-for-byte what it was before.
    """
    if db.step_done(con, year, rnd, "practice"):
        return

    starters, values, columns, names = compute_practice(
        con, year, rnd, entrants)
    if not starters:
        log.warning("%d R%d: no starters, practice skipped", year, rnd)
        return

    _write_rows(con, "practice", year, rnd, "practice", starters, values, columns)

    n_no = sum(1 for _, _, n in starters
               if not values.get(n) or values[n][-1] == 0)
    log.info("%d R%d practice stored for %d starters from %s "
             "(%d without a valid lap)", year, rnd, len(starters),
             ", ".join(names) or "NO SESSION", n_no)


# ------------------------------------------------- step: sprint qualifying
def compute_sprint_qualifying(con, year: int, rnd: int):
    """Pure recomputation of what ``fetch_sprint_qualifying`` stores - no writes.

    Returns ``(starters, values, columns, session)``. ``session`` is None both
    when there are no starters and on a conventional weekend (no sprint
    qualifying exists); the caller checks starters first, exactly as the
    original code did, so the two cases stay distinct.

    Same rationale as ``compute_practice``: the validator must recompute races
    through the real production code path.
    """
    starters = _starters(con, year, rnd)
    ses = sprint_qualifying_session(con, year, rnd) if starters else None
    if not starters or ses is None:
        return starters, {}, [], ses

    laps = o1.get_laps(ses["session_key"])
    best = o1.best_practice_laps(laps)

    bests = {num: rec["best_lap_s"] for num, rec in best.items()}
    timed = [t for t in bests.values() if t is not None]
    session_best = min(timed) if timed else None
    ranks = clean.derive_rank(bests) if timed else {k: None for k in bests}

    all_numbers = {n for _, _, n in starters if n is not None}
    values: dict[int, list] = {}
    for num in all_numbers | set(best):
        rec = best.get(num)
        b = rec["best_lap_s"] if rec else None
        gap = (None if (b is None or session_best is None)
               else (b - session_best) / session_best * 100.0)
        values[num] = [
            b,
            ranks.get(num),
            rec["lap_count"] if rec else 0,
            gap,
            1 if b is not None else 0,
        ]

    columns = ["year", "round", "driver", "driver_number", "team",
               "best_sq_s", "sq_rank", "laps", "gap_to_best_pct",
               "has_sq_lap"]
    return starters, values, columns, ses


def fetch_sprint_qualifying(con, year: int, rnd: int) -> None:
    """One-lap sprint-qualifying speed from OpenF1 (sprint weekends only).

    FastF1's own SQ session is always empty or raises, so this is the only
    source for this feature.
    """
    if db.step_done(con, year, rnd, "sprint_qualifying"):
        return

    starters, values, columns, ses = compute_sprint_qualifying(con, year, rnd)
    if not starters:
        return

    if ses is None:
        # conventional weekend: no sprint qualifying exists, so this is not
        # missing data - record it as done with 0 rows to avoid retrying.
        log.info("%d R%d: no sprint qualifying (conventional weekend)", year, rnd)
        db.log_step(con, year, rnd, "sprint_qualifying", 0)
        return

    _write_rows(con, "sprint_qualifying", year, rnd, "sprint_qualifying",
                starters, values, columns)

    n_no = sum(1 for _, _, n in starters
               if not values.get(n) or values[n][-1] == 0)
    log.info("%d R%d sprint qualifying stored for %d starters "
             "(%d without a lap)", year, rnd, len(starters), n_no)
