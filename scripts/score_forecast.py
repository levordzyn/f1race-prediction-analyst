"""Save a forecast BEFORE its race and score it AFTERWARDS.

WHY THIS IS A SEPARATE SCRIPT
  ``f1pred.cli --save`` writes the prediction and stops. This reads it back
  and compares it with what happened. Keeping the two apart is what stops a
  forecast from being quietly re-written after the result exists: this script
  never writes to ``forecasts``, and it only writes to ``results`` through
  the normal fetch path when you explicitly ask it to with ``--fetch``.

THREE JOBS
  (default)   score a saved forecast against what actually happened, and
              write a scorecard into ``reports/``
  --fetch     fetch the race results first, then score
  --preflight confirm, BEFORE the race, that the saved forecast is complete
              and usable: car count, grid values (including any pit-lane
              start), the top three of each mode, and that the scatter plot
              exists

WHAT IT CHECKS FIRST
  The no-peeking verdict. Every saved row carries ``created_at`` (when the
  forecast was written) and ``race_start_utc`` (scheduled lights-out). If the
  forecast was not written before the race started, the metrics are printed
  with a loud NO-PEEKING CHECK FAILED banner and marked unverified, because
  a prediction written after the result is a back-fit, not a forecast.

WHAT IT WARNS ABOUT
  One race is one observation. A winner hit on a single race is 0% or 100% by
  construction, so that line always carries an explicit small-sample warning.

EXIT CODES
  0  scored and the no-peeking check passed (or --preflight passed)
  1  no forecast to score, nothing has a result, or a check failed
  2  the race has not run yet - the expected state before lights out

Run:
  python scripts/score_forecast.py --preflight              # before the race
  python scripts/score_forecast.py                          # after the race
  python scripts/score_forecast.py --fetch                  # fetch + score
  python scripts/score_forecast.py --year 2026 --round 20 --mode full
"""
from __future__ import annotations

import argparse
import math
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from f1pred import db, forecast  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def _pp(x, nd: int = 3) -> str:
    """Format a metric, or 'n/a' when it is genuinely undefined.

    A baseline can legitimately be undefined: when every car carries the same
    value its ranking is constant, so Spearman has no meaning and there is no
    distinct car to put first. Printing 'nan' reads like a bug; 'n/a' says the
    quantity is not defined here rather than that something failed.
    """
    if x is None:
        return "-"
    if not math.isfinite(x):
        return "n/a"
    return f"{x:.{nd}f}"


def _pct(x) -> str:
    """The same rule for the hit-rate columns, which can be undefined too."""
    if x is None or not math.isfinite(x):
        return "n/a"
    return f"{x:.0%}"


def _fmt_source(label: str, source: str) -> str:
    """Append source annotation to baseline label."""
    return f"{label} ({source})"


def _compute_baselines_from_saved_grids(con, year: int, rnd: int, mode: str,
                                        m: pd.DataFrame) -> dict:
    """Compute additional baselines from saved grids and qualifying order.

    Returns dict of {label: {mae, rho, winner_hit, podium_hit, source}}.
    """
    from scipy.stats import spearmanr
    import numpy as np

    act = m.set_index("driver")["finish"].to_dict()
    drivers = sorted(act.keys())

    # 1. Qualifying-order baseline (from saved grid_pred)
    gp = m.set_index("driver")["grid_pred"].to_dict()
    mae_gp = sum(abs(gp.get(d, 0) - act[d]) for d in drivers) / len(drivers)
    rho_gp = spearmanr([gp.get(d, 0) for d in drivers],
                       [act[d] for d in drivers]).statistic
    order_gp = sorted(drivers, key=lambda d: gp.get(d, 0))
    win_gp = int(order_gp[0] == min(act, key=act.get))
    pod_gp = len(set(order_gp[:3]) & {d for d, v in act.items() if v <= 3}) / 3

    # 2. Official grid baseline (reconstructed for 2026 R20; for other races
    #    this would need a --grid-file or similar input)
    # For now, only compute if we're on 2026 R20 and can reconstruct from known penalties.
    official_grid = None
    if year == 2026 and rnd == 20:
        official_grid = {
            'NOR': 1, 'ANT': 2, 'LAW': 3, 'HUL': 4, 'HAD': 5, 'BEA': 6,
            'RUS': 7, 'ALO': 8, 'ALB': 9, 'PIA': 10, 'CAM': 11, 'LIN': 12,
            'SAI': 13, 'LEC': 14, 'COL': 15, 'GAS': 16, 'STR': 17, 'BOT': 18,
            'BOR': 19, 'HAM': 20, 'VER': 21, 'PER': 22
        }
    # If a race has results.grid populated (not all -1), use that
    elif not m["grid"].isna().all() and (m["grid"] > 0).any():
        # Check if results.grid has real values (not all -1/0)
        valid_grid = m[m["grid"] > 0].copy()
        if len(valid_grid) == len(m):
            official_grid = valid_grid.set_index("driver")["grid"].to_dict()

    og_metrics = None
    if official_grid is not None:
        mae_og = sum(abs(official_grid.get(d, 0) - act[d]) for d in drivers) / len(drivers)
        rho_og = spearmanr([official_grid.get(d, 0) for d in drivers],
                           [act[d] for d in drivers]).statistic
        order_og = sorted(drivers, key=lambda d: official_grid.get(d, 0))
        win_og = int(order_og[0] == min(act, key=act.get))
        pod_og = len(set(order_og[:3]) & {d for d, v in act.items() if v <= 3}) / 3
        og_metrics = {
            "mae": mae_og, "rho": rho_og,
            "winner_hit": win_og, "podium_hit": pod_og,
            "source": "official grid (FIA Doc 51 / formula1.com)"
        }

    # 3. Pole-sitter wins baseline (from qualifying order)
    pole_driver = min(drivers, key=lambda d: gp.get(d, 0))
    pole_win = int(pole_driver == min(act, key=act.get))
    pole_pod = len({pole_driver} & {d for d, v in act.items() if v <= 3}) / 3

    baselines = {
        "qualifying-order baseline": {
            "mae": mae_gp, "rho": rho_gp,
            "winner_hit": win_gp, "podium_hit": pod_gp,
            "source": "saved grid_pred (qualifying order)"
        },
        "pole-sitter wins": {
            "mae": None, "rho": None,  # ranking-only baseline
            "winner_hit": pole_win, "podium_hit": pole_pod,
            "source": f"pole-sitter = {pole_driver} (qualifying P1)"
        },
    }
    if og_metrics:
        baselines["official-grid baseline"] = og_metrics

    return baselines


def _na_note(r: dict) -> str:
    """Explain any 'n/a' cells in this scorecard, or return ''.

    'n/a' without a sentence reads like something failed. It usually did not:
    a baseline is undefined when it gave every car the same value, and the
    honest reading of a constant ranking is "not defined here", not "zero".
    Saying why also stops a later reader from assuming the number was dropped.
    """
    undefined = [lb for lb, b in r["baselines"].items()
                 if any(b[k] is not None and not math.isfinite(b[k])
                        for k in ("mae", "rho", "winner_hit", "podium_hit"))]
    if not undefined:
        return ""
    txt = (" and ".join(undefined)
           + " produced one identical value for every car in this race, so "
             "its ranking is constant: rank correlation is undefined and "
             "there is no distinct car to rank first.")
    if any("grid" in lb for lb in undefined):
        txt += (
            " For the grid baseline that means no valid starting grid exists "
            "in `results` - either the race has not been fetched yet, or "
            "FastF1 published no grid at all (GridPosition of 0, -1 or NULL; "
            "2026 R20 returned -1 for all 22 cars). Every slot is then "
            "filled with field size + 1, which is right for a pit-lane "
            "start but identical across the whole field.")
    return txt


def scorecard_path(db_path: Path, year: int, rnd: int, mode: str) -> Path:
    """A scorecard belongs beside the database it scored.

    Deriving this from the database instead of a fixed project folder is what
    stops a run against a throwaway copy from writing a file that looks like
    a real scorecard for a race that has not happened. That is not
    hypothetical: test_forecast_flow.py fills `results` with simulated
    results on a temp copy, and because the path was hard-coded to
    ``reports/`` it wrote ``scorecard_2026_r20_full.md`` into the real
    reports folder, naming a simulated winner for a race still three hours
    away. It had to be deleted. Following the database means a copy scores
    into the copy's folder and only the real run scores into ``reports/``.
    """
    return db_path.parent / "reports" / f"scorecard_{year}_r{rnd}_{mode}.md"


def write_scorecard(r: dict, path: Path) -> Path:
    """Write the scorecard as Markdown next to the project's other reports."""
    lines: list[str] = []
    a = lines.append
    a(f"# Forecast scorecard - {r['year']} round {r['round']} "
      f"({r['mode']} mode)")
    a("")
    a(f"- **Forecast written:** {r['created_at']}")
    a(f"- **Race scheduled to start:** {r['race_start_utc']}")
    verdict = {True: "PASSED - written before lights out",
               False: "**FAILED** - written at or after lights out",
               None: "UNKNOWN - scheduled start not recorded"}[r["saved_before_race"]]
    a(f"- **No-peeking check:** {verdict}")
    a(f"- **Model:** {r['model_version']}, alpha {r['alpha']}, "
      f"{r['n_train_races']} training races")
    a(f"- **Features ({len(r['features'])}):** "
      f"{', '.join(r['features'])}")
    if r.get("note"):
        a(f"- **Note:** {r['note']}")
    a(f"- **Scored on:** {r['n_scored']} of {r['n_forecast']} forecast "
      f"drivers")
    a(f"- **Scorecard written:** "
      f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    a("")

    # ---- Predicted top 3 vs Actual top 3 -------------------------------
    a("## Predicted top 3 vs Actual top 3")
    a("")
    # We need to reconstruct this from the saved data
    # For the scorecard, we'll note that the console output has the full table
    a("*See console output for the full predicted vs actual top-3 table with match markers.*")
    a("")

    # ---- Top-10 actual vs predicted ------------------------------------
    a("## Top-10 actual vs predicted (see console output)")
    a("")

    # ---- Model vs ALL baselines ----------------------------------------
    a("## Model vs ALL baselines (this race only)")
    a("")
    a("| Ranking | MAE | Spearman | Winner hit | Podium hit | Source |")
    a("|---|---:|---:|---:|---:|---|")
    a(f"| **MODEL** | {_pp(r['mae'])} | {_pp(r['rho'], 4)} | "
      f"{_pct(r['winner_hit'])} | {_pct(r['podium_hit'])} | — |")
    for label, b in r["baselines"].items():
        a(f"| {label} | {_pp(b['mae'])} | {_pp(b['rho'], 4)} | "
          f"{_pct(b['winner_hit'])} | {_pct(b['podium_hit'])} | — |")
    a("")
    if r.get("best_baseline") is not None:
        d = r["model_minus_best_mae"]
        pct = (abs(d) / r["best_baseline_mae"] * 100
               if r["best_baseline_mae"] else 0.0)
        a(f"**Improvement = model MAE - best baseline MAE = "
          f"{d:+.3f}** ({'better' if d < 0 else 'worse'} by {pct:.2f}%, "
          f"best baseline: {r['best_baseline']}).")
        a("")
    note = _na_note(r)
    if note:
        a(f"**n/a:** {note}")
        a("")
    a("## Winner and podium")
    a("")
    a(f"- **Predicted winner:** {r['winner_pred']}")
    a(f"- **Actual winner:** {r['winner_act']}")
    a("")
    if r.get("forecast_without_result"):
        a(f"- Forecast but no classified result (not scored): "
          f"{', '.join(r['forecast_without_result'])}")
        a("")
    a("## Small-sample warning")
    a("")
    a("This is **one race**. A winner or podium hit rate over 1 race can "
      "only be 0% or 100%, and a single MAE is one draw from a wide "
      "distribution. Nothing here supports a claim about model quality - "
      "that is what the 69-race walk-forward evaluation in Phases 3/4/5 is "
      "for. Compare this race against its own baselines only, and re-check "
      "after several more forecasts have been saved and scored.")
    a("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def report_one(con, year: int, rnd: int, mode: str, db_path: Path,
               save_card: bool = True) -> tuple[str, int]:
    """Print one mode's verdict. Returns (status, exit_code)."""
    r = forecast.score(con, year, rnd, mode)

    rule(f"SCORED FORECAST - {mode.upper()} MODE - {year} R{rnd}")
    if r["status"] == "no-forecast":
        print(f"  {r['detail']}")
        return "no-forecast", 1
    if r["status"] == "not-run":
        print(f"  {r['detail']}")
        print(f"  forecast written : {r['created_at']}")
        print(f"  race starts      : {r['race_start_utc']}")
        print(f"  cars predicted   : {r['n_forecast']}")
        before = None
        if r.get("race_start_utc") not in (None, "None"):
            try:
                before = (forecast._naive(r["created_at"])
                          < forecast._naive(r["race_start_utc"]))
            except (ValueError, TypeError):
                before = None
        print(f"  written before it: {before}")
        print()
        print("  NOTHING TO SCORE YET: the race has no results. That is the")
        print("  expected state before lights out - the forecast is stored,")
        print("  and this script will score it once results exist.")
        print()
        print("  If you are here because you already ran the fetch and it")
        print("  reported nothing, the result is simply not published yet.")
        print("  Wait, then re-run the same command - re-running is safe.")
        return "not-run", 2
    if r["status"] == "no-score":
        print(f"  {r['detail']}")
        return "no-score", 1

    # ---- the no-peeking verdict, printed before any metric ---------------
    print(f"  forecast written : {r['created_at']}")
    print(f"  race starts      : {r['race_start_utc']}")
    print(f"  model            : {r['model_version']}")
    print(f"  written first?   : {r['saved_before_race']}")
    if r.get("created_at_disagrees"):
        print("  WARNING: the saved rows disagree about created_at.")
    if r.get("race_start_disagrees"):
        print("  WARNING: the saved rows disagree about race_start_utc.")

    if r["saved_before_race"] is False:
        print()
        rule("*** NO-PEEKING CHECK FAILED ***")
        print("  This forecast was written at or after the scheduled start")
        print("  of the race. The numbers below may be a back-fit rather")
        print("  than a forecast and must NOT be quoted as a result.")
        print("  Re-save the forecast before the next race starts.")
    elif r["saved_before_race"] is None:
        print()
        print("  The scheduled start time is unknown for this round, so the")
        print("  saved-before-the-race check CANNOT be made. Treat the")
        print("  numbers below as unverified.")
    else:
        print()
        print("  NO-PEEKING CHECK PASSED - written before lights out.")

    # ---- scope ---------------------------------------------------------
    n_sc, n_fc = r["n_scored"], r["n_forecast"]

    # Load actual finishes for this race
    act_df = pd.read_sql_query(
        "SELECT driver, finish FROM results WHERE year=? AND round=?",
        con, params=(year, rnd))
    act = act_df.set_index("driver")["finish"].to_dict()

    # Official grid for 2026 R20 (reconstructed from FIA Doc 51)
    official_grid = None
    if year == 2026 and rnd == 20:
        official_grid = {
            'NOR': 1, 'ANT': 2, 'LAW': 3, 'HUL': 4, 'HAD': 5, 'BEA': 6,
            'RUS': 7, 'ALO': 8, 'ALB': 9, 'PIA': 10, 'CAM': 11, 'LIN': 12,
            'SAI': 13, 'LEC': 14, 'COL': 15, 'GAS': 16, 'STR': 17, 'BOT': 18,
            'BOR': 19, 'HAM': 20, 'VER': 21, 'PER': 22
        }

    print()
    print(f"  note     : {r.get('note')}")
    print(f"  features : {r['features']}")
    print(f"  alpha    : {r['alpha']}   training races: {r['n_train_races']}")
    print(f"  scored   : {n_sc} of {n_fc} forecast drivers "
          f"(on a race of {n_fc} cars)")
    if r.get("forecast_without_result"):
        print(f"  no result: {r['forecast_without_result']}  "
              f"(<- started but not classified, so not scored)")
    if r.get("in_race_not_forecast"):
        print(f"  not forecast: {r['in_race_not_forecast']}")
    print(f"  predicted winner: {r['winner_pred']}   "
          f"actual winner  : {r['winner_act']}")

    # ---- predicted top 3 vs actual top 3 -------------------------------
    print()
    rule("PREDICTED TOP 3 vs ACTUAL TOP 3")
    fc = forecast.load(con, year, rnd, mode)
    pred_top3 = fc.head(3)["driver"].tolist()
    act_top3 = [d for d, f in sorted(act.items(), key=lambda x: x[1])[:3]]
    print(f"  {'':<6} {'Predicted':<12} {'Actual':<12} {'Match'}")
    print(f"  {'-' * 6} {'-' * 12} {'-' * 12} {'-' * 6}")
    for i in range(3):
        p = pred_top3[i] if i < len(pred_top3) else "—"
        a = act_top3[i] if i < len(act_top3) else "—"
        if p == a:
            mark = "✅ exact"
        elif p in act_top3:
            mark = "🔄 podium wrong spot"
        else:
            mark = "❌"
        print(f"  P{i+1:<2} {p:<12} {a:<12} {mark}")

    # Podium hit count (0-3)
    pod_hit = len(set(pred_top3) & set(act_top3))
    print(f"\n  Podium hit: {pod_hit} of 3 predicted drivers finished on the podium.")

    # ---- top-10 actual vs predicted ------------------------------------
    print()
    rule("TOP 10: ACTUAL vs PREDICTED")
    # Build full predicted order from the saved forecast
    pred_order = fc.set_index("driver")["pred_pos"].to_dict()
    # Load early forecast if available
    early_order = {}
    if mode == "full":
        early_fc = forecast.load(con, year, rnd, "early")
        if not early_fc.empty:
            early_order = early_fc.set_index("driver")["pred_pos"].to_dict()
    else:
        early_order = pred_order
    # Sort by actual finish
    top10 = sorted(act.items(), key=lambda x: x[1])[:10]
    print(f"  {'Act':>3} {'Drv':<5} {'Full pred':>9} {'err':>5}  {'Early pred':>10} {'err':>5}  {'Official grid':>13}")
    print(f"  {'-' * 3} {'-' * 5} {'-' * 9} {'-' * 5}  {'-' * 10} {'-' * 5}  {'-' * 13}")
    for d, fin in top10:
        fp = pred_order.get(d, 0)
        ep = early_order.get(d, 0)
        og = official_grid.get(d, 0) if official_grid else 0
        ferr = fp - fin if fp else "N/A"
        eerr = ep - fin if ep else "N/A"
        print(f"  {fin:>3} {d:<5} {fp:>9} {ferr:>5}  {ep:>10} {eerr:>5}  {og:>13}")

    # ---- metrics vs ALL baselines --------------------------------------
    print()
    rule("MODEL vs ALL BASELINES (this race only)")

    # Load saved forecast to get grid_pred (qualifying order)
    m = forecast.load(con, year, rnd, mode).merge(
        pd.DataFrame(list(act.items()), columns=["driver", "finish"]),
        on="driver", how="inner")

    # Compute additional baselines
    extra_baselines = _compute_baselines_from_saved_grids(con, year, rnd, mode, m)
    all_baselines = {**r["baselines"], **extra_baselines}

    # Determine best baseline by MAE (among those with MAE)
    mae_baselines = {k: v for k, v in all_baselines.items() if v.get("mae") is not None}
    if mae_baselines:
        best_label = min(mae_baselines, key=lambda k: mae_baselines[k]["mae"])
        best_mae = mae_baselines[best_label]["mae"]
    else:
        best_label, best_mae = None, None

    # Print table
    print(f"  {'Ranking':<38} {'MAE':>7} {'Spearman':>9} {'Winner':>8} {'Podium':>8} {'Source'}")
    print(f"  {'-' * 38} {'-' * 7} {'-' * 9} {'-' * 8} {'-' * 8} {'-' * 30}")
    print(f"  {'MODEL':<38} {_pp(r['mae']):>7} {_pp(r['rho'], 4):>9} "
          f"{_pct(r['winner_hit']):>8} {_pct(r['podium_hit']):>8}  —")
    for label, b in sorted(all_baselines.items()):
        mae_str = _pp(b["mae"]) if b.get("mae") is not None else "n/a"
        rho_str = _pp(b["rho"], 4) if b.get("rho") is not None else "n/a"
        win_str = _pct(b["winner_hit"]) if b.get("winner_hit") is not None else "n/a"
        pod_str = _pct(b["podium_hit"]) if b.get("podium_hit") is not None else "n/a"
        src = b.get("source", "")
        print(f"  {label:<38} {mae_str:>7} {rho_str:>9} "
              f"{win_str:>8} {pod_str:>8}  ({src})")

    # Best baseline and improvement
    if best_label is not None:
        d = r["mae"] - best_mae
        pct = (abs(d) / best_mae * 100) if best_mae else 0.0
        print(f"\n  {'-' * 38} {'-' * 7}")
        print(f"  {'Best baseline (' + best_label + ')':<38} {_pp(best_mae):>7}")
        print(f"  {'MODEL - best baseline':<38} {d:>+7.3f}   "
              f"{'better' if d < 0 else 'worse'} ({pct:.2f}%)")

    # n/a explanations
    undefined = [lb for lb, b in all_baselines.items()
                 if any(b[k] is not None and not math.isfinite(b[k])
                        for k in ("mae", "rho", "winner_hit", "podium_hit"))]
    if undefined:
        txt = (" and ".join(undefined)
               + " produced one identical value for every car in this race, so "
                 "its ranking is constant: rank correlation is undefined and "
                 "there is no distinct car to rank first.")
        if any("grid" in lb.lower() for lb in undefined):
            txt += (
                " For the grid baseline that means no valid starting grid exists "
                "in `results` - either the race has not been fetched yet, or "
                "FastF1 published no grid at all (GridPosition of 0, -1 or NULL; "
                "2026 R20 returned -1 for all 22 cars). Every slot is then "
                "filled with field size + 1, which is right for a pit-lane "
                "start but identical across the whole field.")
        print()
        print(textwrap.fill(txt, width=78, initial_indent="  n/a: ",
                            subsequent_indent="  "))

    # Small-sample warning
    print()
    print("  SMALL-SAMPLE WARNING: this is ONE race. A winner or podium hit")
    print("  rate over 1 race can only be 0% or 100%, and a single MAE is")
    print("  one draw from a wide distribution. Nothing here supports a")
    print("  claim about model quality - that is what the 69-race")
    print("  walk-forward evaluation in Phase 3/4/5 is for. Compare this")
    print("  race against its own baselines only, and re-check after several")
    print("  more forecasts have been saved and scored.")

    if save_card and r["saved_before_race"] is not True:
        print()
        print("  Scorecard NOT written: the no-peeking check did not pass,")
        print("  so there is nothing worth recording as a result.")
    elif save_card:
        p = write_scorecard(r, scorecard_path(db_path, year, rnd, mode))
        print()
        try:
            shown: Path | str = p.relative_to(ROOT)
        except ValueError:
            shown = p                      # scoring a copy lives elsewhere
        print(f"  SCORECARD: {shown}  ({p.stat().st_size:,} bytes)")

    return r["status"], (0 if r["saved_before_race"] is True else 1)


def preflight(con, year: int, rnd: int) -> int:
    """Confirm the saved forecast is complete and usable BEFORE the race."""
    rule(f"PREFLIGHT - {year} R{rnd} (before the race)")
    fails: list[str] = []

    def chk(n: int, cond: bool, msg: str) -> None:
        print(f"  [{n:>2}] {'PASS' if cond else 'FAIL'}  {msg}")
        if not cond:
            fails.append(msg)

    modes = [m for (m,) in con.execute(
        "SELECT DISTINCT mode FROM forecasts WHERE year=? AND round=?"
        " ORDER BY mode", (year, rnd))]
    chk(1, bool(modes), f"a forecast is on file (modes: {modes or 'none'})")
    if not modes:
        return 1

    n_results = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?",
        (year, rnd)).fetchone()[0]
    chk(2, n_results == 0,
        f"the race has not run yet (results rows: {n_results})")

    row = con.execute(
        "SELECT expected_size FROM sessions WHERE year=? AND round=?",
        (year, rnd)).fetchone()
    expected = int(row[0]) if row and row[0] else 22
    print(f"  expected field size: {expected}")

    fc_all = forecast.load(con, year, rnd, modes[0])
    for i, mode in enumerate(modes, start=3):
        fc = forecast.load(con, year, rnd, mode)
        chk(i, len(fc) == expected,
            f"{mode}: {len(fc)} cars saved, expected {expected}")

    # ---- grid ------------------------------------------------------------
    print()
    print("  GRID (the grid baseline's call, saved with the forecast)")
    print(f"  {'pos':>4} {'driver':<8} {'team':<22} "
          f"{'full grid':>10} {'early grid':>11}")
    full = forecast.load(con, year, rnd, "full") if "full" in modes else None
    early = (forecast.load(con, year, rnd, "early")
             if "early" in modes else None)
    merged = full if full is not None else early
    if full is not None and early is not None:
        merged = full.merge(early, on="driver", suffixes=("_f", "_e"))
    n = len(merged)
    pit_lane = 0
    for _, r in merged.iterrows():
        gf = r.get("grid_pred_f", r.get("grid_pred"))
        ge = r.get("grid_pred_e", r.get("grid_pred"))
        team = r.get("team_f", r.get("team"))
        flag = ""
        if (isinstance(gf, float) and gf == expected + 1):
            pit_lane += 1
            flag = "   <- no qualifying lap / pit-lane start"
        print(f"  {int(r.get('pred_pos_f', r.get('pred_pos', 0))):>4} "
              f"{r['driver']:<8} {str(team)[:22]:<22} "
              f"{_pp(gf, 0):>10} {_pp(ge, 0):>11}{flag}")
    print()
    chk(5, n == expected, f"grid listed for all {expected} cars ({n})")
    vals = [r.get("grid_pred_f", r.get("grid_pred"))
            for _, r in merged.iterrows()]
    finite = [v for v in vals if isinstance(v, (int, float))]
    chk(6, len(finite) == n,
        "every car has a real grid value (nobody defaulted to 23 by "
        "accident)")
    chk(7, len(set(finite)) == len(finite),
        "no two cars share a grid slot")
    in_range = all(1 <= v <= expected + 1 for v in finite)
    chk(8, in_range, "every grid value is inside 1..field+1")
    print(f"  grid slots filled from a qualifying lap: "
          f"{sum(1 for v in finite if v <= expected)} of {n}"
          f"   no-lap / pit-lane: {pit_lane}")

    # ---- top three per mode ---------------------------------------------
    print()
    print("  TOP 3 PER MODE")
    for mode in modes:
        fc = forecast.load(con, year, rnd, mode)
        print(f"    {mode:<6} " + "  ".join(
            f"{i}. {r.driver} ({r.team})" for i, r in
            enumerate(fc.head(3).itertuples(), start=1)))
    chk(9, all(len(forecast.load(con, year, rnd, m).head(3)) == 3
               for m in modes), "each saved mode has a top 3")

    # ---- provenance ------------------------------------------------------
    print()
    print("  PROVENANCE")
    for mode in modes:
        fc = forecast.load(con, year, rnd, mode)
        print(f"    {mode:<6} {fc['created_at'].iloc[0]}  "
              f"{fc['model_version'].iloc[0]}  alpha "
              f"{fc['alpha'].iloc[0]}  {fc['n_train_races'].iloc[0]} "
              f"training races")
        print(f"           {fc['note'].iloc[0]}")

    # ---- scatter plot ----------------------------------------------------
    print()
    plots = sorted((ROOT / "reports").glob(
        f"gap_vs_prediction_{year}_r{rnd}_*.png"))
    chk(10, bool(plots), "the scatter plot exists in reports/")
    for p in plots:
        print(f"    {p.relative_to(ROOT)}  ({p.stat().st_size:,} bytes)")

    rule("PREFLIGHT RESULT")
    if fails:
        print(f"  {len(fails)} FAILED:")
        for f in fails:
            print(f"    - {f}")
        return 1
    print("  ALL CHECKS PASSED - the forecast is complete and pre-race.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="python scripts/score_forecast.py",
        description="Score a forecast saved before its race, after the race.")
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--mode", choices=("auto", "early", "full"),
                    default="auto",
                    help="auto (default) scores every mode that was saved")
    ap.add_argument("--db", default=None, help="database file (default: f1.db)")
    ap.add_argument("--fetch", action="store_true",
                    help="fetch the race results first, then score")
    ap.add_argument("--preflight", action="store_true",
                    help="before the race: confirm the saved forecast is "
                         "complete (cars, grid, top 3, scatter plot)")
    args = ap.parse_args()

    db_path = Path(args.db) if args.db else db.DB_PATH
    con = db.connect(db_path)
    con.row_factory = None

    if args.year is None or args.round is None:
        row = con.execute(
            "SELECT year, round FROM forecasts ORDER BY year DESC,"
            " round DESC LIMIT 1").fetchone()
        if row is None:
            row = con.execute(
                "SELECT year, round FROM sessions ORDER BY year DESC,"
                " round DESC LIMIT 1").fetchone()
        if row is None:
            print("ERROR: the database holds no races at all.")
            con.close()
            return 1
        year, rnd = int(row[0]), int(row[1])
    else:
        year, rnd = args.year, args.round

    print(f"  database : {args.db or db.DB_PATH}")
    print(f"  target   : {year} round {rnd}")
    print(f"  mode     : {args.mode}")
    print()

    if args.preflight:
        code = preflight(con, year, rnd)
        con.close()
        return code

    if args.fetch:
        from f1pred import fetch
        rule(f"FETCHING RESULTS - {year} R{rnd}")
        try:
            summary = fetch.fetch_year(con, year, rounds={rnd})
            print(f"  {summary}")
        except Exception as exc:                       # noqa: BLE001
            print(f"  fetch failed: {type(exc).__name__}: {exc}")
            print()
            print("  This usually means the result is not published yet.")
            print("  Wait for the race to finish and the classification to")
            print("  appear, then re-run the same command - re-running is")
            print("  safe and will simply fetch what is now available.")
            con.close()
            return 2
        n = con.execute("SELECT COUNT(*) FROM results WHERE year=? AND"
                        " round=?", (year, rnd)).fetchone()[0]
        print(f"  results rows now: {n}")
        if n == 0:
            print()
            print("  NO RESULT PUBLISHED YET - nothing was fetched.")
            print("  Wait for the classification, then re-run the same")
            print("  command. Re-running is safe: this script never writes")
            print("  to `forecasts`, and the fetch only adds results.")
            con.close()
            return 2
        print()

    modes = (["full", "early"] if args.mode == "auto" else [args.mode])
    saved = {r[0] for r in con.execute(
        "SELECT DISTINCT mode FROM forecasts WHERE year=? AND round=?",
        (year, rnd))}
    print(f"  saved modes for this weekend: {sorted(saved) or 'none'}")
    print()

    codes: list[int] = []
    ran_any = False
    for mode in modes:
        if args.mode == "auto" and mode not in saved:
            continue
        ran_any = True
        _status, code = report_one(con, year, rnd, mode, db_path)
        codes.append(code)
        print()
    if not ran_any:
        rule("NO FORECAST ON FILE")
        print(f"  No saved forecast for {year} R{rnd} in mode '{args.mode}'.")
        print("  Save one before the race with:")
        print(f"    python -m f1pred.cli --year {year} --round {rnd} "
              f"--mode {args.mode} --save")
        con.close()
        return 1

    con.close()
    rule("RESULT")
    if any(c == 2 for c in codes):
        print("  Race has not run yet - nothing to score (exit 2).")
        return 2
    if any(c != 0 for c in codes):
        print("  scored, but the no-peeking check did not pass (exit 1).")
        return 1
    print(f"  scored {len(codes)} mode(s); no-peeking check passed;")
    print(f"  scorecards in {db_path.parent / 'reports'}"
          f"\\scorecard_{year}_r{rnd}_<mode>.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
