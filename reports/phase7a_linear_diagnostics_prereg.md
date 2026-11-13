# Phase 7A Pre-registration: Linear Regression Diagnostics

**Date:** 2026-11-09 (pre-registration)  
**Author:** F1 Prediction Project  
**Status:** PRE-REGISTRATION (before any diagnostics run)

---

## Research Question

> **Is the current Ridge regression fit linear adequate for F1 race finishing position prediction? Or are there hidden nonlinearities, heteroskedasticity, or leverage points that indicate the linear model is misspecified?**

This diagnostic is the gatekeeper for Phase 7: if the linear fit is adequate, tree models (XGBoost, LightGBM) are expected to show at best marginal gains; if nonlinearity/heteroskedasticity/leverage issues are found, tree models have a credible mechanism to improve.

---

## Pre-registered Hypotheses & Success Criteria

### H0 (Null): Linear fit is adequate
- Residuals show no systematic pattern vs fitted values
- Residuals are approximately normal (Shapiro-Wilk p > 0.05 on subsample)
- No heteroskedasticity (Breusch-Pagan p > 0.05)
- No autocorrelation (Durbin-Watson ≈ 2)
- Ramsey RESET test p > 0.05 (no omitted nonlinear terms)
- All VIF < 5 (no severe multicollinearity)
- Partial residual plots show random scatter

### H1 (Alternative): Linear fit is inadequate
Any of the above violated → evidence that linear model is misspecified and tree models have a credible mechanism to improve.

**Decision rule for Phase 7 gate:**
- If H0 rejected → proceed to Task B/C with strong expectation that trees can improve
- If H0 not rejected → proceed with trees but expect at best marginal gains; document honestly

---

## Pre-registered Analysis Plan

### A.1 Walk-forward Residual Collection
- Run `walk_forward` with Ridge (α=1.0, `ALL_FEATURES`, 173 validation folds, MIN_TRAIN_RACES=20)
- For each validation fold, save per-row residuals: `residual = pred - finish`
- Metadata per residual: `year`, `round`, `driver`, `pred`, `finish`, all 12 features
- Total residuals expected: ~3460 (173 races × ~20 drivers)

### A.2 Global Residual Diagnostics (aggregated across all folds)
| Diagnostic | Method | Threshold | Decision |
|------------|--------|-----------|----------|
| Residual vs Fitted plot | Visual | No pattern | Qualitative |
| Q-Q plot | Visual | Approx normal | Qualitative |
| Scale-Location | Visual | No funnel | Qualitative |
| Shapiro-Wilk (subsample n=5000) | `scipy.stats.shapiro` | p > 0.05 | Pass/Fail |
| Breusch-Pagan | `statsmodels.stats.diagnostic.het_breuschpagan` | p > 0.05 | Pass/Fail |
| Durbin-Watson | `statsmodels.stats.stattools.durbin_watson` | 1.5 < DW < 2.5 | Pass/Fail |
| Skewness | `scipy.stats.skew` | | Report |
| Kurtosis | `scipy.stats.kurtosis` | | Report |

### A.3 Ramsey RESET Test (per fold, then aggregate)
- For each validation fold: fit Ridge on train, predict test, then fit auxiliary regression on test set: `residual ~ pred + pred² + pred³`
- Test joint significance of `pred² + pred³` (F-test)
- Aggregate p-values across folds (Fisher's method)
- **Threshold:** aggregate p < 0.05 → reject linearity

### A.4 VIF per Fold (Multicollinearity)
- For each fold's training set, compute VIF for all 12 features
- Use `statsmodels.stats.outliers_influence.variance_inflation_factor`
- Thresholds: VIF > 5 → warning; VIF > 10 → severe
- Report: mean/median/max VIF per feature across folds
- Pre-identified suspect pairs: `q_position`/`q_gap_pct`, `practice_pos`/`practice_gap_pct`, `grid`/`q_position`

### A.5 Partial Residual Plots (Component+Residual)
For each of 12 features: plot `(residual + β_j × x_j) vs x_j` (component+residual)
- If curved pattern → nonlinearity in that feature
- If random scatter → linear adequate
- Save 12 PNGs: `reports/phase7a_partial_residual_<feature>.png`

### A.6 Influence Diagnostics (Cook's Distance)
- Per fold, compute Cook's D on training set
- Flag D > 4/n_train
- Aggregate: which driver-races most frequently influential?
- Check if influencers = DNF, first-lap incidents, wet races

### A.7 Interaction Screening (pre-registered top-5 pairs)
Top-5 features by |coef|: `grid`, `q_position`, `driver_form`, `team_form`, `practice_pos`
Test all pairs (10 combinations): add `x_i × x_j` to fold model, likelihood ratio test
- Report which interactions significant (p < 0.05 after Bonferroni)
- **Not promoting to model** — diagnostic only

---

## Visualization Plan (all saved to `reports/`)

| Plot | Filename | Description |
|------|----------|-------------|
| Residual vs Fitted | `phase7a_residual_vs_fitted.png` | Check patterns/funnel |
| Q-Q Plot | `phase7a_qq_plot.png` | Normality |
| Scale-Location | `phase7a_scale_location.png` | Heteroskedasticity |
| Residual Histogram | `phase7a_residual_hist.png` | Skew/kurtosis |
| Partial Residual (12) | `phase7a_partial_residual_<feat>.png` | Per-feature nonlinearity |
| Residual vs Race Order | `phase7a_residual_vs_order.png` | Autocorrelation |
| Cook's Distance | `phase7a_cooks_distance.png` | Influence points |
| VIF Heatmap | `phase7a_vif_heatmap.png` | Multicollinearity |

---

## Decision Rules (Gate for Task B/C)

| Outcome | Action |
|---------|--------|
| H0 not rejected (linear adequate) | Proceed to Task B/C but expect **marginal gains at best**; document honestly; Ridge remains production |
| H0 rejected (nonlinearity/heteroskedasticity) | Proceed to Task B/C with **strong expectation** trees can improve; Ridge demoted to baseline |

---

## Software Dependencies (Pre-verified)

| Package | Version | Purpose |
|---------|---------|---------|
| `statsmodels` | 0.14.x | BP, RESET, VIF, Cook's D |
| `scipy` | 1.18.1 | Shapiro, skew, kurtosis, DW |
| `statsmodels.stats.diagnostic` | | Breusch-Pagan, RESET |
| `statsmodels.stats.outliers_influence` | | VIF, Cook's D |
| `matplotlib` | 3.11.2 | Plots |

All verified available in environment (Python 3.14.5, scipy 1.18.1, statsmodels available).

---

## Output Artifacts (Committed Regardless of Outcome)

| Artifact | Path |
|----------|------|
| Pre-registration (this file) | `reports/phase7a_linear_diagnostics_prereg.md` |
| Diagnostic report | `reports/phase7a_linear_diagnostics.md` |
| Residual diagnostic panel | `reports/phase7a_residual_diagnostics.png` |
| 12 Partial residual plots | `reports/phase7a_partial_residual_<feat>.png` |
| VIF heatmap | `reports/phase7a_vif_heatmap.png` |
| Diagnostic script | `scripts/run_phase7a_linear_diagnostics.py` |

---

## Sign-off

**Pre-registered by:** F1 Prediction Project  
**Date:** 2026-11-09  
**Commit:** Before any diagnostic code runs  
**Status:** ✅ PRE-REGISTERED — No diagnostic code has been executed yet