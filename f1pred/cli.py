"""Phase 5: early and full forecast modes behind one CLI (spec lines 40, 90).

Two modes, decided by WHAT DATA EXISTS for the weekend, not by hope:

  early  - after the last practice session: recent form + practice pace.
           7 features. NO `grid`: the starting grid only exists once
           qualifying and any penalties are published, so using it before
           then would read the future (spec line 74: features may only use
           information available at the forecast time for that mode).
  full   - after qualifying: early + q_position, q_gap_pct, no_q_time,
           on_pole, grid. 12 features.

Every mode prints:
  * which mode it used and WHY,
  * WARNING lines for anything unavailable that was dropped,
  * the top-3 and the full predicted order,
  * that mode's walk-forward MAE against the baselines it can honestly
    score (early mode has no grid, so it is not given the grid baseline),
  * a gap-vs-prediction scatter using the gap that mode actually has -
    practice for early, qualifying for full.

Usage:
    python -m f1pred.cli                       # latest race, auto mode
    python -m f1pred.cli --year 2026 --round 19
    python -m f1pred.cli --year 2026 --round 19 --mode early
    python -m f1pred.cli --db path/to/copy.db   # read a different database

Exit codes: 0 = forecast produced, 1 = refused (message says what is missing).
"""
from __future__ import annotations

import argparse
import math
import sys
import textwrap
from pathlib import Path

from . import db, features, forecast, model, report

# Get the active walk-forward function based on MODEL_VERSION
_walk_forward = model.get_walk_forward_fn()

# Early mode's comparators. The grid baseline needs the starting grid, which
# is exactly what early mode does not have (spec line 45).
# Re-pointed at model.py so forecast scoring uses the same lists without a
# circular import: cli imports forecast for --save, forecast must not import
# cli. Every use below is unchanged.
EARLY_BASELINES = model.EARLY_BASELINES
FULL_BASELINES = model.FULL_BASELINES

MODE_FEATURES = {
    "early": list(features.EARLY_FEATURES),
    "full": list(features.FULL_FEATURES),
}

# Which gap the scatter plots, per mode.
SCATTER = {
    "early": dict(x_col="practice_gap_pct", missing_col="no_practice_time",
                  x_label="practice gap to fastest lap (%)"),
    "full": dict(x_col="q_gap_pct", missing_col="no_q_time",
                 x_label="qualifying gap to fastest lap (%)"),
}


def _rule(title: str = "") -> None:
    print("=" * 78)
    if title:
        print(title)
        print("=" * 78)


def _wrap(text: str, indent: str = "  ") -> None:
    print(textwrap.fill(text, width=74, initial_indent=indent,
                        subsequent_indent=indent))


def _cap(have: int, total: int, noun: str) -> str:
    """'0 of 0 cars with a time' reads badly; say what actually happened."""
    if total == 0:
        return "none recorded (0 rows)"
    return f"{have} of {total} cars with a {noun}"


def _why(have: int, total: int, what: str) -> str:
    """Sentence fragment for a refusal: why this session cannot be used."""
    if total == 0:
        return f"{what} has not been recorded (0 rows)"
    if have == 0:
        return f"none of the {total} cars has usable {what}"
    return f"only {have} of {total} cars has usable {what}"


def probe(con, year: int, rnd: int) -> dict:
    """Count what pre-race data exists for one weekend.

    SUM() over no rows is NULL, hence the `or 0`.
    """
    q = con.execute(
        "SELECT COUNT(*), SUM(has_qualifying_time) FROM qualifying"
        " WHERE year=? AND round=?", (year, rnd)).fetchone()
    p = con.execute(
        "SELECT COUNT(*), SUM(has_practice_lap) FROM practice"
        " WHERE year=? AND round=?", (year, rnd)).fetchone()
    r = con.execute(
        "SELECT COUNT(*), SUM(grid IS NOT NULL AND grid > 0) FROM results"
        " WHERE year=? AND round=?", (year, rnd)).fetchone()
    return {
        "results": int(r[0] or 0),
        "grid_rows": int(r[1] or 0),
        "q_rows": int(q[0] or 0),
        "q_times": int(q[1] or 0),
        "p_rows": int(p[0] or 0),
        "p_laps": int(p[1] or 0),
    }


def choose_mode(info: dict, requested: str) -> tuple[str | None, list[str], list[str]]:
    """-> (mode or None, warnings, fatal reasons)."""
    warnings: list[str] = []
    fatal: list[str] = []

    has_q = info["q_times"] > 0
    has_p = info["p_laps"] > 0
    has_grid = info["grid_rows"] > 0

    if requested == "full":
        if not has_q:
            fatal.append(
                f"full mode needs qualifying, but "
                f"{_why(info['q_times'], info['q_rows'], 'qualifying')}. "
                f"There is nothing to build q_position / q_gap_pct / "
                f"on_pole from.")
            return None, warnings, fatal
        mode = "full"
    elif requested == "early":
        if not has_p:
            fatal.append(
                f"early mode needs practice, but "
                f"{_why(info['p_laps'], info['p_rows'], 'practice')}. "
                f"There is nothing to build practice_pos / practice_gap_pct "
                f"from.")
            return None, warnings, fatal
        mode = "early"
    else:                                     # auto
        if has_q:
            mode = "full"
        elif has_p:
            mode = "early"
        else:
            fatal.append(
                "neither qualifying nor practice exists for this weekend: "
                f"{_why(info['q_times'], info['q_rows'], 'qualifying')}; "
                f"{_why(info['p_laps'], info['p_rows'], 'practice')}. "
                "There is no pre-race evidence to forecast from.")
            return None, warnings, fatal

    if mode == "early":
        # Distinguish "missing" from "excluded on purpose" - telling the user
        # qualifying is unavailable when the banner above it says 22/22 would
        # be a flat contradiction.
        if info["q_times"] > 0:
            warnings.append(
                "qualifying EXISTS for this weekend but early mode excludes "
                "it deliberately - forecast-time features only. Pass "
                "--mode full (or auto) to use it.")
        else:
            warnings.append(
                "qualifying is unavailable, so these features were dropped: "
                + ", ".join(features.FEATURE_GROUPS["qualifying"]) + ".")
        if not has_grid:
            warnings.append(
                "'grid' is excluded from early mode BY POLICY - it is a "
                "practice-only feature set - so the grid baseline is not one "
                "of its comparators. That holds whether or not results.grid "
                "is populated; it is not a statement about missing data.")
        else:
            warnings.append(
                "'grid' is excluded from early mode BY POLICY - a "
                "practice-only set must not read a starting grid, because a "
                "genuinely early forecast is made before qualifying has run. "
                "The exclusion holds even though a grid value exists here.")
        if info["q_rows"] == 0:
            warnings.append(
                "no qualifying rows exist at all - if qualifying has not "
                "happened yet this is exactly the expected state.")
    else:
        if not has_grid:
            if info.get("forecast"):
                warnings.append(
                    "this race has not run, so `results` holds no starting "
                    "grid for it; 'grid' is taken from qualifying.q_position "
                    "- the official qualifying order - so every car that set "
                    "a lap carries a real slot and the grid baseline is "
                    "stored as `grid_pred` beside the prediction. Only a car "
                    "with no qualifying lap falls back to field size + 1.")
            else:
                warnings.append(
                    "qualifying exists but no car has a published grid slot; "
                    "'grid' is filled with field size + 1 (pit-lane/no-slot "
                    "handling) rather than 0.")
        if info["p_laps"] == 0:
            warnings.append("practice has no laps for this weekend.")
    return mode, warnings, fatal


def _banner(mode: str, year: int, rnd: int, info: dict, cols: list[str],
            requested: str, warnings: list[str]) -> None:
    _rule(f"MODE: {'EARLY (practice only)' if mode == 'early' else 'FULL (after qualifying)'}"
          f"   -  {year} R{rnd}")
    print(f"  requested --mode {requested}; chosen from the data actually present")
    print(f"  qualifying : {_cap(info['q_times'], info['q_rows'], 'time')}")
    print(f"  practice   : {_cap(info['p_laps'], info['p_rows'], 'lap')}")
    print(f"  features   : {len(cols)} -> {', '.join(cols)}")
    print(f"  baselines  : "
          f"{', '.join(EARLY_BASELINES if mode == 'early' else FULL_BASELINES)}")
    if info.get("forecast"):
        print("  RESULT     : none - this race has not run, so it is")
        print("               predicted without being scored")
    else:
        print(f"  grid       : {_cap(info['grid_rows'], info['results'], 'slot')}")
    for w in warnings:
        for i, line in enumerate(textwrap.wrap("WARNING: " + w, width=76)):
            print(f"  {line}" if i == 0 else f"      {line}")
    print()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m f1pred.cli",
        description="Race forecast in early (practice-only) or full "
                    "(post-qualifying) mode.")
    ap.add_argument("--year", type=int, help="race year (default: latest)")
    ap.add_argument("--round", type=int, help="race round (default: latest)")
    ap.add_argument("--mode", choices=("auto", "early", "full"),
                    default="auto",
                    help="auto (default) picks full when qualifying exists, "
                         "otherwise early")
    ap.add_argument("--db", default=None,
                    help="database file (default: f1.db)")
    ap.add_argument("--save", action="store_true",
                    help="write the predicted order to the `forecasts` "
                         "table, so it can be scored after the race. Only "
                         "meaningful for a race that has not run yet.")
    ap.add_argument("--fetch", action="store_true",
                    help="fetch this weekend's pre-race sessions (practice, "
                         "and qualifying once it has run) before forecasting. "
                         "Needs explicit --year and --round; never writes "
                         "to `results`.")
    ap.add_argument("--grid-file", default=None,
                    help="CSV file with official starting grid (after penalties) "
                         "for full mode. Columns: driver,grid_pos. Required for "
                         "full-mode --save; if absent, full mode refuses to save. "
                         "q_position is still derived from qualifying as a separate "
                         "feature. The grid in training always means the real "
                         "starting grid; this file provides it at forecast time.")
    args = ap.parse_args(argv)

    # Windows cp1252 cannot encode the medal emoji (see scripts/run_phase4.py)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    db_path = Path(args.db) if args.db else db.DB_PATH
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}")
        return 1

    con = db.connect(db_path)
    con.row_factory = None

    # ---------------------------------------------------------- fetch
    # Runs BEFORE the race is picked from `results`: an unrun weekend has no
    # results row, so the normal pick would never find it. This is the only
    # path that writes pre-race data for a race that has not happened, and
    # it still never touches `results` - that stays the job of the normal
    # fetch once the classification exists.
    if args.fetch:
        if args.year is None or args.round is None:
            print("ERROR: --fetch needs explicit --year and --round,")
            print("       because it fetches one specific weekend.")
            con.close()
            return 1
        from . import fetch as _fetch
        try:
            summary = _fetch.fetch_upcoming(con, args.year, args.round)
        except Exception as exc:                       # noqa: BLE001
            print(f"ERROR: fetch failed: {type(exc).__name__}: {exc}")
            con.close()
            return 1
        print(f"  fetched: {summary['event']} ({summary['status']})")
        print(f"    entrants {summary['entrants']}   practice "
              f"{summary['practice_rows']}   qualifying "
              f"{summary['qualifying_rows']}")
        if summary.get("expected_size") is not None:
            print(f"    expected field size {summary['expected_size']}")
        print()

    # ---------------------------------------------------------- pick race
    if args.year is not None and args.round is not None:
        target = (args.year, args.round)
    else:
        row = con.execute(
            "SELECT year, round FROM results ORDER BY year DESC, round DESC"
            " LIMIT 1").fetchone()
        if row is None:
            print("ERROR: the database holds no races at all.")
            con.close()
            return 1
        target = (int(row[0]), int(row[1]))
    year, rnd = target

    info = probe(con, year, rnd)
    # A race with no results rows has not run: that is a FORECAST, not a
    # mistake - provided at least one pre-race session exists for it.
    is_forecast = info["results"] == 0
    info["forecast"] = is_forecast
    if is_forecast and info["q_rows"] == 0 and info["p_rows"] == 0:
        print(f"ERROR: {year} R{rnd} has no results, no qualifying and no "
              f"practice")
        print("       in this database - nothing exists for this weekend.")
        _wrap("A race has to be fetched before it can be forecast. It needs "
              "at least one pre-race session: spec line 56 allows forecast "
              "mode 'only if the required session data is already "
              "published'.")
        con.close()
        return 1

    # ------------------------------------------------------ choose a mode
    mode, warnings, fatal = choose_mode(info, args.mode)
    if mode is None:
        print(f"ERROR: cannot forecast {year} R{rnd} in mode "
              f"'{args.mode}'.")
        for f in fatal:
            print()
            _wrap("ERROR: " + f)
        print()
        _wrap("Fix: pass --mode early once practice has run, or --mode full "
              "once qualifying has run, or --mode auto to let the data "
              "decide.")
        con.close()
        return 1

    # Refuse to run forecast on already-run races in auto mode.
    # Explicit mode selection (--mode early/full) is allowed with warnings.
    if args.mode == "auto" and not is_forecast and info["q_rows"] > 0:
        print(f"ERROR: {year} R{rnd} already has results - that is a result, not a forecast. "
              f"In auto mode, a forecast may only be run while the race is unrun or pre-qualifying.")
        _wrap("Use --mode early or --mode full explicitly to run walk-forward "
              "evaluation on historical races. Use --save on a race that has not run "
              "yet. Once qualifying and results exist, the forecast window has closed "
              "in auto mode.")
        con.close()
        return 1

    # ---------------------------------------------------------- optional official grid
    # Read --grid-file if provided. This provides the real starting grid after
    # penalties, which is what the `grid` feature means in training.
    official_grid: dict[str, int] | None = None
    if args.grid_file:
        import csv
        grid_path = Path(args.grid_file)
        if not grid_path.exists():
            print(f"ERROR: --grid-file not found: {grid_path}")
            con.close()
            return 1
        with grid_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if "driver" not in reader.fieldnames or "grid_pos" not in reader.fieldnames:
                print("ERROR: --grid-file must have columns: driver,grid_pos")
                con.close()
                return 1
            official_grid = {row["driver"].strip().upper(): int(row["grid_pos"])
                            for row in reader}
        print(f"  loaded official grid: {len(official_grid)} drivers from {grid_path}")

    cols = MODE_FEATURES[mode]
    _banner(mode, year, rnd, info, cols, args.mode, warnings)

    # ---------------------------------------------------------- features
    # forecast_race appends the un-run weekend's rows with finish = NULL
    # `con` stays open past this point: --save writes the forecast after the
    # predictions exist, and closing here would force a second connection.
    df = features.build_features(
        con, forecast_race=(year, rnd) if is_forecast else None,
        official_grid=official_grid)

    # ------------------------------------------------ walk-forward model
    if is_forecast:
        _rule(f"TRUE FORECAST - {year} R{rnd} HAS NOT RUN YET")
        _wrap("The rows below are predictions made from everything known "
              "before the race. There is no finishing order to compare "
              "them to, so no hit rate, no error column and no MAE are "
              "computed FOR THIS RACE - only the historical accuracy of the "
              "model is reported, because that is a property of the model "
              "and not of a race that has not happened.")
        print()
    _rule(f"WALK-FORWARD FORECAST - {mode.upper()} MODE")
    estimator_name = "XGBoost" if model.MODEL_VERSION.startswith("phase7-xgboost") else "Ridge"
    alpha_str = f"Ridge alpha {model.RIDGE_ALPHA}" if estimator_name == "Ridge" else "pre-registered hyperparameters"
    print(f"  expanding window, min {model.MIN_TRAIN_RACES} training races, {alpha_str}")
    wf = _walk_forward(df, cols)
    print(f"  validated {wf['n_races']} races / {wf['n_rows']} rows on the "
          f"{len(cols)} {mode} features")
    print(f"  MAE {wf['mae']:.3f}   Spearman {wf['rho']:.4f}")

    try:
        g = report.race_preds(wf["preds"], year, rnd)
    except ValueError as exc:
        print()
        print(f"  ERROR: {exc}")
        con.close()
        return 1

    print()
    report.top3_printout(g, year, rnd)
    report.order_table(g, year, rnd)

    # --------------------------------------------------- save the forecast
    # Placed before the plots and the baseline tables on purpose: the order
    # above is the whole point of --save, and a matplotlib failure later in
    # main() must not be able to lose it.
    if args.save:
        print()
        if not is_forecast:
            _wrap("--save was requested, but this race already has results, "
                  "so there is nothing to forecast: `forecast.save` refuses "
                  "a race that has run, because a prediction written after "
                  "the result is a back-fit rather than a forecast. Nothing "
                  "was written.")
        elif mode == "full" and args.grid_file is None:
            _wrap("--save in full mode requires --grid-file. The real starting "
                  "grid (after penalties) must be supplied at forecast time, "
                  "because that is what the `grid` feature means in training. "
                  "The qualifying order (q_position) is still derived separately. "
                  "Nothing was written.")
        else:
            # Pre-race penalty check: if we have an official grid, compare it
            # to qualifying order and list any differences (penalties).
            if official_grid is not None:
                print()
                _rule("PRE-RACE PENALTY CHECK")
                q_grid = {d: int(g) for d, g in con.execute(
                    "SELECT driver, q_position FROM qualifying "
                    "WHERE year=? AND round=? AND q_position IS NOT NULL",
                    (year, rnd)).fetchall()}
                if q_grid:
                    diffs = []
                    for d, og in sorted(official_grid.items(), key=lambda x: x[1]):
                        qg = q_grid.get(d.upper())
                        if qg is not None and og != qg:
                            diffs.append(f"  {d:4}  qualifying {qg:2} -> official {og:2}  ({og - qg:+d})")
                    if diffs:
                        print("  Penalties / grid shifts detected:")
                        print("\n".join(diffs))
                    else:
                        print("  No grid shifts - official grid matches qualifying order.")
                    print()

            # Provenance recorded with every forecast. The early one is
            # labelled explicitly because it is generated AFTER qualifying
            # has run even though it never looks at qualifying: saying so
            # prevents a later reader from mistaking it for a pre-qualifying
            # prediction.
            if mode == "early":
                note = ("generated after qualifying, practice-only features"
                        if info["q_rows"] else
                        "generated before qualifying, practice-only features")
            else:
                note = "generated after qualifying, full feature set"
            try:
                n = forecast.save(con, year, rnd, mode, g, cols, df,
                                  note=note)
            except ValueError as exc:
                print(f"  ERROR: {exc}")
                con.close()
                return 1
            fc_head = forecast.load(con, year, rnd, mode)
            if n == 0:
                _rule(f"FORECAST ALREADY ON FILE - {mode.upper()} MODE, "
                      f"{year} R{rnd}")
                _wrap("A forecast for this weekend and mode was written "
                      f"earlier and has NOT been overwritten. Re-running "
                      f"--save is a safe no-op by design: a forecast "
                      f"replaced after the fact would destroy the evidence "
                      f"that it predated the race.")
                print()
                print(f"  written at : {fc_head['created_at'].iloc[0]}")
                print(f"  model      : {fc_head['model_version'].iloc[0]}")
                print(f"  cars       : {len(fc_head)}")
                print()
            else:
                _rule(f"FORECAST SAVED - {mode.upper()} MODE, {year} R{rnd}")
                _wrap(f"{n} rows written to the `forecasts` table, one per "
                      f"driver, with `created_at` set to the moment they "
                      f"were written and `race_start_utc` from FastF1's "
                      f"schedule. The feature list, alpha, model version "
                      f"and the grid baseline's call are stored alongside, "
                      f"so `scripts/score_forecast.py` can prove the "
                      f"forecast predated the result and score the model "
                      f"against the grid baseline on the same drivers.")
                print()
                print(f"  written at : {fc_head['created_at'].iloc[0]}")
                print(f"  race starts: {fc_head['race_start_utc'].iloc[0]}")
                print(f"  model      : {fc_head['model_version'].iloc[0]}")
                print(f"  alpha      : {fc_head['alpha'].iloc[0]}   "
                      f"training races: "
                      f"{fc_head['n_train_races'].iloc[0]}")
                print(f"  features   : {fc_head['features'].iloc[0]}")
                print(f"  note       : {fc_head['note'].iloc[0]}")
                print(f"  cars       : {len(fc_head)}")
        print()

    # ------------------------------------------------- this mode's baselines
    bl_labels = EARLY_BASELINES if mode == "early" else FULL_BASELINES
    bl = model.run_baselines(df, labels=bl_labels)

    _rule(f"THIS MODE'S WALK-FORWARD MAE vs BASELINES ({mode})")

    def _f(x: float, nd: int = 4) -> str:
        # A baseline can be legitimately undefined: on an un-run race every
        # grid slot is filled identically, so the grid baseline predicts one
        # value for all cars and a rank correlation has no meaning. "n/a"
        # says that; printing "nan" would look like a bug.
        return f"{x:.{nd}f}" if math.isfinite(x) else "n/a"

    print(f"  {'ranking':<40} {'MAE':>7} {'Spearman':>9}")
    print(f"  {'-' * 40} {'-' * 7} {'-' * 9}")
    print(f"  {'MODEL (' + mode + ' features)':<40} {wf['mae']:>7.3f} "
          f"{_f(wf['rho']):>9}")
    for label, b in bl.items():
        print(f"  {label:<40} {b['mae']:>7.3f} {_f(b['rho']):>9}")
    undefined = [lb for lb, b in bl.items() if not math.isfinite(b["rho"])]
    if undefined:
        print()
        _wrap("n/a = " + "; ".join(
            f"{lb} predicts one identical value for every car here" for lb in
            undefined) + ", so rank correlation is undefined. Every car ends "
            "up in the same slot when no valid grid exists: on an un-run "
            "race `results` holds nothing yet, and on a race that has run "
            "FastF1 can still publish no grid at all (0, -1 or NULL - which "
            "is what happened in 2026 R20). Both are filled with field size "
            "+ 1, honest for a pit-lane start but constant across the field, "
            "so the ranking is flat and no winner can be picked from it.")
    if bl:
        best = min(b["mae"] for b in bl.values())
        print(f"  {'-' * 40} {'-' * 7} {'-' * 9}")
        print(f"  {'best baseline':<40} {best:>7.3f}")
        d = wf["mae"] - best
        print(f"  {'MODEL - best baseline':<40} {d:>+7.3f}   "
              f"({'beats it' if d < 0 else 'does NOT beat it'})")
    print()
    print(f"  Winner/podium for this mode are in the full Phase 4 report; "
          f"here the")
    print(f"  comparison is MAE, which is what the ladder is scored on.")
    if mode == "early":
        print()
        _wrap("Early mode is NOT scored against the grid baseline: the grid "
              "is precisely what it cannot know at forecast time, so beating "
              "it would be an unfair claim.")

    # ------------------------------------------------------------- scatter
    print()
    _rule("PLOT")
    path = report.gap_scatter(g, df, year, rnd, **SCATTER[mode])
    print(f"  {path}  ({path.stat().st_size:,} bytes)")

    _rule(f"FORECAST COMPLETE - {mode.upper()} MODE, {year} R{rnd}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
