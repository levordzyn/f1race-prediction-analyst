# Phase 7B: XGBoost Walk-Forward Evaluation

**Date:** 2026-11-11T02:15:56.353187+00:00
**Model:** XGBoost (pre-registered hyperparameters)
**Pre-registration:** `reports/phase7b_xgboost_prereg.md`

## Verdict

**ACCEPTED** — Promote to production; bump MODEL_VERSION; update LIMITATIONS.md

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
| monotone_constraints | [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, -1] |
| Walk-forward folds | 173 (MIN_TRAIN_RACES=20) |

## Primary Metrics

| Metric | XGBoost | Ridge (This Run) | Δ (XGB - Ridge) |
|--------|---------|------------------|-----------------|
| MAE | 3.2376 | 3.2784 | -0.0372 |
| Spearman ρ | 0.6715 | 0.6668 | +0.0047 |
| Podium hit rate | 0.684 | 0.680 | +0.004 |
| Winner hit rate | 0.543 | 0.550 | -0.006 |

## Paired Bootstrap (1000 resamples, seed=42)

- **Mean ΔMAE (per-race):** -0.0372
- **95% CI:** [-0.0651, -0.0058]
- **CI excludes 0:** Yes
- **Sign test p:** 0.0013
- **Wilcoxon p:** 0.0002

✅ PASS: MAE improvement with CI excluding 0

## Shuffled-Label Control (Mandatory Sanity Check)

| Seed | Shuffled MAE | Real MAE | Gap |
|------|--------------|----------|-----|
| 42 | 4.7639 | 3.2376 | 1.5263 |
| 123 | 4.7639 | 3.2376 | 1.5263 |
| 456 | 4.7639 | 3.2376 | 1.5263 |

**Average gap:** 1.5263 positions ✅ PASS (>1.5)

## Overfitting Check

- **Mean Train MAE:** 3.1526
- **Mean Test MAE:** 3.2367
- **Train-Test Gap:** 0.0841 ✅ PASS (<0.5)

## Feature Importance Comparison

| Feature | XGB Gain | Ridge |coef| |
|---------|----------|-------|
| q_position | 778.62 | 1.1229 |
| grid | 404.71 | 0.9877 |
| practice_pos | 143.19 | 0.8223 |
| q_gap_pct | 141.08 | 0.0132 |
| team_form | 103.14 | 0.8975 |
| driver_form | 56.26 | 0.1464 |
| on_pole | 50.37 | 0.1757 |
| practice_gap_pct | 39.12 | 0.1029 |
| non_finish_rate | 25.05 | 0.0722 |
| practice_laps_30 | 15.37 | 0.0150 |
| no_q_time | 2.08 | 0.2787 |
| no_practice_time | 0.06 | 0.1705 |

- **Spearman ρ (|coef| vs gain):** 0.5175 (Moderate)
- **Pearson r:** 0.7595

## Verdict Summary

| Criterion | Result | Detail |
|-----------|--------|--------|
| MAE improvement with significant CI | PASS | XGB MAE=3.238 vs Ridge=3.278, Δ=-0.037, CI=[-0.065, -0.006] |
| Shuffled-label sanity check | PASS | Shuffled MAE=4.764, Real MAE=3.238, Gap=1.526 |
| Podium hit rate ≥ Ridge | PASS | XGB=0.684 vs Ridge=0.680 |
| Winner hit rate ≥ Ridge | FAIL | XGB=0.543 vs Ridge=0.550 |
| No severe overfitting (train-test gap < 0.5) | PASS | Train MAE=3.153, Test MAE=3.237, Gap=0.084 |

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
*Generated: 2026-11-11T02:15:56.354703+00:00*
