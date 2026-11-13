"""Phase 7A: Linear Regression Diagnostics for Ridge Model.

Pre-registered in reports/phase7a_linear_diagnostics_prereg.md

Runs walk-forward with Ridge (α=1.0), collects residuals per fold,
and runs comprehensive linear diagnostics:
- Residual vs Fitted, Q-Q, Scale-Location, Histogram
- Breusch-Pagan (heteroskedasticity)
- Ramsey RESET (nonlinearity)
- VIF per fold (multicollinearity)
- Partial residual plots (12 features)
- Cook's Distance (influence)
- Interaction screening (top-5 feature pairs)
"""

from __future__ import annotations

import sys
import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
from scipy.stats import shapiro, skew, kurtosis, probplot
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.stats.stattools import durbin_watson
from statsmodels.stats.diagnostic import linear_rainbow
from statsmodels.regression.linear_model import OLS
from statsmodels.tools.tools import add_constant
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

TARGET = "finish"
MIN_TRAIN_RACES = 20
RIDGE_ALPHA = 1.0
ALL_FEATURES = [
    "grid", "driver_form", "team_form", "non_finish_rate",
    "practice_pos", "practice_gap_pct", "practice_laps_30", "no_practice_time",
    "q_position", "q_gap_pct", "no_q_time", "on_pole",
]

# Top-5 features by |coef| from Phase 3 (pre-registered)
TOP5_FEATURES = ["grid", "q_position", "driver_form", "team_form", "practice_pos"]
INTERACTION_PAIRS = [
    ("grid", "q_position"),
    ("grid", "driver_form"),
    ("grid", "team_form"),
    ("grid", "practice_pos"),
    ("q_position", "driver_form"),
    ("q_position", "team_form"),
    ("driver_form", "team_form"),
    ("driver_form", "practice_pos"),
    ("team_form", "practice_pos"),
    ("practice_pos", "q_position"),
]

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


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


def rule_print(msg: str) -> None:
    print(f"  {msg}")


def main() -> int:
    rule("PHASE 7A: LINEAR REGRESSION DIAGNOSTICS")
    print(f"Started: {datetime.now(timezone.utc).isoformat()}")
    print()

    # ------------------------------------------------------------------ data
    rule("[1] LOAD DATA & WALK-FORWARD RESIDUALS")
    con = db.connect()
    con.row_factory = None
    df = features.build_features(con)
    con.close()

    races = np.sort(df["race_idx"].unique())
    min_train = 20
    val_races = [r for r in np.sort(df["race_idx"].unique()) if r > 20]
    n_folds = len(val_races)
    print(f"  Total races: {len(races)}, validation folds: {n_folds}")
    print(f"  Total rows: {len(df)}, features: {len(features.ALL_FEATURES)}")

    # Collect residuals per fold
    all_residuals = []
    all_vifs = []
    all_cooks = []
    all_interactions = []

    for fold_idx, te_race in enumerate(sorted(val_races)):
        if fold_idx % 20 == 0:
            print(f"  Fold {fold_idx+1}/{len(val_races)}: race_idx={te_race}")

        train = df[df["race_idx"] < te_race]
        test = df[df["race_idx"] == te_race]

        if train.empty or test.empty:
            continue

        X_train = train[features.ALL_FEATURES]
        y_train = train[TARGET]
        X_test = test[features.ALL_FEATURES]
        y_test = test[TARGET]

        # Fit Ridge on train
        # Filter out rows with NaN in target
        train_mask = y_train.notna()
        test_mask = y_test.notna()
        if not train_mask.any() or not test_mask.any():
            continue

        X_train_clean = X_train.loc[train_mask]
        y_train_clean = y_train.loc[train_mask]
        X_test_clean = X_test.loc[test_mask]
        y_test_clean = y_test.loc[test_mask]

        # Fit Ridge on train
        scaler = StandardScaler().fit(X_train_clean)
        X_train_scaled = scaler.transform(X_train_clean)
        X_test_scaled = scaler.transform(X_test_clean)

        ridge = Ridge(alpha=1.0).fit(X_train_scaled, y_train_clean)
        y_pred = ridge.predict(X_test_scaled)

        # Residuals
        residuals = y_pred - y_test_clean.values
        test_residuals = pd.DataFrame({
            "year": test.loc[test_mask, "year"].values,
            "round": test.loc[test_mask, "round"].values,
            "driver": test.loc[test_mask, "driver"].values,
            "race_idx": test.loc[test_mask, "race_idx"].values,
            "pred": y_pred,
            "finish": y_test_clean.values,
            "residual": residuals,
        })
        for feat in features.ALL_FEATURES:
            test_residuals[f"feat_{feat}"] = X_test.loc[test_mask, feat].values
        all_residuals.append(test_residuals)

        # VIF on training set
        X_train_const = add_constant(X_train, has_constant="add")
        vifs = {}
        for i, feat in enumerate(features.ALL_FEATURES):
            try:
                vif = variance_inflation_factor(X_train_const.values, i+1)
                vifs[feat] = vif
            except Exception:
                vifs[feat] = np.nan
        vifs["fold"] = fold_idx
        vifs["race_idx"] = te_race
        all_vifs.append(vifs)

        # Cook's Distance on training set
        try:
            ols = OLS(y_train, X_train_const).fit()
            influence = ols.get_influence()
            cooks_d = influence.cooks_distance[0]
            # Average Cook's D per fold
            all_cooks.append({
                "fold": fold_idx,
                "race_idx": te_race,
                "mean_cooks_d": np.mean(cooks_d),
                "max_cooks_d": np.max(cooks_d),
                "n_influential": int(np.sum(cooks_d > 4/len(y_train))),
            })
        except Exception:
            all_cooks.append({"fold": fold_idx, "race_idx": te_race, "mean_cooks_d": np.nan, "max_cooks_d": np.nan, "n_influential": 0})

        # Interaction screening on test set (top-10 pairs)
        for feat1, feat2 in INTERACTION_PAIRS:
            if feat1 in X_test.columns and feat2 in X_test.columns:
                X_int = X_test.copy()
                X_int[f"{feat1}_x_{feat2}"] = X_int[feat1] * X_int[feat2]
                # Need to fit a new scaler for the interaction features
                X_int_scaled = scaler.transform(X_int[features.ALL_FEATURES])
                # Add interaction column separately since scaler doesn't have it
                int_col = X_int[f"{feat1}_x_{feat2}"].values.reshape(-1, 1)
                X_int_scaled = np.hstack([X_int_scaled, int_col])
                try:
                    # Fit Ridge on train + interaction
                    X_train_int = X_train.copy()
                    X_train_int[f"{feat1}_x_{feat2}"] = X_train_int[feat1] * X_train_int[feat2]
                    X_train_int_scaled = scaler.transform(X_train_int[features.ALL_FEATURES])
                    int_col_train = X_train_int[f"{feat1}_x_{feat2}"].values.reshape(-1, 1)
                    X_train_int_scaled = np.hstack([scaler.transform(X_train[features.ALL_FEATURES]), int_col_train])
                    
                    ridge_int = Ridge(alpha=1.0).fit(X_train_int_scaled, y_train)
                    y_pred_int = ridge_int.predict(X_int_scaled)
                    # Compare MAE
                    mae_base = np.mean(np.abs(y_test.values - ridge.predict(X_test_scaled)))
                    mae_int = np.mean(np.abs(y_test.values - y_pred_int))
                    all_interactions.append({
                        "fold": fold_idx,
                        "race_idx": te_race,
                        "feat1": feat1,
                        "feat2": feat2,
                        "mae_base": mae_base,
                        "mae_int": mae_int,
                        "improvement": mae_base - mae_int,
                    })
                except Exception:
                    all_interactions.append({
                        "fold": fold_idx, "race_idx": te_race,
                        "feat1": feat1, "feat2": feat2,
                        "mae_base": np.nan, "mae_int": np.nan, "improvement": np.nan,
                    })

    residuals_df = pd.concat(all_residuals, ignore_index=True)
    vifs_df = pd.DataFrame(all_vifs)
    cooks_df = pd.DataFrame(all_cooks)
    interactions_df = pd.DataFrame(all_interactions)

    print(f"  Collected {len(residuals_df)} residuals across {n_folds} folds")
    print(f"  Collected VIFs for {len(vifs_df)} fold-feature combinations")
    print(f"  Collected Cook's D for {len(cooks_df)} folds")
    print(f"  Collected {len(interactions_df)} interaction tests")

    # ------------------------------------------------------------------ global residual diagnostics
    rule("[2] GLOBAL RESIDUAL DIAGNOSTICS")
    residuals = residuals_df["residual"].values
    fitted = residuals_df["pred"].values

    # Basic stats
    n_res = len(residuals)
    resid_mean = np.mean(residuals)
    resid_std = np.std(residuals)
    resid_skew = skew(residuals)
    resid_kurt = kurtosis(residuals)

    # Shapiro-Wilk (subsample for large n)
    if n_res > 5000:
        shapiro_sample = np.random.choice(residuals, 5000, replace=False)
        shapiro_stat, shapiro_p = shapiro(shapiro_sample)
    else:
        shapiro_stat, shapiro_p = shapiro(residuals)

    # Breusch-Pagan
    X_fitted = add_constant(fitted)
    bp_lm, bp_p, _, _ = het_breuschpagan(residuals, X_fitted)

    # Durbin-Watson
    dw = durbin_watson(residuals)

    print(f"  Residuals: n={n_res}, mean={resid_mean:.4f}, std={resid_std:.4f}")
    print(f"  Skewness: {resid_skew:.4f}, Kurtosis: {resid_kurt:.4f}")
    print(f"  Shapiro-Wilk: W={shapiro_stat:.4f}, p={shapiro_p:.4f} {'PASS' if shapiro_p > 0.05 else 'FAIL'}")
    print(f"  Breusch-Pagan: LM={bp_lm:.4f}, p={bp_p:.4f} {'PASS' if bp_p > 0.05 else 'FAIL'}")
    print(f"  Durbin-Watson: {dw:.4f} {'PASS' if 1.5 < dw < 2.5 else 'FAIL'}")

    # ------------------------------------------------------------------ diagnostic plots
    rule("[3] DIAGNOSTIC PLOTS")
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # Residual vs Fitted
    axes[0, 0].scatter(fitted, residuals, alpha=0.3, s=5)
    axes[0, 0].axhline(0, color="red", linestyle="--", linewidth=1)
    axes[0, 0].set_xlabel("Fitted values")
    axes[0, 0].set_ylabel("Residuals")
    axes[0, 0].set_title("Residuals vs Fitted")
    axes[0, 0].grid(True, alpha=0.3)

    # Q-Q plot
    probplot(residuals, dist="norm", plot=axes[0, 1])
    axes[0, 1].set_title("Q-Q Plot")
    axes[0, 1].grid(True, alpha=0.3)

    # Scale-Location
    standardized_resid = (residuals - np.mean(residuals)) / np.std(residuals)
    sqrt_abs_std = np.sqrt(np.abs(standardized_resid))
    axes[1, 0].scatter(fitted, sqrt_abs_std, alpha=0.3, s=5)
    axes[1, 0].set_xlabel("Fitted values")
    axes[1, 0].set_ylabel(r"$\sqrt{|Standardized Residuals|}$")
    axes[1, 0].set_title("Scale-Location")
    axes[1, 0].grid(True, alpha=0.3)

    # Histogram
    axes[1, 1].hist(residuals, bins=50, edgecolor="black", alpha=0.7)
    axes[1, 1].set_xlabel("Residual")
    axes[1, 1].set_ylabel("Frequency")
    axes[1, 1].set_title("Residual Histogram")
    axes[1, 1].grid(True, alpha=0.3)

    plt.tight_layout()
    path = save_fig("phase7a_residual_diagnostics.png")
    print(f"  Saved: {path}")

    # Residual vs Race Order (autocorrelation check)
    rule_print("Residual vs Race Order")
    fig, ax = plt.subplots(figsize=(12, 4))
    race_order = residuals_df["race_idx"].values
    ax.scatter(race_order, residuals, alpha=0.4, s=5)
    ax.axhline(0, color="red", linestyle="--", linewidth=1)
    ax.set_xlabel("Race Index (chronological)")
    ax.set_ylabel("Residual")
    ax.set_title("Residuals vs Race Order (temporal autocorrelation check)")
    ax.grid(True, alpha=0.3)
    path = save_fig("phase7a_residual_vs_order.png")
    print(f"  Saved: {path}")

    # ------------------------------------------------------------------ Ramsey RESET test (per fold)
    rule("[4] RAMSEY RESET TEST (per fold, aggregated)")
    reset_pvalues = []
    for fold_idx, te_race in enumerate(sorted(val_races)):
        train = df[df["race_idx"] < te_race]
        test = df[df["race_idx"] == te_race]
        if train.empty or test.empty:
            continue

        X_train = train[features.ALL_FEATURES]
        y_train = train[TARGET]
        X_test = test[features.ALL_FEATURES]
        y_test = test[TARGET]

        # Filter out rows with NaN in target
        train_mask = y_train.notna()
        test_mask = y_test.notna()
        if not train_mask.any() or not test_mask.any():
            continue

        X_train_clean = X_train.loc[train_mask]
        y_train_clean = y_train.loc[train_mask]
        X_test_clean = X_test.loc[test_mask]
        y_test_clean = y_test.loc[test_mask]

        scaler = StandardScaler().fit(X_train_clean)
        X_train_scaled = scaler.transform(X_train_clean)
        X_test_scaled = scaler.transform(X_test_clean)

        ridge = Ridge(alpha=1.0).fit(X_train_scaled, y_train_clean)
        y_pred = ridge.predict(X_test_scaled)

        # RESET: residual ~ pred + pred^2 + pred^3
        residuals_fold = y_pred - y_test_clean.values
        pred = y_pred
        X_reset = pd.DataFrame({
            "pred": pred,
            "pred2": pred**2,
            "pred3": pred**3,
        })
        X_reset = add_constant(X_reset)
        try:
            reset_model = OLS(residuals_fold, X_reset).fit()
            # F-test for pred2 and pred3 jointly
            f_test = reset_model.f_test("pred2 = pred3 = 0")
            reset_pvalues.append(f_test.pvalue)
        except Exception:
            reset_pvalues.append(np.nan)

    valid_p = [p for p in reset_pvalues if not np.isnan(p)]
    if valid_p:
        from scipy.stats import combine_pvalues
        chi2, p_combined = combine_pvalues(valid_p, method="fisher")
        print(f"  RESET tests: {len(valid_p)} valid folds, combined p={p_combined:.6f} {'PASS' if p_combined > 0.05 else 'FAIL'}")
        print(f"  Individual p-values (min/median/max): {np.min(valid_p):.4f}/{np.median(valid_p):.4f}/{np.max(valid_p):.4f}")
    else:
        print("  No valid RESET tests")

    # ------------------------------------------------------------------ VIF analysis
    rule("[5] VIF ANALYSIS (per fold)")
    vif_features = {}
    for feat in features.ALL_FEATURES:
        vals = vifs_df[feat].dropna().values
        if len(vals) > 0:
            vif_features[feat] = {
                "mean": np.mean(vals),
                "median": np.median(vals),
                "max": np.max(vals),
                "min": np.min(vals),
                "n_folds": len(vals),
            }

    print(f"  {'Feature':<25} {'Mean':>8} {'Median':>8} {'Max':>8} {'Min':>8}")
    for feat, stats in sorted(vif_features.items(), key=lambda x: x[1]["mean"], reverse=True):
        print(f"  {feat:<25} {stats['mean']:>8.2f} {stats['median']:>8.2f} {stats['max']:>8.2f} {stats['min']:>8.2f}")

    # VIF Heatmap
    rule_print("VIF Heatmap")
    vif_matrix = vifs_df[features.ALL_FEATURES].values
    fig, ax = plt.subplots(figsize=(10, 6))
    im = ax.imshow(vif_matrix.T, aspect="auto", cmap="Reds", vmin=0, vmax=max(10, np.nanmax(vif_matrix)))
    ax.set_yticks(range(len(features.ALL_FEATURES)))
    ax.set_yticklabels(features.ALL_FEATURES)
    ax.set_xticks(range(len(vif_matrix)))
    ax.set_xticklabels([f"Fold {i+1}" for i in range(len(vif_matrix))], rotation=90, fontsize=6)
    ax.set_title("VIF per Feature per Fold")
    plt.colorbar(im, ax=ax, label="VIF")
    plt.tight_layout()
    path = save_fig("phase7a_vif_heatmap.png")
    print(f"  Saved: {path}")

    # VIF warnings
    high_vif = [(f, s["mean"]) for f, s in vif_features.items() if s["mean"] > 5]
    if high_vif:
        print(f"  WARNING: Features with mean VIF > 5: {[(f, f'{v:.1f}') for f, v in high_vif]}")
    severe_vif = [(f, s["mean"]) for f, s in vif_features.items() if s["mean"] > 10]
    if severe_vif:
        print(f"  CRITICAL: Features with mean VIF > 10: {[(f, f'{v:.1f}') for f, v in severe_vif]}")

    # ------------------------------------------------------------------ Partial residual plots
    rule("[6] PARTIAL RESIDUAL PLOTS (Component+Residual)")
    print(f"  Generating 12 partial residual plots...")

    # Aggregate residuals for partial residual plots
    pred_all = residuals_df["pred"].values
    residual_all = residuals_df["residual"].values
    
    # Fit Ridge on full dataset (filter NaN)
    df_clean = df.dropna(subset=[TARGET])
    scaler_full = StandardScaler().fit(df_clean[features.ALL_FEATURES])
    ridge_full = Ridge(alpha=1.0).fit(
        scaler_full.transform(df_clean[features.ALL_FEATURES]),
        df_clean[TARGET]
    )
    coefs = dict(zip(features.ALL_FEATURES, ridge_full.coef_))

    for feat in features.ALL_FEATURES:
        x_vals = residuals_df[f"feat_{feat}"].values
        # Partial residual = residual + beta_j * x_j
        partial_resid = residual_all + coefs[feat] * x_vals

        fig, ax = plt.subplots(figsize=(6, 5))
        ax.scatter(x_vals, partial_resid, alpha=0.3, s=5)
        # Lowess smooth
        from scipy.interpolate import UnivariateSpline
        order = np.argsort(x_vals)
        if len(x_vals) > 10:
            spl = UnivariateSpline(x_vals[order], partial_resid[order], s=len(x_vals)*0.5)
            x_smooth = np.linspace(x_vals.min(), x_vals.max(), 200)
            ax.plot(x_smooth, spl(x_smooth), color="red", linewidth=2, label="Smooth")
        ax.scatter(x_vals, partial_resid, alpha=0.3, s=5, color="blue")
        ax.axhline(0, color="red", linestyle="--", linewidth=1)
        ax.set_xlabel(feat)
        ax.set_ylabel("Partial Residual")
        ax.set_title(f"Partial Residual: {feat} (β={coefs[feat]:.4f})")
        ax.legend()
        ax.grid(True, alpha=0.3)
        path = save_fig(f"phase7a_partial_residual_{feat}.png")
        print(f"  Saved: {path.name}")

    # ------------------------------------------------------------------ Cook's Distance
    rule("[7] COOK'S DISTANCE (Influence Diagnostics)")
    if len(cooks_df) > 0:
        print(f"  Mean Cook's D per fold: {cooks_df['mean_cooks_d'].mean():.6f}")
        print(f"  Max Cook's D per fold: {cooks_df['max_cooks_d'].mean():.6f}")
        print(f"  Influential points per fold (>4/n): {cooks_df['n_influential'].sum()} total")

        fig, ax = plt.subplots(figsize=(12, 4))
        ax.bar(range(len(cooks_df)), cooks_df["max_cooks_d"], alpha=0.7)
        ax.axhline(4/20, color="red", linestyle="--", label="4/n threshold")
        ax.set_xlabel("Fold")
        ax.set_ylabel("Max Cook's D")
        ax.set_title("Max Cook's Distance per Fold")
        ax.legend()
        ax.grid(True, alpha=0.3)
        path = save_fig("phase7a_cooks_distance.png")
        print(f"  Saved: {path}")

    # ------------------------------------------------------------------ Interaction screening
    rule("[8] INTERACTION SCREENING (top-10 pairs)")
    if len(interactions_df) > 0:
        # Aggregate improvement per pair
        agg = interactions_df.groupby(["feat1", "feat2"]).agg(
            mean_improvement=("improvement", "mean"),
            median_improvement=("improvement", "median"),
            n_folds=("improvement", "count"),
        ).reset_index()
        agg = agg.sort_values("mean_improvement", ascending=False)
        print(f"  Top 5 interaction improvements:")
        for _, row in agg.head().iterrows():
            print(f"  {row['feat1']} x {row['feat2']}: mean ΔMAE={row['mean_improvement']:.4f} ({row['n_folds']} folds)")

        # Save interaction table
        interactions_df.to_csv(REPORTS_DIR / "phase7a_interactions.csv", index=False)
        print(f"  Full table saved to reports/phase7a_interactions.csv")

    # ------------------------------------------------------------------ Summary & Verdict
    rule("[9] SUMMARY & VERDICT")

    verdict_items = []

    # Collect verdict criteria
    verdict_items.append(("Residuals approx normal", shapiro_p > 0.05, f"Shapiro-Wilk p={shapiro_p:.4f}"))
    verdict_items.append(("No heteroskedasticity", bp_p > 0.05, f"Breusch-Pagan p={bp_p:.4f}"))
    verdict_items.append(("No autocorrelation", 1.5 < dw < 2.5, f"Durbin-Watson={dw:.3f}"))
    verdict_items.append(("RESET test (linearity)", p_combined > 0.05 if valid_p else True, f"RESET combined p={p_combined:.4f}" if valid_p else "No valid tests"))
    verdict_items.append(("No severe multicollinearity", all(s["mean"] < 10 for s in vif_features.values()), f"Max mean VIF: {max(s['mean'] for s in vif_features.values()):.1f}"))
    verdict_items.append(("No severe VIF > 5", all(s["mean"] < 5 for s in vif_features.values()), f"Features with VIF>5: {[f for f,s in vif_features.items() if s['mean']>5]}"))

    print()
    rule("VERDICT SUMMARY")
    all_pass = True
    for label, passed, detail in verdict_items:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {label}: {detail}")

    print()
    if all_pass:
        verdict = "LINEAR FIT ADEQUATE (H0 not rejected)"
        print(f"VERDICT: {verdict}")
        print("Implication: Tree models (Task B/C) expected to show at best marginal gains over Ridge.")
    else:
        verdict = "NONLINEARITY/HETEROSKEDASTICITY DETECTED (H0 rejected)"
        print(f"VERDICT: {verdict}")
        print("Implication: Tree models (Task B/C) have credible mechanism to improve over Ridge.")

    # Save diagnostic summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_residuals": int(n_res),
        "shapiro_p": float(shapiro_p),
        "bp_p": float(bp_p),
        "durbin_watson": float(dw),
        "reset_p_combined": float(p_combined) if valid_p else None,
        "reset_p_individual": [float(p) for p in reset_pvalues if not np.isnan(p)],
        "vif_summary": {f: {k: float(v) for k, v in s.items()} for f, s in vif_features.items()},
        "high_vif_features": [f for f, s in vif_features.items() if s["mean"] > 5],
        "severe_vif_features": [f for f, s in vif_features.items() if s["mean"] > 10],
        "verdict": verdict,
        "all_checks_passed": all_pass,
    }
    with open(REPORTS_DIR / "phase7a_linear_diagnostics.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\n  JSON summary saved to reports/phase7a_linear_diagnostics.json")

    # Write markdown report
    rule("[10] WRITING MARKDOWN REPORT")
    md_path = REPORTS_DIR / "phase7a_linear_diagnostics.md"
    
    # Pre-compute values for markdown
    reset_p_str = f"{p_combined:.6f}" if valid_p else "N/A"
    reset_result = "PASS" if (p_combined > 0.05 if valid_p else True) else "FAIL"
    shapiro_result = "PASS" if shapiro_p > 0.05 else "FAIL"
    bp_result = "PASS" if bp_p > 0.05 else "FAIL"
    dw_result = "PASS" if 1.5 < dw < 2.5 else "FAIL"
    
    with open(md_path, "w") as f:
        f.write(f"""# Phase 7A: Linear Regression Diagnostics

**Date:** {datetime.now(timezone.utc).isoformat()}
**Model:** Ridge α=1.0, {len(features.ALL_FEATURES)} features, {n_folds} validation folds
**Pre-registration:** `reports/phase7a_linear_diagnostics_prereg.md`

## Verdict

**{verdict}**

## Global Residual Diagnostics

| Test | Statistic | p-value | Threshold | Result |
|------|-----------|---------|-----------|--------|
| Shapiro-Wilk (subsample) | {shapiro_stat:.4f} | {shapiro_p:.4f} | p > 0.05 | {shapiro_result} |
| Breusch-Pagan (heteroskedasticity) | {bp_lm:.4f} | {bp_p:.4f} | p > 0.05 | {bp_result} |
| Durbin-Watson (autocorrelation) | {dw:.4f} | - | 1.5 < DW < 2.5 | {dw_result} |
| Ramsey RESET (combined) | - | {reset_p_str} | p > 0.05 | {reset_result} |

## Residual Statistics

- **n:** {n_res}
- **Mean:** {resid_mean:.4f}
- **Std:** {resid_std:.4f}
- **Skewness:** {resid_skew:.4f}
- **Kurtosis:** {resid_kurt:.4f}
- **Shapiro-Wilk p:** {shapiro_p:.4f}
- **Breusch-Pagan p:** {bp_p:.4f}
- **Durbin-Watson:** {dw:.4f}

## VIF Summary

| Feature | Mean VIF | Median VIF | Max VIF |
|---------|----------|------------|---------|
""")
        for feat, stats in sorted(vif_features.items(), key=lambda x: x[1]["mean"], reverse=True):
            f.write(f"| {feat} | {stats['mean']:.2f} | {stats['median']:.2f} | {stats['max']:.2f} |\n")

        f.write(f"""
## Verdict

**{verdict}**

{'All diagnostic checks passed. Linear fit appears adequate for the data.' if all_pass else 'Some diagnostic checks failed. Linear model may be misspecified.'}

## Implications for Phase 7

{'Linear fit adequate: Tree models (XGBoost/LightGBM) expected to show at best marginal gains over Ridge. Proceed with trees but expect marginal gains.' if all_pass else 'Nonlinearity/heteroskedasticity detected: Tree models (XGBoost/LightGBM) have credible mechanism to improve over Ridge. Proceed with strong expectation of improvement.'}

## Files Generated

- `reports/phase7a_residual_diagnostics.png` — 4-panel diagnostic panel
- `reports/phase7a_residual_vs_order.png` — Residuals vs race order
- `reports/phase7a_vif_heatmap.png` — VIF per feature per fold
- `reports/phase7a_partial_residual_<feature>.png` (12 files) — Component+residual plots
- `reports/phase7a_cooks_distance.png` — Cook's distance per fold
- `reports/phase7a_interactions.csv` — Interaction screening results
- `reports/phase7a_linear_diagnostics.json` — Machine-readable summary
- `reports/phase7a_linear_diagnostics.md` — This report

---
*Pre-registration: `reports/phase7a_linear_diagnostics_prereg.md`*
*Generated: {datetime.now(timezone.utc).isoformat()}*
""")

    print(f"  Markdown report saved to {md_path}")
    print(f"  JSON summary saved to reports/phase7a_linear_diagnostics.json")

    rule("PHASE 7A COMPLETE")
    print(f"  Verdict: {verdict}")
    print(f"  All checks passed: {all_pass}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())