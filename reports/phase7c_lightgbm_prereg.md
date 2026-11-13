# Phase 7C Pre-registration: LightGBM Regression (Walk-Forward)

**Date:** 2026-11-10 (pre-registration)  
**Author:** F1 Prediction Project  
**Status:** PRE-REGISTRATION (before any LightGBM model runs)

---

## Pre-registered Hyperparameters (IMMUTABLE after this point)

### Varian C1: LightGBM `regression_l1` (MAE-native objective)

```python
LIGHTGBM_L1_PARAMS = {
    "objective": "regression_l1",     # MAE native, directly optimizes MAE
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
```

**Rationale:**
- XGBoost used `reg:squarederror` (MSE) → bias toward outliers in back-markers
- MAE-native objective directly targets our evaluation metric
- May fix podium collapse by not over-penalizing large errors on back-markers
- Same regularization strength as XGBoost for fair comparison

**Important Limitation:** LightGBM does NOT support monotone constraints with `regression_l1` objective. This variant will run WITHOUT monotone constraints. This is a known LightGBM limitation.

### Varian C2: LightGBM `regression` with `metric=mae` (MSE objective, MAE metric)

```python
LIGHTGBM_MSE_PARAMS = {
    "objective": "regression",        # MSE objective (default)
    "metric": "mae",                  # but track MAE for early stopping/monitoring
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
```

**Rationale:**
- Standard MSE objective but with MAE as monitoring metric
- Baseline for comparison: does MAE-native objective actually help?
- Same tree structure, different loss function

**Hyperparameters are FROZEN** — no tuning after seeing results. Any change requires new pre-registration.

---

## Monotone Constraints (REQUIRED, SAME AS XGBOOST WHERE SUPPORTED)

LightGBM supports monotone constraints: `+1` (increasing), `-1` (decreasing), `0` (unconstrained).

| Feature | Expected Direction | Constraint | Justification |
|---------|-------------------|------------|---------------|
| `grid` | ↑ grid → ↑ finish (worse) | `+1` | Starting further back → worse finish |
| `driver_form` | ↑ form → ↑ finish (worse) | `+1` | Higher avg finish = worse recent performance |
| `team_form` | ↑ form → ↑ finish (worse) | `+1` | Same logic |
| `non_finish_rate` | ↑ DNF rate → ↑ finish (worse) | `+1` | More DNFs → worse finish |
| `practice_pos` | ↑ pos → ↑ finish (worse) | `+1` | Worse practice → worse finish |
| `practice_gap_pct` | ↑ gap → ↑ finish (worse) | `+1` | Larger gap to fastest = worse pace |
| `practice_laps_30` | ↑ laps → ↓ finish (better) | `-1` | More running = better preparation |
| `no_practice_time` | flag=1 → ↑ finish (worse) | `+1` | No practice = unknown = worse |
| `q_position` | ↑ q_pos → ↑ finish (worse) | `+1` | Worse qualifying = worse finish |
| `q_gap_pct` | ↑ gap → ↑ finish (worse) | `+1` | Larger gap to pole = worse pace |
| `no_q_time` | flag=1 → ↑ finish (worse) | `+1` | No quali time = unknown = worse |
| `on_pole` | pole=1 → ↓ finish (better) | `-1` | Pole position → better finish |

**Format for LightGBM:** List of 12 values in `ALL_FEATURES` order.

```python
MONOTONE_CONSTRAINTS = [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, -1]
# Order: grid, driver_form, team_form, non_finish_rate,
#        practice_pos, practice_gap_pct, practice_laps_30, no_practice_time,
#        q_position, q_gap_pct, no_q_time, on_pole
```

**LightGBM Limitation:** `regression_l1` objective does NOT support monotone constraints. Varian C1 will run WITHOUT monotone constraints. Varian C2 (`regression` objective) WILL use monotone constraints.

---

## Success Criteria (PRE-REGISTERED)

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| **MAE** | LightGBM MAE < Ridge MAE (3.278) **AND** 95% CI for ΔMAE excludes 0 | Must beat linear baseline |
| **Podium hit rate** | ≥ 65% (ideally ≥ 68% Ridge parity) | No podium collapse |
| **Winner hit rate** | ≥ 55% | Competitive winner prediction |
| **Shuffled-label MAE** | ≥ 5.0 (collapse to ~5.14) | Sanity check: no leakage |
| **Train/test gap** | < 0.15 | No overfitting |

**Decision Rule (per varian):**
- If **MAE improvement with CI excluding 0** AND **podium hit ≥ 65%** → **ACCEPTED**
- If **MAE improvement** but **podium hit < 50%** → **NULL** (document trade-off)
- If **no MAE improvement** → **REJECTED**

---

## Pre-registered Analysis Plan

### C.1 Implementation: `f1pred/lightgbm_model.py`
- Function `walk_forward_lightgbm(df, features, min_train=20, shuffle=False, monotone_constraints=None, params=None)`
- **Identical fold structure** to `model.walk_forward`: expanding window, 173 folds, train 1..k-1, test k
- **No StandardScaler** — LightGBM is scale-invariant
- **Native missing handling**: LightGBM learns default direction for NaN (do NOT impute)
- Returns: per-fold predictions, MAE, Spearman, hit rates, feature importance (gain/split)

### C.2 Shuffled-Label Control (MANDATORY)
- `walk_forward_lightgbm(..., shuffle=True)` — scrambles `y_train` inside each fold
- Expected MAE collapse to ~5.14 (naive)
- If shuffled MAE ≈ real MAE → **LEAKAGE**, stop and debug

### C.3 Walk-Forward Execution (per varian)
1. Run baseline (no shuffle) → per-race MAE, ρ, hit rates
2. Run shuffled control (3 seeds) → confirm collapse
3. Per-race paired delta: `delta_race = MAE_lgb_race - MAE_ridge_race`
4. Paired bootstrap 95% CI (1000 resamples, seed=42) on mean delta
5. Sign test + Wilcoxon signed-rank on per-race deltas

### C.4 Cross-Model Feature Importance Comparison
- LightGBM: `gain` (primary), `split`
- Compare ranking vs Ridge coef ranking AND vs XGBoost gain (Spearman ρ)
  - ρ > 0.7 → consistent feature importance across tree models
  - ρ < 0.4 → different signal found

### C.5 Overfitting Check
- Per fold: train MAE vs test MAE
- If train MAE << test MAE (gap > 0.15) → overfit
- **No tuning allowed** — report honestly

### C.6 Podium Hit by Race Type (if columns available)
- Sprint weekend, wet race, era breakdown
- DNF in actual top-3 vs no DNF

---

## Shuffled-Label Control (Pre-registered Sanity Check)

| Scenario | Expected MAE | Interpretation |
|----------|--------------|----------------|
| Real labels | ~3.0 | Model learns signal |
| Shuffled labels | ~5.14 | No signal, random guessing |
| Shuffled ≈ Real | **LEAKAGE** | Stop and debug |

**Threshold:** Shuffled MAE must be > real MAE + 1.5 positions

---

## Success Criteria Summary (Gate for Promotion)

| Criterion | PASS → ACCEPTED | NULL | FAIL → REJECTED |
|-----------|----------------|------|-----------------|
| ΔMAE < 0 (CI excludes 0) AND podium ≥ 65% | ✅ | | |
| ΔMAE < 0 (CI excludes 0) but podium < 50% | | ✅ | |
| No MAE improvement | | | ✅ |

---

## Verdict Options (Mutually Exclusive, per varian)

| Verdict | Action |
|---------|--------|
| **ACCEPTED** | Promote to production; bump `MODEL_VERSION`; update `LIMITATIONS.md` |
| **NULL** | Keep separate in `lightgbm_model.py`; document as experiment; Ridge/XGB remain production |
| **REJECTED** | Revert all LightGBM code; document why it failed |

---

## Software Dependencies (Pre-verified)

| Package | Version | Notes |
|---------|---------|-------|
| `lightgbm` | 4.7.0 | `pip install lightgbm==4.7.0` |
| `scikit-learn` | 1.9.1 | For sklearn API wrapper |
| `numpy` | 2.4.6 | |
| `pandas` | 2.3.3 | |

---

## Output Artifacts (Committed Regardless of Verdict)

| Artifact | Path |
|----------|------|
| Pre-registration (this file) | `reports/phase7c_lightgbm_prereg.md` |
| Model implementation | `f1pred/lightgbm_model.py` |
| Run script | `scripts/run_phase7c_lightgbm.py` |
| Results report | `reports/phase7c_lightgbm.md` |
| Feature importance plots | `reports/phase7c_lightgbm_importance.png` |

---

## Pre-registration Sign-off

**Pre-registered by:** F1 Prediction Project  
**Date:** 2026-11-10  
**Commit:** Before any LightGBM code runs  
**Status:** ✅ PRE-REGISTERED — No LightGBM code executed yet