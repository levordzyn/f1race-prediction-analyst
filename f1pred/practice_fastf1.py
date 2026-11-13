"""Practice pace from FastF1 (for 2018-2022 seasons where OpenF1 has no coverage).

Kept in its own module so the practice data source can be swapped per season.
FastF1 stays the primary source for qualifying/grid/race/sprint - see ``f1pred.fetch``.

WHY FASTF1 FOR PRACTICE (2018-2022)
----------------------------------
OpenF1 coverage starts at 2023. For 2018-2022, FastF1 is the only source
for practice lap data. FastF1 requires F1 account auth for lap data.

FIELDS RELIED ON (verified against FastF1 3.9.0):
  session.results: Abbreviation, TeamName, DriverNumber
  session.laps:    DriverNumber, LapTime, Sector1Time, Sector2Time, Sector3Time,
                   IsPitOutLap, LapNumber, Deleted

MATCHING RULE
-------------
FastF1 session date <-> sessions.event_date (exact match by year/round).

LAP VALIDITY RULES (identical to OpenF1 path, decided BEFORE any metric)
-------------------------------------------------------------------------
Rule 1 - sector arithmetic:
  duration_sector_1 + duration_sector_2 + duration_sector_3 must add up to
  lap_duration within SECTOR_TOLERANCE_S = 0.1 s.
  Tolerance is set from the data's own precision: every value is stored to
  3 decimals, so rounding contributes at most 3*0.0005 + 0.0005 = 0.002 s.
  0.1 s is 50x that - enough to absorb any line-crossing artefact - while
  still being ~1400x smaller than the 142.3 s error in the single lap that
  exposed this defect (PIA, 2026 R4 lap 35: sectors sum to 202.620 s but
  lap_duration says 60.351 s).
  MISSING SECTORS ARE NEVER REJECTED. If any of the three sector times is
  absent the lap simply cannot be checked, so it is kept - we only reject
  what we can prove is wrong.

Rule 2 - implausible speed:
  A lap must be at least MIN_LAP_FRACTION (90%) of the session's SECOND
  fastest usable lap. The fastest lap is deliberately excluded from forming
  the reference, because the fastest lap is exactly the one under suspicion.
  Threshold: across all 89 races the largest legitimate gap between a
  session's fastest and second-fastest lap was 0.8%, so a 10% cutoff leaves
  a 12x margin. Only laps that are FASTER than the reference can ever be
  rejected, so a driver who merely ran slowly is never touched.
  Applied only once the session holds at least MIN_LAPS_FOR_REFERENCE = 10
  usable laps; below that the reference is not trustworthy and nothing is
  rejected.

lap_count still counts every lap row (including pit-out and rejected ones):
"laps completed" measures how many laps the driver actually drove, which is
a different question from whether a recorded duration can be trusted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from . import clean, db, openf1 as o1
from .practice import _starters

log = logging.getLogger(__name__)

# FastF1 session name -> what we use internally
PRACTICE_NAMES = ("FP1", "FP2", "FP3")

# Lap validity rules (IDENTICAL to openf1.py)
SECTOR_TOLERANCE_S = 0.1
MIN_LAP_FRACTION = 0.90
MIN_LAPS_FOR_REFERENCE = 10

REJECT_SECTOR = "sector_mismatch"
REJECT_FAST = "implausibly_fast"
REJECT_PREEXISTING = "null_or_pit_out"


def _sector_sum(lap: dict[str, Any]) -> float | None:
    """Sum of the three sector times, or None when any one is missing."""
    parts = [lap.get(f"Sector{i}Time") for i in (1, 2, 3)]
    if any(p is None for p in parts):
        return None
    return float(sum(parts))


def classify_laps(laps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[tuple[dict[str, Any], str]]]:
    """Split lap rows into (usable, rejected) applying both validity rules.

    This is the single code path used by ``best_practice_laps`` AND by the
    cross-check validator, so the check that produces stored data is literally
    the same function that audits it.

    Returns ``(valid, rejected)`` where ``rejected`` is a list of
    ``(lap, reason)`` with reason one of REJECT_PREEXISTING, REJECT_SECTOR,
    REJECT_FAST.
    """
    kept: list[dict[str, Any]] = []
    rejected: list[tuple[dict[str, Any], str]] = []

    # pass 1: pre-existing rules, then rule 1 (sector arithmetic)
    for lap in laps:
        if lap.get("LapTime") is None or lap.get("IsPitOutLap"):
            rejected.append((lap, REJECT_PREEXISTING))
            continue
        total = _sector_sum(lap)
        if total is not None and \
                abs(total - lap["LapTime"]) > SECTOR_TOLERANCE_S:
            rejected.append((lap, REJECT_SECTOR))
            continue
        kept.append(lap)

    # pass 2: rule 2 (implausible speed) - only if we can trust the reference
    if len(kept) >= MIN_LAPS_FOR_REFERENCE:
        ordered = sorted(l["LapTime"] for l in kept)
        reference = ordered[1]              # 2nd fastest, never the suspect one
        floor = reference * MIN_LAP_FRACTION
        survivors: list[dict[str, Any]] = []
        for lap in kept:
            if lap["LapTime"] < floor:
                rejected.append((lap, REJECT_FAST))
            else:
                survivors.append(lap)
        kept = survivors

    return kept, rejected


def get_sessions(year: int) -> list[dict[str, Any]]:
    """All FastF1 sessions for a season (includes testing days)."""
    import fastf1
    return fastf1.get_event_schedule(year, include_testing=False).to_dict("records")


def _utc_date(value) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.to_pydatetime()


# ------------------------------------------------------------- session lookup
def resolve_meeting(con, year: int, rnd: int) -> int | None:
    """Get meeting_key from sessions table, or fetch from FastF1 if not present.

    For 2023+, meeting_key is populated by OpenF1 fetch.
    For 2018-2022, we need to fetch it from FastF1 session info.
    """
    row = con.execute(
        "SELECT meeting_key FROM sessions WHERE year=? AND round=?",
        (year, rnd),
    ).fetchone()
    if row and row[0] is not None:
        return row[0]

    # Not in DB (2018-2022), fetch from FastF1
    import fastf1
    try:
        # Load the race session to get meeting_key
        ses = fastf1.get_session(year, rnd, "R")
        ses.load(laps=False, telemetry=False, weather=False, messages=False)
        return ses.session_info["Meeting"]["Key"]
    except Exception as exc:
        log.warning("%d R%d: failed to get meeting_key from FastF1: %s", year, rnd, exc)
        return None


def _meeting_sessions(year: int, meeting_key: int) -> list[dict]:
    """Every FastF1 session belonging to one meeting."""
    return [s for s in get_sessions(year)
            if s.get("MeetingKey") == meeting_key]


def practice_sessions(year: int, meeting_key: int, rnd: int | None = None) -> list[dict]:
    """Practice sessions of the weekend, in schedule order.

    Conventional weekends have FP1/FP2/FP3; sprint weekends have exactly one (FP1).
    Returns [] when the meeting cannot be resolved.
    """
    import fastf1
    
    # If round not provided, try to find it from the database
    if rnd is None:
        import sqlite3
        from . import db as _db
        con = _db.connect()
        row = con.execute(
            "SELECT round FROM sessions WHERE year=? AND meeting_key=?",
            (year, meeting_key),
        ).fetchone()
        con.close()
        if not row:
            return []
        rnd = row[0]

    sessions = []
    for name in ("FP1", "FP2", "FP3"):
        try:
            ses = fastf1.get_session(year, rnd, name)
            ses.load(laps=False, telemetry=False, weather=False, messages=False)
            info = ses.session_info
            if info.get("Type") == "Practice":
                sessions.append({
                    "session_key": info["Key"],
                    "session_name": info["Name"],
                    "session_type": info["Type"],
                    "start_date_utc": info["StartDate"],
                    "meeting_key": info["Meeting"]["Key"],
                })
        except Exception as exc:
            continue
    sessions.sort(key=lambda s: s.get("start_date_utc", ""))
    return sessions


def _fastf1_laps_to_dicts(laps_df) -> list[dict]:
    """Convert FastF1 laps DataFrame to list of dicts for openf1.classify_laps.

    Maps FastF1 column names to OpenF1 expected keys:
    - LapTime -> lap_duration (seconds)
    - IsPitOutLap -> is_pit_out_lap
    - Sector1Time -> duration_sector_1 (seconds)
    - Sector2Time -> duration_sector_2 (seconds)
    - Sector3Time -> duration_sector_3 (seconds)
    - DriverNumber -> driver_number
    - LapNumber -> lap_number
    - Deleted -> deleted flag
    """
    records = []
    for _, row in laps_df.iterrows():
        lt = row.get("LapTime")
        lap_duration = lt.total_seconds() if pd.notna(lt) else None

        rec = {
            "lap_duration": lap_duration,
            "is_pit_out_lap": bool(row.get("IsPitOutLap", False)),
            "duration_sector_1": row["Sector1Time"].total_seconds() if pd.notna(row.get("Sector1Time")) else None,
            "duration_sector_2": row["Sector2Time"].total_seconds() if pd.notna(row.get("Sector2Time")) else None,
            "duration_sector_3": row["Sector3Time"].total_seconds() if pd.notna(row.get("Sector3Time")) else None,
            "driver_number": int(row["DriverNumber"]) if pd.notna(row.get("DriverNumber")) else None,
            "lap_number": int(row["LapNumber"]) if pd.notna(row.get("LapNumber")) else None,
        }
        # Deleted laps are excluded by classify_laps anyway, but we can mark them
        if pd.notna(row.get("Deleted")) and row["Deleted"]:
            rec["deleted"] = True
        records.append(rec)
    return records


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
    """Write one row per starter into ``table`` with EXPLICIT column names."""
    if not starters:
        log.warning("%d R%d: no starters, %s skipped", year, rnd, step)
        return

    out = []
    for driver, team, number in starters:
        rec = values.get(number) if number is not None else None
        if rec is None:
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
def compute_practice_fastf1(con, year: int, rnd: int, entrants=None):
    """Pure recomputation of what ``fetch_practice_fastf1`` would store - writes nothing.

    Returns ``(starters, values, columns, session_names)``.

    Extracted from ``fetch_practice_fastf1`` so the cross-check validator can recompute
    every one of the 2018-2022 races through the IDENTICAL production code path.
    """
    starters = _starters(con, year, rnd)
    if not starters and entrants:
        starters = entrants
    if not starters:
        return starters, {}, [], []

    # Get meeting key from sessions table, or fetch from FastF1 if not present
    meeting_key = resolve_meeting(con, year, rnd)
    if meeting_key is None:
        log.warning("%d R%d: could not resolve meeting_key, cannot fetch FastF1 practice", year, rnd)
        return starters, {}, [], []

    sessions = practice_sessions(year, meeting_key, rnd)
    if not sessions:
        log.warning("%d R%d: no FastF1 practice sessions found", year, rnd)
        # Still write missing-data rows for starters
        values = {num: [0, None, None, 0, 0, None, 0] for _, _, num in starters if num is not None}
        return starters, values, [
            "year", "round", "driver", "driver_number", "team",
            "n_sessions", "best_practice_s", "practice_rank",
            "laps_completed", "pit_out_laps", "gap_to_best_pct",
            "has_practice_lap"
        ], []

    # aggregate every practice of the weekend (FP1+FP2+FP3, or FP1 alone)
    import fastf1
    per_session = []
    for s in sessions:
        try:
            ses = fastf1.get_session(year, rnd, s["session_name"])
            ses.load(laps=True, telemetry=False, weather=False, messages=False)
            # Verify laps are actually loaded
            if ses.laps is None or len(ses.laps) == 0:
                log.warning("%d R%d %s: no laps loaded", year, rnd, s["session_name"])
                continue
        except Exception as exc:
            log.warning("%d R%d %s: failed to load laps: %s", year, rnd, s["session_name"], exc)
            continue
        # Convert FastF1 laps DataFrame to list of dicts for openf1.classify_laps
        laps_list = _fastf1_laps_to_dicts(ses.laps)
        per_session.append(o1.best_practice_laps(laps_list))

    merged = _merge_sessions(per_session)

    bests = {num: rec["best_lap_s"] for num, rec in merged.items()}
    timed = [t for t in bests.values() if t is not None]
    session_best = min(timed) if timed else None

    all_numbers = {n for _, _, n in starters if n is not None}

    # RANK STARTERS ONLY. FastF1 practice sessions also contain reserve and
    # test drivers who never start the race. Ranking `merged` counted those
    # phantom drivers, so their ranks consumed numbers and real starters were
    # pushed as high as P27 in a 22-car field.
    starter_bests = {num: bests[num] for num in bests if num in all_numbers}
    timed_starters = [t for t in starter_bests.values() if t is not None]
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


def fetch_practice_fastf1(con, year: int, rnd: int, entrants=None) -> None:
    """One row per starter: weekend best practice lap, laps, missing flag.

    Uses FastF1 lap data (requires F1 account auth).
    """
    if db.step_done(con, year, rnd, "practice"):
        return

    starters, values, columns, names = compute_practice_fastf1(
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


if __name__ == "__main__":                       # pragma: no cover
    import sys
    from . import db as _db

    con = _db.connect()
    con.row_factory = sqlite3.Row
    # Test on 2023 R1 (has FastF1 practice)
    frame = compute_practice_fastf1(con, 2023, 1)
    con.close()
    print(frame)
    sys.exit(0)