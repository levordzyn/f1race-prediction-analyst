# Phase 7C: LightGBM Walk-Forward Evaluation

**Date:** 2026-11-11T02:25:27.696757+00:00
**Model:** LightGBM (two pre-registered variants)
**Pre-registration:** `reports/phase7c_lightgbm_prereg.md`

## Variant C1: LightGBM `regression_l1` (MAE-native)

**Verdict:** NULL

| Metric | LightGBM C1 | Ridge (This Run) | Δ (LGB - Ridge) |
|--------|-------------|------------------|-----------------|
| MAE | 3.1193 | 3.2784 | -0.1545 |
| Spearman ρ | 0.6683 | 0.6668 | +0.0016 |
| Podium hit rate | 0.678 | 0.680 | -0.002 |
| Winner hit rate | 0.514 | 0.550 | -0.035 |

**Paired Bootstrap vs Ridge (1000 resamples, seed=42):**
- Mean ΔMAE: -0.1545
- 95% CI: [-0.1931, -0.1157]
- CI excludes 0: Yes
- Sign test p: 0.0000
- Wilcoxon p: 0.0000

**Shuffled-Label Control:**
- Average shuffled MAE: 5.1968
- Real MAE: 3.1193
- Gap: 2.0775 ✅ PASS

**Winner Hit Rate Check:**
- Winner hit: 0.514 ❌ FAIL (<55%)

**Overfitting Check:**
- Train MAE: 2.6187
- Test MAE: 3.1195
- Gap: 0.5008 ❌ FAIL (≥0.15)

## Variant C2: LightGBM `regression` (MSE objective, MAE metric)

**Verdict:** NULL

| Metric | LightGBM C2 | Ridge (This Run) | Δ (LGB - Ridge) |
|--------|-------------|------------------|-----------------|
| MAE | 3.2381 | 3.2784 | -0.0365 |
| Spearman ρ | 0.6708 | 0.6668 | +0.0041 |
| Podium hit rate | 0.678 | 0.680 | -0.002 |
| Winner hit rate | 0.532 | 0.550 | -0.018 |

**Paired Bootstrap vs Ridge (1000 resamples, seed=42):**
- Mean ΔMAE: -0.0365
- 95% CI: [-0.0591, -0.0097]
- CI excludes 0: Yes
- Sign test p: 0.0023
- Wilcoxon p: 0.0002

**Shuffled-Label Control:**
- Average shuffled MAE: 4.7952
- Real MAE: 3.2381
- Gap: 1.5570 ✅ PASS

**Winner Hit Rate Check:**
- Winner hit: 0.532 ❌ FAIL (<55%)

**Overfitting Check:**
- Train MAE: 3.1605
- Test MAE: 3.2375
- Gap: 0.0770 ✅ PASS (<0.15)

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
| MAE improvement (CI excludes 0) | ✅ | ✅ |
| Podium hit ≥ 65% | ✅ | ✅ |
| Winner hit ≥ 55% | ❌ | ❌ |
| Shuffled-label gap > 1.5 | ✅ | ✅ |
| Train-test gap < 0.15 | ❌ | ✅ |
| **ALL CRITERIA MET** | ❌ NULL | ❌ NULL |

## Summary

| Variant | MAE | ΔMAE vs Ridge | CI Excludes 0 | Podium Hit | Winner Hit | Verdict |
|---------|-----|---------------|---------------|------------|------------|---------|
| C1 (regression_l1) | 3.1193 | -0.1545 | Yes | 0.678 | 0.514 | NULL |
| C2 (regression+mae) | 3.2381 | -0.0365 | Yes | 0.678 | 0.532 | NULL |

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
*Generated: 2026-11-11T02:25:27.698625+00:00*
