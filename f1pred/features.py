"""Build the feature frame: one row per (year, round, driver).

Originally written for Phase 3; Phase 6a appends the six sprint columns and
Phase 6b the seven weather columns, kept OUTSIDE ``ALL_FEATURES`` so every
already-accepted Phase 3/4/5 number stays exactly as reported.

WHY IT IS SHAPED THIS WAY
-------------------------
* Every column is knowable BEFORE the race starts. Nothing here reads the
  target (results.finish) of the same race.
* "Recent" form uses ``shift(1)`` inside a per-driver group, so a row only
  ever sees races strictly before its own. That is the whole leakage defence.
* A team has TWO drivers per race, so form for teams is collapsed to one row
  per (team, race) BEFORE shifting - otherwise shift(1) would reach the team's
  OTHER driver in the SAME race and leak the target. See build_features().
* Defaults are constants that need no dataset statistics: mid-field is derived
  from that race's own field size, and the non-finish default is 0.0. Nothing
  computes a mean over all 1816 rows, which would leak future results.

THE 12 FEATURES (spec line 35) and their groups (spec line 82)
--------------------------------------------------------------
group "grid_form"  (1) : grid, driver_form, team_form, non_finish_rate
group "practice"   (2) : practice_pos, practice_gap_pct, practice_laps_30,
                         no_practice_time
group "qualifying" (3) : q_position, q_gap_pct, no_q_time, on_pole
groups "sprint" (4) and "weather" (5) are Phase 6.

"Recent non-finish rate" is not named in any group on spec line 82, so it is
placed with grid_form: like driver_form and team_form it is derived purely
from past races. That assumption is stated rather than buried.

FORMS THE SPEC LEFT UNKNOWNS (line 53: "do not assume") - our choices:
  * form window  = FORM_WINDOW = 5 previous races
  * non-finish   = status NOT in {Finished, Lapped}
  * debut form   = mid-field, (field_n + 1) / 2
  * debut rate   = 0.0
"""
from __future__ import annotations

import logging
import sqlite3

import pandas as pd

log = logging.getLogger(__name__)

# Previous races counted by "recent" form. The spec does not state a window.
FORM_WINDOW = 5

# Statuses that mean the driver REACHED THE CHEQUERED FLAG. 'Lapped' is a
# finish - the driver is classified, just a lap down. Verified against all
# 1816 stored statuses: Finished 1136, Lapped 414, and everything else
# (Retired 232, Did not start 16, Disqualified 10, Accident 3, Withdrew 2,
# Collision damage 2, Undertray 1) is a genuine non-finish.
FINISHING_STATUSES = frozenset({"Finished", "Lapped"})

TARGET = "finish"

# Column groups, added to the model one at a time (spec line 82).
FEATURE_GROUPS: dict[str, list[str]] = {
    "grid_form": ["grid", "driver_form", "team_form", "non_finish_rate"],
    "practice": ["practice_pos", "practice_gap_pct", "practice_laps_30",
                 "no_practice_time"],
    "qualifying": ["q_position", "q_gap_pct", "no_q_time", "on_pole"],
}

ALL_FEATURES: list[str] = [c for g in FEATURE_GROUPS.values() for c in g]

# ---- MODE FEATURE SETS (spec line 40) -------------------------------------
# Early mode is what you know after the LAST PRACTICE session: recent form and
# practice pace. `grid` is deliberately NOT early: the starting grid only
# exists once qualifying - and any penalty - has been published, so using it
# before then would be reading the future.
EARLY_FEATURES: list[str] = [
    "driver_form", "team_form", "non_finish_rate",
    "practice_pos", "practice_gap_pct", "practice_laps_30", "no_practice_time",
]

# Full mode = early + qualifying + grid + pole (spec line 40, "adds qualifying
# and grid features and the pole effect").
FULL_FEATURES: list[str] = list(ALL_FEATURES)

assert set(EARLY_FEATURES) < set(FULL_FEATURES), \
    "early mode must be a strict subset of full mode"
assert set(FULL_FEATURES) - set(EARLY_FEATURES) == \
    set(FEATURE_GROUPS["qualifying"]) | {"grid"}, \
    "full mode must add exactly qualifying + grid"

# ---- GROUPS FOR PERMUTATION IMPORTANCE (spec line 80) ----------------------
# This is a DIFFERENT grouping from FEATURE_GROUPS and that is on purpose:
# FEATURE_GROUPS records the order features are added to the ladder, where
# grid legitimately travels with the form features as one rung. Permutation
# importance asks how much walk-forward MAE rises when a BLOCK of
# information is destroyed, so grid is separated out - "where you start" and
# "how well you have been doing" are different pieces of evidence.
#   grid       : 1 feature   - where the car lines up
#   form       : 3 features  - driver/team recent results + DNF rate
#   practice   : 4 features  - Friday/Saturday pace and running
#   qualifying : 4 features  - Saturday pace, gaps, pole flag
# The four blocks cover all 12 features exactly once, no overlap.
PERM_GROUPS: dict[str, list[str]] = {
    "grid": ["grid"],
    "form": ["driver_form", "team_form", "non_finish_rate"],
    "practice": list(FEATURE_GROUPS["practice"]),
    "qualifying": list(FEATURE_GROUPS["qualifying"]),
}

assert sorted(c for v in PERM_GROUPS.values() for c in v) == \
    sorted(ALL_FEATURES), "PERM_GROUPS must partition ALL_FEATURES"

# ---- PHASE 6a: SPRINT (spec line 91) ---------------------------------------
# Deliberately NOT folded into FEATURE_GROUPS / ALL_FEATURES. ALL_FEATURES is
# the locked 12-feature set that every already-accepted Phase 3 and Phase 4
# number is computed on - run_phase3, run_phase4, check_features,
# check_coef_signs and diagnose_permutation all call
# walk_forward(df, ALL_FEATURES). Adding sprint there would silently rewrite
# results that have already been signed off. Sprint is therefore measured as
# an ADDITIVE stage on top of the 12.
#
# All six are pre-race information for the race being predicted: sprint
# qualifying and the sprint race are held on the Saturday, the Grand Prix on
# the Sunday. `has_sprint` comes from `sessions.event_format` (a calendar
# fact published before the weekend), NOT from whether the sprint table has
# rows - the latter would only become true once the sprint had run.
#
# `no_sprint_result` is an exact linear duplicate of (1 - has_sprint) in this
# dataset: no sprint has ever had a starter without a result, so it carries
# no new information and Ridge will split that weight arbitrarily between the
# two. It is kept because the spec asks for a missing flag; the duplication
# is reported rather than quietly dropped (same policy as the q_position /
# q_gap_pct collinearity already documented).
SPRINT_FEATURES: list[str] = [
    "has_sprint",         # 1 = this weekend has a sprint (calendar fact)
    "sq_rank",            # sprint qualifying position
    "sq_gap_pct",         # gap to the fastest sprint-qualifying lap (%)
    "no_sq_lap",          # 1 = driver set no sprint-qualifying lap
    "sprint_pos",         # sprint race result
    "no_sprint_result",   # 1 = no sprint race result recorded
]

# ---- PHASE 6b: WEATHER (spec line 64) --------------------------------------
# Four measured quantities plus exactly THREE interaction terms, all chosen
# BEFORE any MAE was computed - the spec asks for "only a few pre-chosen
# interaction terms, not a full cross-product". Stating the reason now is
# what makes the choice falsifiable later instead of data-mined:
#   rain_x_q_position      wet conditions erase the advantage of starting up
#                          front, so grid place should matter less in rain
#   rain_x_non_finish_rate a driver already prone to retiring should be more
#                          likely to retire when it is slippery
#   wind_x_grid            a car running in traffic is in disturbed air for
#                          longer, and crosswinds act hardest on that car
# Anything else would be a search over combinations, which is how you
# manufacture an improvement that does not survive next season.
WEATHER_FEATURES: list[str] = [
    "temp_c", "humidity_pct", "rain_mm", "wind_kmh",
    "rain_x_q_position", "rain_x_non_finish_rate", "wind_x_grid",
]

# Everything build_features() ALWAYS produces, in ladder order.
BUILT_FEATURES: list[str] = list(ALL_FEATURES) + list(SPRINT_FEATURES)

# The complete Phase 6 set. Weather is conditional - see the note where it
# is merged: observed weather only exists once the date has passed, so a
# future race has none and its columns are deliberately absent rather than
# filled with a made-up number.
PHASE6_FEATURES: list[str] = list(BUILT_FEATURES) + list(WEATHER_FEATURES)


def _forecast_spine(con: sqlite3.Connection, year: int, rnd: int,
                    official_grid: dict[str, int] | None = None) -> pd.DataFrame:
    """Starter rows for a weekend that has NOT run yet.

    ``results`` is the spine of every normal build and it does not exist for
    a race still to come, so the field is taken from whichever pre-race
    sessions do exist - qualifying and/or practice.

    ``finish`` is NULL on purpose: a result cannot be known before the race
    by any means, so those rows are predicted but never scored.

    ``grid`` comes from ``qualifying.q_position`` rather than being left NULL.
    Our tables only record a grid alongside a result, so there is no
    ``results.grid`` to read yet - but qualifying order IS the starting grid
    before penalties are applied. On history it matches ``results.grid``
    exactly for 1377 of 1816 rows, and every row where it differs is a
    penalty that shifted the order behind it (2023 R2 LEC: qualified 2nd,
    started 12th; ALO/GAS/HAM and the rest each move up one). Leaving it
    NULL would be worse than wrong: ``build_features`` fills a NULL grid
    with ``field_n + 1``, which would hand all 22 cars the same value,
    switch the grid feature off entirely and make the grid baseline call
    every driver 23rd. Drivers who never set a qualifying lap have no
    ``q_position`` and do fall back to that fill, exactly as they do on a
    raced weekend.

    If ``official_grid`` is provided (from --grid-file), it OVERRIDES the
    qualifying-derived grid for the forecast rows. This is the real starting
    grid after penalties, which is what the `grid` feature means in training.
    The qualifying order is still recorded separately as `q_position`.
    """
    q = pd.read_sql_query(
        "SELECT driver, team, q_position AS grid FROM qualifying"
        " WHERE year=? AND round=?",
        con, params=(year, rnd))
    p = pd.read_sql_query(
        "SELECT driver, team FROM practice WHERE year=? AND round=?",
        con, params=(year, rnd))
    p["grid"] = float("nan")
    if q.empty and p.empty:
        raise ValueError(
            f"no qualifying and no practice rows for {year} R{rnd}, so the "
            f"starting field cannot be determined - there is nothing to "
            f"forecast with.")
    # qualifying rows come first, so drop_duplicates(keep="first") below
    # prefers a driver's qualifying grid over the practice placeholder.
    both = pd.concat([q, p], ignore_index=True)
    # One driver must be one row: the same name appearing in both sessions is
    # one person, not two starters.
    clash = both.groupby("driver")["team"].nunique()
    if (clash > 1).any():
        log.warning("_forecast_spine: team differs between sessions for %s",
                    list(clash[clash > 1].index))
    spine = both.drop_duplicates("driver", keep="first")

    # Apply official grid if provided - this is the real starting grid after
    # penalties. The qualifying order remains in q_position (set later in
    # build_features). We merge on driver name (uppercase for safety).
    if official_grid is not None:
        og = {k.upper(): v for k, v in official_grid.items()}
        spine = spine.copy()
        spine["grid"] = spine["driver"].str.upper().map(og)
        # Any driver not in the official grid falls back to qualifying order
        # (which is already in the 'grid' column from qualifying.q_position)
        missing = spine["grid"].isna()
        if missing.any():
            log.info("_forecast_spine: %d driver(s) not in official_grid, "
                     "falling back to qualifying order", int(missing.sum()))

    out = pd.DataFrame({
        "year": year,
        "round": rnd,
        "driver": spine["driver"].to_numpy(),
        "team": spine["team"].to_numpy(),
        "grid": pd.to_numeric(spine["grid"], errors="coerce").to_numpy(),
        "finish": float("nan"),
    })
    return out


def build_features(con: sqlite3.Connection,
                   form_window: int = FORM_WINDOW,
                   forecast_race: tuple[int, int] | None = None,
                   official_grid: dict[str, int] | None = None) -> pd.DataFrame:
    """Return the full feature frame, one row per starter per race.

    ``forecast_race=(year, round)`` adds the spine of a weekend that has not
    run yet: no results row, therefore nothing to score it against. Those
    rows carry ``finish = NULL`` - they are PREDICTED but never SCORED - and
    every form feature still works, because the frame is ordered by race_idx
    and the forecast row is each driver's LAST row, so ``shift(1)`` reads the
    previous race rather than the race being forecast.

    With the argument left as None (every existing caller) no forecast rows
    are appended, so the output is exactly the history frame: one row per
    results row, no NULL target.
    """
    res = pd.read_sql_query(
        "SELECT year, round, driver, team, grid, finish FROM results", con)

    n_forecast = 0
    forecast_key: tuple[int, int] | None = None
    if forecast_race is not None:
        fy, fr = forecast_race
        if ((res["year"] == fy) & (res["round"] == fr)).any():
            raise ValueError(
                f"{fy} R{fr} already has results rows, so it has already run "
                f"- that is a normal race, not a forecast. Call "
                f"build_features without forecast_race.")
        last = res[["year", "round"]].drop_duplicates().sort_values(
            ["year", "round"]).iloc[-1]
        if (int(last["year"]), int(last["round"])) >= (fy, fr):
            raise ValueError(
                f"forecast race {fy} R{fr} is not the latest race in this "
                f"database (latest is {int(last['year'])} "
                f"R{int(last['round'])}). Forecasting a race in the middle "
                f"would train later, already-run races on its NULL result.")
        spine = _forecast_spine(con, fy, fr, official_grid=official_grid)
        res = pd.concat([res, spine], ignore_index=True)
        n_forecast, forecast_key = len(spine), (fy, fr)
        log.info("build_features: forecast race %d R%d - %d starter row(s) "
                 "with no result; predicted, never scored", fy, fr, n_forecast)

    qual = pd.read_sql_query(
        "SELECT year, round, driver, q_position, gap_to_pole_pct,"
        "       has_qualifying_time FROM qualifying", con)
    prac = pd.read_sql_query(
        "SELECT year, round, driver, practice_rank, gap_to_best_pct,"
        "       laps_completed, has_practice_lap FROM practice", con)
    stat = pd.read_sql_query(
        "SELECT year, round, driver, status FROM race_status", con)
    # Phase 6a. `gap_to_best_pct` and `sprint_position` are ALIASED here on
    # purpose: `practice` already contributes a column called
    # `gap_to_best_pct`, and an unaliased duplicate would come back as
    # gap_to_best_pct_x / _y and quietly break every downstream column name.
    sq = pd.read_sql_query(
        "SELECT year, round, driver, sq_rank,"
        "       gap_to_best_pct AS sq_gap_pct, has_sq_lap"
        " FROM sprint_qualifying", con)
    spr = pd.read_sql_query(
        "SELECT year, round, driver, sprint_position AS sprint_pos,"
        "       has_sprint_result FROM sprint", con)
    sess = pd.read_sql_query(
        "SELECT year, round, event_format FROM sessions", con)

    # left joins keep results as the spine: 1816 rows in, 1816 rows out.
    # validate= catches a duplicated key instead of silently fanning out.
    df = res.merge(qual, on=["year", "round", "driver"], how="left",
                   validate="one_to_one")
    df = df.merge(prac, on=["year", "round", "driver"], how="left",
                  validate="one_to_one")
    df = df.merge(stat, on=["year", "round", "driver"], how="left",
                  validate="one_to_one")
    df = df.merge(sq, on=["year", "round", "driver"], how="left",
                  validate="one_to_one")
    df = df.merge(spr, on=["year", "round", "driver"], how="left",
                  validate="one_to_one")
    # event_format is per RACE, so both drivers of a team get the same value:
    # many_to_one, not one_to_one.
    df = df.merge(sess, on=["year", "round"], how="left",
                  validate="many_to_one")
    if df["event_format"].isna().any():
        miss = (df.loc[df["event_format"].isna(), ["year", "round"]]
                .drop_duplicates())
        where = ", ".join(f"{int(y)} R{int(r)}"
                          for y, r in miss.itertuples(index=False))
        raise ValueError(
            f"sessions has no event_format for {where}. Without it there is "
            f"no way to know whether that weekend has a sprint, and guessing "
            f"would put a wrong 0/1 on every car in it.")
    df["has_sprint"] = (df["event_format"] != "conventional").astype(int)
    df = df.drop(columns=["event_format"])

    # ---- Phase 6b: observed race-day weather ------------------------------
    # Weather is ONE row per race, hence many_to_one like event_format.
    #
    # It is merged only when it exists for EVERY race in this frame. Observed
    # weather only exists once the date has passed, so a race still to come
    # has none - and inventing a placeholder would be a lie, while refusing
    # outright would break forecasting for a reason that has nothing to do
    # with racing. When it is missing the columns are missing too, and a
    # caller that needs them (the Phase 6 ladder) checks for them explicitly.
    wx = pd.read_sql_query(
        "SELECT year, round, temp_c, humidity_pct, rain_mm, wind_kmh"
        " FROM weather", con)
    have_wx = {(int(y), int(r)) for y, r in
               zip(wx["year"], wx["round"])}
    want_wx = {(int(y), int(r)) for y, r in
               zip(df["year"], df["round"])}
    missing_wx = sorted(want_wx - have_wx)
    if missing_wx:
        log.warning(
            "build_features: no observed weather for %d race(s) %s - the "
            "weather columns are omitted. Observed weather only exists "
            "after the date has passed; a future race needs a supplied "
            "weather forecast instead.",
            len(missing_wx),
            ", ".join(f"{y} R{r}" for y, r in missing_wx[:5]))
    else:
        df = df.merge(wx, on=["year", "round"], how="left",
                      validate="many_to_one")

    n_missing_status = int(df["status"].isna().sum())
    if n_missing_status and forecast_key is not None:
        # The forecast race has no status because it has not run: expected.
        fmask = ((df["year"] == forecast_key[0])
                 & (df["round"] == forecast_key[1]))
        n_missing_status -= int((fmask & df["status"].isna()).sum())
    if n_missing_status:
        # race_status is verified 1:1 with results, so this should be 0.
        log.warning("build_features: %d row(s) have no race status",
                    n_missing_status)

    # ---- chronological race index, 1..89 ---------------------------------
    races = (df[["year", "round"]].drop_duplicates()
             .sort_values(["year", "round"]).reset_index(drop=True))
    races["race_idx"] = range(1, len(races) + 1)
    df = df.merge(races, on=["year", "round"], how="left",
                  validate="many_to_one")

    # cars actually in THIS race - used for every "start behind everyone" fill
    field = (df.groupby(["year", "round"]).size().rename("field_n")
             .reset_index())
    df = df.merge(field, on=["year", "round"], validate="many_to_one")
    mid_field = (df["field_n"] + 1) / 2.0        # e.g. 20 cars -> 10.5

    # ---- leakage-free "recent" form --------------------------------------
    # Each driver appears exactly once per round (PK year,round,driver), so
    # inside a driver group shift(1) is precisely "the previous race I ran".
    d = df.sort_values(["driver", "race_idx"])
    df["driver_form"] = (
        d.groupby("driver")["finish"]
         .transform(lambda s: s.shift(1)
                    .rolling(form_window, min_periods=1).mean())
    )
    # Non-finish rate over the SAME previous races. Unknown status counts as
    # "did finish" (0) rather than as a non-finish; verified 0 unknown rows.
    known = d["status"].notna()
    d_nonfin = (known & ~d["status"].isin(FINISHING_STATUSES)).astype(int)
    df["non_finish_rate"] = (
        d_nonfin.groupby(d["driver"])
                .transform(lambda s: s.shift(1)
                           .rolling(form_window, min_periods=1).mean())
    )

    # Team form MUST collapse first: a team has two rows per race, so a
    # row-level shift(1) inside a team would read the other driver's finish in
    # THIS race - target leakage. One row per (team, race), then shift.
    tr = (df[["team", "race_idx", "finish"]]
          .groupby(["team", "race_idx"], as_index=False)["finish"].mean()
          .sort_values(["team", "race_idx"]))
    tr["team_form"] = (
        tr.groupby("team")["finish"]
          .transform(lambda s: s.shift(1)
                     .rolling(form_window, min_periods=1).mean())
    )
    df = df.merge(tr[["team", "race_idx", "team_form"]],
                  on=["team", "race_idx"], how="left",
                  validate="many_to_one")

    # ---- missing-history defaults (constants, so no leakage) -------------
    df["driver_form"] = df["driver_form"].fillna(mid_field)
    df["team_form"] = df["team_form"].fillna(mid_field)
    df["non_finish_rate"] = df["non_finish_rate"].fillna(0.0)

    # ---- grid: pit-lane / no-grid start ----------------------------------
    # FastF1 reports GridPosition 0 or NULL for a pit-lane start. Such a car
    # lines up behind every grid slot, so it becomes field_n + 1. Verified on
    # the only 5 such rows (2023 R13 MAG, 2023 R15 STR, 2023 R19 STR,
    # 2024 R20 OCO, 2026 R19 HIR) - all 5 hold a real q_position, i.e. they
    # qualified and then started from the pit lane.
    bad_grid = df["grid"].isna() | (df["grid"] <= 0)
    df["grid"] = df["grid"].mask(bad_grid, df["field_n"] + 1)
    n_grid = int(bad_grid.sum())
    if n_grid:
        log.info("build_features: %d grid value(s) were 0/NULL - filled "
                 "with field size + 1 (pit-lane start)", n_grid)

    # ---- qualifying features ---------------------------------------------
    # 6 rows have no q_position AND no time (they never set a lap). They carry
    # no_q_time = 1, so the flag carries the signal and the fill is inert.
    df["q_position"] = df["q_position"].fillna(df["field_n"] + 1)
    # gap is NULL for the 22 rows without a qualifying time. Fill 0 + flag:
    # with no_q_time = 1 the model can separate "genuinely on pole pace"
    # (gap 0, flag 0) from "unknown" (gap 0, flag 1).
    df["q_gap_pct"] = df["gap_to_pole_pct"].fillna(0.0)
    df["no_q_time"] = 1 - df["has_qualifying_time"].fillna(0).astype(int)
    # computed from the RAW position so an unfilled row is never pole
    df["on_pole"] = (df["q_position"].notna()
                     & (df["q_position"] == 1)).astype(int)

    # ---- practice features ------------------------------------------------
    # practice_rank is NULL only for the 2 rows that set no practice lap.
    df["practice_pos"] = df["practice_rank"].fillna(df["field_n"] + 1)
    df["practice_gap_pct"] = df["gap_to_best_pct"].fillna(0.0)
    df["practice_laps_30"] = df["laps_completed"].fillna(0) / 30.0
    df["no_practice_time"] = 1 - df["has_practice_lap"].fillna(0).astype(int)

    # ---- Phase 6a: sprint --------------------------------------------------
    # Same fill conventions as q_position / q_gap_pct / practice_pos so the
    # three pace groups stay comparable: an unknown position means "behind
    # every classified car" (field_n + 1), an unknown gap means 0.0 plus a
    # flag that says the 0.0 is a fill and not a measured zero.
    #
    # A non-sprint weekend has no rows in either sprint table, so all four
    # of its sprint columns land exactly on those fills - that is the
    # intended encoding of "there was no sprint here", not missing data.
    bad_sq = df["sq_rank"].isna() | (df["sq_rank"] <= 0)
    df["sq_rank"] = df["sq_rank"].mask(bad_sq, df["field_n"] + 1)
    df["sq_gap_pct"] = df["sq_gap_pct"].fillna(0.0)
    df["no_sq_lap"] = 1 - df["has_sq_lap"].fillna(0).astype(int)

    bad_sp = df["sprint_pos"].isna() | (df["sprint_pos"] <= 0)
    df["sprint_pos"] = df["sprint_pos"].mask(bad_sp, df["field_n"] + 1)
    df["no_sprint_result"] = 1 - df["has_sprint_result"].fillna(0).astype(int)

    # the raw 0/1 source columns are only inputs to the flags above
    df = df.drop(columns=["has_sq_lap", "has_sprint_result"])

    # ---- Phase 6b: three pre-chosen weather interactions ------------------
    # Only reached when the weather merge happened. The interactions are
    # formed from RAW values; every column then passes through the same
    # StandardScaler fitted inside walk_forward, so the product's scale is
    # handled there exactly like any other feature.
    if "rain_mm" in df.columns:
        # grid, q_position and non_finish_rate are all already filled above,
        # so none of these products can be NULL.
        df["rain_x_q_position"] = df["rain_mm"] * df["q_position"]
        df["rain_x_non_finish_rate"] = df["rain_mm"] * df["non_finish_rate"]
        df["wind_x_grid"] = df["wind_kmh"] * df["grid"]

    # Sorted by race then DRIVER, deliberately NOT by finish: a constant or
    # tied prediction breaks ties by row order, and ordering rows by finish
    # would then hand the model the winner for free. Driver order is
    # independent of the target.
    df = df.sort_values(["race_idx", "driver"]).reset_index(drop=True)

    # ---- assertions: catch a regression before it poisons a result --------
    assert len(df) == len(res), \
        f"row count drifted: {len(df)} vs {len(res)}"

    # One row per (year, round, driver). This guard replaces a hard-coded
    # `assert len(df) == 1816`, which was the Phase 1 snapshot of 89 races.
    # That number could not live here: the moment the 90th race has a result
    # it would fire and every command in the project would stop working -
    # including the post-race scoring this module exists to feed. The
    # guarantee the constant was standing in for is that a join must never
    # multiply rows, which is stated here in a form that stays true as the
    # database grows, and it applies to the forecast path as well.
    dup = df.duplicated(["year", "round", "driver"], keep=False)
    assert not dup.any(), (
        f"join produced {int(dup.sum())} duplicate (year, round, driver) rows")

    if forecast_key is None:
        # DNS drivers have NULL finish; they are excluded from scoring in walk_forward
        pass
    else:
        # history keeps its guarantee; forecast rows must be the opposite
        fmask = ((df["year"] == forecast_key[0])
                 & (df["round"] == forecast_key[1]))
        assert df.loc[fmask, "finish"].isna().all(), \
            "forecast rows must carry NULL finish (predicted, not scored)"
    # Weather is present only when its merge happened (a race whose date has
    # not passed has no observed weather), so the required set is decided by
    # whether the columns exist - never by silently allowing NULLs in ones
    # that ARE supposed to be there. A NULL here would be dropped by
    # scikit-learn and quietly change the row count.
    weather_here = "temp_c" in df.columns
    required = list(PHASE6_FEATURES) if weather_here else list(BUILT_FEATURES)
    for col in required:
        assert col in df.columns, f"feature {col} missing"
        assert df[col].notna().all(), f"feature {col} has NULLs"
    assert df[required].select_dtypes("object").empty, \
        "a feature is not numeric"
    # the 12 base features must be untouched by the Phase 6 additions
    assert set(ALL_FEATURES) < set(df.columns), "base feature set shrank"
    return df


def describe() -> pd.DataFrame:
    """Small table for reports: group -> features."""
    rows = []
    for g, cols in FEATURE_GROUPS.items():
        for c in cols:
            rows.append({"group": g, "feature": c})
    return pd.DataFrame(rows)


if __name__ == "__main__":                       # pragma: no cover
    import sys

    from . import db

    con = db.connect()
    con.row_factory = sqlite3.Row
    frame = build_features(con)
    con.close()
    print(frame.shape)
    print(frame[["year", "round", "driver", TARGET] + ALL_FEATURES].head(10)
          .to_string(index=False))
    sys.exit(0)
