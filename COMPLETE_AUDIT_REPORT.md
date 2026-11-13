# COMPLETE AUDIT REPORT — F1 PREDICTION ANALYST

**Audit Date:** 2026-11-10  
**Auditor:** Principal ML Engineer (AI Agent)  
**Repository:** C:\Users\outbnx_\Documents\F1 PROJECTS

---

## 1. FILE AND MODULE INVENTORY

### Core Package (`f1pred/`)
| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 1 | Package marker |
| `db.py` | 315 | SQLite schema, connection, migrations |
| `fetch.py` | 1106 | FastF1 + OpenF1 data ingestion |
| `features.py` | 567 | Feature engineering (12 + 6 + 7 features) |
| `model.py` | 570 | Walk-forward validation, baselines, Ridge |
| `forecast.py` | 305 | Save/score forecasts, immutability |
| `report.py` | 428 | Console + PNG reports (Phase 4) |
| `cli.py` | 568 | Early/Full forecast modes, --save |
| `clean.py` | 200 | Team aliases, validation rules |
| `xgboost_model.py` | 314 | XGBoost walk-forward (Phase 7B) |
| `lightgbm_model.py` | 315 | LightGBM walk-forward (Phase 7C) |
| `practice.py` | 387 | OpenF1 practice + sprint qualifying |
| `practice_fastf1.py` | 428 | FastF1 practice for 2018-2022 |
| `openf1.py` | 186 | OpenF1 API client, lap validity |
| `httpcache.py` | ~100 | Rate-limited HTTP caching |
| `credentials.py` | ~50 | F1 account credential loading |

### Scripts (`scripts/`)
- **Phase runners:** `run_phase3.py`, `run_phase4.py`, `run_phase6a.py`, `run_phase6b.py`, `run_phase7a_linear_diagnostics.py`, `run_phase7b_xgboost.py`, `run_phase7c_lightgbm.py`, `run_phase7d_final.py`
- **Tests:** `test_modes.py` (40), `test_forecast_flow.py` (31), `test_upcoming_fetch.py` (18), `verify_race_status.py` (14)
- **Diagnostics:** 50+ scripts for data verification, repair, debugging
- **Scoring:** `score_forecast.py` (759 lines)

### Documentation
- `PROJECT_ARCHITECTURE.md` — System architecture
- `LIMITATIONS.md` — Known limitations
- `PHASE7_EXECUTION_PLAN.md` — Phase 7 plan
- `reports/phase7*.md` — Phase 7 experiment reports

---

## 2. CURRENT SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES                             │
├─────────────────────────────────────────────────────────────────┤
│  FastF1 (auth)          │  OpenF1 (no auth)      │  Open-Meteo │
│  - Race results         │  - Practice laps       │  - Weather  │
│  - Qualifying           │  - Sprint qualifying   │             │
│  - Sprint race          │                        │             │
│  - Session schedule     │                        │             │
└───────────┬─────────────┴───────────┬────────────┴─────────────┘
            │                         │
            ▼                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FETCH PIPELINE (fetch.py)                    │
│  fetch_year() → fetch_race() → fetch_race_status()              │
│           → assign_field_sizes() → fetch_qualifying()           │
│           → fetch_sprint() → fetch_practice() / fetch_practice_fastf1() │
│           → fetch_sprint_qualifying()                           │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SQLITE DATABASE (f1.db)                    │
│  results, sessions, driver_numbers, race_status, qualifying,   │
│  sprint, practice, sprint_qualifying, weather, fetch_log,      │
│  forecasts                                                      │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FEATURE ENGINEERING (features.py)             │
│  build_features() → 12 base + 6 sprint + 7 weather features    │
│  Leakage prevention: shift(1), grouped shift, constant defaults │
└────────────────────────────────┬────────────────────────────────┘
                                 │
               ┌─────────────────┼─────────────────┐
               ▼                 ▼                 ▼
      ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
      │    RIDGE     │  │   XGBOOST    │  │  LIGHTGBM    │
      │  (model.py)  │  │(xgboost_model)│  │(lightgbm_mdl)│
      │  alpha=1.0   │  │  200 trees   │  │  200 trees   │
      │  scaler/fold │  │  monotone    │  │  2 variants  │
      └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
             │                 │                 │
             └─────────────────┼─────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   WALK-FORWARD VALIDATION                       │
│  Expanding window, MIN_TRAIN_RACES=20, 173 folds               │
│  Metrics: MAE, Spearman, Winner/Podium hit, bootstrap CI       │
└────────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FORECAST PIPELINE (cli.py)                    │
│  --mode early (7 features) | --mode full (12 features)         │
│  --save → forecasts table (immutable, pre-race timestamp)      │
│  score_forecast.py → scorecards after race                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. CRITICAL DEFECTS

### 3.1 LightGBM C1 Severe Overfitting — **CRITICAL**
- **Finding:** LightGBM C1 (regression_l1) has train MAE = 2.6187, test MAE = 3.1195, **gap = 0.5008**
- **Pre-registration threshold:** "No severe overfitting (train-test gap < 0.15)"
- **Verdict in script:** ACCEPTED (incorrect — only checked MAE improvement + podium hit)
- **Root cause:** The verdict logic in `run_phase7c_lightgbm.py` lines 340-345 checks `mae_improved and podium_ok` but does NOT require `overfit_ok` for ACCEPTED verdict
- **Impact:** Model would not generalize; C1 should be REJECTED

### 3.2 LightGBM C2 Winner Hit Below Pre-registration Threshold — **HIGH**
- **Finding:** LightGBM C2 winner hit rate = 0.532 (92/173)
- **Pre-registration (phase7c_lightgbm_prereg.md):** "Winner hit ≥ 55% to be ACCEPTED"
- **Verdict in script:** ACCEPTED (incorrect — winner hit is 53.2% < 55%)
- **Root cause:** Verdict logic doesn't check winner hit threshold

### 3.3 LightGBM Monotone Constraints Incompatible with regression_l1 — **HIGH**
- **Finding:** LightGBM `regression_l1` objective does NOT support `monotone_constraints`
- **Code:** `lightgbm_model.py` line 140: `if monotone_constraints is not None and lgb_params.get("objective") != "regression_l1":`
- **Impact:** C1 runs WITHOUT monotone constraints despite pre-registration requiring them
- **Fix:** Either change C1 objective to "regression" or document that constraints are not applied

### 3.4 Pandas FutureWarnings in GroupBy.apply — **MEDIUM**
- **Files:** `xgboost_model.py:187`, `lightgbm_model.py:200`
- **Issue:** `DataFrameGroupBy.apply operated on the grouping columns` deprecation warning
- **Fix:** Add `include_groups=False` to groupby calls

### 3.5 Weather Data Only for ~90/193 Races — **MEDIUM**
- **Finding:** `build_features` logs "no observed weather for 103 race(s)"
- **Impact:** Phase 6b weather features unavailable for 2018-2022 seasons
- **Root cause:** Open-Meteo historical data only available for recent seasons
- **Mitigation:** Documented in code; future races need forecast data

### 3.6 2018-2022 Practice Data via FastF1 Requires Auth — **LOW**
- **Finding:** FastF1 lap data needs F1 account credentials
- **Status:** Works when credentials provided; falls back gracefully
- **Risk:** If auth expires, 5 seasons of practice data become unavailable

---

## 4. MAJOR TECHNICAL DEBT

| Item | Location | Effort | Priority |
|------|----------|--------|----------|
| Fix LightGBM verdict logic | `run_phase7c_lightgbm.py` | 1 hr | Critical |
| Fix monotone constraints for LGB C1 | `lightgbm_model.py` | 2 hr | High |
| Fix pandas FutureWarnings | `xgboost_model.py`, `lightgbm_model.py` | 30 min | Medium |
| Add explicit feature schema validation | `features.py` | 2 hr | Medium |
| Residual diagnostics (Phase 7A) | `run_phase7a_linear_diagnostics.py` | 4 hr | High |
| Starting grid resolution pipeline | `features.py`, `fetch.py` | 4 hr | High |
| Model serialization/loading | `model.py`, `forecast.py` | 2 hr | Medium |

---

## 5. DATA INTEGRITY RISKS

### 5.1 Starting Grid Accuracy
- **Current:** `grid` feature uses `qualifying.q_position` (official qualifying order)
- **Problem:** Grid penalties not reflected in historical training data
- **Evidence:** 2026 R20 São Paulo — FastF1 published `GridPosition = -1` for all 22 cars
- **Fix:** Need official starting grid (FIA Doc 51) for training, not just forecast

### 5.2 DNS/DNF Handling
- **Current:** `finish = NULL` for DNS; `race_status` captures DNF
- **Risk:** Non-finish rate feature uses `FINISHING_STATUSES = {"Finished", "Lapped"}`
- **Verification:** 3898 race_status rows match results 1:1 ✓

### 5.3 Team Alias Drift
- **Current:** `TEAM_ALIASES` in `clean.py` maps historical names to canonical
- **Risk:** New team (Cadillac 2026) added; future renames need manual updates
- **Mitigation:** Unknown names logged as warning, not error

### 5.4 Duplicate Race Detection
- **Current:** Primary keys on (year, round, driver) prevent duplicates
- **Verification:** All table counts consistent (3898 rows per core table) ✓

---

## 6. MACHINE LEARNING RISKS

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Target leakage via shift(1) bug | Low | Critical | Unit tests verify shift behavior |
| Future weather in historical preds | Medium | High | Weather only merged when complete |
| Monotone constraints not enforced | High | Medium | LGB C1 runs without them |
| Overfitting (LGB C1) | Confirmed | Critical | Reject C1; C2 passes |
| Small validation sample (173 folds) | Medium | Medium | Bootstrap CI, warn in reports |
| Grid penalties in training | High | High | Need official grid for history |

---

## 7. VALIDATION RISKS

| Risk | Status |
|------|--------|
| Walk-forward folds = 173 (not 69 as some docs say) | Verified: 193 total races, MIN_TRAIN=20 → 173 folds |
| Race counts: 89 vs 90 vs 193 | 193 = all races 2018-2026; 89 = 2023-2026 only |
| Winner hit: 95/173 = 54.9% (XGB) | Verified in run_phase7b |
| Podium hit: 355/519 = 68.4% (XGB) | Verified |
| Shuffled-label gap: 1.53 (XGB) | Pass (>1.5 threshold) |
| Bootstrap CI: 1000 resamples, seed=42 | Implemented in both XGB and LGB |

---

## 8. PRODUCTION RISKS

| Risk | Status |
|------|--------|
| Forecast immutability | ✓ Enforced by PK + INSERT (not REPLACE) |
| Pre-race timestamp check | ✓ `created_at` < `race_start_utc` required |
| Grid file required for full-mode --save | ✓ Enforced in cli.py |
| Official grid vs qualifying order | ✓ Separate columns; penalty check implemented |
| Database backup before destructive ops | ⚠ Manual only (f1_backup_*.db) |
| Dependency on FastF1/OpenF1 APIs | ⚠ No SLA; cache + retry implemented |
| Model version tracking | ✓ `MODEL_VERSION = "phase7-xgboost-1.0"` |

---

## 9. PRIORITIZED REPAIR PLAN

### Phase 1: Critical Fixes (Immediate)
1. **Fix LightGBM verdict logic** — C1 REJECTED (overfit), C2 NULL (winner hit < 55%)
2. **Fix monotone constraints** — LGB C1 cannot use them with regression_l1
3. **Fix pandas FutureWarnings** — Add `include_groups=False`

### Phase 2: Data Integrity (High Priority)
4. **Starting grid resolution pipeline** — Use official grid (FIA Doc 51) for training
5. **Residual diagnostics repair** — Complete Phase 7A investigation
6. **Weather data for 2018-2022** — Document limitation or find source

### Phase 3: ML Improvements (Medium Priority)
7. **Feature schema validation** — Explicit contract between train/inference
8. **Model serialization** — Save/load XGBoost model for production
9. **Additional features** — Teammate gap, circuit history (per Phase 3.5)

### Phase 4: Production Hardening (Medium Priority)
10. **Automated backup script** — Before any DB modification
11. **CLI help improvements** — Better error messages
12. **Dependency pinning** — requirements.txt with exact versions

### Phase 5: Documentation (Ongoing)
13. **Update PROJECT_ARCHITECTURE.md** — Reflect actual implementation
14. **Complete LIMITATIONS.md** — All known issues documented
15. **Runbook** — Operational procedures for Phase 7P (2026 tail)

---

## 10. VERIFICATION STATUS

| Test Suite | Status | Details |
|------------|--------|---------|
| `test_modes.py` | 40/40 PASS | Mode selection, forecasting, saving |
| `test_forecast_flow.py` | 31/31 PASS | Fetch → save → score lifecycle |
| `test_upcoming_fetch.py` | 18/18 PASS | Pre-race data fetching |
| `verify_race_status.py` | 14/14 PASS | Race status integrity |
| `verify_identifiers.py` | 17/17 PASS | Session identifier verification |
| `verify_sprint.py` | 18/18 PASS | Sprint data verification |
| `verify_phase1.py` | 17/17 PASS | Phase 1 data integrity |

**All regression tests PASS** ✓

---

*End of Audit Report*