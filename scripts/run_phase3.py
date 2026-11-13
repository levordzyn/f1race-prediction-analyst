"""Run Phase 3: walk-forward validation, baselines, and the feature-group ladder.

Prints, in order:
  1. the split (how many races train, how many validate, no future data);
  2. the three unfitted baselines: grid, practice-order, recent-form;
  3. the feature groups added ONE AT A TIME, with MAE before and after each;
  4. standardized Ridge coefficients (mean over the 69 folds);
  5. the shuffled-label sanity check - scrambled labels must get much worse;
  6. a small-sample warning on winner/podium hit rates.

Run:  python scripts/run_phase3.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model  # noqa: E402

pd.set_option("display.width", 200)


def rule(title: str = "") -> None:
    print("=" * 78)
    if title:
        print(title)
        print("=" * 78)


def pct(value: float) -> str:
    """Format a rate, showing n/a when the metric is genuinely undefined
    (a constant prediction has no winner to predict)."""
    return "n/a" if value is None or np.isnan(value) else f"{value:.1%}"


def main() -> int:
    con = db.connect()
    con.row_factory = None
    df = features.build_features(con)
    con.close()

    races = np.sort(df["race_idx"].unique())
    min_train = model.MIN_TRAIN_RACES
    n_val = len(races) - min_train
    val_rows = int((df["race_idx"] > races[min_train - 1]).sum())

    # ------------------------------------------------------------------ split
    rule("1. THE SPLIT - expanding window, no future data in training")
    print(f"  races total                 : {len(races)}  (rows {len(df)})")
    print(f"  minimum training window     : {min_train} races")
    print(f"  validation races            : {n_val}  (rows {val_rows})")
    print(f"  fold k trains on races 1..k and tests race k+1; training grows")
    print(f"  from {min_train} races to {len(races)-1}, so race {int(races[min_train])} "
          f"is the first ever scored.")
    print(f"  features                    : {len(features.ALL_FEATURES)} "
          f"in {len(features.FEATURE_GROUPS)} groups")
    print(f"  each fold fits StandardScaler on TRAIN only, then Ridge(alpha="
          f"{model.RIDGE_ALPHA})")

    # ------------------------------------------------------------ baselines
    rule("2. BASELINES - unfitted, scored on the identical validation races")
    bl = model.run_baselines(df, min_train=min_train)
    print(f"  {'model':<30} {'MAE':>7} {'Spearman':>9} {'races':>6} "
          f"{'rows':>6} {'winner':>7} {'podium':>7}")
    for label, r in bl.items():
        print(f"  {label:<30} {r['mae']:>7.3f} {r['rho']:>9.4f} "
              f"{r['n_races']:>6} {r['n_rows']:>6} "
              f"{pct(r['winner_hit']):>7} {pct(r['podium_hit']):>7}")

    # ---------------------------------------------------------------- ladder
    rule("3. FEATURE GROUPS ADDED ONE AT A TIME - MAE before and after each")
    stages = model.run_ladder(df, min_train=min_train)
    print(f"  {'group':<56} {'before':>7} {'after':>7} {'delta':>7}")
    for s in stages:
        name = s["name"]
        if s["before"] is None:
            print(f"  {name:<56} {'-':>7} {s['mae']:>7.3f} {'-':>7}")
        else:
            print(f"  {name:<56} {s['before']:>7.3f} {s['mae']:>7.3f} "
                  f"{s['delta']:>+7.3f}")
    print()
    print("  full metrics at each stage:")
    print(f"  {'stage':<56} {'MAE':>7} {'Spearman':>9} {'races':>6} {'rows':>6}")
    for s in stages:
        print(f"  {s['name']:<56} {s['mae']:>7.3f} {s['rho']:>9.4f} "
              f"{s['n_races']:>6} {s['n_rows']:>6}")

    print()
    print("  per-race effect of each group (69 validation races):")
    for i in range(1, len(stages)):
        a = stages[i - 1]["per_race"][["year", "round", "mae"]] \
            .rename(columns={"mae": "before"})
        b = stages[i]["per_race"][["year", "round", "mae"]] \
            .rename(columns={"mae": "after"})
        m = a.merge(b, on=["year", "round"], validate="one_to_one")
        d = m["after"] - m["before"]
        better = int((d < -1e-12).sum())
        same = int((d.abs() <= 1e-12).sum())
        worse = int((d > 1e-12).sum())
        print(f"    {stages[i]['name']}")
        # d = after - before, so NEGATIVE is an improvement
        print(f"      better in {better:>2} races, same in {same:>2}, "
              f"worse in {worse:>2} | mean {d.mean():+.4f} | "
              f"biggest gain {d.min():+.3f}, biggest loss {d.max():+.3f}")
        if d.max() > 0.5:                 # a group that hurts badly somewhere
            row = m.loc[d.idxmax()]
            print(f"      driven by an outlier: {int(row['year'])} R"
                  f"{int(row['round'])} went {row['before']:.3f} -> "
                  f"{row['after']:.3f} MAE (+{row['after'] - row['before']:.3f})")
    print()
    total_gain = stages[-1]["mae"] - stages[0]["mae"]
    print(f"  net effect of all {len(features.ALL_FEATURES)} features vs no features: "
          f"{total_gain:+.3f} positions MAE")
    best_base = min(r["mae"] for r in bl.values())
    print(f"  best baseline MAE           : {best_base:.3f}")
    print(f"  final model vs best baseline: {stages[-1]['mae'] - best_base:+.3f}"
          f"   (negative = model beats the baseline)")
    print(f"  improvement formula         : "
          f"{100 * (best_base - stages[-1]['mae']) / best_base:.2f}% better "
          f"than the best baseline")

    # --------------------------------------------------------- coefficients
    rule("4. STANDARDIZED RIDGE COEFFICIENTS (mean over the folds)")
    last = stages[-1]
    print(f"  {last['n_folds']} folds; coefficients are in positions per 1 "
          f"standard deviation,")
    print(f"  so their magnitudes are directly comparable:")
    print()
    coef = pd.Series(last["coef_mean"]).sort_values(key=abs, ascending=False)
    cstd = pd.Series(last["coef_std"])
    print(f"  {'feature':<20} {'mean coef':>11} {'std':>8}  {'direction':<12}")
    for name, val in coef.items():
        direction = "higher -> P" if val > 0 else "higher -> better"
        print(f"  {name:<20} {val:>11.4f} {cstd[name]:>8.4f}  {direction:<12}")

    # -------------------------------------------------------- shuffle check
    rule("5. SHUFFLED-LABEL SANITY CHECK - scrambling must destroy performance")
    real = stages[-1]["mae"]
    shuf = [model.walk_forward(df, features.ALL_FEATURES, min_train=min_train,
                               shuffle=True, seed=s)["mae"] for s in (0, 1, 2)]
    shuf_mean = float(np.mean(shuf))
    worse = shuf_mean > real + 0.5
    print(f"  real labels  MAE            : {real:.3f}")
    print(f"  shuffled MAE (seeds 0,1,2)  : "
          f"{', '.join(f'{m:.3f}' for m in shuf)}   mean {shuf_mean:.3f}")
    print(f"  shuffled is worse by        : {shuf_mean - real:+.3f} positions")
    print(f"  verdict                     : "
          f"{'PASS - scrambled labels score much worse' if worse else 'FAIL - something is leaking'}")
    for r in bl.values():
        if shuf_mean <= r["mae"]:
            print(f"  note: shuffled MAE {shuf_mean:.3f} is not worse than "
                  f"{r['mae']:.3f}")

    # ------------------------------------------------------------- hit rates
    rule("6. WINNER / PODIUM HIT RATES - SMALL SAMPLE, READ WITH CARE")
    nr = stages[-1]["n_races"]
    print(f"  {nr} validation races is a SMALL SAMPLE for hit rates.")
    print(f"  a single lucky or unlucky race moves them by "
          f"{100/nr:.1f} percentage points,")
    print(f"  so treat them as indicative only - MAE and Spearman over "
          f"{nr} races are")
    print(f"  the numbers to trust. Winner is a 1-of-{df['field_n'].max()}"
          f" draw; a naive uniform guess")
    print(f"  scores about {1/20:.1%}.")
    print()
    print(f"  {'model':<56} {'winner':>8} {'podium':>8}")
    for label, r in list(bl.items()) + [(s["name"], s) for s in stages]:
        print(f"  {label:<56} {pct(r['winner_hit']):>8} {pct(r['podium_hit']):>8}")

    rule("PHASE 3 COMPLETE" if worse else "PHASE 3 - SANITY CHECK FAILED")
    return 0 if worse else 1


if __name__ == "__main__":
    sys.exit(main())
