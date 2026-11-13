# Phase 7D: Head-to-Head Final & Consolidation

**Date:** 2026-11-11T02:28:08.237126+00:00
**Models compared:** Ridge (baseline), XGBoost, LightGBM C2
**Pre-registrations:** Phase 7A/7B/7C

---

## Ladder Table

| Model | MAE | ρ | Winner | Podium | Overfit Gap | Status |
|-------|-----|---|--------|--------|-------------|--------|
| Ridge (baseline) | 3.2784 | 0.6668 | 0.550 | 0.680 | ~0.08 | Baseline |
| **XGBoost** | **3.2376** | 0.6715 | 0.543 | 0.684 | 0.084 | **ACCEPTED** |
| **LightGBM C2** | 3.2381 | 0.6708 | 0.532 | 0.678 | 0.077 | **ACCEPTED** |
| LightGBM C1 | 3.1193 | N/A | 0.514 | 0.678 | **0.501** | **REJECTED** |

---

## Head-to-Head: XGBoost vs LightGBM C2

- **Mean ΔMAE (XGB - LGB):** -0.0008
- **95% CI:** [-0.0097, +0.0082]
- **CI excludes 0:** No
- **Sign test p:** 0.7611
- **Wilcoxon p:** 0.5458

**Interpretation:** Statistically indistinguishable (CI contains 0)

---

## Each vs Ridge

| Model | Mean ΔMAE | 95% CI | CI Excludes 0 |
|-------|-----------|--------|---------------|
| XGBoost | -0.0372 | [-0.0651, -0.0058] | True |
| LightGBM C2 | -0.0365 | [-0.0591, -0.0097] | True |

---

## Ensemble (50/50 XGB + LGB C2)

- **Ensemble MAE:** 3.2365
- **Best single MAE:** 3.2376
- **Gain vs best single:** +0.0011
- **Ensemble vs Ridge:** Δ=-0.0382, CI=[-0.0635, -0.0102], excludes 0: True

**Ensemble verdict:** NOT WARRANTED — no meaningful gain over best single

---

## Feature Importance Correlation

| Comparison | Spearman ρ |
|------------|------------|
| Ridge vs XGBoost | 0.5175 |
| Ridge vs LightGBM C2 | 0.4965 |
| XGBoost vs LightGBM C2 | 0.9301 |

**Interpretation:** High consistency across tree models

---

## Final Model Selection

**Selected Model:** **XGBoost**

**Reason:** Statistically indistinguishable; XGBoost chosen for maturity, monotone constraints support, and ecosystem

---

## Phase 7 Summary

| Phase | Task | Result |
|-------|------|--------|
| 7A | Linear Diagnostics | H0 REJECTED — nonlinearity/heteroskedasticity detected |
| 7B | XGBoost | **ACCEPTED** (MAE=3.238, Δ=-0.037, CI excludes 0) |
| 7C | LightGBM | **C2 ACCEPTED** (MAE=3.238), C1 REJECTED (overfit) |
| 7D | Consolidation | **XGBoost selected** |

---

## Model Finalization

**Final model to promote:** **XGBoost**

**Next steps (awaiting user approval):**
1. Bump `MODEL_VERSION` to `phase7-xgboost-1.0`
2. Update `LIMITATIONS.md` with §7B (XGBoost bug + resolution), §7C (LightGBM results), §7D (final selection)
3. Save forecast for upcoming race with `--grid-file`
4. Run full regression suite (must PASS 100%)

---

*Generated: 2026-11-11T02:28:09.927239+00:00*
*Pre-registrations: `reports/phase7a_linear_diagnostics_prereg.md`, `reports/phase7b_xgboost_prereg.md`, `reports/phase7c_lightgbm_prereg.md`*
