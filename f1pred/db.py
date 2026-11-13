"""SQLite schema + connection for the Phase 1 data layer.

Design notes
------------
* ``results`` keeps the EXACT 7-column layout that ``f1_baseline.py``
  defines (year, round, event, driver, team, grid, finish) so the existing
  starter script keeps working untouched.
* Everything Phase 1 adds lives in its own table keyed by (year, round),
  with ``driver`` = FastF1's Abbreviation as the canonical join key
  (verified: 0 abbreviation mismatches vs OpenF1 across 1794 pairs).
* ``fetch_log`` makes fetching idempotent: a step that completed with real
  rows is never repeated. A step that produced ZERO rows is NOT logged, so
  a race that has not run yet is retried on the next run instead of being
  remembered as "done" (this is the bug Appendix A had).
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path("f1.db")

SCHEMA = """
-- unchanged from Appendix A; f1_baseline.py depends on this layout
CREATE TABLE IF NOT EXISTS results (
    year   INTEGER,
    round  INTEGER,
    event  TEXT,
    driver TEXT,
    team   TEXT,
    grid   REAL,
    finish REAL,
    PRIMARY KEY (year, round, driver)
);

-- static event metadata, one row per completed race
CREATE TABLE IF NOT EXISTS sessions (
    year              INTEGER,
    round             INTEGER,
    event             TEXT,
    event_format      TEXT,      -- conventional | sprint_qualifying | sprint_shootout
    event_date        TEXT,      -- UTC date, ISO
    meeting_key       INTEGER,   -- OpenF1 meeting (NULL until practice step runs)
    expected_size     INTEGER,   -- drivers expected on this grid (20 or 22)
    n_starters        INTEGER,   -- rows actually in results
    PRIMARY KEY (year, round)
);

-- driver_number <-> abbreviation for this race (join key provenance)
CREATE TABLE IF NOT EXISTS driver_numbers (
    year          INTEGER,
    round         INTEGER,
    driver        TEXT,
    driver_number INTEGER,
    PRIMARY KEY (year, round, driver)
);

-- race STATUS, one row per starter.
--
-- Deliberately NOT a column on results: results must stay exactly the 7
-- columns f1_baseline.py depends on (asserted by check [3] in
-- scripts/test_baseline_fetch.py). And position alone can never reveal a
-- retirement - FastF1 classifies retirees with a real position, verified on
-- all 54 non-'Finished' sprint rows, every one of which still carries a
-- sprint_position. Status is the only DNF signal there is.
--
-- Feature 7 of the 12 ("recent non-finish rate") is built from this. The row
-- set matches results 1:1 because fetch_race_status applies the same "did the
-- driver take part" test fetch_race does, so it joins cleanly on
-- (year, round, driver).
CREATE TABLE IF NOT EXISTS race_status (
    year    INTEGER,
    round   INTEGER,
    driver  TEXT,
    status  TEXT,       -- FastF1 Status: 'Finished', 'Retired', 'Accident', ...
    PRIMARY KEY (year, round, driver)
);

-- qualifying, one row per STARTER (left-joined onto results, so a driver who
-- set no lap still appears with has_qualifying_time = 0)
--
-- q_position IS FastF1's official Position. We tried ranking lap times
-- instead (derive_rank) and it was wrong: official beats the lap rank 277:14
-- against results.grid, and for 2025 R17 the published Q2 time for ANT is
-- faster than SAI's best yet SAI is classified P2 - so the Q1/Q2/Q3 columns
-- carry laps that never counted toward classification. Official Position can
-- contain ties (2023 R10: PER and BOT both 15) and gaps when a qualifier does
-- not start; both are real and kept. validate_positions(allow_ties=True)
-- downgrades them to warnings. q_position_official mirrors the raw FastF1
-- value for provenance.
CREATE TABLE IF NOT EXISTS qualifying (
    year                INTEGER,
    round               INTEGER,
    driver              TEXT,
    driver_number       INTEGER,
    team                TEXT,
    q_position          REAL,     -- FastF1 official Position, NULL if not classified
    q_position_official REAL,     -- same value, kept for provenance (may contain ties)
    q1_s                REAL,     -- seconds
    q2_s                REAL,
    q3_s                REAL,
    best_q_s            REAL,     -- min of the segments the driver set
    gap_to_pole_pct     REAL,     -- (best - pole) / pole * 100
    has_qualifying_time INTEGER,   -- 0/1 missing flag
    PRIMARY KEY (year, round, driver)
);

-- sprint RACE result (FastF1 'S'), one row per starter, sprint weekends only
CREATE TABLE IF NOT EXISTS sprint (
    year             INTEGER,
    round            INTEGER,
    driver           TEXT,
    driver_number    INTEGER,
    team             TEXT,
    sprint_position  REAL,     -- finishing position in the sprint
    sprint_status    TEXT,
    sprint_grid      REAL,     -- starting position; NULL if FastF1 omits it
    sprint_points    REAL,
    has_sprint_result INTEGER,  -- 0/1
    PRIMARY KEY (year, round, driver)
);

-- practice pace, one row per STARTER per race (Source: OpenF1, own module so
-- the source can be swapped later - FastF1 lap data needs an F1 account).
--
-- n_sessions is how many practice sessions exist for this weekend (3 on a
-- conventional weekend, 1 on a sprint weekend - verified: sprint weekends
-- have exactly one practice, which is FP1). best_practice_s is the fastest
-- valid lap across ALL practice sessions of the weekend, with null lap
-- durations and pit-out laps excluded (per spec).
CREATE TABLE IF NOT EXISTS practice (
    year                INTEGER,
    round               INTEGER,
    driver              TEXT,
    driver_number       INTEGER,
    team                TEXT,
    n_sessions          INTEGER,   -- practice sessions found (0 => missing flag)
    best_practice_s     REAL,      -- fastest valid lap, seconds; NULL if none
    practice_rank       REAL,      -- DERIVED rank of best_practice_s, 1 = fastest
    laps_completed      INTEGER,   -- every lap row incl. pit-out (per spec)
    pit_out_laps        INTEGER,   -- how many of those were pit-out
    gap_to_best_pct     REAL,      -- (best - session_best) / session_best * 100
    has_practice_lap    INTEGER,   -- 0/1 missing flag
    PRIMARY KEY (year, round, driver)
);

-- sprint qualifying one-lap speed (OpenF1 'Sprint Qualifying' laps).
--
-- FastF1's SQ session is ALWAYS empty (verified 18/18) or raises ValueError
-- (6 sprint_shootout weekends), because Ergast has no sprint-qualifying data.
-- So the sprint-weekend one-lap-speed feature comes from OpenF1 instead.
CREATE TABLE IF NOT EXISTS sprint_qualifying (
    year                INTEGER,
    round               INTEGER,
    driver              TEXT,
    driver_number       INTEGER,
    team                TEXT,
    best_sq_s           REAL,      -- fastest valid lap; NULL if none
    sq_rank             REAL,      -- DERIVED rank of best_sq_s, 1 = fastest
    laps                INTEGER,
    gap_to_best_pct     REAL,
    has_sq_lap          INTEGER,   -- 0/1 missing flag
    PRIMARY KEY (year, round, driver)
);

-- which fetch steps produced real data for a race
CREATE TABLE IF NOT EXISTS fetch_log (
    year    INTEGER,
    round   INTEGER,
    step    TEXT,      -- race | race_status | qualifying | sprint | practice | sprint_qualifying
    nrows   INTEGER,
    run_at  TEXT,
    PRIMARY KEY (year, round, step)
);

-- OBSERVED race-day weather (Phase 6b). One row per RACE, not per driver:
-- every car in a race shares the sky. `source` records where the numbers
-- came from so any value can be traced back to its provider.
CREATE TABLE IF NOT EXISTS weather (
    year          INTEGER,
    round         INTEGER,
    event_date    TEXT,   -- the race date, i.e. the day the lookup used
    lat           REAL,
    lon           REAL,
    temp_c        REAL,   -- temperature_2m_mean        (deg C)
    humidity_pct  REAL,   -- relative_humidity_2m_mean  (%)
    rain_mm       REAL,   -- rain_sum                   (mm, race day)
    wind_kmh      REAL,   -- wind_speed_10m_max         (km/h)
    source        TEXT,
    PRIMARY KEY (year, round)
);

-- A forecast WRITTEN BEFORE THE RACE, kept so it can be scored afterwards.
--
-- Why its own table: `results` is the authority for what happened and must
-- keep exactly the 7 columns f1_baseline.py depends on, so a prediction can
-- never live there. This table holds only what the model said, and nothing
-- here is ever updated once written - `created_at` is the evidence that the
-- prediction predates the result, and score_forecast refuses to report a run
-- whose created_at is not before `race_start_utc`.
--
-- One row per driver per (year, round, mode): the same weekend can carry both
-- an early forecast (written before qualifying) and a full one (written after
-- it), and they are different predictions that must not overwrite each other.
--
-- `pred` is the raw Ridge output, which is what MAE is scored on everywhere
-- else in this project; `pred_pos` is its 1..N ordering, which is what the
-- winner and podium hit rates use. Storing both keeps the two definitions
-- from being confused at scoring time.
CREATE TABLE IF NOT EXISTS forecasts (
    year            INTEGER,
    round           INTEGER,
    mode            TEXT,        -- early | full
    model_version   TEXT,        -- estimator/config label, see model.MODEL_VERSION
    created_at      TEXT,        -- UTC ISO8601, when this forecast was written
    race_start_utc  TEXT,        -- UTC ISO8601 of lights out (from schedule)
    driver          TEXT,
    team            TEXT,
    pred            REAL,        -- raw model output; MAE is scored on this
    pred_pos        INTEGER,     -- 1..N ordering of `pred`, 1 = predicted winner
    grid_pred       REAL,        -- the GRID BASELINE's call for this driver,
                                 -- saved alongside so both are scored later
    features        TEXT,        -- JSON list of feature names used
    alpha           REAL,        -- Ridge alpha actually used
    n_train_races   INTEGER,     -- races the model was fitted on
    note            TEXT,        -- provenance, e.g. practice-only-after-Q
    PRIMARY KEY (year, round, mode, driver)
);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA)
    _migrate(con)
    con.commit()
    return con


def _migrate(con: sqlite3.Connection) -> None:
    """Add columns introduced after a table was first created.

    SQLite cannot ADD COLUMN inside CREATE TABLE IF NOT EXISTS, and this
    project evolves one phase at a time, so each new column is appended here
    instead of forcing the user to delete f1.db and re-download everything.
    """
    existing = {
        row[1]
        for row in con.execute("PRAGMA table_info(qualifying)").fetchall()
    }
    if "q_position_official" not in existing:
        # place it right after q_position for readability
        con.execute("ALTER TABLE qualifying ADD COLUMN q_position_official REAL")
        log.info("migrated: qualifying.q_position_official added")

    # `forecasts` columns introduced with the scoring flow. ALTER TABLE can
    # only append, so a migrated table and a freshly created one can differ
    # in column ORDER - which is exactly why every INSERT in this project
    # names its columns explicitly.
    fc_cols = {
        row[1]
        for row in con.execute("PRAGMA table_info(forecasts)").fetchall()
    }
    wanted = (("model_version", "TEXT"), ("grid_pred", "REAL"),
              ("note", "TEXT"))
    missing = [c for c, _t in wanted if c not in fc_cols]
    if missing:
        n = con.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0]
        if n:
            # Never ALTER a table that already holds forecasts: the new
            # columns would be NULL on every existing row, and a forecast
            # without its model_version or grid_pred cannot be scored
            # against one that has them. Refuse instead of degrading.
            raise RuntimeError(
                f"forecasts is missing {missing} but already holds {n} "
                "row(s); refusing to ALTER because those rows would carry "
                "NULL for columns a new forecast would have filled")
        for c, t in wanted:
            if c in missing:
                con.execute(f"ALTER TABLE forecasts ADD COLUMN {c} {t}")
        log.info("migrated: forecasts added %s", ", ".join(missing))


def step_done(con: sqlite3.Connection, year: int, round_: int, step: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM fetch_log WHERE year=? AND round=? AND step=?",
        (year, round_, step),
    ).fetchone()
    return row is not None


def log_step(con: sqlite3.Connection, year: int, round_: int, step: str,
             nrows: int) -> None:
    from datetime import datetime, timezone
    con.execute(
        "INSERT OR REPLACE INTO fetch_log (year, round, step, nrows, run_at)"
        " VALUES (?,?,?,?,?)",
        (year, round_, step, nrows,
         datetime.now(timezone.utc).isoformat(timespec="seconds")),
    )
    con.commit()


def starters(con: sqlite3.Connection, year: int, round_: int) -> list[sqlite3.Row]:
    """Drivers that took part in the race, in finish order."""
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT driver, team, grid, finish FROM results "
        "WHERE year=? AND round=? ORDER BY finish",
        (year, round_),
    ).fetchall()
    return rows
