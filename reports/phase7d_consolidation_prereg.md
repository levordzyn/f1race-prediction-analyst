# Phase 7D Pre-registration: Head-to-Head Comparison & Consolidation

**Date:** 2026-11-09 (pre-registration)  
**Author:** F1 Prediction Project  
**Status:** PRE-REGISTRATION (before head-to-head comparison)

---

## Context

This pre-registration documents the plan for Task D: Head-to-Head comparison of Ridge, XGBoost, LightGBM, and existing models (Two-stage, LambdaMART), leading to a final consolidated model decision.

**Prerequisites:** Tasks A, B, C completed with pre-registered results documented.

---

## D.1 Ladder Final (Pre-registered Comparison Table)

All models evaluated on **identical 173 validation folds** (MIN_TRAIN_RACES=20, walk-forward expanding window).

| Stage | Model | MAE | ρ | Winner% | Podium% | Δ vs Ridge | 95% CI | Verdict |
|-------|-------|-----|---|---------|---------|------------|--------|---------|
| 0 | Ridge α=1.0 (baseline) | 3.069 | 0.7084 | 63.8% | 67.6% | — | — | Baseline |
| 1 | XGBoost (Task B) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 2 | LightGBM (Task C) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 3 | Two-stage DNF × Ridge (existing) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 4 | Two-stage DNF × Best Tree | TBD | TBD | TBD | TBD | TBD | TBD | TBD |
| 5 | LambdaMART ranker (Task 10) | TBD | TBD | TBD | TBD | TBD | TBD | TBD |

**All metrics on identical 173 validation folds (MIN_TRAIN_RACES=20).**

---

## D.2 Two-Stage with Best Tree (Pre-registered)

**Only if Task B or C is ACCEPTED.**

### D.2.1 Architecture
```
Stage 1: LogisticRegression (or tree-based classifier) → P(DNF)
Stage 2: Ridge (or best tree regressor) → E[finish | finish]
Combined: E[finish] = (1 - P(DNF)) × E[finish | finish] + P(DNF) × (field_n + 0.5)
```

### D.2.2 Pre-registered Variants to Test

| Variant | DNF Classifier | Finish Regressor | Label |
|---------|----------------|------------------|-------|
| 1 | LogisticRegression | Ridge | `two_stage_ridge` |
| 2 | LogisticRegression | XGBoost (if ACCEPTED) | `two_stage_xgb` |
| 3 | LogisticRegression | LightGBM (if ACCEPTED) | `two_stage_lgbm` |
| 4 | XGBoost Classifier | XGBoost Regressor | `two_stage_xgb_full` |
| 4 | LightGBM Classifier | LightGBM Regressor | `two_stage_lgbm_full` |

**Pre-registered Hypothesis:** Two-stage with best tree regressor ≥ Two-stage with Ridge

**Success Criteria:**
- MAE improvement ≥ 0.02 vs `two_stage_ridge`
- Podium hit ≥ `two_stage_ridge`

---

## D.3 Model Ensemble (Pre-registered, Conditional)

**Only if Ridge and Best Tree are BOTH strong but neither dominates.**

### D.3.1 Pre-registered Ensemble Variants (NO TUNING)

| Ensemble | Formula | Condition |
|----------|---------|-----------|
| Simple Average | `0.5 × pred_ridge + 0.5 × pred_best_tree` | Both ACCEPTED, neither dominates |
| Inverse-MAE Weighted | `w_r × pred_r + w_t × pred_t` where `w ∝ 1/MAE` | Pre-registered weights |

**NO stacking, NO nested CV, NO meta-learner** — too complex, high leakage risk.

**Success Criteria:** Ensemble MAE beats both components with paired CI excluding 0.

---

## D.4 Final Verdict Framework

### Verdict Decision Tree (Pre-registered)

```
                    ┌─────────────────────────┐
                    │ Any tree ACCEPTED?      │
                    └───────────┬─────────────┘
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
            YES                                   NO
              │                                   │
              ▼                                   ▼
    ┌─────────────────────┐             ┌─────────────────────┐
    │ Compare Ridge vs    │             │ Ridge remains       │
    │ Best Tree head-to-  │             │ PRODUCTION MODEL    │
    │ head (paired CI)    │             │ (MODEL_VERSION =    │
    └─────────┬───────────┘             │  phase5-ridge-1.0)  │
              │                         └─────────────────────┘
       ┌──────┴──────┐
       ▼             ▼
   Tree wins      Ridge wins / Tie
       │               │
       ▼               ▼
┌───────────────┐  ┌──────────────────┐
│ Best Tree     │  │ Ridge remains    │
│ becomes       │  │ PRODUCTION       │
│ PRODUCTION    │  │ (version bump    │
│ (version bump │  │  only if ensemble│
│  to phase7-   │  │  or two-stage   │
│  <model>-1.0) │  │  improves it)    │
└───────────────┘  └──────────────────┘
```

### Pre-registered Final Model Options (Mutually Exclusive)

| Final Model | Condition | Version Bump |
|-------------|-----------|--------------|
| Ridge (phase5) | No tree ACCEPTED | No (stay phase5-ridge-1.0) |
| XGBoost | XGB ACCEPTED, beats Ridge | `phase7-xgboost-1.0` |
| LightGBM | LGBM ACCEPTED, beats Ridge & XGB | `phase7-lightgbm-1.0` |
| Two-Stage + Best Tree | Tree ACCEPTED, two-stage beats Ridge | `phase7-two_stage_<model>-1.0` |
| Ensemble | Both ACCEPTED, ensemble beats both | `phase7-ensemble-1.0` |
| Ridge | No tree ACCEPTED | None (stay `phase5-ridge-1.0`) |

---

## D.5 Documentation Updates (Pre-registered)

### 1. `PROJECT_ARCHITECTURE.md` Updates
| Section | Change |
|---------|--------|
| Part 2 (Tech Stack) | Add `xgboost==3.4.1`, `lightgbm==4.7.0` |
| Part 7 (Modeling) | Add sub-sections for XGBoost, LightGBM, monotone constraints |
| Part 10 (Results) | Add head-to-head comparison table |
| Part 12 (Decision Log) | Add Task A-D decisions with timestamps |
| Appendix B | Add new file hashes for `xgboost_model.py`, `lightgbm_model.py`, etc. |

### 2. `LIMITATIONS.md` Updates
| Section | Addition |
|---------|----------|
| §13 (new) | Tree model comparison — all verdicts, CIs, trade-offs |
| §6 (coef signs) | Add tree importance vs Ridge coef comparison |
| §12 (Decision Log) | Task A-D decisions with timestamps |

### 3. `reports/final_accuracy_report.md`
- Replace with consolidated Task 7 results
- Include head-to-head table, verdict rationale, trade-offs

### 4. New Reports
| Report | Path |
|--------|------|
| Phase 7A diagnostics | `reports/phase7a_linear_diagnostics.md` |
| Phase 7B XGBoost | `reports/phase7b_xgboost.md` |
| Phase 7C LightGBM | `reports/phase7c_lightgbm.md` |
| Phase 7C vs XGBoost | `reports/phase7c_vs_xgboost.md` |
| Phase 7D Final | `reports/phase7d_consolidation.md` |
| Final Accuracy | `reports/final_accuracy_report.md` |

---

## D.6 Final Forecast (If Upcoming Race)

**Condition:** Only if final model differs from current production (`phase5-ridge-1.0`)

| Item | Detail |
|------|--------|
| Race | Next upcoming race (check calendar) |
| Model | Final selected model |
| Grid source | `--grid-file` from FIA/formula1.com |
| Output | Forecast saved with new `MODEL_VERSION` |
| Scorecard | Generated post-race |

---

## D.6 Regression Suite (All Must PASS)

```powershell
$env:PYTHONUTF8 = "1"
python scripts\test_modes.py
python scripts\test_forecast_flow.py
python scripts\test_upcoming_fetch.py
python scripts\verify_race_status.py
python scripts\verify_2018_2022.py
python scripts\test_xgboost_model.py       # NEW
python scripts\test_lightgbm_model.py      # NEW
python scripts\test_phase7_ensemble.py     # NEW (if ensemble implemented)
```

**All must PASS before closing Phase 7.**

---

## D.7 Final Deliverables Checklist

| Deliverable | Path | Status |
|-------------|------|--------|
| Phase 7A diagnostics report | `reports/phase7a_linear_diagnostics.md` | ☐ |
| 12 partial residual plots | `reports/phase7a_partial_residual_*.png` | ☐ |
| Phase 7B XGBoost report | `reports/phase7b_xgboost.md` | ☐ |
| Phase 7C LightGBM report | `reports/phase7c_lightgbm.md` | ☐ |
| XGBoost vs LightGBM | `reports/phase7c_vs_xgboost.md` | ☐ |
| Phase 7D Final Report | `reports/phase7d_consolidation.md` | ☐ |
| `PROJECT_ARCHITECTURE.md` | Updated | ☐ |
| `LIMITATIONS.md` | §13 + §12 + §6 updates | ☐ |
| `reports/final_accuracy_report.md` | Consolidated | ☐ |
| `PROJECT_ARCHITECTURE.md` | Appendix B hashes updated | ☐ |
| `LIMITATIONS.md` | §13 (tree comparison) + §12 (decision log) | ☐ |
| `requirements.txt` | xgboost, lightgbm pinned | ☐ |
| Forecast (if upcoming) | New `--save` with final model | ☐ |
| Regression suite | All PASS | ☐ |

---

## Sign-off

**Pre-registered by:** F1 Prediction Project  
**Date:** 2026-11-09  
**Commit:** Before Task D execution  
**Prerequisite:** Tasks A, B, C completed with documented verdicts  
**Status:** ✅ PRE-REGISTERED