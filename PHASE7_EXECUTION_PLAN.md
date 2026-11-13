# Phase 7 Execution Plan Summary

## Pre-registration Documents Created ✅

| Task | Pre-registration File | Status |
|------|----------------------|--------|
| Task A: Linear Diagnostics | `reports/phase7a_linear_diagnostics_prereg.md` | ✅ Created |
| Task B: XGBoost | `reports/phase7b_xgboost_prereg.md` | ✅ Created |
| Task C: LightGBM | `reports/phase7c_lightgbm_prereg.md` | ✅ Created |
| Task D: Consolidation | `reports/phase7d_consolidation_prereg.md` | ✅ Created |

## Dependencies Installed ✅
- `xgboost==3.4.1` ✅
- `lightgbm==4.7.0` ✅
- `statsmodels` (available) ✅

## Environment Verified ✅
- Python 3.14.5 ✅
- `xgboost==3.4.1` ✅
- `lightgbm==4.7.0` ✅
- `statsmodels` available ✅
- `scikit-learn==1.9.1` ✅

---

## Execution Plan (Sequential, No Parallel)

### Phase 7A: Linear Regression Diagnostics (Task A)
**Duration Estimate:** ~2-3 hours  
**Input:** Current Ridge model (phase5-ridge-1.0, 173 validation folds)  
**Output:** Diagnostic report + 12 partial residual plots + verdict

**Steps:**
1. Create backup: `f1_backup_<timestamp>_pre_phase7_diagnostics.db`
2. Implement `scripts/run_phase7a_linear_diagnostics.py`
3. Run diagnostics (residual plots, BP test, RESET test, VIF, partial residuals, Cook's D, interactions)
2. Generate 12 partial residual plots + diagnostic panel
4. Write `reports/phase7a_linear_diagnostics.md` with verdict
3. **Gate Decision:** H0 (linear adequate) vs H1 (nonlinearity detected) → informs Task B/C expectations

### Phase 7B: XGBoost Regression (Task B)
**Duration Estimate:** ~3-4 hours  
**Pre-req:** Task A verdict documented  
**Output:** XGBoost model + verdict

**Pre-registered Hyperparams (FROZEN):**
```python
XGBOOST_PARAMS = {
    "n_estimators": 200, "max_depth": 4, "learning_rate": 0.05,
    "subsample": 0.8, "colsample_bytree": 0.8, "min_child_weight": 5,
    "reg_alpha": 1.0, "reg_lambda": 1.0,
    "objective": "reg:squarederror", "random_state": 42, "n_jobs": 1
}
MONOTONE_CONSTRAINTS = [1,1,1,1, 1,1,-1,1, 1,1,1,-1]  # 12 features
```

**Steps:**
1. Create `f1pred/xgboost_model.py` with `walk_forward_xgboost()`
2. Create `scripts/run_phase7b_xgboost.py`
3. Run shuffled-label control (sanity check)
4. Run walk-forward (173 folds)
5. Paired bootstrap vs Ridge (1000 resamples, seed=42)
6. Feature importance (gain/weight/cover) + comparison vs Ridge coef
7. Overfitting check (train vs test MAE gap)
8. Write verdict → `reports/phase7b_xgboost.md`

### Phase 7C: LightGBM Regression (Task C)
**Duration Estimate:** ~3-4 hours  
**Pre-req:** Task B completed  
**Pre-registered Hyperparams (FROZEN):**
```python
LIGHTGBM_PARAMS = {
    "n_estimators": 200, "max_depth": 4, "learning_rate": 0.05,
    "num_leaves": 15, "min_child_samples": 10,
    "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8,
    "reg_alpha": 1.0, "reg_lambda": 1.0,
    "objective": "regression", "metric": "mae",
    "random_state": 42, "n_jobs": 1, "verbose": -1
}
```
Same monotone constraints as XGBoost.

**Steps:** Same pattern as Task B → `f1pred/lightgbm_model.py`, `scripts/run_phase7c_lightgbm.py`

### Phase 7D: Consolidation (Task D)
**Pre-req:** Tasks A, B, C complete with verdicts

1. **Head-to-Head Table:** Ridge vs XGB vs LGBM vs Two-Stage vs LambdaMART
2. **Two-Stage with Best Tree** (if any tree ACCEPTED)
3. **Ensemble** (only if both Ridge and best tree strong but neither dominates)
4. **Final Verdict** → bump `MODEL_VERSION` if new model wins
4. Update docs: `PROJECT_ARCHITECTURE.md`, `LIMITATIONS.md`, `requirements.txt`
4. Run full regression suite
5. Save forecast with new model (if upcoming race)

---

## Pre-registration Files Created

| File | Purpose |
|------|---------|
| `reports/phase7a_linear_diagnostics_prereg.md` | Task A pre-reg |
| `reports/phase7b_xgboost_prereg.md` | Task B pre-reg (hyperparams frozen) |
| `reports/phase7c_lightgbm_prereg.md` | Task C pre-reg (hyperparams frozen) |
| `reports/phase7d_consolidation_prereg.md` | Task D pre-reg (verdict framework) |

---

## Next Steps (Awaiting Your Confirmation)

**Ready to proceed with Task A (Linear Diagnostics)?**

**Key decisions needed from you:**
1. ✅ Confirm pre-registration documents look correct
2. ✅ Confirm hyperparameters for XGBoost/LightGBM are acceptable
3. ✅ Confirm monotone constraints are correct (12 features, physics-based)
4. ✅ Confirm success criteria thresholds are acceptable
5. ✅ Confirm Task A → Task B → Task C → Task D sequence is acceptable

**Once you confirm, I'll:**
1. Create database backup
2. Start Task A (Linear Diagnostics) implementation
3. Run diagnostics, produce verdict
4. Based on Task A verdict, proceed to Task B (XGBoost)

**Estimated total timeline:** ~10-12 hours of compute time across 4 tasks

---

**Ready to proceed with Task A (Linear Diagnostics)?**