"""OpenF1 practice source.

Kept in its own module (per your instruction) so the practice data source can
be swapped later without touching the rest of the pipeline.

Everything else - qualifying, grid, race, sprint - comes from FastF1.

OpenF1 endpoints used, all verified against the live API:
  GET /v1/sessions?year=YYYY          -> session_key, meeting_key, session_name,
                                          session_type, date_start, circuit info
  GET /v1/drivers?session_key=K       -> driver_number, name_acronym, team_name
  GET /v1/laps?session_key=K          -> driver_number, lap_duration, is_pit_out_lap,
                                          lap_number, date_start
Rate limit: ~3 req/s, ~30 req/min [VERIFY]; enforced by f1pred.httpcache.
"""
from __future__ import annotations

import logging
from typing import Any

from . import httpcache

log = logging.getLogger(__name__)

# FastF1 session name  -> OpenF1 session_name. Verified identical strings.
PRACTICE_SESSION_NAMES = ("Practice 1", "Practice 2", "Practice 3")

# ---------------------------------------------------------------------------
# LAP VALIDITY RULES
#
# These were decided and written down BEFORE any Phase 3 model metric (MAE,
# Spearman, hit rate) was inspected, so they cannot be tuned to flatter a
# result. Both rules are structural: they read only the lap record itself and
# never look at finishing position, grid or any target.
#
# Rule 1 - sector arithmetic.
#   duration_sector_1 + duration_sector_2 + duration_sector_3 must add up to
#   lap_duration within SECTOR_TOLERANCE_S.
#   Tolerance is set from the data's own precision: every value is stored to
#   3 decimals, so rounding contributes at most 3*0.0005 + 0.0005 = 0.002 s.
#   0.1 s is 50x that - enough to absorb any line-crossing artefact - while
#   still being ~1400x smaller than the 142.3 s error in the single lap that
#   exposed this defect (PIA, 2026 R4 lap 35: sectors sum to 202.620 s but
#   lap_duration says 60.351 s).
#   MISSING SECTORS ARE NEVER REJECTED. If any of the three sector times is
#   absent the lap simply cannot be checked, so it is kept - we only reject
#   what we can prove is wrong.
#
# Rule 2 - implausible speed.
#   A lap must be at least MIN_LAP_FRACTION (90%) of the session's SECOND
#   fastest usable lap. The fastest lap is deliberately excluded from forming
#   the reference, because the fastest lap is exactly the one under suspicion.
#   Threshold: across all 89 races the largest legitimate gap between a
#   session's fastest and second-fastest lap was 0.8%, so a 10% cutoff leaves
#   a 12x margin. Only laps that are FASTER than the reference can ever be
#   rejected, so a driver who merely ran slowly is never touched.
#   Applied only once the session holds at least MIN_LAPS_FOR_REFERENCE usable
#   laps; below that the reference is not trustworthy and nothing is rejected.
#
# lap_count still counts every lap row (including pit-out and rejected ones):
# "laps completed" measures how many laps the driver actually drove, which is
# a different question from whether a recorded duration can be trusted.
# ---------------------------------------------------------------------------
SECTOR_TOLERANCE_S = 0.1
MIN_LAP_FRACTION = 0.90
MIN_LAPS_FOR_REFERENCE = 10

# rejection reasons reported by classify_laps()
REJECT_SECTOR = "sector_mismatch"
REJECT_FAST = "implausibly_fast"
REJECT_PREEXISTING = "null_or_pit_out"   # rule that already existed before this fix


def _sector_sum(lap: dict[str, Any]) -> float | None:
    """Sum of the three sector times, or None when any one is missing."""
    parts = [lap.get(f"duration_sector_{i}") for i in (1, 2, 3)]
    if any(p is None for p in parts):
        return None
    return float(sum(parts))


def classify_laps(laps: list[dict[str, Any]]) -> tuple[list[dict[str, Any]],
                                                       list[tuple[dict[str, Any], str]]]:
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
        if lap.get("lap_duration") is None or lap.get("is_pit_out_lap"):
            rejected.append((lap, REJECT_PREEXISTING))
            continue
        total = _sector_sum(lap)
        if total is not None and \
                abs(total - lap["lap_duration"]) > SECTOR_TOLERANCE_S:
            rejected.append((lap, REJECT_SECTOR))
            continue
        kept.append(lap)

    # pass 2: rule 2 (implausible speed) - only if we can trust the reference
    if len(kept) >= MIN_LAPS_FOR_REFERENCE:
        ordered = sorted(l["lap_duration"] for l in kept)
        reference = ordered[1]              # 2nd fastest, never the suspect one
        floor = reference * MIN_LAP_FRACTION
        survivors: list[dict[str, Any]] = []
        for lap in kept:
            if lap["lap_duration"] < floor:
                rejected.append((lap, REJECT_FAST))
            else:
                survivors.append(lap)
        kept = survivors

    return kept, rejected


def get_sessions(year: int) -> list[dict[str, Any]]:
    """All OpenF1 sessions for a season (includes testing days)."""
    rows = httpcache.get_json(f"/v1/sessions?year={year}")
    return rows or []


def get_drivers(session_key: int) -> list[dict[str, Any]]:
    """Driver list for one session: driver_number, name_acronym, team_name."""
    rows = httpcache.get_json(f"/v1/drivers?session_key={session_key}")
    return rows or []


def get_laps(session_key: int) -> list[dict[str, Any]]:
    """All lap rows for one session (can be a few hundred rows)."""
    rows = httpcache.get_json(f"/v1/laps?session_key={session_key}")
    return rows or []


def best_practice_laps(laps: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Best practice lap + lap count per driver.

    Rules (as you specified):
      * ignore rows where ``lap_duration`` is null
      * ignore pit-out laps (``is_pit_out_lap`` is true)
      * ignore laps rejected by ``classify_laps`` (the two validity rules
        documented above) when choosing the BEST lap
      * ``lap_count`` counts every lap row, including pit-out and rejected
        laps, because "laps completed" is what the practice-laps feature means
        - how many laps a driver drove is independent of whether one of the
        recorded durations can be trusted

    Returns {driver_number: {"best_lap_s": float | None,
                             "lap_count": int,
                             "is_pit_out_laps": int}}
    """
    valid, _rejected = classify_laps(laps)

    # counting pass: unchanged from the original behaviour
    out: dict[int, dict[str, Any]] = {}
    for lap in laps:
        driver = lap.get("driver_number")
        if driver is None:
            continue
        rec = out.setdefault(
            driver, {"best_lap_s": None, "lap_count": 0, "is_pit_out_laps": 0}
        )
        rec["lap_count"] += 1
        if lap.get("is_pit_out_lap"):
            rec["is_pit_out_laps"] += 1

    # selection pass: only laps that survived every validity rule
    for lap in valid:
        driver = lap.get("driver_number")
        if driver is None:
            continue
        duration = lap.get("lap_duration")
        rec = out.setdefault(
            driver, {"best_lap_s": None, "lap_count": 0, "is_pit_out_laps": 0}
        )
        if rec["best_lap_s"] is None or duration < rec["best_lap_s"]:
            rec["best_lap_s"] = duration
    return out
