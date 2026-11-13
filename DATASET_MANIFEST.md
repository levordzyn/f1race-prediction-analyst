# DATASET MANIFEST — F1 PREDICTION ANALYST

**Generated:** 2026-11-10  
**Database:** `f1.db` (SHA256: `a1b2c3d4...` — compute on demand)  
**Scope:** Complete forensic audit of all data populations, validation folds, and metric denominators.

---

## 1. MASTER POPULATION COUNTS

| Population | Scope | Races | Driver-Starts | Source |
|------------|-------|-------|---------------|--------|
| **Full Historical** | 2018–2026 (all completed) | **193** | **3,898** | `results` table |
| **Legacy (Phase 3–6)** | 2023–2026 only | **90** | **1,838** | `results` WHERE year ≥ 2023 |
| **2026 Season Tail** | R21–R23 (future) | 3 | 66 (proj.) | Not in DB |
| **Total incl. future** | 2018–2026 + 3 future | 196 | ~3,964 | — |

### Per-Season Breakdown (Full Historical)

| Year | Races | Driver-Starts | Cars/Race | Notes |
|------|-------|---------------|-----------|-------|
| 2018 | 21 | 420 | 20 | |
| 2019 | 21 | 420 | 20 | |
| 2020 | 17 | 340 | 20 | COVID-shortened |
| 2021 | 22 | 440 | 20 | |
| 2022 | 22 | 440 | 20 | |
| 2023 | 22 | 440 | 20 | |
| 2024 | 24 | 479 | 19–20 | 2 races with 19 starters |
| 2025 | 24 | 479 | 19–20 | 2 races with 19 starters |
| 2026 | 20 | 440 | 22 | R21–R23 not yet run |
| **TOTAL** | **193** | **3,898** | — | |

---

## 2. VALIDATION FOLD DEFINITIONS

### 2.1 Walk-Forward Protocol (Fixed)

- **Method:** Expanding window, chronological
- **MIN_TRAIN_RACES:** 20 (constant across all phases)
- **Training set for fold k:** Races with `race_idx` 1..k-1
- **Test set for fold k:** Single race with `race_idx` = k
- **First validation fold:** Race with `race_idx` = 21
- **Last validation fold:** Race with `race_idx` = max (193 for full, varies for subsets)

### 2.2 Fold Counts by Population

| Population | Total Races | MIN_TRAIN | Validation Folds | Finite-Finish Folds | Excluded (DNS) |
|------------|-------------|-----------|------------------|---------------------|----------------|
| **Full (2018–2026)** | 193 | 20 | **173** | **171** | 2 (R81, R83) |
| **Legacy (2023–2026)** | 90 | 20 | **70** | 70 | 0 |
| **Phase 3–6 (original)** | 89* | 20 | 69 | 69 | 0 |

> **Note:** The "89 races" / "69 folds" in early documentation referred to a 2023–2025 snapshot (before 2026 data was added). The legacy dataset now has **90 races** (2023–2026 inclusive), yielding **70 validation folds**.

### 2.3 DNS Exclusions (Full Dataset Only)

| Race Index | Year-Round | Event | DNS Drivers | NaN Count |
|------------|------------|-------|-------------|-----------|
| 81 | 2021 R22 | Saudi Arabia | 1 | 1 |
| 83 | 2022 R2 | Saudi Arabia | 1 | 1 |

These 2 validation folds have **at least one driver with NaN finish** (DNS). The walk-forward implementation excludes such folds from per-race scoring (winner/podium hit, per-race MAE) but **includes them in the global MAE/ρ averages** via the pooled prediction array.

---

## 3. OUT-OF-FOLD OBSERVATION COUNTS

| Metric | Full (2018–2026) | Legacy (2023–2026) | Phase 3–6 (Original) |
|--------|------------------|-------------------|---------------------|
| Total driver-starts | 3,898 | 1,838 | 1,794* |
| Validation folds | 173 | 70 | 69 |
| Validation driver-starts (raw) | 3,498 | 1,416 | 1,378 |
| **Validation rows with finite finish** | **3,496** | **1,416** | **1,378** |
| Excluded (DNS in validation) | 2 | 0 | 0 |
| Training driver-starts | 402 | 422 | 416 |

> **Critical:** The **3,496** figure is the denominator for all global MAE/ρ calculations in the full dataset. It equals 3,498 raw validation rows minus 2 DNS drivers.

---

## 4. FEATURE FRAME STRUCTURE

### 4.1 Core Feature Frame (`features.build_features()`)

| Column | Type | Missing Handling | Leakage Control |
|--------|------|------------------|-----------------|
| `race_idx` | int | — | Chronological key |
| `year`, `round` | int | — | — |
| `driver` | string | — | Join key |
| `team` | string | — | Canonical via `clean_team_name()` |
| `finish` | float | NaN for DNS / future | **Target** |
| `grid` | float | `field_n + 1` for pit-lane/NULL | Qualifying order proxy |
| `driver_form` | float | `(field_n + 1) / 2` debut | `shift(1)` per driver |
| `team_form` | float | `(field_n + 1) / 2` debut | Collapse → `shift(1)` per team |
| `non_finish_rate` | float | 0.0 debut | `shift(1)` per driver |
| `practice_pos` | float | `field_n + 1` | `shift(1)` not needed (pre-race) |
| `practice_gap_pct` | float | 0.0 + flag | — |
| `practice_laps_30` | float | 0.0 | — |
| `no_practice_time` | int (0/1) | — | — |
| `q_position` | float | `field_n + 1` | — |
| `q_gap_pct` | float | 0.0 + flag | — |
| `no_q_time` | int (0/1) | — | — |
| `on_pole` | int (0/1) | — | — |

### 4.2 Phase 6 Features (Additive, NOT in `ALL_FEATURES`)

| Group | Features | Count |
|-------|----------|-------|
| Sprint | `has_sprint`, `sq_rank`, `sq_gap_pct`, `no_sq_lap`, `sprint_pos`, `no_sprint_result` | 6 |
| Weather | `temp_c`, `humidity_pct`, `rain_mm`, `wind_kmh`, `rain_x_q_position`, `rain_x_non_finish_rate`, `wind_x_grid` | 7 |

---

## 5. BASELINE DEFINITIONS

| Baseline | Column | Mode | Scoring |
|----------|--------|------|---------|
| Grid | `grid` | Full only | MAE + rank |
| Practice-order | `practice_pos` | Both | MAE + rank |
| Recent-form | `driver_form` | Both | MAE + rank |
| Pole-sitter | `grid` (rank) | Both | Winner/Podium hit |
| Best qualifying gap | `q_gap_pct` (excl. `no_q_time`) | Full | Winner/Podium hit |
| Best driver form | `driver_form` | Both | Winner/Podium hit |

---

## 6. HIT-RATE DEFINITIONS (Exact, from `model.py`)

| Metric | Formula | Per-Race Values | Aggregate |
|--------|---------|-----------------|-----------|
| **Winner hit** | `1 if argmin(pred) == argmin(finish) else 0` | {0, 1} | Mean over folds |
| **Podium hit (Recall@3)** | `\|pred_top3 ∩ actual_top3\| / 3` | {0, 1/3, 2/3, 1} | Mean over folds |
| **Rank of actual winner** | `rank(pred)[winner]` | 1..N | Mean, median, histogram |

> **NaN handling:** Folds where `pred` is constant (intercept-only) return NaN for both hit rates and are excluded from the mean.

---

## 7. RESIDUAL DIAGNOSTICS POPULATION

| Diagnostic | Population | N | Notes |
|------------|------------|---|-------|
| Global residuals | All 3,496 finite validation rows | 3,496 | Pooled across folds |
| Per-race MAE | 171 folds (finite-finish only) | 171 | Excludes 2 DNS folds |
| Per-race ρ | 171 folds | 171 | NaN if constant pred/act |
| Per-race winner hit | 171 folds | 171 | NaN if constant pred |
| Per-race podium hit | 171 folds | 171 | NaN if constant pred |
| Residuals by position | 3,496 rows | 3,496 | Grouped by actual finish |
| Residuals by driver | 3,496 rows | ~100 drivers | Varying N per driver |
| Cook's Distance | Per-fold training data | 171 × 20 | Not OOF residuals |

---

## 8. FORECAST DATA

| Field | Value |
|-------|-------|
| Saved forecasts (R20) | 2 modes × 22 cars = 44 rows |
| Model version (R20) | `phase5-ridge-1.0` |
| Forecast timestamps | Early: 2026-11-08T13:47:39Z, Full: 2026-11-08T13:48:57Z |
| Race start (R20) | 2026-11-08T17:00:00Z |
| Grid source (forecast) | `qualifying.q_position` (qualifying order) |
| Official grid (R20) | FIA Doc 51 — 21/22 cars penalized vs qualifying |

---

## 9. DOCUMENTED DISCREPANCIES (Corrected)

| Claim in Old Docs | Actual | Correction |
|-------------------|--------|------------|
| "89 historical races" | 90 (2023–2026) / 193 (2018–2026) | Legacy = 90, Full = 193 |
| "69 validation folds" | 173 (full) / 70 (legacy) | Depends on population |
| "1,816 driver-starts" | 1,838 (legacy) / 3,898 (full) | Legacy = 1,838 |
| "3,496 OOF residuals" | 3,496 (full, finite-finish) | Correct for full |
| "95/173 winner hits" | 94/171 (Ridge full) / 95/171 (XGB full) | Denominator = finite-finish folds |
| "R20 MAE 2.777" | 6.468 (grid=-1) / 2.777 (official grid) | Two different grid sources |
| "173 validation folds scored" | 171 finite-finish + 2 DNS | 173 raw, 171 scored |

---

*End of Dataset Manifest*