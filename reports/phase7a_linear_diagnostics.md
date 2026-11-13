# Phase 7A: Linear Regression Diagnostics

**Date:** 2026-11-10T11:02:18.539043+00:00
**Model:** Ridge α=1.0, 12 features, 173 validation folds
**Pre-registration:** `reports/phase7a_linear_diagnostics_prereg.md`

## Verdict

**NONLINEARITY/HETEROSKEDASTICITY DETECTED (H0 rejected)**

## Global Residual Diagnostics

| Test | Statistic | p-value | Threshold | Result |
|------|-----------|---------|-----------|--------|
| Shapiro-Wilk (subsample) | 0.9303 | 0.0000 | p > 0.05 | FAIL |
| Breusch-Pagan (heteroskedasticity) | 114.5256 | 0.0000 | p > 0.05 | FAIL |
| Durbin-Watson (autocorrelation) | 2.1206 | - | 1.5 < DW < 2.5 | PASS |
| Ramsey RESET (combined) | - | 0.999056 | p > 0.05 | PASS |

## Residual Statistics

- **n:** 3496
- **Mean:** -0.0484
- **Std:** 4.3040
- **Skewness:** -1.0915
- **Kurtosis:** 1.4448
- **Shapiro-Wilk p:** 0.0000
- **Breusch-Pagan p:** 0.0000
- **Durbin-Watson:** 2.1206

## VIF Summary

| Feature | Mean VIF | Median VIF | Max VIF |
|---------|----------|------------|---------|
| q_position | 15.08 | 13.55 | 25.41 |
| grid | 11.62 | 10.77 | 18.60 |
| driver_form | 8.07 | 8.37 | 10.82 |
| team_form | 6.62 | 6.35 | 9.41 |
| practice_pos | 5.35 | 5.10 | 9.75 |
| practice_gap_pct | 3.78 | 2.84 | 8.32 |
| non_finish_rate | 2.78 | 3.20 | 3.75 |
| q_gap_pct | 2.42 | 1.67 | 5.27 |
| no_practice_time | 1.67 | 1.55 | 2.54 |
| no_q_time | 1.26 | 1.16 | 1.76 |
| practice_laps_30 | 1.21 | 1.23 | 1.37 |
| on_pole | 1.19 | 1.18 | 1.24 |

## Verdict

**NONLINEARITY/HETEROSKEDASTICITY DETECTED (H0 rejected)**

Some diagnostic checks failed. Linear model may be misspecified.

## Implications for Phase 7

Nonlinearity/heteroskedasticity detected: Tree models (XGBoost/LightGBM) have credible mechanism to improve over Ridge. Proceed with strong expectation of improvement.

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
*Generated: 2026-11-10T11:02:18.539540+00:00*
