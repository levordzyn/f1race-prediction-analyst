"""XGBoost Model for F1 Prediction - Phase 7B.

Pre-registered in reports/phase7b_xgboost_prereg.md

Walk-forward expanding window with pre-registered hyperparameters and monotone constraints.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import bootstrap, wilcoxon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model

# Pre-registered hyperparameters (FROZEN)
XGBOOST_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "reg_alpha": 1.0,
    "reg_lambda": 1.0,
    "objective": "reg:squarederror",
    "random_state": 42,
    "n_jobs": 1,
}

# Pre-registered monotone constraints (12 features in ALL_FEATURES order)
MONOTONE_CONSTRAINTS = [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, -1]
# Order: grid, driver_form, team_form, non_finish_rate,
#        practice_pos, practice_gap_pct, practice_laps_30, no_practice_time,
#        q_position, q_gap_pct, no_q_time, on_pole

TARGET = "finish"
MIN_TRAIN_RACES = 20
N_BOOTSTRAP = 1000
BOOTSTRAP_SEED = 42


def walk_forward_xgboost(
    df: pd.DataFrame,
    feature_cols: list[str],
    min_train_races: int = MIN_TRAIN_RACES,
    shuffle: bool = False,
    monotone_constraints: list[int] | None = None,
) -> dict:
    """
    Walk-forward expanding window with XGBoost.

    Args:
        df: Full feature DataFrame with race_idx, features, target
        feature_cols: List of feature column names
        min_train_races: Minimum races in training set before validation starts
        shuffle: If True, shuffle y_train within each fold (sanity check)
        monotone_constraints: List of 12 constraint values (+1, -1, 0)

    Returns:
        dict with keys: predictions, mae, spearman, podium_hit, winner_hit,
                        feature_importance, train_mae_per_fold, test_mae_per_fold
    """
    try:
        import xgboost as xgb
    except ImportError:
        raise RuntimeError("xgboost not installed. Run: pip install xgboost==3.4.1")

    races = np.sort(df["race_idx"].unique())
    val_races = [r for r in races if r > min_train_races]
    n_folds = len(val_races)

    all_predictions = []
    all_residuals = []
    train_mae_list = []
    test_mae_list = []
    feature_importance_gain = []
    feature_importance_weight = []
    feature_importance_cover = []

    for fold_idx, te_race in enumerate(val_races):
        train = df[df["race_idx"] < te_race].copy()
        test = df[df["race_idx"] == te_race].copy()

        if train.empty or test.empty:
            continue

        X_train = train[feature_cols]
        y_train = train[TARGET].copy()
        X_test = test[feature_cols]
        y_test = test[TARGET].copy()

        # Handle NaN in target (DNS drivers) - only filter TRAINING data
        train_mask = y_train.notna()
        test_mask = y_test.notna()
        
        # Check if this is a forecast race (all finishes are NaN)
        is_forecast_race = not test_mask.any()
        
        if not train_mask.any():
            continue

        X_train = X_train.loc[train_mask]
        y_train = y_train.loc[train_mask]
        
        # For test, keep ALL rows (including DNS with NaN finish) for prediction
        # Only filter for metrics computation later

        # Shuffle control
        if shuffle:
            rng = np.random.default_rng(42 + fold_idx)
            y_train = y_train.sample(frac=1.0, random_state=rng).reset_index(drop=True)

        # Train XGBoost (no scaling needed, native NaN handling)
        params = XGBOOST_PARAMS.copy()
        if monotone_constraints is not None:
            # XGBoost expects dict mapping feature names to constraints
            params["monotone_constraints"] = dict(zip(feature_cols, monotone_constraints))

        xgb_model = xgb.XGBRegressor(**params)
        xgb_model.fit(X_train, y_train)

        # Predict on ALL test rows (including DNS with NaN finish)
        y_pred = xgb_model.predict(X_test)

        # Collect predictions for ALL test rows
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

        # For metrics, only use rows with finite finishes
        scored_mask = test_mask if not is_forecast_race else np.zeros(len(test), dtype=bool)
        
        if not is_forecast_race and scored_mask.any():
            residuals = y_pred[scored_mask] - y_test.values[scored_mask]
            all_residuals.append(residuals)

            # Train/test MAE for overfitting check
            y_pred_train = xgb_model.predict(X_train)
            train_mae = np.mean(np.abs(y_pred_train - y_train.values))
            test_mae = np.mean(np.abs(residuals))
            train_mae_list.append(train_mae)
            test_mae_list.append(test_mae)
        else:
            # For forecast race, still compute train MAE
            y_pred_train = xgb_model.predict(X_train)
            train_mae = np.mean(np.abs(y_pred_train - y_train.values))
            train_mae_list.append(train_mae)

        # Feature importance (gain, weight, cover)
        booster = xgb_model.get_booster()
        importance = booster.get_score(importance_type="gain")
        imp_gain = np.array([importance.get(f, 0.0) for f in feature_cols])
        feature_importance_gain.append(imp_gain)

        importance_w = booster.get_score(importance_type="weight")
        imp_weight = np.array([importance_w.get(f, 0.0) for f in feature_cols])
        feature_importance_weight.append(imp_weight)

        importance_c = booster.get_score(importance_type="cover")
        imp_cover = np.array([importance_c.get(f, 0.0) for f in feature_cols])
        feature_importance_cover.append(imp_cover)

    if not all_predictions:
        raise ValueError("No valid folds produced")

    predictions_df = pd.concat(all_predictions, ignore_index=True)

    # Aggregate metrics - only on non-forecast races (finite residuals/finishes)
    scored_mask = predictions_df["residual"].notna()
    overall_mae = float(np.mean(np.abs(predictions_df.loc[scored_mask, "residual"].values)))
    overall_spearman = float(predictions_df.loc[scored_mask, "pred"].corr(
        predictions_df.loc[scored_mask, "finish"], method="spearman"))

    # Podium and winner hit rates - compute per-race to match Ridge implementation
    def _hits_per_race(pred_vals: np.ndarray, act_vals: np.ndarray) -> tuple[float, float]:
        """Match Ridge _hits: winner=1 if argmin(pred)==argmin(act), podium=recall@3"""
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
    mean_weight = np.mean(feature_importance_weight, axis=0) if feature_importance_weight else np.zeros(len(feature_cols))
    mean_cover = np.mean(feature_importance_cover, axis=0) if feature_importance_cover else np.zeros(len(feature_cols))

    feature_importance = pd.DataFrame({
        "feature": feature_cols,
        "gain": mean_gain,
        "weight": mean_weight,
        "cover": mean_cover,
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
        "residuals_per_fold": all_residuals,
    }


def paired_bootstrap_delta(
    ridge_preds: pd.DataFrame,
    xgb_preds: pd.DataFrame,
    n_resamples: int = N_BOOTSTRAP,
    seed: int = BOOTSTRAP_SEED,
) -> dict:
    """
    Paired bootstrap 95% CI on per-race MAE delta (XGB - Ridge).

    Args:
        ridge_preds: Ridge walk-forward predictions (with 'finish' and 'pred' columns)
        xgb_preds: XGBoost walk-forward predictions (with 'residual' column)
        n_resamples: Number of bootstrap resamples
        seed: Random seed

    Returns:
        dict with mean_delta, ci_lower, ci_upper, p_value
    """
    # Compute residuals if not present
    if "residual" not in ridge_preds.columns:
        ridge_preds = ridge_preds.copy()
        ridge_preds["residual"] = ridge_preds["pred"] - ridge_preds["finish"]
    if "residual" not in xgb_preds.columns:
        xgb_preds = xgb_preds.copy()
        xgb_preds["residual"] = xgb_preds["pred"] - xgb_preds["finish"]

    # Compute per-race MAE for both models
    ridge_race_mae = ridge_preds.groupby("race_idx")["residual"].apply(lambda x: np.mean(np.abs(x))).reset_index()
    ridge_race_mae.columns = ["race_idx", "mae_ridge"]

    xgb_race_mae = xgb_preds.groupby("race_idx")["residual"].apply(lambda x: np.mean(np.abs(x))).reset_index()
    xgb_race_mae.columns = ["race_idx", "mae_xgb"]

    # Merge on race_idx
    merged = ridge_race_mae.merge(xgb_race_mae, on="race_idx", how="inner")
    deltas = merged["mae_xgb"].values - merged["mae_ridge"].values
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


def compare_feature_importance(ridge_coefs: dict, xgb_importance: pd.DataFrame) -> dict:
    """Compare Ridge coefficients vs XGBoost feature importance (gain)."""
    # Ridge: absolute coefficient values
    ridge_rank = pd.Series({f: abs(c) for f, c in ridge_coefs.items()}).sort_values(ascending=False)
    xgb_rank = xgb_importance.set_index("feature")["gain"].sort_values(ascending=False)

    common = ridge_rank.index.intersection(xgb_rank.index)
    if len(common) < 2:
        return {"spearman_rho": np.nan, "pearson_r": np.nan, "n_common": 0}

    from scipy.stats import spearmanr, pearsonr
    rho, _ = spearmanr(ridge_rank[common], xgb_rank[common])
    r, _ = pearsonr(ridge_rank[common], xgb_rank[common])

    return {
        "spearman_rho": float(rho),
        "pearson_r": float(r),
        "n_common": int(len(common)),
        "ridge_rank": ridge_rank[common].to_dict(),
        "xgb_rank": xgb_rank[common].to_dict(),
    }