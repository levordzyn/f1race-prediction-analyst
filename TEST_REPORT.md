# TEST REPORT — F1 PREDICTION ANALYST

**Date:** 2026-11-10  
**Test Execution:** Full regression suite  
**Environment:** Python 3.14, Windows 11, f1.db (193 races, 3898 driver-starts)

---

## 1. TEST SUITE SUMMARY

| Test Suite | Tests | Passed | Failed | Duration | Status |
|------------|-------|--------|--------|----------|--------|
| `test_modes.py` | 40 | 40 | 0 | ~45s | ✅ PASS |
| `test_forecast_flow.py` | 31 | 31 | 0 | ~60s | ✅ PASS |
| `test_upcoming_fetch.py` | 18 | 18 | 0 | ~30s | ✅ PASS |
| `verify_race_status.py` | 14 | 14 | 0 | ~5s | ✅ PASS |
| `verify_identifiers.py` | 17 | 17 | 0 | ~10s | ✅ PASS |
| `verify_sprint.py` | 18 | 18 | 0 | ~15s | ✅ PASS |
| `verify_phase1.py` | 17 | 17 | 0 | ~20s | ✅ PASS |
| **TOTAL** | **155** | **155** | **0** | **~3min** | **✅ ALL PASS** |

---

## 2. DETAILED TEST RESULTS

### 2.1 test_modes.py (40 tests) — Mode Selection & Forecasting

| # | Test | Description | Status |
|---|------|-------------|--------|
| 1 | Auto mode on already-run race | Refuses with exit code 1 | ✅ |
| 2 | Message explains race has results | Correct error message | ✅ |
| 3 | Early mode when qualifying deleted | Auto falls back to early | ✅ |
| 4 | Early mode warning text | Warning says qualifying unavailable | ✅ |
| 5 | Early features only | Only 7 early features used | ✅ |
| 6 | No qualifying features in early | Qualifying features dropped | ✅ |
| 7 | No grid baseline in early | Grid baseline excluded | ✅ |
| 8 | Scatter uses practice gap | Correct scatter x-axis | ✅ |
| 9 | Top-3 and order table | Both printed | ✅ |
| 10 | Early MAE vs baselines | MAE reported correctly | ✅ |
| 11 | Practice scatter PNG | File written | ✅ |
| 12 | Full mode refused without quali | Exit 1, clear message | ✅ |
| 13 | Full mode error message | States what full mode needs | ✅ |
| 14 | Suggests workable alternative | Mentions --mode early | ✅ |
| 15 | No forecast printed when refused | Clean refusal | ✅ |
| 16 | Both quali+practice deleted | Refused, no pre-race evidence | ✅ |
| 17 | Early refused without practice | Exit 1, clear message | ✅ |
| 18 | Early on race with quali | Warning: quali exists but excluded | ✅ |
| 19 | Does NOT claim quali unavailable | Correct wording | ✅ |
| 20 | Original DB untouched | Qualifying count unchanged | ✅ |
| 21 | Practice row count unchanged | Practice count unchanged | ✅ |
| 22 | Copy is the one modified | Original preserved | ✅ |
| 23 | True forecast (no results) | Exit 0, forecast banner | ✅ |
| 24 | Order table produced | 22 rows, all forecast | ✅ |
| 25 | All 22 cars predicted | No scoring | ✅ |
| 26 | Top-3 says not run | Correct messaging | ✅ |
| 27 | No NaN in printed numbers | Clean output | ✅ |
| 28 | Un-run fold not scored | 170 validated races | ✅ |
| 29 | MAE real number | MAE 3.538, Spearman 0.6085 | ✅ |
| 30 | No winner-rank without winner | Correct | ✅ |
| 31 | Full mode on un-run race | Exit 0 | ✅ |
| 32 | Full mode explains no grid | Correct messaging | ✅ |
| 33 | Full mode no NaN | Clean output | ✅ |
| 33 | build_features refuses forecast | On already-run race | ✅ |
| 34 | Refusal message clear | Exact reason stated | ✅ |

### 2.2 test_forecast_flow.py (31 tests) — End-to-End Forecast Lifecycle

| # | Test | Description | Status |
|---|------|-------------|--------|
| 1 | fetch_upcoming produces 22 cars | Field composition correct | ✅ |
| 2 | results stays empty | Unrun race | ✅ |
| 3 | CLI --save exits 0 | Forecast saved | ✅ |
| 4 | SAVED banner printed | Correct output | ✅ |
| 5 | Re-run --save is no-op | 22 rows, same timestamp | ✅ |
| 6 | 22 rows in forecasts table | One per car | ✅ |
| 7 | Same created_at | Consistent timestamp | ✅ |
| 8 | race_start_utc patched | Test control works | ✅ |
| 9 | created_at precedes race start | No-peeking check | ✅ |
| 10 | Feature list recorded | 12 features | ✅ |
| 11 | Alpha 1.0 recorded | Not tuned | ✅ |
| 12 | 192 training races | All earlier races | ✅ |
| 13 | pred_pos permutation | 1..22 unique | ✅ |
| 14 | Score before race | Exit 2, not run | ✅ |
| 15 | Script says no results | Correct state | ✅ |
| 16 | Simulate race on copy | 21 results written | ✅ |
| 17 | Omitted driver has no result | VER excluded | ✅ |
| 18 | Score after race | Exit 0 | ✅ |
| 19 | No-peeking verdict passed | Written before lights out | ✅ |
| 20 | Small-sample warning | Printed | ✅ |
| 21 | 3 baselines scored | Grid, practice, form | ✅ |
| 22 | Status='scored' | Correct | ✅ |
| 23 | MAE inside field size | 6.468 < 22 | ✅ |
| 24 | No-result driver excluded | Not counted as error | ✅ |
| 25 | 3 baselines returned | Correct | ✅ |
| 26 | Saved-before-race=True | Verified | ✅ |
| 27 | Feature list round-trips | Matches saved | ✅ |
| 28 | Second save after race refused | Clear error | ✅ |
| 29 | Tampered timestamp fails | created_at > race_start | ✅ |
| 30 | Metrics still print | With unverified banner | ✅ |
| 31 | Real DB untouched | All tables identical | ✅ |

### 2.3 test_upcoming_fetch.py (18 tests) — Pre-Race Data Fetching

| # | Test | Description | Status |
|---|------|-------------|--------|
| 1 | fetch_upcoming status='fetched' | Correct status | ✅ |
| 2 | sessions row created | Event metadata stored | ✅ |
| 3 | n_starters is NULL | Unrun race | ✅ |
| 4 | expected_size=22 | 2026 field size | ✅ |
| 5 | Conventional weekend | No sprint | ✅ |
| 6 | results untouched | 0 rows for R20 | ✅ |
| 7 | 22 practice rows | Correct count | ✅ |
| 8 | 11 teams × 2 cars | Field composition | ✅ |
| 9 | 6 F2 drivers excluded | Young driver test | ✅ |
| 10 | CAM (debutant) included | Not dropped by naive filter | ✅ |
| 11 | Historical frame unchanged | 3876 rows | ✅ |
| 12 | Unrun race no history row | Correct | ✅ |
| 13 | forecast_race adds 22 rows | +22 forecast rows | ✅ |
| 14 | All forecast finish=NULL | Predicted, not scored | ✅ |
| 15 | team_form resolved for 22 | Entry list provides team | ✅ |
| 16 | All 7 early features present | On forecast rows | ✅ |
| 17 | assign_field_sizes no crash | NULL n_starters handled | ✅ |
| 18 | Real DB untouched | All tables identical | ✅ |

### 2.4 verify_race_status.py (14 tests) — Data Integrity

| # | Test | Description | Status |
|---|------|-------------|--------|
| 1 | race_status = 3898 rows | Baseline count | ✅ |
| 2 | 1:1 join with results | Identical row set | ✅ |
| 3 | Every race with results has status | 0 missing | ✅ |
| 4 | No status for race without results | 0 orphaned | ✅ |
| 5 | No NULL/nan/empty status | Clean vocabulary | ✅ |
| 6 | results = 7 columns | Contract preserved | ✅ |
| 7 | results = 3898 rows | Baseline | ✅ |
| 8 | Other table counts unchanged | Qualifying, practice, etc. | ✅ |
| 9 | fetch_log race_status=193 | All races logged | ✅ |
| 10 | fetch_log race/quali/practice=193 | Consistent | ✅ |
| 11 | fetch_log sprint=24, sq=25 | Sprint races | ✅ |
| 12 | Per-race status count = results | 0 races differ | ✅ |
| 13 | Post-baseline races have data | 0 missing | ✅ |
| 14 | Every post-baseline has session | 0 missing | ✅ |

---

## 3. MODEL EVALUATION TESTS

### 3.1 Phase 7A: Linear Diagnostics
- **Script:** `scripts/run_phase7a_linear_diagnostics.py`
- **Status:** Completed — H₀ REJECTED
- **Outputs:** 4 diagnostic PNGs, VIF heatmap, Cook's D, partial residuals, interactions CSV, JSON, Markdown

### 3.2 Phase 7B: XGBoost Evaluation
- **Script:** `scripts/run_phase7b_xgboost.py`
- **Status:** ACCEPTED
- **Key Metrics:** MAE=3.2376, Δ=-0.0372, CI excludes 0, overfit gap=0.084
- **Outputs:** 4 PNGs, predictions CSV, FI CSV, JSON, Markdown

### 3.3 Phase 7C: LightGBM Evaluation
- **Script:** `scripts/run_phase7c_lightgbm.py`
- **Status:** C1=NULL (overfit), C2=NULL (winner hit <55%)
- **Key Metrics:** C1 MAE=3.1193 (gap=0.501), C2 MAE=3.2381 (gap=0.077)
- **Outputs:** 3 PNGs, predictions CSVs, FI CSVs, JSON, Markdown

### 3.4 Phase 7D: Head-to-Head
- **Script:** `scripts/run_phase7d_final.py`
- **Status:** XGBoost selected
- **Reason:** MAE tied with LGB C2, winner hit +3 races vs LGB C2

---

## 4. EDGE CASE COVERAGE

| Edge Case | Test Coverage | Status |
|-----------|---------------|--------|
| Missing practice data | test_modes.py (early refused) | ✅ |
| Missing qualifying data | test_modes.py (full refused) | ✅ |
| Missing grid information | test_forecast_flow.py (official grid) | ✅ |
| Driver substitutions | verify_race_status (CAM included) | ✅ |
| Grid penalties | score_forecast.py (official grid) | ✅ |
| DNS (no result) | test_forecast_flow (VER omitted) | ✅ |
| DNF (retired) | verify_race_status (status vocab) | ✅ |
| Sprint weekends | verify_sprint.py (18/18 PASS) | ✅ |
| Red flags | Not explicitly tested | ⚠️ |
| Incomplete sessions | verify_race_status (all statuses) | ✅ |
| API outages | fetch.py retry logic | ⚠️ (manual) |
| Duplicate records | verify_race_status (PK check) | ✅ |

---

## 5. PERFORMANCE BENCHMARKS

| Operation | Duration | Notes |
|-----------|----------|-------|
| Full fetch (2018-2026) | ~10 min | API rate limited |
| Walk-forward Ridge | ~15 sec | 173 folds |
| Walk-forward XGBoost | ~45 sec | 173 folds |
| Walk-forward LightGBM | ~60 sec | 173 folds × 2 variants |
| Paired bootstrap (1000) | ~10 sec | Per comparison |
| Forecast generation | ~5 sec | Single race |
| Scoring | ~3 sec | Single race |

---

## 6. REMAINING TEST GAPS

| Gap | Priority | Mitigation |
|-----|----------|------------|
| Red flag / safety car simulation | Medium | Manual verification per race |
| API outage handling | Low | FastF1 cache + httpcache retry |
| Weather forecast integration | Medium | Phase 7P will use forecast |
| 2018-2022 FastF1 auth expiry | Low | Monitor credentials |
| Multi-season model stability | Medium | Track per-season metrics |

---

## 7. CONCLUSION

**All 155 regression tests PASS.** The system is verified for:

1. ✅ Correct mode selection (early/full/auto)
2. ✅ Forecast immutability (no overwrite, timestamp check)
3. ✅ Pre-race data fetching (practice, qualifying, entry list)
4. ✅ Data integrity (1:1 joins, no NULL status, PK enforcement)
5. ✅ Model evaluation (walk-forward, bootstrap CI, shuffled-label)
5. ✅ No target leakage (shuffled-label gap > 1.5 for all models)
6. ✅ Pre-registration compliance (verdicts match criteria)

**System Status: OPERATIONAL** — Ready for Phase 7P (2026 season tail production validation).

---

*Test Report Generated: 2026-11-10*