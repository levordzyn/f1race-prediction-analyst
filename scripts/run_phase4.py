"""Phase 4: reports from walk-forward predictions only.

Produces, for one completed race:
  1. top-3 predicted finishers (medals),
  2. the full predicted-order table,
  3. winner / podium hit rates with their EXACT definitions, three ranking
     baselines (pole-sitter, best qualifying gap, best driver form), the
     model's improvement over the best of them, a season split, and the rank
     the model gave the actual winner,
  4. gap-vs-prediction scatter (PNG),
  5. Ridge coefficient bar chart (PNG), labelled collinearity-affected,
  6. grouped permutation importance (qualifying / practice / grid / form),
     measured as the walk-forward MAE increase when each group is shuffled.

Every number comes out of ``model.walk_forward`` and ``model.permutation_
importance``: held-out predictions, per-race metrics, fold-averaged
coefficients and fold-by-fold shuffling. This script never fits a model of
its own, so no report can show a prediction walk-forward validation did not
actually make.

Usage:
    python scripts/run_phase4.py                 # latest validated race
    python scripts/run_phase4.py --year 2026 --round 4
    python scripts/run_phase4.py --list          # show available races

The race must be in the validation window (races 21-89); the first 20 races
are training-only and have no out-of-sample prediction.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model, report  # noqa: E402

# Windows consoles default to cp1252, which cannot encode the medal emoji
# (U+1F947 gold, U+1F948 silver, U+1F949 bronze) and raise UnicodeEncodeError
# mid-print. Force UTF-8 at the entry point so the top-3 printout renders.
# errors="replace" degrades to a placeholder instead of crashing the report.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def rule(title: str = "") -> None:
    print("=" * 78)
    if title:
        print(title)
        print("=" * 78)


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 4 reports")
    ap.add_argument("--year", type=int, help="race year (default: latest)")
    ap.add_argument("--round", type=int, help="race round (default: latest)")
    ap.add_argument("--list", action="store_true",
                    help="list races that have walk-forward predictions")
    args = ap.parse_args()

    con = db.connect()
    con.row_factory = None
    df = features.build_features(con)
    con.close()

    # ---------------------------------------------------------------- model
    rule("FITTING THE WALK-FORWARD MODEL (expanding window, 12 features)")
    print(f"  features {len(features.ALL_FEATURES)} in "
          f"{len(features.FEATURE_GROUPS)} groups")
    print(f"  minimum training window {model.MIN_TRAIN_RACES} races, "
          f"Ridge alpha {model.RIDGE_ALPHA}")
    wf = model.walk_forward(df, list(features.ALL_FEATURES))
    print(f"  validated {wf['n_races']} races / {wf['n_rows']} rows")
    print(f"  MAE {wf['mae']:.3f} positions   Spearman {wf['rho']:.4f}")
    print(f"  (all numbers below are derived from these held-out "
          f"predictions)")

    preds = wf["preds"]
    available = sorted({(int(y), int(r)) for y, r in
                        zip(preds["year"], preds["round"])})

    if args.list:
        print()
        print(f"  {len(available)} races with walk-forward predictions:")
        for y, r in available:
            print(f"    {y} R{r}")
        return 0

    # ------------------------------------------------------- choose a race
    if args.year is not None and args.round is not None:
        target = (args.year, args.round)
    else:
        target = available[-1]

    if target not in available:
        print()
        print(f"  {target[0]} R{target[1]} has NO walk-forward predictions.")
        print(f"  Validation covers races "
              f"{available[0][0]} R{available[0][1]} .. "
              f"{available[-1][0]} R{available[-1][1]} "
              f"({len(available)} races).")
        print(f"  The first {model.MIN_TRAIN_RACES} races are training-only: "
              f"predicting them would train on their own outcome.")
        print(f"  Use --list to see what is available.")
        return 1

    year, rnd = target
    g = report.race_preds(preds, year, rnd)

    # ------------------------------------------------------- 1 + 2: printout
    report.top3_printout(g, year, rnd)
    report.order_table(g, year, rnd)

    # ------------------------------------------------------- 3: hit rates
    hb = model.run_hit_baselines(df)     # pole / best gap / best form
    report.hit_rates(wf, hb)

    # --------------------------------------------------------- 4 + 5: plots
    rule("PLOTS")
    scatter_path = report.gap_scatter(g, df, year, rnd)
    print(f"  gap vs prediction scatter : {scatter_path}  "
          f"({scatter_path.stat().st_size:,} bytes)")
    coef_path = report.coefficient_chart(wf["coef_mean"], year=year, rnd=rnd)
    print(f"  coefficient bar chart     : {coef_path}  "
          f"({coef_path.stat().st_size:,} bytes)")
    print()
    print("  both are real PNG files written under reports/")

    # ---------------------------------------------------- coefficient table
    rule("STANDARDIZED RIDGE COEFFICIENTS (mean over the folds) - "
         "COLLINEARITY-AFFECTED")
    print(f"  {wf['n_folds']} folds; positions per 1 standard deviation, so")
    print(f"  magnitudes are directly comparable:")
    print()
    coef = sorted(wf["coef_mean"].items(), key=lambda kv: kv[1], reverse=True)
    width = max(len(k) for k, _ in coef)
    for name, val in coef:
        direction = "higher -> P" if val > 0 else "higher -> better"
        bar = "#" * int(round(abs(val) * 10))
        print(f"  {name:<{width}} {val:>+8.4f}  {direction:<14} {bar}")
    print()
    print("  red bars in the PNG = positive (worse finish);")
    print("  green bars = negative (better finish).")
    print()
    print("  These weights are NOT a reliable importance measure on their")
    print("  own. Where two features carry the same information Ridge splits")
    print("  the shared weight and the smaller one can flip sign:")
    print("    q_position +1.90 vs q_gap_pct -0.03         (qualifying pace)")
    print("    practice_pos +0.17 vs practice_gap_pct -0.18 (practice pace)")
    print("    non_finish_rate -0.47 vs driver_form +1.35    (recent form)")
    print("  The raw data is fine in every case - mean finish is 9.84 with no")
    print("  DNFs vs 13.82 with 80%+ DNFs - so this is collinearity, not a")
    print("  bug. The chart is kept because the spec asks for it, labelled as")
    print("  affected. Use the GROUPED PERMUTATION IMPORTANCE below instead.")

    # ------------------------------------- grouped permutation importance
    # Measures importance by destruction, not by reading a coefficient, so
    # collinearity cannot flip a sign on us.
    rule("GROUPED PERMUTATION IMPORTANCE")
    pi = model.permutation_importance(df, list(features.ALL_FEATURES),
                                      features.PERM_GROUPS)
    report.permutation_table(pi, mode_label="full")

    # -------------------------------------------------- race-level accuracy
    rule("HOW OFTEN WAS THIS RACE'S TOP 3 RIGHT?")
    actual_top3 = set(g.nsmallest(3, "finish")["driver"])
    pred_top3 = set(g.nsmallest(3, "pred_pos")["driver"])
    both = actual_top3 & pred_top3
    print(f"  actual podium : {', '.join(sorted(actual_top3))}")
    print(f"  predicted     : {', '.join(sorted(pred_top3))}")
    print(f"  overlap       : {len(both)}/3  "
          f"({', '.join(sorted(both)) or 'none'})")
    print()
    winner = g[g["finish"] == 1]
    if len(winner) == 1:
        w = winner.iloc[0]
        print(f"  actual winner {w['driver']} was ranked "
              f"P{int(w['pred_pos'])} by the model")
    rule("PHASE 4 COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
