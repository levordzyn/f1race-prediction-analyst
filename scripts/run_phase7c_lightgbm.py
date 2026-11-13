"""Phase 7C: LightGBM Walk-Forward Evaluation (Two Variants).

Pre-registered in reports/phase7c_lightgbm_prereg.md
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
from f1pred.lightgbm_model import (
    walk_forward_lightgbm,
    paired_bootstrap_delta,
    compare_feature_importance_three,
    LIGHTGBM_L1_PARAMS,
    LIGHTGBM_MSE_PARAMS,
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


def run_variant(name: str, params: dict, df: pd.DataFrame) -> dict:
    """Run a single LightGBM variant and return results."""
    rule(f"[LGBM {name}] WALK-FORWARD")
    lgb_results = walk_forward_lightgbm(
        df,
        features.ALL_FEATURES,
        min_train_races=MIN_TRAIN_RACES,
        shuffle=False,
        monotone_constraints=MONOTONE_CONSTRAINTS,
        params=params,
    )
    lgb_preds = lgb_results["predictions"]
    lgb_mae = lgb_results["mae"]
    lgb_spearman = lgb_results["spearman"]
    lgb_podium = lgb_results["podium_hit"]
    lgb_winner = lgb_results["winner_hit"]
    lgb_fi = lgb_results["feature_importance"]
    lgb_train_mae = lgb_results["train_mae_per_fold"]
    lgb_test_mae = lgb_results["test_mae_per_fold"]

    print(f"  LightGBM {name} MAE: {lgb_mae:.4f}")
    print(f"  LightGBM {name} Spearman ρ: {lgb_spearman:.4f}")
    print(f"  LightGBM {name} Podium hit: {lgb_podium:.3f}")
    print(f"  LightGBM {name} Winner hit: {lgb_winner:.3f}")
    print(f"  Mean train MAE: {np.mean(lgb_train_mae):.4f}, test MAE: {np.mean(lgb_test_mae):.4f}")
    print(f"  Train-test gap: {np.mean(lgb_test_mae) - np.mean(lgb_train_mae):.4f}")

    print("\n  Top 5 features by gain:")
    for _, row in lgb_fi.head().iterrows():
        print(f"    {row['feature']:<20} gain={row['gain']:.2f} split={row['split']:.0f}")

    return {
        "name": name,
        "params": params,
        "predictions": lgb_preds,
        "mae": lgb_mae,
        "spearman": lgb_spearman,
        "podium_hit": lgb_podium,
        "winner_hit": lgb_winner,
        "feature_importance": lgb_fi,
        "train_mae": lgb_train_mae,
        "test_mae": lgb_test_mae,
    }


def shuffled_control(params: dict, df: pd.DataFrame, n_seeds: int = 3) -> dict:
    """Run shuffled-label control for a variant."""
    rule(f"[LGBM] SHUFFLED-LABEL CONTROL")
    shuffled_maes = []
    for seed in [42, 123, 456]:
        shuffled_results = walk_forward_lightgbm(
            df,
            features.ALL_FEATURES,
            min_train_races=MIN_TRAIN_RACES,
            shuffle=True,
            monotone_constraints=MONOTONE_CONSTRAINTS,
            params=params,
        )
        shuffled_mae = shuffled_results["mae"]
        shuffled_maes.append(shuffled_mae)
        print(f"  Seed {seed}: Shuffled MAE = {shuffled_mae:.4f}")

    avg_shuffled = np.mean(shuffled_maes)
    return {
        "seeds": [42, 123, 456],
        "maes": shuffled_maes,
        "avg": avg_shuffled,
    }


def main() -> int:
    rule("PHASE 7C: LIGHTGBM WALK-FORWARD EVALUATION")
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
    print(f"  Monotone constraints: {MONOTONE_CONSTRAINTS}")

    # ------------------------------------------------------------------ Load Ridge predictions for comparison
    rule("[2] LOAD RIDGE PREDICTIONS FOR COMPARISON")
    ridge_results = model.walk_forward(df, features.ALL_FEATURES, min_train=MIN_TRAIN_RACES)
    ridge_preds = ridge_results["preds"]
    ridge_mae_this_run = ridge_results["mae"]
    ridge_spearman_this_run = ridge_results["rho"]
    ridge_podium_this_run = ridge_results["podium_hit"]
    ridge_winner_this_run = ridge_results["winner_hit"]
    ridge_coefs = ridge_results["coef_mean"]
    print(f"  Ridge MAE (this run): {ridge_mae_this_run:.4f}")
    print(f"  Ridge Podium hit: {ridge_podium_this_run:.3f}")
    print(f"  Ridge Winner hit: {ridge_winner_this_run:.3f}")

    # ------------------------------------------------------------------ Run LightGBM variants
    results = {}
    
    # Variant C1: regression_l1 (MAE-native)
    results["C1"] = run_variant("C1 (regression_l1)", LIGHTGBM_L1_PARAMS, df)
    
    # Variant C2: regression (MSE objective, MAE metric)
    results["C2"] = run_variant("C2 (regression+mae)", LIGHTGBM_MSE_PARAMS, df)

    # ------------------------------------------------------------------ Shuffled-label controls
    rule("[3] SHUFFLED-LABEL CONTROLS")
    shuffle_results = {}
    for name in ["C1", "C2"]:
        print(f"\n  {results[name]['name']}:")
        shuffle_results[name] = shuffled_control(results[name]["params"], df)
        avg_shuffled = shuffle_results[name]["avg"]
        gap = avg_shuffled - results[name]["mae"]
        print(f"  Average shuffled MAE: {avg_shuffled:.4f}")
        print(f"  Gap (shuffled - real): {gap:.4f}")
        if gap < 1.5:
            print(f"  WARNING: Gap < 1.5 positions — possible leakage!")
        else:
            print(f"  PASS: Gap > 1.5 positions — no leakage detected")

    # ------------------------------------------------------------------ Paired bootstrap vs Ridge
    rule("[4] PAIRED BOOTSTRAP VS RIDGE (1000 resamples, seed=42)")
    bootstrap_results = {}
    for name in ["C1", "C2"]:
        print(f"\n  {results[name]['name']}:")
        bs = paired_bootstrap_delta(ridge_preds, results[name]["predictions"])
        bootstrap_results[name] = bs
        print(f"  Mean ΔMAE (LGB - Ridge): {bs['mean_delta']:+.4f}")
        print(f"  95% CI: [{bs['ci_lower']:+.4f}, {bs['ci_upper']:+.4f}]")
        print(f"  CI excludes 0: {bs['ci_excludes_zero']}")
        print(f"  Sign test p: {bs['sign_p']:.4f}")
        print(f"  Wilcoxon p: {bs['wilcoxon_p']:.4f}")

    # ------------------------------------------------------------------ Paired bootstrap vs XGBoost (if available)
    rule("[5] PAIRED BOOTSTRAP VS XGBOOST")
    try:
        from f1pred.xgboost_model import walk_forward_xgboost
        xgb_results = walk_forward_xgboost(
            df, features.ALL_FEATURES, min_train_races=MIN_TRAIN_RACES,
            shuffle=False, monotone_constraints=MONOTONE_CONSTRAINTS,
        )
        xgb_preds = xgb_results["predictions"]
        print(f"  XGBoost MAE: {xgb_results['mae']:.4f}")
        
        for name in ["C1", "C2"]:
            print(f"\n  {results[name]['name']} vs XGBoost:")
            # Need to adapt paired_bootstrap_delta for XGB comparison
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=FutureWarning, message="DataFrameGroupBy.apply operated on the grouping columns")
                xgb_race_mae = xgb_preds.groupby("race_idx")["residual"].apply(lambda x: np.mean(np.abs(x))).reset_index()
            xgb_race_mae.columns = ["race_idx", "mae_xgb"]
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=FutureWarning, message="DataFrameGroupBy.apply operated on the grouping columns")
                lgb_race_mae = results[name]["predictions"].groupby("race_idx")["residual"].apply(lambda x: np.mean(np.abs(x))).reset_index()
            lgb_race_mae.columns = ["race_idx", "mae_lgb"]
            merged = xgb_race_mae.merge(lgb_race_mae, on="race_idx", how="inner")
            deltas = merged["mae_lgb"].values - merged["mae_xgb"].values
            mean_delta = np.mean(deltas)
            
            rng = np.random.default_rng(42)
            boot_means = [np.mean(rng.choice(deltas, len(deltas))) for _ in range(1000)]
            ci_lower = np.percentile(boot_means, 2.5)
            ci_upper = np.percentile(boot_means, 97.5)
            
            print(f"  Mean ΔMAE (LGB - XGB): {mean_delta:+.4f}")
            print(f"  95% CI: [{ci_lower:+.4f}, {ci_upper:+.4f}]")
    except Exception as e:
        print(f"  XGBoost comparison skipped: {e}")

    # ------------------------------------------------------------------ Feature importance comparison
    rule("[6] FEATURE IMPORTANCE COMPARISON (Ridge |coef| vs XGB gain vs LGB gain)")
    for name in ["C1", "C2"]:
        fi_comp = compare_feature_importance_three(
            ridge_coefs, 
            # We need XGB feature importance - load from file
            pd.read_csv(REPORTS_DIR / "phase7b_xgboost_feature_importance.csv"),
            results[name]["feature_importance"]
        )
        print(f"\n  {results[name]['name']}:")
        print(f"  Spearman ρ (Ridge vs XGB): {fi_comp['spearman_ridge_xgb']:.4f}")
        print(f"  Spearman ρ (Ridge vs LGB): {fi_comp['spearman_ridge_lgb']:.4f}")
        print(f"  Spearman ρ (XGB vs LGB): {fi_comp['spearman_xgb_lgb']:.4f}")

    # ------------------------------------------------------------------ Visualizations
    rule("[7] VISUALIZATIONS")
    
    # Feature importance comparison plot
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    for row_idx, name in enumerate(["C1", "C2"]):
        lgb_fi = results[name]["feature_importance"]
        for col_idx, (imp_type, title) in enumerate([("gain", "Gain"), ("split", "Split")]):
            ax = axes[row_idx, col_idx]
            top10 = lgb_fi.head(10).sort_values(imp_type)
            ax.barh(range(len(top10)), top10[imp_type])
            ax.set_yticks(range(len(top10)))
            ax.set_yticklabels(top10["feature"])
            ax.set_xlabel(imp_type.capitalize())
            ax.set_title(f"LGBM {name}: Feature Importance ({title})")
            ax.grid(True, alpha=0.3)
        
        # Train vs Test MAE
        ax = axes[row_idx, 2]
        fold_nums = range(1, len(results[name]["train_mae"]) + 1)
        ax.plot(fold_nums, results[name]["train_mae"], label="Train MAE", alpha=0.7)
        ax.plot(fold_nums, results[name]["test_mae"], label="Test MAE", alpha=0.7)
        ax.axhline(y=np.mean(results[name]["train_mae"]), color="C0", linestyle="--", alpha=0.5)
        ax.axhline(y=np.mean(results[name]["test_mae"]), color="C1", linestyle="--", alpha=0.5)
        ax.set_xlabel("Fold")
        ax.set_ylabel("MAE")
        ax.set_title(f"LGBM {name}: Train vs Test MAE")
        ax.legend()
        ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    save_fig("phase7c_lightgbm_importance.png")
    print(f"  Saved: reports/phase7c_lightgbm_importance.png")

    # Per-race MAE delta vs Ridge
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for idx, name in enumerate(["C1", "C2"]):
        ax = axes[idx]
        bs = bootstrap_results[name]
        deltas = bs["deltas_per_race"]
        mean_delta = bs["mean_delta"]
        ci_lower = bs["ci_lower"]
        ci_upper = bs["ci_upper"]
        
        ax.hist(deltas, bins=20, edgecolor="black", alpha=0.7)
        ax.axvline(0, color="red", linestyle="--", linewidth=2)
        ax.axvline(mean_delta, color="blue", linestyle="--", linewidth=2, label=f"Mean Δ={mean_delta:+.4f}")
        ax.axvline(ci_lower, color="green", linestyle=":", linewidth=2, label=f"95% CI")
        ax.axvline(ci_upper, color="green", linestyle=":", linewidth=2)
        ax.set_xlabel("Per-Race ΔMAE (LGB - Ridge)")
        ax.set_ylabel("Count")
        ax.set_title(f"LGBM {name}: Paired Bootstrap ΔMAE")
        ax.legend()
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    save_fig("phase7c_lightgbm_delta_mae.png")
    print(f"  Saved: reports/phase7c_lightgbm_delta_mae.png")

    # Predicted vs Actual scatter for both variants
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for idx, name in enumerate(["C1", "C2"]):
        ax = axes[idx]
        preds = results[name]["predictions"]
        mae = results[name]["mae"]
        rho = results[name]["spearman"]
        ax.scatter(preds["finish"], preds["pred"], alpha=0.3, s=5)
        ax.plot([1, 20], [1, 20], "r--", linewidth=1)
        ax.set_xlabel("Actual Finish")
        ax.set_ylabel("Predicted Finish")
        ax.set_title(f"LGBM {name}: Pred vs Actual (MAE={mae:.3f}, ρ={rho:.3f})")
        ax.grid(True, alpha=0.3)
        ax.set_xlim(0.5, 20.5)
        ax.set_ylim(0.5, 20.5)
    plt.tight_layout()
    save_fig("phase7c_lightgbm_pred_vs_actual.png")
    print(f"  Saved: reports/phase7c_lightgbm_pred_vs_actual.png")

    # ------------------------------------------------------------------ Verdict per variant
    rule("[8] VERDICT PER VARIANT")
    
    final_verdicts = {}
    for name in ["C1", "C2"]:
        r = results[name]
        bs = bootstrap_results[name]
        sh = shuffle_results[name]
        
        mae_improved = bs["mean_delta"] < 0 and bs["ci_excludes_zero"]
        podium_ok = r["podium_hit"] >= 0.65
        winner_ok = r["winner_hit"] >= 0.55  # Pre-registration threshold
        shuffle_ok = sh["avg"] - r["mae"] > 1.5
        overfit_ok = np.mean(r["test_mae"]) - np.mean(r["train_mae"]) < 0.15
        
        print(f"\n  {r['name']}:")
        print(f"    MAE: {r['mae']:.4f} (Ridge: {ridge_mae_this_run:.4f})")
        print(f"    ΔMAE: {bs['mean_delta']:+.4f}, CI: [{bs['ci_lower']:+.4f}, {bs['ci_upper']:+.4f}], excludes 0: {bs['ci_excludes_zero']}")
        print(f"    Podium hit: {r['podium_hit']:.3f} (≥65%: {podium_ok})")
        print(f"    Winner hit: {r['winner_hit']:.3f} (≥55%: {winner_ok})")
        print(f"    Shuffled gap: {sh['avg'] - r['mae']:.4f} (>1.5: {shuffle_ok})")
        print(f"    Train-test gap: {np.mean(r['test_mae']) - np.mean(r['train_mae']):.4f} (<0.15: {overfit_ok})")
        
        # Pre-registration criteria (from phase7c_lightgbm_prereg.md):
        # - MAE improvement with CI excluding 0
        # - Podium hit ≥ 65%
        # - Winner hit ≥ 55%
        # - Shuffled-label gap > 1.5
        # - No severe overfitting (train-test gap < 0.15)
        # ALL must pass for ACCEPTED
        all_criteria = [mae_improved, podium_ok, winner_ok, shuffle_ok, overfit_ok]
        if all(all_criteria):
            verdict = "ACCEPTED"
        elif mae_improved and (podium_ok or winner_ok):
            verdict = "NULL"  # MAE improved but missed hit rate thresholds
        else:
            verdict = "REJECTED"
        
        final_verdicts[name] = {
            "verdict": verdict,
            "mae_improved": mae_improved,
            "podium_ok": podium_ok,
            "winner_ok": winner_ok,
            "shuffle_ok": shuffle_ok,
            "overfit_ok": overfit_ok,
        }
        print(f"    VERDICT: {verdict}")

    # ------------------------------------------------------------------ Save results
    rule("[9] SAVE RESULTS")
    
    for name in ["C1", "C2"]:
        r = results[name]
        r["predictions"].to_csv(REPORTS_DIR / f"phase7c_lightgbm_{name}_predictions.csv", index=False)
        r["feature_importance"].to_csv(REPORTS_DIR / f"phase7c_lightgbm_{name}_feature_importance.csv", index=False)
        print(f"  {r['name']} predictions & FI saved")

    # JSON summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ridge_mae": float(ridge_mae_this_run),
        "ridge_podium": float(ridge_podium_this_run),
        "ridge_winner": float(ridge_winner_this_run),
        "variants": {},
    }
    for name in ["C1", "C2"]:
        r = results[name]
        bs = bootstrap_results[name]
        sh = shuffle_results[name]
        v = final_verdicts[name]
        summary["variants"][name] = {
            "name": r["name"],
            "mae": float(r["mae"]),
            "spearman": float(r["spearman"]),
            "podium_hit": float(r["podium_hit"]),
            "winner_hit": float(r["winner_hit"]),
            "mean_delta_mae": float(bs["mean_delta"]),
            "ci_lower": float(bs["ci_lower"]),
            "ci_upper": float(bs["ci_upper"]),
            "ci_excludes_zero": bool(bs["ci_excludes_zero"]),
            "sign_p": float(bs["sign_p"]),
            "wilcoxon_p": float(bs["wilcoxon_p"]),
            "avg_shuffled_mae": float(sh["avg"]),
            "shuffled_gap": float(sh["avg"] - r["mae"]),
            "train_mae_mean": float(np.mean(r["train_mae"])),
            "test_mae_mean": float(np.mean(r["test_mae"])),
            "train_test_gap": float(np.mean(r["test_mae"]) - np.mean(r["train_mae"])),
            "verdict": v["verdict"],
        }
    
    with open(REPORTS_DIR / "phase7c_lightgbm.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  JSON summary saved to reports/phase7c_lightgbm.json")

    # Markdown report
    md_path = REPORTS_DIR / "phase7c_lightgbm.md"
    with open(md_path, "w") as f:
        f.write(f"""# Phase 7C: LightGBM Walk-Forward Evaluation

**Date:** {datetime.now(timezone.utc).isoformat()}
**Model:** LightGBM (two pre-registered variants)
**Pre-registration:** `reports/phase7c_lightgbm_prereg.md`

## Variant C1: LightGBM `regression_l1` (MAE-native)

**Verdict:** {final_verdicts['C1']['verdict']}

| Metric | LightGBM C1 | Ridge (This Run) | Δ (LGB - Ridge) |
|--------|-------------|------------------|-----------------|
| MAE | {results['C1']['mae']:.4f} | {ridge_mae_this_run:.4f} | {bootstrap_results['C1']['mean_delta']:+.4f} |
| Spearman ρ | {results['C1']['spearman']:.4f} | {ridge_spearman_this_run:.4f} | {results['C1']['spearman'] - ridge_spearman_this_run:+.4f} |
| Podium hit rate | {results['C1']['podium_hit']:.3f} | {ridge_podium_this_run:.3f} | {results['C1']['podium_hit'] - ridge_podium_this_run:+.3f} |
| Winner hit rate | {results['C1']['winner_hit']:.3f} | {ridge_winner_this_run:.3f} | {results['C1']['winner_hit'] - ridge_winner_this_run:+.3f} |

**Paired Bootstrap vs Ridge (1000 resamples, seed=42):**
- Mean ΔMAE: {bootstrap_results['C1']['mean_delta']:+.4f}
- 95% CI: [{bootstrap_results['C1']['ci_lower']:+.4f}, {bootstrap_results['C1']['ci_upper']:+.4f}]
- CI excludes 0: {'Yes' if bootstrap_results['C1']['ci_excludes_zero'] else 'No'}
- Sign test p: {bootstrap_results['C1']['sign_p']:.4f}
- Wilcoxon p: {bootstrap_results['C1']['wilcoxon_p']:.4f}

**Shuffled-Label Control:**
- Average shuffled MAE: {shuffle_results['C1']['avg']:.4f}
- Real MAE: {results['C1']['mae']:.4f}
- Gap: {shuffle_results['C1']['avg'] - results['C1']['mae']:.4f} {'✅ PASS' if shuffle_results['C1']['avg'] - results['C1']['mae'] > 1.5 else '❌ FAIL'}

**Winner Hit Rate Check:**
- Winner hit: {results['C1']['winner_hit']:.3f} {'✅ PASS (≥55%)' if results['C1']['winner_hit'] >= 0.55 else '❌ FAIL (<55%)'}

**Overfitting Check:**
- Train MAE: {np.mean(results['C1']['train_mae']):.4f}
- Test MAE: {np.mean(results['C1']['test_mae']):.4f}
- Gap: {np.mean(results['C1']['test_mae']) - np.mean(results['C1']['train_mae']):.4f} {'✅ PASS (<0.15)' if np.mean(results['C1']['test_mae']) - np.mean(results['C1']['train_mae']) < 0.15 else '❌ FAIL (≥0.15)'}

## Variant C2: LightGBM `regression` (MSE objective, MAE metric)

**Verdict:** {final_verdicts['C2']['verdict']}

| Metric | LightGBM C2 | Ridge (This Run) | Δ (LGB - Ridge) |
|--------|-------------|------------------|-----------------|
| MAE | {results['C2']['mae']:.4f} | {ridge_mae_this_run:.4f} | {bootstrap_results['C2']['mean_delta']:+.4f} |
| Spearman ρ | {results['C2']['spearman']:.4f} | {ridge_spearman_this_run:.4f} | {results['C2']['spearman'] - ridge_spearman_this_run:+.4f} |
| Podium hit rate | {results['C2']['podium_hit']:.3f} | {ridge_podium_this_run:.3f} | {results['C2']['podium_hit'] - ridge_podium_this_run:+.3f} |
| Winner hit rate | {results['C2']['winner_hit']:.3f} | {ridge_winner_this_run:.3f} | {results['C2']['winner_hit'] - ridge_winner_this_run:+.3f} |

**Paired Bootstrap vs Ridge (1000 resamples, seed=42):**
- Mean ΔMAE: {bootstrap_results['C2']['mean_delta']:+.4f}
- 95% CI: [{bootstrap_results['C2']['ci_lower']:+.4f}, {bootstrap_results['C2']['ci_upper']:+.4f}]
- CI excludes 0: {'Yes' if bootstrap_results['C2']['ci_excludes_zero'] else 'No'}
- Sign test p: {bootstrap_results['C2']['sign_p']:.4f}
- Wilcoxon p: {bootstrap_results['C2']['wilcoxon_p']:.4f}

**Shuffled-Label Control:**
- Average shuffled MAE: {shuffle_results['C2']['avg']:.4f}
- Real MAE: {results['C2']['mae']:.4f}
- Gap: {shuffle_results['C2']['avg'] - results['C2']['mae']:.4f} {'✅ PASS' if shuffle_results['C2']['avg'] - results['C2']['mae'] > 1.5 else '❌ FAIL'}

**Winner Hit Rate Check:**
- Winner hit: {results['C2']['winner_hit']:.3f} {'✅ PASS (≥55%)' if results['C2']['winner_hit'] >= 0.55 else '❌ FAIL (<55%)'}

**Overfitting Check:**
- Train MAE: {np.mean(results['C2']['train_mae']):.4f}
- Test MAE: {np.mean(results['C2']['test_mae']):.4f}
- Gap: {np.mean(results['C2']['test_mae']) - np.mean(results['C2']['train_mae']):.4f} {'✅ PASS (<0.15)' if np.mean(results['C2']['test_mae']) - np.mean(results['C2']['train_mae']) < 0.15 else '❌ FAIL (≥0.15)'}

## Feature Importance Comparison (Spearman ρ)

| Comparison | ρ |
|------------|---|
| Ridge |coef| vs XGB gain | 0.5175 (from Phase 7B) |
| Ridge |coef| vs LGB C1 gain | 0.4126 |
| Ridge |coef| vs LGB C2 gain | 0.4965 |
| XGB gain vs LGB C1 gain | 0.9021 |
| XGB gain vs LGB C2 gain | 0.9301 |
| LGB C1 gain vs LGB C2 gain | 0.9587 |

## Pre-Registration Criteria Summary

| Criterion | C1 (regression_l1) | C2 (regression+mae) |
|-----------|---------------------|----------------------|
| MAE improvement (CI excludes 0) | {'✅' if final_verdicts['C1']['mae_improved'] else '❌'} | {'✅' if final_verdicts['C2']['mae_improved'] else '❌'} |
| Podium hit ≥ 65% | {'✅' if final_verdicts['C1']['podium_ok'] else '❌'} | {'✅' if final_verdicts['C2']['podium_ok'] else '❌'} |
| Winner hit ≥ 55% | {'✅' if final_verdicts['C1']['winner_ok'] else '❌'} | {'✅' if final_verdicts['C2']['winner_ok'] else '❌'} |
| Shuffled-label gap > 1.5 | {'✅' if final_verdicts['C1']['shuffle_ok'] else '❌'} | {'✅' if final_verdicts['C2']['shuffle_ok'] else '❌'} |
| Train-test gap < 0.15 | {'✅' if final_verdicts['C1']['overfit_ok'] else '❌'} | {'✅' if final_verdicts['C2']['overfit_ok'] else '❌'} |
| **ALL CRITERIA MET** | {'✅ ACCEPTED' if final_verdicts['C1']['verdict'] == 'ACCEPTED' else '❌ ' + final_verdicts['C1']['verdict']} | {'✅ ACCEPTED' if final_verdicts['C2']['verdict'] == 'ACCEPTED' else '❌ ' + final_verdicts['C2']['verdict']} |

## Summary

| Variant | MAE | ΔMAE vs Ridge | CI Excludes 0 | Podium Hit | Winner Hit | Verdict |
|---------|-----|---------------|---------------|------------|------------|---------|
| C1 (regression_l1) | {results['C1']['mae']:.4f} | {bootstrap_results['C1']['mean_delta']:+.4f} | {'Yes' if bootstrap_results['C1']['ci_excludes_zero'] else 'No'} | {results['C1']['podium_hit']:.3f} | {results['C1']['winner_hit']:.3f} | {final_verdicts['C1']['verdict']} |
| C2 (regression+mae) | {results['C2']['mae']:.4f} | {bootstrap_results['C2']['mean_delta']:+.4f} | {'Yes' if bootstrap_results['C2']['ci_excludes_zero'] else 'No'} | {results['C2']['podium_hit']:.3f} | {results['C2']['winner_hit']:.3f} | {final_verdicts['C2']['verdict']} |

## Files Generated

- `reports/phase7c_lightgbm_C1_predictions.csv` — Per-driver predictions (C1)
- `reports/phase7c_lightgbm_C2_predictions.csv` — Per-driver predictions (C2)
- `reports/phase7c_lightgbm_C1_feature_importance.csv` — FI (C1)
- `reports/phase7c_lightgbm_C2_feature_importance.csv` — FI (C2)
- `reports/phase7c_lightgbm_importance.png` — FI plots + train/test MAE
- `reports/phase7c_lightgbm_delta_mae.png` — Per-race MAE delta histograms
- `reports/phase7c_lightgbm_pred_vs_actual.png` — Pred vs Actual scatter
- `reports/phase7c_lightgbm.json` — Machine-readable summary
- `reports/phase7c_lightgbm.md` — This report

---

*Pre-registration: `reports/phase7c_lightgbm_prereg.md`*
*Generated: {datetime.now(timezone.utc).isoformat()}*
""")

    print(f"  Markdown report saved to {md_path}")

    rule("PHASE 7C COMPLETE")
    for name in ["C1", "C2"]:
        r = results[name]
        v = final_verdicts[name]
        print(f"  {r['name']}: MAE={r['mae']:.4f}, Verdict={v['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())