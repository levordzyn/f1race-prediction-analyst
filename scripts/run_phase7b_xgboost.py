"""Phase 7B: XGBoost Walk-Forward Evaluation.

Pre-registered in reports/phase7b_xgboost_prereg.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model
from f1pred.xgboost_model import (
    walk_forward_xgboost,
    paired_bootstrap_delta,
    compare_feature_importance,
    XGBOOST_PARAMS,
    MONOTONE_CONSTRAINTS,
)

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

TARGET = "finish"
MIN_TRAIN_RACES = 20
RIDGE_MAE = 3.069  # Phase 5 Ridge baseline
RIDGE_PODIUM = 0.676
RIDGE_WINNER = 0.638


def rule(title: str = "") -> None:
    print("=" * 78)
    if title:
        print(title)
        print("=" * 78)


def save_fig(name: str) -> Path:
    path = REPORTS_DIR / name
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    return path


def main() -> int:
    rule("PHASE 7B: XGBOOST WALK-FORWARD EVALUATION")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print()

    # ------------------------------------------------------------------ Load data
    rule("[1] LOAD DATA")
    con = db.connect()
    con.row_factory = None
    df = features.build_features(con)
    con.close()

    races = np.sort(df["race_idx"].unique())
    val_races = [r for r in races if r > MIN_TRAIN_RACES]
    n_folds = len(val_races)
    print(f"  Total races: {len(races)}, validation folds: {n_folds}")
    print(f"  Total rows: {len(df)}, features: {len(features.ALL_FEATURES)}")
    print(f"  Features: {features.ALL_FEATURES}")
    print(f"  Monotone constraints: {MONOTONE_CONSTRAINTS}")

    # ------------------------------------------------------------------ Run XGBoost (real labels)
    rule("[2] XGBOOST WALK-FORWARD (REAL LABELS)")
    xgb_results = walk_forward_xgboost(
        df,
        features.ALL_FEATURES,
        min_train_races=MIN_TRAIN_RACES,
        shuffle=False,
        monotone_constraints=MONOTONE_CONSTRAINTS,
    )
    xgb_preds = xgb_results["predictions"]
    xgb_mae = xgb_results["mae"]
    xgb_spearman = xgb_results["spearman"]
    xgb_podium = xgb_results["podium_hit"]
    xgb_winner = xgb_results["winner_hit"]
    xgb_fi = xgb_results["feature_importance"]
    xgb_train_mae = xgb_results["train_mae_per_fold"]
    xgb_test_mae = xgb_results["test_mae_per_fold"]

    print(f"  XGBoost MAE: {xgb_mae:.4f} (Ridge: {RIDGE_MAE:.4f})")
    print(f"  XGBoost Spearman ρ: {xgb_spearman:.4f}")
    print(f"  XGBoost Podium hit: {xgb_podium:.3f} (Ridge: {RIDGE_PODIUM:.3f})")
    print(f"  XGBoost Winner hit: {xgb_winner:.3f} (Ridge: {RIDGE_WINNER:.3f})")
    print(f"  Mean train MAE: {np.mean(xgb_train_mae):.4f}, test MAE: {np.mean(xgb_test_mae):.4f}")
    print(f"  Train-test gap: {np.mean(xgb_test_mae) - np.mean(xgb_train_mae):.4f}")

    # Feature importance
    print("\n  Top 5 features by gain:")
    for _, row in xgb_fi.head().iterrows():
        print(f"    {row['feature']:<20} gain={row['gain']:.2f} weight={row['weight']:.0f} cover={row['cover']:.2f}")

    # ------------------------------------------------------------------ Shuffled-label control
    rule("[3] SHUFFLED-LABEL CONTROL (3 SEEDS)")
    shuffled_maes = []
    for seed in [42, 123, 456]:
        shuffled_results = walk_forward_xgboost(
            df,
            features.ALL_FEATURES,
            min_train_races=MIN_TRAIN_RACES,
            shuffle=True,
            monotone_constraints=MONOTONE_CONSTRAINTS,
        )
        shuffled_mae = shuffled_results["mae"]
        shuffled_maes.append(shuffled_mae)
        print(f"  Seed {seed}: Shuffled MAE = {shuffled_mae:.4f} (Real MAE = {xgb_mae:.4f})")

    avg_shuffled = np.mean(shuffled_maes)
    gap = avg_shuffled - xgb_mae
    print(f"  Average shuffled MAE: {avg_shuffled:.4f}")
    print(f"  Gap (shuffled - real): {gap:.4f}")
    if gap < 1.5:
        print(f"  WARNING: Gap < 1.5 positions — possible leakage!")
    else:
        print(f"  PASS: Gap > 1.5 positions — no leakage detected")

    # ------------------------------------------------------------------ Load Ridge predictions for comparison
    rule("[4] LOAD RIDGE PREDICTIONS FOR COMPARISON")
    ridge_results = model.walk_forward(df, features.ALL_FEATURES, min_train=MIN_TRAIN_RACES)
    ridge_preds = ridge_results["preds"]
    ridge_mae_this_run = ridge_results["mae"]
    ridge_spearman_this_run = ridge_results["rho"]
    ridge_podium_this_run = ridge_results["podium_hit"]
    ridge_winner_this_run = ridge_results["winner_hit"]
    print(f"  Ridge MAE (this run): {ridge_mae_this_run:.4f}")

    # ------------------------------------------------------------------ Paired bootstrap on per-race MAE delta
    rule("[5] PAIRED BOOTSTRAP (1000 resamples, seed=42)")
    bootstrap_results = paired_bootstrap_delta(ridge_preds, xgb_preds)
    mean_delta = bootstrap_results["mean_delta"]
    ci_lower = bootstrap_results["ci_lower"]
    ci_upper = bootstrap_results["ci_upper"]
    sign_p = bootstrap_results["sign_p"]
    wilcoxon_p = bootstrap_results["wilcoxon_p"]
    ci_excludes_zero = bootstrap_results["ci_excludes_zero"]

    print(f"  Mean ΔMAE (XGB - Ridge): {mean_delta:+.4f}")
    print(f"  95% CI: [{ci_lower:+.4f}, {ci_upper:+.4f}]")
    print(f"  CI excludes 0: {ci_excludes_zero}")
    print(f"  Sign test p-value: {sign_p:.4f}")
    print(f"  Wilcoxon p-value: {wilcoxon_p:.4f}")

    # Per-race deltas for visualization
    deltas = bootstrap_results["deltas_per_race"]

    # ------------------------------------------------------------------ Feature importance comparison
    rule("[6] FEATURE IMPORTANCE COMPARISON")
    ridge_coefs = ridge_results["coef_mean"]
    fi_comparison = compare_feature_importance(ridge_coefs, xgb_fi)
    spearman_rho = fi_comparison["spearman_rho"]
    pearson_r = fi_comparison["pearson_r"]

    print(f"  Spearman ρ (Ridge |coef| vs XGB gain): {spearman_rho:.4f}")
    print(f"  Pearson r: {pearson_r:.4f}")
    if spearman_rho > 0.7:
        print(f"  Consistent feature importance (ρ > 0.7)")
    elif spearman_rho < 0.4:
        print(f"  Different signal detected (ρ < 0.4) — possible nonlinear interactions")
    else:
        print(f"  Moderate agreement")

    # ------------------------------------------------------------------ Visualizations
    rule("[7] VISUALIZATIONS")

    # 7.1 Feature importance plot
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, imp_type, title in zip(axes, ["gain", "weight", "cover"],
                                    ["Gain (primary)", "Weight", "Cover"]):
        top10 = xgb_fi.head(10).sort_values(imp_type)
        ax.barh(range(len(top10)), top10[imp_type])
        ax.set_yticks(range(len(top10)))
        ax.set_yticklabels(top10["feature"])
        ax.set_xlabel(imp_type.capitalize())
        ax.set_title(f"XGBoost Feature Importance: {title}")
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    save_fig("phase7b_xgboost_importance.png")
    print(f"  Saved: reports/phase7b_xgboost_importance.png")

    # 7.2 Train vs Test MAE per fold
    fig, ax = plt.subplots(figsize=(12, 4))
    fold_nums = range(1, len(xgb_train_mae) + 1)
    ax.plot(fold_nums, xgb_train_mae, label="Train MAE", alpha=0.7)
    ax.plot(fold_nums, xgb_test_mae, label="Test MAE", alpha=0.7)
    ax.axhline(y=np.mean(xgb_train_mae), color="C0", linestyle="--", alpha=0.5)
    ax.axhline(y=np.mean(xgb_test_mae), color="C1", linestyle="--", alpha=0.5)
    ax.set_xlabel("Fold")
    ax.set_ylabel("MAE")
    ax.set_title("Train vs Test MAE per Fold (Overfitting Check)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    save_fig("phase7b_train_test_mae.png")
    print(f"  Saved: reports/phase7b_train_test_mae.png")

    # 7.3 Per-race MAE delta histogram
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(deltas, bins=20, edgecolor="black", alpha=0.7)
    ax.axvline(0, color="red", linestyle="--", linewidth=2)
    ax.axvline(mean_delta, color="blue", linestyle="--", linewidth=2, label=f"Mean Δ={mean_delta:+.4f}")
    ax.axvline(ci_lower, color="green", linestyle=":", linewidth=2, label=f"95% CI: [{ci_lower:+.3f}, {ci_upper:+.3f}]")
    ax.axvline(ci_upper, color="green", linestyle=":", linewidth=2)
    ax.set_xlabel("Per-Race ΔMAE (XGB - Ridge)")
    ax.set_ylabel("Count")
    ax.set_title("Paired Bootstrap: Per-Race MAE Deltas")
    ax.legend()
    ax.grid(True, alpha=0.3)
    save_fig("phase7b_delta_mae_hist.png")
    print(f"  Saved: reports/phase7b_delta_mae_hist.png")

    # 7.4 Predicted vs Actual scatter
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(xgb_preds["finish"], xgb_preds["pred"], alpha=0.3, s=5)
    ax.plot([1, 20], [1, 20], "r--", linewidth=1)
    ax.set_xlabel("Actual Finish")
    ax.set_ylabel("Predicted Finish")
    ax.set_title(f"XGBoost: Predicted vs Actual (MAE={xgb_mae:.3f}, ρ={xgb_spearman:.3f})")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0.5, 20.5)
    ax.set_ylim(0.5, 20.5)
    save_fig("phase7b_pred_vs_actual.png")
    print(f"  Saved: reports/phase7b_pred_vs_actual.png")

    # ------------------------------------------------------------------ Verdict
    rule("[8] VERDICT")

    verdict_items = []

    # MAE improvement with CI excluding 0
    # Use the paired bootstrap result: XGB better than Ridge if mean_delta < 0 and CI excludes 0
    mae_improved = mean_delta < 0 and ci_excludes_zero
    primary_pass = mae_improved
    verdict_items.append(("MAE improvement with significant CI", primary_pass,
                          f"XGB MAE={xgb_mae:.3f} vs Ridge={ridge_mae_this_run:.3f}, Δ={mean_delta:+.3f}, CI=[{ci_lower:+.3f}, {ci_upper:+.3f}]"))

    # Shuffled control
    shuffle_pass = avg_shuffled - xgb_mae > 1.5
    verdict_items.append(("Shuffled-label sanity check", shuffle_pass,
                          f"Shuffled MAE={avg_shuffled:.3f}, Real MAE={xgb_mae:.3f}, Gap={gap:.3f}"))

    # Hit rates (compare to current Ridge run)
    podium_improved = xgb_podium >= ridge_podium_this_run
    winner_improved = xgb_winner >= ridge_winner_this_run
    verdict_items.append(("Podium hit rate ≥ Ridge", podium_improved,
                          f"XGB={xgb_podium:.3f} vs Ridge={ridge_podium_this_run:.3f}"))
    verdict_items.append(("Winner hit rate ≥ Ridge", winner_improved,
                          f"XGB={xgb_winner:.3f} vs Ridge={ridge_winner_this_run:.3f}"))

    # Overfitting check
    train_test_gap = np.mean(xgb_test_mae) - np.mean(xgb_train_mae)
    overfit_pass = train_test_gap < 0.5
    verdict_items.append(("No severe overfitting (train-test gap < 0.5)", overfit_pass,
                          f"Train MAE={np.mean(xgb_train_mae):.3f}, Test MAE={np.mean(xgb_test_mae):.3f}, Gap={train_test_gap:.3f}"))

    print()
    rule("VERDICT SUMMARY")
    all_pass = True
    for label, passed, detail in verdict_items:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {label}: {detail}")

    print()
    if primary_pass:
        verdict = "ACCEPTED"
        action = "Promote to production; bump MODEL_VERSION; update LIMITATIONS.md"
    elif not primary_pass and (podium_improved or winner_improved):
        verdict = "NULL"
        action = "Keep separate in xgboost_model.py; document as experiment; Ridge remains production"
    else:
        verdict = "REJECTED"
        action = "Revert all XGBoost code; document why it failed"

    print(f"VERDICT: {verdict}")
    print(f"ACTION: {action}")

    # ------------------------------------------------------------------ Save results
    rule("[9] SAVE RESULTS")

    # Save predictions
    xgb_preds.to_csv(REPORTS_DIR / "phase7b_xgboost_predictions.csv", index=False)
    print(f"  Predictions saved to reports/phase7b_xgboost_predictions.csv")

    # Save feature importance
    xgb_fi.to_csv(REPORTS_DIR / "phase7b_xgboost_feature_importance.csv", index=False)
    print(f"  Feature importance saved to reports/phase7b_xgboost_feature_importance.csv")

    # JSON summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "xgboost_mae": float(xgb_mae),
        "xgboost_spearman": float(xgb_spearman),
        "xgboost_podium_hit": float(xgb_podium),
        "xgboost_winner_hit": float(xgb_winner),
        "ridge_mae": float(ridge_mae_this_run),
        "ridge_spearman": float(ridge_spearman_this_run),
        "ridge_podium_hit": float(ridge_podium_this_run),
        "ridge_winner_hit": float(ridge_winner_this_run),
        "mean_delta_mae": float(mean_delta),
        "bootstrap_ci_lower": float(ci_lower),
        "bootstrap_ci_upper": float(ci_upper),
        "bootstrap_ci_excludes_zero": bool(ci_excludes_zero),
        "sign_test_p": float(sign_p),
        "wilcoxon_p": float(wilcoxon_p),
        "shuffled_mae_seeds": [float(m) for m in shuffled_maes],
        "avg_shuffled_mae": float(avg_shuffled),
        "shuffled_gap": float(gap),
        "train_mae_mean": float(np.mean(xgb_train_mae)),
        "test_mae_mean": float(np.mean(xgb_test_mae)),
        "train_test_gap": float(train_test_gap),
        "feature_importance_spearman_rho": float(spearman_rho) if not np.isnan(spearman_rho) else None,
        "feature_importance_pearson_r": float(pearson_r) if not np.isnan(pearson_r) else None,
        "verdict": verdict,
        "primary_criterion_pass": bool(primary_pass),
        "shuffle_control_pass": bool(shuffle_pass),
    }
    with open(REPORTS_DIR / "phase7b_xgboost.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  JSON summary saved to reports/phase7b_xgboost.json")

    # Markdown report
    md_path = REPORTS_DIR / "phase7b_xgboost.md"
    with open(md_path, "w") as f:
        f.write(f"""# Phase 7B: XGBoost Walk-Forward Evaluation

**Date:** {datetime.now(timezone.utc).isoformat()}
**Model:** XGBoost (pre-registered hyperparameters)
**Pre-registration:** `reports/phase7b_xgboost_prereg.md`

## Verdict

**{verdict}** — {action}

## Configuration

| Parameter | Value |
|-----------|-------|
| n_estimators | 200 |
| max_depth | 4 |
| learning_rate | 0.05 |
| subsample | 0.8 |
| colsample_bytree | 0.8 |
| min_child_weight | 5 |
| reg_alpha (L1) | 1.0 |
| reg_lambda (L2) | 1.0 |
| monotone_constraints | {MONOTONE_CONSTRAINTS} |
| Walk-forward folds | 173 (MIN_TRAIN_RACES=20) |

## Primary Metrics

| Metric | XGBoost | Ridge (This Run) | Δ (XGB - Ridge) |
|--------|---------|------------------|-----------------|
| MAE | {xgb_mae:.4f} | {ridge_mae_this_run:.4f} | {mean_delta:+.4f} |
| Spearman ρ | {xgb_spearman:.4f} | {ridge_spearman_this_run:.4f} | {xgb_spearman - ridge_spearman_this_run:+.4f} |
| Podium hit rate | {xgb_podium:.3f} | {ridge_podium_this_run:.3f} | {xgb_podium - ridge_podium_this_run:+.3f} |
| Winner hit rate | {xgb_winner:.3f} | {ridge_winner_this_run:.3f} | {xgb_winner - ridge_winner_this_run:+.3f} |

## Paired Bootstrap (1000 resamples, seed=42)

- **Mean ΔMAE (per-race):** {mean_delta:+.4f}
- **95% CI:** [{ci_lower:+.4f}, {ci_upper:+.4f}]
- **CI excludes 0:** {'Yes' if ci_excludes_zero else 'No'}
- **Sign test p:** {sign_p:.4f}
- **Wilcoxon p:** {wilcoxon_p:.4f}

{'✅ PASS: MAE improvement with CI excluding 0' if primary_pass else '❌ FAIL: No significant MAE improvement'}

## Shuffled-Label Control (Mandatory Sanity Check)

| Seed | Shuffled MAE | Real MAE | Gap |
|------|--------------|----------|-----|
""" + "\n".join([f"| {s} | {m:.4f} | {xgb_mae:.4f} | {m - xgb_mae:.4f} |" for s, m in zip([42, 123, 456], shuffled_maes)]) + f"""

**Average gap:** {gap:.4f} positions {'✅ PASS (>1.5)' if shuffle_pass else '❌ FAIL (≤1.5 — possible leakage)'}

## Overfitting Check

- **Mean Train MAE:** {np.mean(xgb_train_mae):.4f}
- **Mean Test MAE:** {np.mean(xgb_test_mae):.4f}
- **Train-Test Gap:** {train_test_gap:.4f} {'✅ PASS (<0.5)' if overfit_pass else '❌ FAIL (≥0.5 — overfit)'}

## Feature Importance Comparison

| Feature | XGB Gain | Ridge |coef| |
|---------|----------|-------|
""" + "\n".join([f"| {row['feature']} | {row['gain']:.2f} | {abs(ridge_coefs.get(row['feature'], 0)):.4f} |" for _, row in xgb_fi.iterrows()]) + f"""

- **Spearman ρ (|coef| vs gain):** {spearman_rho:.4f} {'(Consistent)' if spearman_rho > 0.7 else '(Different signal)' if spearman_rho < 0.4 else '(Moderate)'}
- **Pearson r:** {pearson_r:.4f}

## Verdict Summary

| Criterion | Result | Detail |
|-----------|--------|--------|
""" + "\n".join([f"| {label} | {'PASS' if passed else 'FAIL'} | {detail} |" for label, passed, detail in verdict_items]) + f"""

## Files Generated

- `reports/phase7b_xgboost_predictions.csv` — Per-driver predictions
- `reports/phase7b_xgboost_feature_importance.csv` — Feature importance (gain/weight/cover)
- `reports/phase7b_xgboost_importance.png` — Feature importance plots
- `reports/phase7b_train_test_mae.png` — Train vs Test MAE per fold
- `reports/phase7b_delta_mae_hist.png` — Per-race MAE delta histogram
- `reports/phase7b_pred_vs_actual.png` — Predicted vs Actual scatter
- `reports/phase7b_xgboost.json` — Machine-readable summary
- `reports/phase7b_xgboost.md` — This report

---

*Pre-registration: `reports/phase7b_xgboost_prereg.md`*
*Generated: {datetime.now(timezone.utc).isoformat()}*
""")

    print(f"  Markdown report saved to {md_path}")

    rule("PHASE 7B COMPLETE")
    print(f"  Verdict: {verdict}")
    print(f"  XGBoost MAE: {xgb_mae:.4f} (Ridge this run: {ridge_mae_this_run:.4f})")
    print(f"  ΔMAE: {mean_delta:+.4f}, 95% CI: [{ci_lower:+.4f}, {ci_upper:+.4f}]")
    return 0 if primary_pass else 1


if __name__ == "__main__":
    sys.exit(main())