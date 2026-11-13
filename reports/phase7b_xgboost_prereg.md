# Phase 7B Pre-registration: XGBoost Regression (Walk-Forward)

**Date:** 2026-11-09 (pre-registration)  
**Author:** F1 Prediction Project  
**Status:** PRE-REGISTRATION (before any XGBoost model runs)

---

## Pre-registered Hyperparameters (IMMUTABLE after this point)

```python
XGBOOST_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,              # shallow: dataset small (173 folds, ~1400 train rows/fold)
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,       # conservative for small dataset
    "reg_alpha": 1.0,            # L1
    "reg_lambda": 1.0,           # L2
    "objective": "reg:squarederror",
    "random_state": 42,
    "n_jobs": 1,                 # reproducibility first, speed second
}
```

**Rationale:**
- Dataset small: 173 validation folds, ~1400 train rows/fold (173 races × ~8 drivers after train split)
- Shallow trees (depth 4) + high regularization prevent overfit
- Low learning rate + more estimators = stable convergence
- `min_child_weight=5` prevents overfit to rare driver patterns
- `n_jobs=1` for reproducibility (threading can affect RNG in some versions)

**Hyperparameters are FROZEN** — no tuning after seeing results. Any change requires new pre-registration.

---

## Monotone Constraints (REQUIRED, PRE-REGISTERED)

XGBoost supports monotone constraints: `+1` (increasing), `-1` (decreasing), `0` (unconstrained).

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

**All constraints are PHYSICAL DOMAIN KNOWLEDGE**, not data-driven. This prevents the model from learning spurious negative relationships.

**Format for XGBoost:** List of 12 values in `ALL_FEATURES` order.

```python
MONOTONE_CONSTRAINTS = [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, -1]
# Order: grid, driver_form, team_form, non_finish_rate,
#        practice_pos, practice_gap_pct, practice_laps_30, no_practice_time,
#        q_position, q_gap_pct, no_q_time, on_pole
```

---

## Success Criteria (PRE-REGISTERED)

| Metric | Threshold | Rationale |
|--------|-----------|-----------|
| **MAE** | XGB MAE < Ridge MAE (3.069) **OR** 95% CI for ΔMAE excludes 0 | Tree must beat linear baseline |
| **Shuffled-label MAE** | ≥ 5.0 (collapse to ~5.14) | Sanity check: no leakage |
| **Paired ΔMAE (XGB − Ridge)** | 95% CI excludes 0 | Per-race paired bootstrap |
| **Podium hit rate** | ≥ Ridge (67.6%) | Secondary metric |
| **Winner hit rate** | ≥ Ridge (63.8%) | Secondary metric |

**Decision Rule:**
- If **MAE improvement** with CI excluding 0 → **ACCEPTED** (promote to production)
- If **no significant MAE gain** but hit rates improve → **NULL** (keep separate, document)
- If **worse or no clear signal** → **REJECTED** (revert, document)

---

## Pre-registered Analysis Plan

### B.1 Implementation: `f1pred/xgboost_model.py`
- Function `walk_forward_xgboost(df, features, min_train=20, shuffle=False, monotone_constraints=None)`
- **Identical fold structure** to `model.walk_forward`: expanding window, 173 folds, train 1..k-1, test k
- **No StandardScaler** — XGBoost is scale-invariant
- **Native missing handling**: XGBoost learns default direction for NaN (do NOT impute)
- Returns: per-fold predictions, MAE, Spearman, hit rates, feature importance (gain/weight/cover)

### B.2 Shuffled-Label Control (MANDATORY)
- `walk_forward_xgboost(..., shuffle=True)` — scrambles `y_train` inside each fold
- Expected MAE collapse to ~5.14 (naive)
- If shuffled MAE ≈ real MAE → **LEAKAGE**, stop and debug

### B.3 Walk-Forward Execution
1. Run baseline (no shuffle) → per-race MAE, ρ, hit rates
2. Run shuffled control (3 seeds) → confirm collapse
3. Per-race paired delta: `delta_race = MAE_xgb_race - MAE_ridge_race`
3. Paired bootstrap 95% CI (1000 resamples, seed=42) on mean delta
4. Sign test + Wilcoxon signed-rank on per-race deltas

### B.4 Feature Importance (Grouped)
- XGBoost: `gain` (primary), `weight`, `cover`
- Aggregate across folds, rank features
- Compare ranking vs Ridge coef ranking (Spearman ρ)
  - ρ > 0.7 → consistent feature importance
  - ρ < 0.4 → trees find different signal (nonlinear interactions?)

### B.5 Overfitting Check
- Per fold: train MAE vs test MAE
- If train MAE << test MAE (gap > 0.5) → overfit
- **No tuning allowed** — report honestly

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
| ΔMAE < 0 (CI excludes 0) | ✅ | | |
| ΔMAE ≥ 0 but hit rates ↑ | | ✅ | |
| Worse or no signal | | | ✅ |

---

## Verdict Options (Mutually Exclusive)

| Verdict | Action |
|---------|--------|
| **ACCEPTED** | Promote to production; bump `MODEL_VERSION`; update `LIMITATIONS.md` |
| **NULL** | Keep separate in `xgboost_model.py`; document as experiment; Ridge remains production |
| **REJECTED** | Revert all XGBoost code; document why it failed |

---

## Software Dependencies (Pre-verified)

| Package | Version | Notes |
|---------|---------|-------|
| `xgboost` | 3.4.1 | `pip install xgboost==3.4.1` |
| `scikit-learn` | 1.9.1 | For sklearn API wrapper |
| `numpy` | 2.4.6 | |
| `pandas` | 2.3.3 | |

---

## Output Artifacts (Committed Regardless of Verdict)

| Artifact | Path |
|----------|------|
| Pre-registration (this file) | `reports/phase7b_xgboost_prereg.md` |
| Model implementation | `f1pred/xgboost_model.py` |
| Run script | `scripts/run_phase7b_xgboost.py` |
| Results report | `reports/phase7b_xgboost.md` |
| Feature importance plots | `reports/phase7b_xgboost_importance.png` |

---

## Pre-registration Sign-off

**Pre-registered by:** F1 Prediction Project  
**Date:** 2026-11-09  
**Commit:** Before any XGBoost code runs  
**Status:** ✅ PRE-REGISTERED — No XGBoost code executed yet