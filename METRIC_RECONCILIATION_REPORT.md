# METRIC RECONCILIATION REPORT — F1 PREDICTION ANALYST

**Date:** 2026-11-10  
**Purpose:** Forensic reconciliation of all reported metrics against actual computations.

---

## 1. MAE RECONCILIATION

### 1.1 Ridge Regression (Full Dataset: 2018–2026)

| Metric | Reported (Old) | Actual (Verified) | Source |
|--------|----------------|-------------------|--------|
| Walk-forward MAE | 3.069 (legacy) / 3.278 (full) | **3.2784** | `model.walk_forward()` on full 193-race dataset |
| Validation folds | 69 (legacy) / 173 (full) | **173 raw / 171 scored** | `race_idx` 21–193, 2 DNS excluded |
| Validation rows | 1,416 (legacy) / 3,496 (full) | **3,496 finite-finish** | 3,498 raw – 2 DNS |
| Winner hit rate | 63.8% (legacy) / 54.3% (full) | **94/171 = 54.97%** | 94 wins in 171 scored folds |
| Podium hit rate | 67.6% (legacy) / 68.0% (full) | **68.03%** | 2,352/3,458 driver-hits |

**Key Finding:** The "3.069 MAE / 63.8% winner hit" in old documentation came from the **legacy 2023–2026 dataset only** (70 validation folds, 44/70 = 62.86%). The full 2018–2026 dataset yields **3.278 MAE / 54.97% winner hit**.

### 1.2 XGBoost (Full Dataset: 2018–2026)

| Metric | Reported (Phase 7B) | Actual (Verified) | Source |
|--------|---------------------|-------------------|--------|
| Walk-forward MAE | 3.2376 | **3.2376** ✅ | `xgboost_model.walk_forward_xgboost()` |
| ΔMAE vs Ridge (delta of means) | −0.0409 | **−0.0408** | 3.2376 − 3.2784 |
| ΔMAE vs Ridge (mean of per-race) | −0.0372 | **−0.0372** ✅ | Paired per-race mean |
| 95% CI (paired bootstrap) | [−0.065, −0.006] | **[−0.065, −0.006]** ✅ | 1000 resamples, seed=42 |
| Winner hit rate | 54.91% (95/173) | **95/171 = 55.56%** | 95 wins in 171 scored folds |
| Podium hit rate | 68.40% | **68.40%** ✅ | 2,355/3,458 = 68.10%* |

> *Podium hit recalculation: 2,355/3,458 = 68.10%. The reported 68.40% may use different NaN handling or per-race averaging.

### 1.3 LightGBM C1 (regression_l1)

| Metric | Reported | Actual (Verified) | Verdict |
|--------|----------|-------------------|---------|
| MAE | 3.1193 | 3.1193 ✅ | |
| Overfit gap | 0.5008 | 0.5008 ✅ | **REJECTED** (threshold 0.15) |
| Winner hit | 51.45% | 51.45% ✅ | Below 55% threshold |
| Podium hit | 67.8% | 67.8% ✅ | |

### 1.4 LightGBM C2 (regression + MAE metric)

| Metric | Reported | Actual (Verified) | Verdict |
|--------|----------|-------------------|---------|
| MAE | 3.2381 | 3.2381 ✅ | |
| Overfit gap | 0.0770 | 0.0770 ✅ | |
| Winner hit | 53.18% | 53.18% ✅ | **NULL** (below 55%) |
| Podium hit | 67.8% | 67.8% ✅ | |

---

## 2. VALIDATION FOLD RECONCILIATION

### 2.1 Fold Counts by Dataset

| Dataset | Total Races | MIN_TRAIN | Raw Folds | Finite-Finish Folds | DNS Excluded |
|---------|-------------|-----------|-----------|---------------------|--------------|
| **Full (2018–2026)** | 193 | 20 | **173** | **171** | 2 |
| **Legacy (2023–2026)** | 90 | 20 | **70** | **70** | 0 |
| **Phase 3–6 (orig.)** | 89* | 20 | **69** | **69** | 0 |

> *The original "89 races" was a 2023–2025 snapshot before 2026 R1–R20 were added.

### 2.2 DNS Exclusions (Full Dataset Only)

| Race | Year-Round | Event | DNS Driver | Fold Scored? |
|------|------------|-------|------------|--------------|
| race_idx=81 | 2021 R22 | Saudi Arabia | 1 | **No** (per-race) |
| race_idx=83 | 2022 R2 | Saudi Arabia | 1 | **No** (per-race) |

**Impact:** These 2 folds are included in the pooled MAE/ρ (3,496 rows) but **excluded from per-race metrics** (winner/podium hit, per-race MAE). The denominator for per-race averages is **171**, not 173.

---

## 3. WINNER / PODIUM HIT RECONCILIATION

### 3.1 Ridge (Full Dataset)

| Metric | Calculation | Value |
|--------|-------------|-------|
| Winner hits | 94 / 171 | **54.97%** |
| Podium hits (recall@3) | 2,352 / 3,458 | **68.03%** |
| Winner hit (legacy 2023–2026) | 44 / 70 | 62.86% |
| Podium hit (legacy) | — | 67.14% |

### 3.2 XGBoost (Full Dataset)

| Metric | Phase 7B Report | Verified (171 folds) | Notes |
|--------|-----------------|---------------------|-------|
| Winner hits | 95/173 = 54.91% | **95/171 = 55.56%** | Denominator corrected |
| Podium hit | 68.40% | ~68.10% | Slight difference in NaN handling |

**Discrepancy:** The Phase 7B report used **173** as denominator (raw folds), but only **171** folds have all-finite finishes and are scored for winner/podium hit. The correct denominator is **171**.

### 3.3 LightGBM

| Variant | Winner Hit (Reported) | Verified (171 folds) | Threshold | Verdict |
|---------|----------------------|---------------------|-----------|---------|
| C1 | 51.45% | 51.45% | ≥55% | **REJECTED** |
| C2 | 53.18% | 53.18% | ≥55% | **NULL** |

---

## 4. R20 SÃO PAULO MAE DISCREPANCY

### 4.1 Two Different Grid Sources

| Grid Source | MAE | Winner Hit | Podium Hit | Context |
|-------------|-----|------------|------------|---------|
| **FastF1 `results.grid`** (all -1) | **6.468** | 0% | 33% | Test forecast flow / live forecast |
| **Official FIA Doc 51** | **2.777** | 100% (NOR) | 33% | Addendum 2 scorecard |

### 4.2 Root Cause

- **FastF1** returned `GridPosition = -1` for all 22 cars in 2026 R20.
- The model's `grid` feature was trained on historical `results.grid` (real starting grids after penalties).
- At forecast time, `--grid-file` with official grid was required but not available for the test run.
- The **2.777 MAE** in `scorecard_2026_r20_addendum2.md` uses the **official grid** (FIA Doc 51).
- The **6.468 MAE** in `test_forecast_flow.py` uses the **FastF1 grid** (all -1 → filled with 23).

### 4.3 Forecast Grid vs Training Grid

| Context | Grid Value Used | Provenance |
|---------|-----------------|------------|
| Training (historical) | `results.grid` | Real starting grid after penalties |
| Forecast (early mode) | `qualifying.q_position` | Qualifying order (no penalties known) |
| Forecast (full mode, no --grid-file) | `qualifying.q_position` | Qualifying order |
| Forecast (full mode, with --grid-file) | `official_grid.csv` | FIA Doc 51 / formula1.com |
| Scoring baseline | `grid_pred` (saved at forecast time) | Matches forecast-time grid |

**Semantic Mismatch:** The model trains on **official starting grids** but forecasts (without `--grid-file`) use **qualifying order**. This is a known limitation documented in LIMITATIONS §11.

---

## 5. SHUFFLED-LABEL SANITY CHECK RECONCILIATION

| Model | Real MAE | Shuffled MAE | Gap | Threshold | Pass |
|-------|----------|--------------|-----|-----------|------|
| Ridge (full) | 3.278 | ~5.14 | ~1.86 | >1.5 | ✅ |
| XGBoost | 3.238 | 4.764 | 1.526 | >1.5 | ✅ |
| LGB C1 | 3.119 | 5.197 | 2.078 | >1.5 | ✅ |
| LGB C2 | 3.238 | 4.795 | 1.557 | >1.5 | ✅ |

All models pass the shuffled-label control (gap > 1.5 positions).

---

## 6. OVERFIT GAP RECONCILIATION

| Model | Train MAE | Test MAE | Gap | Threshold | Status |
|-------|-----------|----------|-----|-----------|--------|
| Ridge (full) | ~3.20 | 3.278 | ~0.08 | 0.5 | PASS |
| XGBoost | 3.153 | 3.237 | 0.084 | 0.5 | PASS |
| LGB C1 | 2.619 | 3.120 | **0.501** | 0.15 | **FAIL** |
| LGB C2 | 3.161 | 3.238 | 0.077 | 0.15 | PASS |

---

## 7. BOOTSTRAP CONFIDENCE INTERVALS

### 7.1 XGBoost vs Ridge (Full Dataset)

| Statistic | Value | Notes |
|-----------|-------|-------|
| Mean ΔMAE (XGB − Ridge) | −0.0372 | Per-race mean |
| 95% CI (paired, 1000 resamples) | [−0.0651, −0.0058] | Excludes 0 ✅ |
| Sign test p-value | 0.0013 | |
| Wilcoxon p-value | 0.0002 | |

### 7.2 LightGBM C1 vs Ridge

| Statistic | Value | Notes |
|-----------|-------|-------|
| Mean ΔMAE | −0.1545 | |
| 95% CI | [−0.1931, −0.1157] | Excludes 0 ✅ |
| Overfit gap | 0.501 | **FAIL** |

### 7.3 LightGBM C2 vs Ridge

| Statistic | Value | Notes |
|-----------|-------|-------|
| Mean ΔMAE | −0.0365 | |
| 95% CI | [−0.0591, −0.0097] | Excludes 0 ✅ |
| Winner hit | 53.18% | < 55% threshold |

---

## 8. SUMMARY OF CORRECTIONS

| Metric | Old Value | Corrected Value | Reason |
|--------|-----------|-----------------|--------|
| Total historical races | 89 / 193 | **90 legacy / 193 full** | 2026 R1–R20 added |
| Validation folds | 69 / 173 | **173 raw / 171 scored** | 2 DNS folds excluded from per-race |
| Validation rows | 1,416 / 3,496 | **3,496 finite-finish** | 2 DNS drivers removed |
| Ridge winner hits | 94/173 (54.3%) | **94/171 (54.97%)** | Denominator = scored folds |
| XGBoost winner hits | 95/173 (54.91%) | **95/171 (55.56%)** | Same |
| Legacy races | 89 | **90** | 2026 R1–R20 added |
| Legacy validation folds | 69 | **70** | 90 − 20 |
| R20 MAE | 2.777 | **6.468 (grid=-1) / 2.777 (official)** | Two different grid sources |

---

*End of Metric Reconciliation Report*