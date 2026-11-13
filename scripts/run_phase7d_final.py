"""Phase 7D: Head-to-Head Final Comparison & Consolidation.

Compares XGBoost (corrected) vs LightGBM C2 vs Ridge baseline.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model
from f1pred.xgboost_model import walk_forward_xgboost
from f1pred.lightgbm_model import walk_forward_lightgbm
from f1pred.xgboost_model import paired_bootstrap_delta, XGBOOST_PARAMS, MONOTONE_CONSTRAINTS
from f1pred.lightgbm_model import LIGHTGBM_MSE_PARAMS

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

TARGET = "finish"
MIN_TRAIN_RACES = 20
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 42


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


def run_model(name: str, df: pd.DataFrame) -> dict:
    """Run a model and return results."""
    if name == "Ridge":
        results = model.walk_forward(df, features.ALL_FEATURES, min_train=MIN_TRAIN_RACES)
        preds = results["preds"]
        preds["residual"] = preds["pred"] - preds["finish"]
        return {
            "name": "Ridge",
            "mae": results["mae"],
            "spearman": results["rho"],
            "podium_hit": results["podium_hit"],
            "winner_hit": results["winner_hit"],
            "predictions": preds,
        }
    elif name == "XGBoost":
        xgb_results = walk_forward_xgboost(
            df, features.ALL_FEATURES, min_train_races=MIN_TRAIN_RACES,
            shuffle=False, monotone_constraints=MONOTONE_CONSTRAINTS,
        )
        return {
            "name": "XGBoost",
            "mae": xgb_results["mae"],
            "spearman": xgb_results["spearman"],
            "podium_hit": xgb_results["podium_hit"],
            "winner_hit": xgb_results["winner_hit"],
            "predictions": xgb_results["predictions"],
            "feature_importance": xgb_results["feature_importance"],
        }
    elif name == "LightGBM C2":
        lgb_results = walk_forward_lightgbm(
            df, features.ALL_FEATURES, min_train_races=MIN_TRAIN_RACES,
            shuffle=False, monotone_constraints=MONOTONE_CONSTRAINTS,
            params=LIGHTGBM_MSE_PARAMS,
        )
        return {
            "name": "LightGBM C2",
            "mae": lgb_results["mae"],
            "spearman": lgb_results["spearman"],
            "podium_hit": lgb_results["podium_hit"],
            "winner_hit": lgb_results["winner_hit"],
            "predictions": lgb_results["predictions"],
            "feature_importance": lgb_results["feature_importance"],
        }
    else:
        raise ValueError(f"Unknown model: {name}")


def paired_bootstrap_delta_models(preds_a: pd.DataFrame, preds_b: pd.DataFrame,
                                   n_resamples: int = N_BOOTSTRAP,
                                   seed: int = BOOTSTRAP_SEED) -> dict:
    """Paired bootstrap 95% CI on per-race MAE delta (A - B)."""
    # Make copies to avoid modifying originals
    a = preds_a.copy()
    b = preds_b.copy()
    
    for p in [a, b]:
        if "residual" not in p.columns:
            if "pred" in p.columns and "finish" in p.columns:
                p["residual"] = p["pred"] - p["finish"]
            elif "pred_ens" in p.columns and "finish" in p.columns:
                p["residual"] = p["pred_ens"] - p["finish"]
            else:
                raise ValueError(f"Cannot compute residual: columns={p.columns.tolist()}")

    mae_a = a.groupby("race_idx")["residual"].apply(lambda x: np.mean(np.abs(x))).reset_index()
    mae_a.columns = ["race_idx", "mae_a"]
    mae_b = b.groupby("race_idx")["residual"].apply(lambda x: np.mean(np.abs(x))).reset_index()
    mae_b.columns = ["race_idx", "mae_b"]

    merged = mae_a.merge(mae_b, on="race_idx", how="inner")
    deltas = merged["mae_a"].values - merged["mae_b"].values
    mean_delta = np.mean(deltas)

    rng = np.random.default_rng(seed)
    boot_means = [np.mean(rng.choice(deltas, len(deltas))) for _ in range(n_resamples)]
    ci_lower = np.percentile(boot_means, 2.5)
    ci_upper = np.percentile(boot_means, 97.5)

    n_pos = np.sum(deltas > 0)
    n_neg = np.sum(deltas < 0)
    n_tot = n_pos + n_neg
    if n_tot > 0:
        from scipy.stats import binomtest
        sign_p = binomtest(min(n_pos, n_neg), n=n_tot, p=0.5, alternative="two-sided").pvalue
    else:
        sign_p = 1.0

    try:
        from scipy.stats import wilcoxon
        wilc_stat, wilc_p = wilcoxon(deltas, alternative="two-sided")
    except:
        wilc_stat, wilc_p = np.nan, np.nan

    return {
        "mean_delta": float(mean_delta),
        "ci_lower": float(ci_lower),
        "ci_upper": float(ci_upper),
        "sign_p": float(sign_p),
        "wilcoxon_p": float(wilc_p),
        "deltas_per_race": deltas,
        "n_races": int(n_tot),
        "ci_excludes_zero": (ci_lower > 0) or (ci_upper < 0),
    }


def ensemble_predictions(preds_a: pd.DataFrame, preds_b: pd.DataFrame, weight_a: float = 0.5) -> pd.DataFrame:
    """Create ensemble predictions (weighted average of preds)."""
    merged = preds_a.merge(preds_b, on=["year", "round", "race_idx", "driver", "finish"],
                           suffixes=("_a", "_b"))
    merged["pred_ens"] = weight_a * merged["pred_a"] + (1 - weight_a) * merged["pred_b"]
    merged["residual_ens"] = merged["pred_ens"] - merged["finish"]
    # Add compatibility columns for bootstrap function
    merged["pred"] = merged["pred_ens"]
    merged["residual"] = merged["residual_ens"]
    return merged


def main() -> int:
    rule("PHASE 7D: HEAD-TO-HEAD FINAL & CONSOLIDATION")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print()

    # ------------------------------------------------------------------ Load data
    rule("[1] LOAD DATA")
    con = db.connect()
    con.row_factory = None
    df = features.build_features(con)
    con.close()
    print(f"  Total races: {len(df['race_idx'].unique())}, rows: {len(df)}")

    # ------------------------------------------------------------------ Run all models
    rule("[2] RUN ALL MODELS")
    models = {}
    for name in ["Ridge", "XGBoost", "LightGBM C2"]:
        models[name] = run_model(name, df)
        print(f"  {name}: MAE={models[name]['mae']:.4f}, ρ={models[name]['spearman']:.4f}, "
              f"Podium={models[name]['podium_hit']:.3f}, Winner={models[name]['winner_hit']:.3f}")

    # ------------------------------------------------------------------ Head-to-head XGBoost vs LightGBM C2
    rule("[3] HEAD-TO-HEAD: XGBOOST vs LIGHTGBM C2")
    
    xgb_vs_lgb = paired_bootstrap_delta_models(
        models["XGBoost"]["predictions"],
        models["LightGBM C2"]["predictions"]
    )
    print(f"  Mean ΔMAE (XGB - LGB): {xgb_vs_lgb['mean_delta']:+.4f}")
    print(f"  95% CI: [{xgb_vs_lgb['ci_lower']:+.4f}, {xgb_vs_lgb['ci_upper']:+.4f}]")
    print(f"  CI excludes 0: {xgb_vs_lgb['ci_excludes_zero']}")
    print(f"  Sign p: {xgb_vs_lgb['sign_p']:.4f}, Wilcoxon p: {xgb_vs_lgb['wilcoxon_p']:.4f}")

    # ------------------------------------------------------------------ Each vs Ridge
    rule("[4] EACH MODEL vs RIDGE")
    for name in ["XGBoost", "LightGBM C2"]:
        bs = paired_bootstrap_delta_models(
            models[name]["predictions"],
            models["Ridge"]["predictions"]
        )
        print(f"\n  {name} vs Ridge:")
        print(f"    Mean ΔMAE ({name} - Ridge): {bs['mean_delta']:+.4f}")
        print(f"    95% CI: [{bs['ci_lower']:+.4f}, {bs['ci_upper']:+.4f}]")
        print(f"    CI excludes 0: {bs['ci_excludes_zero']}")

    # ------------------------------------------------------------------ Ensemble
    rule("[5] ENSEMBLE (50/50 XGB + LGB C2)")
    ens_preds = ensemble_predictions(
        models["XGBoost"]["predictions"],
        models["LightGBM C2"]["predictions"],
        weight_a=0.5
    )
    ens_mae = np.mean(np.abs(ens_preds["residual_ens"]))
    ens_rho = ens_preds["pred_ens"].corr(ens_preds["finish"], method="spearman")
    print(f"  Ensemble MAE: {ens_mae:.4f} (XGB: {models['XGBoost']['mae']:.4f}, LGB: {models['LightGBM C2']['mae']:.4f})")
    print(f"  Ensemble ρ: {ens_rho:.4f}")

    # Ensemble vs best single
    best_single = min(models["XGBoost"]["mae"], models["LightGBM C2"]["mae"])
    print(f"  Best single MAE: {best_single:.4f}")
    print(f"  Ensemble gain vs best: {best_single - ens_mae:+.4f}")

    # Ensemble vs Ridge
    ens_vs_ridge = paired_bootstrap_delta_models(
        ens_preds, models["Ridge"]["predictions"]
    )
    print(f"  Ensemble vs Ridge: Δ={ens_vs_ridge['mean_delta']:+.4f}, "
          f"CI=[{ens_vs_ridge['ci_lower']:+.4f}, {ens_vs_ridge['ci_upper']:+.4f}]")

    # ------------------------------------------------------------------ Feature importance comparison
    rule("[6] FEATURE IMPORTANCE COMPARISON")
    ridge_results = model.walk_forward(df, features.ALL_FEATURES, min_train=MIN_TRAIN_RACES)
    ridge_coefs = ridge_results["coef_mean"]
    
    xgb_fi = models["XGBoost"]["feature_importance"].set_index("feature")["gain"].sort_values(ascending=False)
    lgb_fi = models["LightGBM C2"]["feature_importance"].set_index("feature")["gain"].sort_values(ascending=False)
    ridge_rank = pd.Series({f: abs(c) for f, c in ridge_coefs.items()}).sort_values(ascending=False)
    
    common = ridge_rank.index.intersection(xgb_fi.index).intersection(lgb_fi.index)
    from scipy.stats import spearmanr
    rho_rx, _ = spearmanr(ridge_rank[common], xgb_fi[common])
    rho_rl, _ = spearmanr(ridge_rank[common], lgb_fi[common])
    rho_xl, _ = spearmanr(xgb_fi[common], lgb_fi[common])
    
    print(f"  Spearman ρ (Ridge vs XGB): {rho_rx:.4f}")
    print(f"  Spearman ρ (Ridge vs LGB): {rho_rl:.4f}")
    print(f"  Spearman ρ (XGB vs LGB): {rho_xl:.4f}")

    # ------------------------------------------------------------------ Final Decision
    rule("[7] FINAL MODEL SELECTION")
    
    ladder = {
        "Ridge": {"mae": models["Ridge"]["mae"], "podium": models["Ridge"]["podium_hit"], 
                  "winner": models["Ridge"]["winner_hit"], "overfit": "~0.08", "status": "Baseline"},
        "XGBoost": {"mae": models["XGBoost"]["mae"], "podium": models["XGBoost"]["podium_hit"],
                    "winner": models["XGBoost"]["winner_hit"], "overfit": "0.084", "status": "ACCEPTED"},
        "LightGBM C2": {"mae": models["LightGBM C2"]["mae"], "podium": models["LightGBM C2"]["podium_hit"],
                        "winner": models["LightGBM C2"]["winner_hit"], "overfit": "0.077", "status": "ACCEPTED"},
        "LightGBM C1": {"mae": 3.1193, "podium": 0.678, "winner": 0.514, "overfit": "0.501", "status": "REJECTED"},
    }
    
    print(f"\n  LADDER TABLE:")
    print(f"  {'Model':<15} {'MAE':>8} {'ρ':>8} {'Winner':>8} {'Podium':>8} {'Overfit':>8} {'Status'}")
    for name, m in ladder.items():
        print(f"  {name:<15} {m['mae']:>8.4f} {m.get('rho', 0):>8.4f} {m['winner']:>8.3f} {m['podium']:>8.3f} {m['overfit']:>8} {m['status']}")

    # Decision logic
    xgb_mae = models["XGBoost"]["mae"]
    lgb_mae = models["LightGBM C2"]["mae"]
    xgb_vs_lgb_delta = xgb_vs_lgb["mean_delta"]
    xgb_vs_lgb_ci = (xgb_vs_lgb["ci_lower"], xgb_vs_lgb["ci_upper"])
    
    print(f"\n  COMPARISON:")
    print(f"  XGBoost MAE: {xgb_mae:.4f}")
    print(f"  LightGBM C2 MAE: {lgb_mae:.4f}")
    print(f"  XGB - LGB: {xgb_vs_lgb_delta:+.4f}, CI: [{xgb_vs_lgb_ci[0]:+.4f}, {xgb_vs_lgb_ci[1]:+.4f}]")
    print(f"  Statistically different: {xgb_vs_lgb['ci_excludes_zero']}")
    
    # Final decision
    if xgb_vs_lgb["ci_excludes_zero"] and xgb_vs_lgb_delta < 0:
        final = "XGBoost"
        reason = "XGBoost statistically significantly better MAE"
    elif xgb_vs_lgb["ci_excludes_zero"] and xgb_vs_lgb_delta > 0:
        final = "LightGBM C2"
        reason = "LightGBM C2 statistically significantly better MAE"
    else:
        final = "XGBoost"
        reason = "Statistically indistinguishable; XGBoost chosen for maturity, monotone constraints support, and ecosystem"
    
    print(f"\n  FINAL MODEL: {final}")
    print(f"  REASON: {reason}")
    print(f"  ENSEMBLE: {'NOT WARRANTED — gain vs best single = {best_single - ens_mae:.4f}' if ens_mae >= best_single - 0.01 else 'WARRANTED'}")

    # For markdown
    final_lower = final.lower().replace(" ", "-")

    # ------------------------------------------------------------------ Save results
    rule("[8] SAVE RESULTS")
    
    # Clean bootstrap results for JSON (remove numpy arrays, convert numpy types)
    def clean_bs(bs):
        cleaned = {}
        for k, v in bs.items():
            if k == "deltas_per_race":
                continue
            if isinstance(v, (np.integer, np.floating)):
                cleaned[k] = float(v)
            elif isinstance(v, np.bool_):
                cleaned[k] = bool(v)
            elif isinstance(v, (np.ndarray, list)):
                continue
            else:
                cleaned[k] = v
        return cleaned
    
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ladder": {k: {kk: float(vv) if isinstance(vv, (int, float)) else vv for kk, vv in v.items()} for k, v in ladder.items()},
        "head_to_head": {
            "xgb_vs_lgb": clean_bs(xgb_vs_lgb),
        },
        "vs_ridge": {
            "xgb": clean_bs(paired_bootstrap_delta_models(models["XGBoost"]["predictions"], models["Ridge"]["predictions"])),
            "lgb": clean_bs(paired_bootstrap_delta_models(models["LightGBM C2"]["predictions"], models["Ridge"]["predictions"])),
            "ensemble": clean_bs(ens_vs_ridge),
        },
        "ensemble": {
            "mae": float(ens_mae),
            "spearman": float(ens_rho),
            "vs_best_single": float(best_single - ens_mae),
        },
        "feature_importance_spearman": {
            "ridge_xgb": float(rho_rx),
            "ridge_lgb": float(rho_rl),
            "xgb_lgb": float(rho_xl),
        },
        "final_model": final,
        "final_reason": reason,
    }
    
    with open(REPORTS_DIR / "phase7d_final.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  JSON saved: reports/phase7d_final.json")

    # Markdown report
    md_path = REPORTS_DIR / "phase7d_final.md"
    with open(md_path, "w") as f:
        f.write(f"""# Phase 7D: Head-to-Head Final & Consolidation

**Date:** {datetime.now(timezone.utc).isoformat()}
**Models compared:** Ridge (baseline), XGBoost, LightGBM C2
**Pre-registrations:** Phase 7A/7B/7C

---

## Ladder Table

| Model | MAE | ρ | Winner | Podium | Overfit Gap | Status |
|-------|-----|---|--------|--------|-------------|--------|
| Ridge (baseline) | {ladder['Ridge']['mae']:.4f} | {ridge_results['rho']:.4f} | {ladder['Ridge']['winner']:.3f} | {ladder['Ridge']['podium']:.3f} | ~0.08 | Baseline |
| **XGBoost** | **{ladder['XGBoost']['mae']:.4f}** | {models['XGBoost']['spearman']:.4f} | {ladder['XGBoost']['winner']:.3f} | {ladder['XGBoost']['podium']:.3f} | 0.084 | **ACCEPTED** |
| **LightGBM C2** | {ladder['LightGBM C2']['mae']:.4f} | {models['LightGBM C2']['spearman']:.4f} | {ladder['LightGBM C2']['winner']:.3f} | {ladder['LightGBM C2']['podium']:.3f} | 0.077 | **ACCEPTED** |
| LightGBM C1 | 3.1193 | N/A | 0.514 | 0.678 | **0.501** | **REJECTED** |

---

## Head-to-Head: XGBoost vs LightGBM C2

- **Mean ΔMAE (XGB - LGB):** {xgb_vs_lgb['mean_delta']:+.4f}
- **95% CI:** [{xgb_vs_lgb['ci_lower']:+.4f}, {xgb_vs_lgb['ci_upper']:+.4f}]
- **CI excludes 0:** {'Yes' if xgb_vs_lgb['ci_excludes_zero'] else 'No'}
- **Sign test p:** {xgb_vs_lgb['sign_p']:.4f}
- **Wilcoxon p:** {xgb_vs_lgb['wilcoxon_p']:.4f}

**Interpretation:** {'XGBoost significantly better' if xgb_vs_lgb['ci_excludes_zero'] and xgb_vs_lgb['mean_delta'] < 0 else 'LightGBM C2 significantly better' if xgb_vs_lgb['ci_excludes_zero'] and xgb_vs_lgb['mean_delta'] > 0 else 'Statistically indistinguishable (CI contains 0)'}

---

## Each vs Ridge

| Model | Mean ΔMAE | 95% CI | CI Excludes 0 |
|-------|-----------|--------|---------------|
| XGBoost | {paired_bootstrap_delta_models(models['XGBoost']['predictions'], models['Ridge']['predictions'])['mean_delta']:+.4f} | [{paired_bootstrap_delta_models(models['XGBoost']['predictions'], models['Ridge']['predictions'])['ci_lower']:+.4f}, {paired_bootstrap_delta_models(models['XGBoost']['predictions'], models['Ridge']['predictions'])['ci_upper']:+.4f}] | {paired_bootstrap_delta_models(models['XGBoost']['predictions'], models['Ridge']['predictions'])['ci_excludes_zero']} |
| LightGBM C2 | {paired_bootstrap_delta_models(models['LightGBM C2']['predictions'], models['Ridge']['predictions'])['mean_delta']:+.4f} | [{paired_bootstrap_delta_models(models['LightGBM C2']['predictions'], models['Ridge']['predictions'])['ci_lower']:+.4f}, {paired_bootstrap_delta_models(models['LightGBM C2']['predictions'], models['Ridge']['predictions'])['ci_upper']:+.4f}] | {paired_bootstrap_delta_models(models['LightGBM C2']['predictions'], models['Ridge']['predictions'])['ci_excludes_zero']} |

---

## Ensemble (50/50 XGB + LGB C2)

- **Ensemble MAE:** {ens_mae:.4f}
- **Best single MAE:** {best_single:.4f}
- **Gain vs best single:** {best_single - ens_mae:+.4f}
- **Ensemble vs Ridge:** Δ={ens_vs_ridge['mean_delta']:+.4f}, CI=[{ens_vs_ridge['ci_lower']:+.4f}, {ens_vs_ridge['ci_upper']:+.4f}], excludes 0: {ens_vs_ridge['ci_excludes_zero']}

**Ensemble verdict:** {'WARRANTED' if ens_mae < best_single - 0.01 else 'NOT WARRANTED — no meaningful gain over best single'}

---

## Feature Importance Correlation

| Comparison | Spearman ρ |
|------------|------------|
| Ridge vs XGBoost | {rho_rx:.4f} |
| Ridge vs LightGBM C2 | {rho_rl:.4f} |
| XGBoost vs LightGBM C2 | {rho_xl:.4f} |

**Interpretation:** {'High consistency across tree models' if rho_xl > 0.8 else 'Moderate consistency' if rho_xl > 0.5 else 'Low consistency'}

---

## Final Model Selection

**Selected Model:** **{final}**

**Reason:** {reason}

---

## Phase 7 Summary

| Phase | Task | Result |
|-------|------|--------|
| 7A | Linear Diagnostics | H0 REJECTED — nonlinearity/heteroskedasticity detected |
| 7B | XGBoost | **ACCEPTED** (MAE=3.238, Δ=-0.037, CI excludes 0) |
| 7C | LightGBM | **C2 ACCEPTED** (MAE=3.238), C1 REJECTED (overfit) |
| 7D | Consolidation | **{final} selected** |

---

## Model Finalization

**Final model to promote:** **{final}**

**Next steps (awaiting user approval):**
1. Bump `MODEL_VERSION` to `phase7-{final_lower}-1.0`
2. Update `LIMITATIONS.md` with §7B (XGBoost bug + resolution), §7C (LightGBM results), §7D (final selection)
3. Save forecast for upcoming race with `--grid-file`
4. Run full regression suite (must PASS 100%)

---

*Generated: {datetime.now(timezone.utc).isoformat()}*
*Pre-registrations: `reports/phase7a_linear_diagnostics_prereg.md`, `reports/phase7b_xgboost_prereg.md`, `reports/phase7c_lightgbm_prereg.md`*
""")

    print(f"  Markdown saved: {md_path}")

    rule("PHASE 7D COMPLETE")
    print(f"  Final model: {final}")
    print(f"  Reason: {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())