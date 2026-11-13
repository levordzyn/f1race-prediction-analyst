"""LightGBM Model for F1 Prediction - Phase 7C.

Pre-registered in reports/phase7c_lightgbm_prereg.md

Walk-forward expanding window with pre-registered hyperparameters and monotone constraints.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import bootstrap, wilcoxon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model

log = logging.getLogger(__name__)

# Pre-registered hyperparameters (FROZEN)
LIGHTGBM_L1_PARAMS = {
    "objective": "regression_l1",
    "metric": "mae",
    "n_estimators": 200,
    "max_depth": 4,
    "num_leaves": 15,
    "learning_rate": 0.05,
    "min_child_samples": 10,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_alpha": 1.0,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": 1,
    "verbose": -1,
}

LIGHTGBM_MSE_PARAMS = {
    "objective": "regression",
    "metric": "mae",
    "n_estimators": 200,
    "max_depth": 4,
    "num_leaves": 15,
    "learning_rate": 0.05,
    "min_child_samples": 10,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_alpha": 1.0,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": 1,
    "verbose": -1,
}

# Pre-registered monotone constraints (same as XGBoost, 12 features in ALL_FEATURES order)
MONOTONE_CONSTRAINTS = [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, -1]
# Order: grid, driver_form, team_form, non_finish_rate,
#        practice_pos, practice_gap_pct, practice_laps_30, no_practice_time,
#        q_position, q_gap_pct, no_q_time, on_pole

TARGET = "finish"
MIN_TRAIN_RACES = 20
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 42


def walk_forward_lightgbm(
    df: pd.DataFrame,
    feature_cols: list[str],
    min_train_races: int = MIN_TRAIN_RACES,
    shuffle: bool = False,
    monotone_constraints: list[int] | None = None,
    params: dict | None = None,
) -> dict:
    """
    Walk-forward expanding window with LightGBM.

    Args:
        df: Full feature DataFrame with race_idx, features, target
        feature_cols: List of feature column names
        min_train_races: Minimum races in training set before validation starts
        shuffle: If True, shuffle y_train within each fold (sanity check)
        monotone_constraints: List of 12 constraint values (+1, -1, 0)
        params: LightGBM parameters dict

    Returns:
        dict with keys: predictions, mae, spearman, podium_hit, winner_hit,
                        feature_importance, train_mae_per_fold, test_mae_per_fold
    """
    try:
        import lightgbm as lgb
    except ImportError:
        raise RuntimeError("lightgbm not installed. Run: pip install lightgbm==4.7.0")

    races = np.sort(df["race_idx"].unique())
    val_races = [r for r in races if r > min_train_races]
    n_folds = len(val_races)

    all_predictions = []
    train_mae_list = []
    test_mae_list = []
    feature_importance_gain = []
    feature_importance_split = []

    for fold_idx, te_race in enumerate(val_races):
        train = df[df["race_idx"] < te_race].copy()
        test = df[df["race_idx"] == te_race].copy()

        if train.empty or test.empty:
            continue

        X_train = train[feature_cols]
        y_train = train[TARGET].copy()
        X_test = test[feature_cols]
        y_test = test[TARGET].copy()

        # Handle NaN in target (DNS drivers)
        train_mask = y_train.notna()
        test_mask = y_test.notna()
        if not train_mask.any() or not test_mask.any():
            continue

        X_train = X_train.loc[train_mask]
        y_train = y_train.loc[train_mask]
        X_test = X_test.loc[test_mask]
        y_test = y_test.loc[test_mask]
        test = test.loc[test_mask]

        # Shuffle control
        if shuffle:
            rng = np.random.default_rng(42 + fold_idx)
            y_train = y_train.sample(frac=1.0, random_state=rng).reset_index(drop=True)

        # Train LightGBM (no scaling needed, native NaN handling)
        lgb_params = params.copy()
        # regression_l1 doesn't support monotone_constraints in LightGBM
        if monotone_constraints is not None and lgb_params.get("objective") != "regression_l1":
            lgb_params["monotone_constraints"] = monotone_constraints
            lgb_params["monotone_constraints_method"] = "basic"
            if fold_idx == 0:
                log.info(f"LightGBM: monotone constraints enabled ({monotone_constraints})")
        elif monotone_constraints is not None and lgb_params.get("objective") == "regression_l1":
            if fold_idx == 0:
                log.warning("LightGBM: monotone constraints NOT SUPPORTED for regression_l1 objective - running without constraints")

        lgb_model = lgb.LGBMRegressor(**lgb_params)
        lgb_model.fit(X_train, y_train)

        # Predict
        y_pred = lgb_model.predict(X_test)

        # Collect predictions
        fold_preds = pd.DataFrame({
            "year": test["year"].values,
            "round": test["round"].values,
            "driver": test["driver"].values,
            "race_idx": test["race_idx"].values,
            "pred": y_pred,
            "finish": y_test.values,
            "residual": y_pred - y_test.values,
        })
        for feat in feature_cols:
            fold_preds[f"feat_{feat}"] = X_test[feat].values
        all_predictions.append(fold_preds)

        # Train/test MAE for overfitting check
        y_pred_train = lgb_model.predict(X_train)
        train_mae = np.mean(np.abs(y_pred_train - y_train.values))
        test_mae = np.mean(np.abs(y_pred - y_test.values))
        train_mae_list.append(train_mae)
        test_mae_list.append(test_mae)

        # Feature importance (gain, split)
        booster = lgb_model.booster_
        importance_gain = booster.feature_importance(importance_type="gain")
        imp_gain = np.array([importance_gain[i] if i < len(importance_gain) else 0.0 for i in range(len(feature_cols))])
        feature_importance_gain.append(imp_gain)

        importance_split = booster.feature_importance(importance_type="split")
        imp_split = np.array([importance_split[i] if i < len(importance_split) else 0.0 for i in range(len(feature_cols))])
        feature_importance_split.append(imp_split)

    if not all_predictions:
        raise ValueError("No valid folds produced")

    predictions_df = pd.concat(all_predictions, ignore_index=True)

    # Aggregate metrics
    overall_mae = np.mean(np.abs(predictions_df["residual"].values))
    overall_spearman = predictions_df["pred"].corr(predictions_df["finish"], method="spearman")

    # Podium and winner hit rates - match Ridge _hits implementation
    def _hits_per_race(pred_vals: np.ndarray, act_vals: np.ndarray) -> tuple[float, float]:
        if np.unique(pred_vals).size < 2:
            return float("nan"), float("nan")
        win = float(int(np.argmin(pred_vals) == np.argmin(act_vals)))
        k = min(3, act_vals.size)
        pred_top = set(np.argsort(pred_vals)[:k])
        act_top = set(np.argsort(act_vals)[:k])
        return win, len(pred_top & act_top) / k

    import warnings
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning, message="DataFrameGroupBy.apply operated on the grouping columns")
        per_race_hits = predictions_df.groupby("race_idx", group_keys=False).apply(
            lambda g: _hits_per_race(g["pred"].values, g["finish"].values)
        )
    winner_hit = per_race_hits.apply(lambda x: x[0]).mean(skipna=True)
    podium_hit = per_race_hits.apply(lambda x: x[1]).mean(skipna=True)

    # Aggregate feature importance
    mean_gain = np.mean(feature_importance_gain, axis=0) if feature_importance_gain else np.zeros(len(feature_cols))
    mean_split = np.mean(feature_importance_split, axis=0) if feature_importance_split else np.zeros(len(feature_cols))

    feature_importance = pd.DataFrame({
        "feature": feature_cols,
        "gain": mean_gain,
        "split": mean_split,
    }).sort_values("gain", ascending=False)

    return {
        "predictions": predictions_df,
        "mae": overall_mae,
        "spearman": overall_spearman,
        "podium_hit": podium_hit,
        "winner_hit": winner_hit,
        "feature_importance": feature_importance,
        "train_mae_per_fold": train_mae_list,
        "test_mae_per_fold": test_mae_list,
    }


def paired_bootstrap_delta(
    ridge_preds: pd.DataFrame,
    lgb_preds: pd.DataFrame,
    n_resamples: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """
    Paired bootstrap 95% CI on per-race MAE delta (LGB - Ridge).
    """
    # Compute residuals if not present
    if "residual" not in ridge_preds.columns:
        ridge_preds = ridge_preds.copy()
        ridge_preds["residual"] = ridge_preds["pred"] - ridge_preds["finish"]
    if "residual" not in lgb_preds.columns:
        lgb_preds = lgb_preds.copy()
        lgb_preds["residual"] = lgb_preds["pred"] - lgb_preds["finish"]

    # Compute per-race MAE for both models
    ridge_race_mae = ridge_preds.groupby("race_idx")["residual"].apply(lambda x: np.mean(np.abs(x))).reset_index()
    ridge_race_mae.columns = ["race_idx", "mae_ridge"]

    lgb_race_mae = lgb_preds.groupby("race_idx")["residual"].apply(lambda x: np.mean(np.abs(x))).reset_index()
    lgb_race_mae.columns = ["race_idx", "mae_lgb"]

    # Merge on race_idx
    merged = ridge_race_mae.merge(lgb_race_mae, on="race_idx", how="inner")
    deltas = merged["mae_lgb"].values - merged["mae_ridge"].values
    mean_delta = np.mean(deltas)

    # Paired bootstrap
    rng = np.random.default_rng(seed)
    boot_means = []
    for _ in range(n_resamples):
        idx = rng.integers(0, len(deltas), len(deltas))
        boot_means.append(np.mean(deltas[idx]))

    ci_lower = np.percentile(boot_means, 2.5)
    ci_upper = np.percentile(boot_means, 97.5)

    # Sign test
    n_positive = np.sum(deltas > 0)
    n_negative = np.sum(deltas < 0)
    n_total = n_positive + n_negative
    if n_total > 0:
        from scipy.stats import binomtest
        sign_p = binomtest(min(n_positive, n_negative), n=n_total, p=0.5, alternative="two-sided").pvalue
    else:
        sign_p = 1.0

    # Wilcoxon signed-rank test
    try:
        wilcoxon_stat, wilcoxon_p = wilcoxon(deltas, alternative="two-sided")
    except Exception:
        wilcoxon_stat, wilcoxon_p = np.nan, np.nan

    return {
        "mean_delta": float(mean_delta),
        "ci_lower": float(ci_lower),
        "ci_upper": float(ci_upper),
        "sign_p": float(sign_p),
        "wilcoxon_p": float(wilcoxon_p),
        "deltas_per_race": deltas,
        "n_races": int(n_total),
        "ci_excludes_zero": (ci_lower > 0) or (ci_upper < 0),
    }


def compare_feature_importance_three(ridge_coefs: dict, xgb_importance: pd.DataFrame, lgb_importance: pd.DataFrame) -> dict:
    """Compare Ridge coefficients vs XGBoost vs LightGBM feature importance (gain)."""
    ridge_rank = pd.Series({f: abs(c) for f, c in ridge_coefs.items()}).sort_values(ascending=False)
    xgb_rank = xgb_importance.set_index("feature")["gain"].sort_values(ascending=False)
    lgb_rank = lgb_importance.set_index("feature")["gain"].sort_values(ascending=False)

    common = ridge_rank.index.intersection(xgb_rank.index).intersection(lgb_rank.index)
    if len(common) < 2:
        return {"spearman_ridge_xgb": np.nan, "spearman_ridge_lgb": np.nan, "spearman_xgb_lgb": np.nan, "n_common": 0}

    from scipy.stats import spearmanr
    rho_rx, _ = spearmanr(ridge_rank[common], xgb_rank[common])
    rho_rl, _ = spearmanr(ridge_rank[common], lgb_rank[common])
    rho_xl, _ = spearmanr(xgb_rank[common], lgb_rank[common])

    return {
        "spearman_ridge_xgb": float(rho_rx),
        "spearman_ridge_lgb": float(rho_rl),
        "spearman_xgb_lgb": float(rho_xl),
        "n_common": int(len(common)),
    }