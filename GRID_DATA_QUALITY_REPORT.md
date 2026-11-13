# GRID DATA QUALITY REPORT — F1 PREDICTION ANALYST

**Date:** 2026-11-10  
**Purpose:** Forensic audit of grid position data quality, semantic consistency, and historical official grid reconstructability.

---

## 1. EXECUTIVE SUMMARY

| Metric | Value | Status |
|--------|-------|--------|
| Qualifying vs Official Grid Match Rate | 71.4% | **Semantic mismatch confirmed** |
| Anomalous grid values (−1, 0, NULL) | 69 rows | **Data quality issues** |
| Qualifying ties (same position, same race) | 7 cases | **Source data quirks** |
| Sprint grid availability | 99.6% | Good |
| 2026 R20 São Paulo grid | All −1 (FastF1 failure) | **Critical gap** |

**Root Cause:** The model's `grid` feature trains on `results.grid` (FastF1 `GridPosition` = official starting grid after penalties) but forecasts use `qualifying.q_position` (qualifying order) unless `--grid-file` is provided. This is a documented semantic mismatch.

---

## 2. QUALIFYING VS OFFICIAL GRID MATCH ANALYSIS

### 2.1 Overall Match Rate

| Population | Total Comparisons | Matches | Mismatches | Match Rate |
|------------|-------------------|---------|------------|------------|
| **Full (2018–2026)** | 3,886 | 2,775 | 1,111 | **71.4%** |
| 2018 | 420 | 309 | 111 | 73.6% |
| 2019 | 418 | 257 | 161 | **61.5%** |
| 2020 | 340 | 279 | 61 | 82.1% |
| 2021 | 438 | 279 | 159 | 63.7% |
| 2022 | 439 | 274 | 165 | 62.4% |
| 2023 | 440 | 330 | 110 | 75.0% |
| 2024 | 479 | 371 | 108 | 77.5% |
| 2025 | 478 | 382 | 96 | 79.9% |
| 2026 | 434 | 294 | 140 | 67.7% |

**Interpretation:** ~29% of drivers start from a different grid position than they qualified. This is due to:
- Grid penalties (gearbox, engine, parc fermé, etc.)
- Pit-lane starts
- Driver substitutions
- Disqualifications from qualifying

### 2.2 Mismatch Direction

| Mismatch Type | Count | Typical Cause |
|---------------|-------|---------------|
| Qualified ahead, started behind | Majority | Grid penalties (gearbox −5, engine −10, etc.) |
| Qualified behind, started ahead | Minority | Other drivers penalized, promoting this driver |
| Pit-lane start | ~5 cases/year | Qualified but started from pits |

---

## 3. ANOMALOUS GRID VALUES

### 3.1 Distribution

| Grid Value | Count | Races Affected | Explanation |
|------------|-------|----------------|-------------|
| **−1.0** | **22** | 2026 R20 (São Paulo) only | FastF1 returned −1 for all 22 cars |
| **0.0** | **44** | Multiple (pre-2023?) | FastF1 reports 0 for pit-lane/no grid |
| **NULL** | **3** | Scattered | Missing data |

### 3.2 Grid = 0 Analysis

| Year | Count | Notes |
|------|-------|-------|
| 2018 | 12 | Likely pit-lane starts |
| 2019 | 8 | |
| 2020 | 4 | |
| 2021 | 6 | |
| 2022 | 8 | |
| 2023+ | 6 | Rare in recent years |

**Handling in features.py:** Values ≤ 0 are replaced with `field_n + 1` (back-of-grid), which is correct for pit-lane starts but loses the distinction between "qualified P5, started from pits" vs "qualified P20, started P20".

---

## 4. 2026 R20 SÃO PAULO — CRITICAL CASE STUDY

### 4.1 FastF1 Failure

| Metric | Value |
|--------|-------|
| Race | 2026 R20 São Paulo Grand Prix |
| FastF1 `GridPosition` | **−1 for all 22 cars** |
| FastF1 `Position` (finish) | Valid (1–22) |
| Qualifying positions | Valid (1–22) |
| Official grid (FIA Doc 51) | **Available, 21/22 penalized** |

### 4.2 Penalty Breakdown (R20)

| Penalty Type | Drivers | Positions Lost |
|--------------|---------|----------------|
| Engine/PU (−30) | VER, PER, HAM | −30, −30, −75 |
| Gearbox (−5) | RUS | −5 |
| Parc fermé / other | LEC (−10), others | Various |
| **Total penalized** | **21/22** | **Only NOR unchanged** |

### 4.3 Impact on Model

| Scenario | Grid Feature Value | MAE | Winner Hit |
|----------|-------------------|-----|------------|
| FastF1 grid (−1 → 23) | All 22 cars = 23 | 6.468 | 0% |
| Qualifying order (fallback) | 1–22 | ~4.2 | ~0% |
| **Official grid (FIA Doc 51)** | **True positions** | **2.777** | **100% (NOR)** |

**Lesson:** The model **requires official grid** for accurate full-mode forecasts on penalty-heavy weekends.

---

## 5. QUALIFYING TIES

### 5.1 Tied Qualifying Positions

| Year | Round | Event | Position | Drivers | Count |
|------|-------|-------|----------|---------|-------|
| 2023 | 10 | Austria | 15 | PER, BOT | 2 |
| 2024 | 8 | Japan | 14 | Two drivers | 2 |
| 2024 | 8 | Japan | 15 | Two drivers | 2 |
| 2024 | 15 | Azerbaijan | 10 | Two drivers | 2 |
| 2024 | 17 | Singapore | 15 | Two drivers | 2 |
| 2025 | 7 | Monaco | 16 | Two drivers | 2 |
| 2026 | 19 | USA | 8 | Two drivers | 2 |

**Handling:** FastF1 reports tied positions. The `q_position` column preserves these ties. The model's monotone constraints assume ordinal relationship, which ties violate slightly.

---

## 6. HISTORICAL OFFICIAL GRID RECONSTRUCTABILITY

### 6.1 Availability by Era

| Era | FastF1 GridPosition | Official Grid Recoverable? | Recommended Source |
|-----|---------------------|----------------------------|-------------------|
| 2018–2022 | Partial (0, −1, NULL common) | **No** | Not reliably recoverable |
| 2023–2025 | Good (mostly valid) | **Partially** | FIA PDFs / formula1.com (manual) |
| 2026 R1–R19 | Good | **Partially** | FIA PDFs / formula1.com (manual) |
| 2026 R20 | **Failed (−1 all)** | **Yes (FIA Doc 51)** | Automated parsing needed |
| 2026 R21–R23 | Future | Future | Automated parsing needed |

### 6.2 Reconstructed Grids (Verified)

| Race | Source | Verified? | Notes |
|------|--------|-----------|-------|
| 2026 R20 | FIA Doc 51 / formula1.com | ✅ | 21/22 penalties confirmed |
| 2023 R2 | FIA Doc / media | ⚠️ | Partial (LEC −10 confirmed) |
| 2023 R19 | FIA Doc / media | ⚠️ | Partial (VER −5 confirmed) |
| 2024 R1 | FIA Doc / media | ⚠️ | Partial (HAM −3 confirmed) |

> **Status:** No systematic historical official grid database exists. Reconstruction requires manual FIA PDF parsing per race.

---

## 7. IMPACT ON MODEL TRAINING & FORECASTING

### 7.1 Training-Time Grid Feature

| Aspect | Current Implementation | Issue |
|--------|----------------------|-------|
| Source | `results.grid` (FastF1 GridPosition) | Contains 0, −1, NULL anomalies |
| Penalty-aware | ✅ Yes (where FastF1 works) | 2026 R20 is all −1 |
| Pit-lane handling | Filled with `field_n + 1` | Loses "qualified well, started from pits" signal |
| Ties | Not present in GridPosition | FastF1 resolves ties |

### 7.2 Forecast-Time Grid Feature

| Mode | Grid Source | Penalty-Aware | Quality |
|------|-------------|---------------|---------|
| Early | `qualifying.q_position` | ❌ No | Qualifying order only |
| Full (no --grid-file) | `qualifying.q_position` | ❌ No | Qualifying order only |
| Full (with --grid-file) | `official_grid.csv` | ✅ Yes | FIA Doc 51 / formula1.com |

### 7.3 Semantic Mismatch Quantified

| Scenario | Grid Feature Value | Represents |
|----------|-------------------|------------|
| Training (historical) | Official starting grid | **Post-penalty reality** |
| Forecast (early) | Qualifying order | **Pre-penalty assumption** |
| Forecast (full, no grid file) | Qualifying order | **Pre-penalty assumption** |
| Forecast (full, with grid file) | Official grid | **Post-penalty reality** |

**Impact:** The model learns "official grid → finish" but forecasts "qualifying order → finish" unless `--grid-file` is provided.

---

## 8. RECOMMENDATIONS

### 8.1 Immediate (Phase 7P — 3 Remaining Races)

1. **Mandate `--grid-file` for all full-mode forecasts** — Never forecast full mode without official grid
2. **Create grid file template** — `official_grid_2026_r{21,22,23}.csv` with `driver,grid_pos` columns
3. **Automate FIA Doc 51 parsing** — Python script to extract grid from PDF
4. **Score against official grid** — Always generate addendum with official grid baseline

### 8.2 Data Schema Enhancements

```sql
-- Add to results table (or new table)
ALTER TABLE results ADD COLUMN grid_source TEXT;  -- 'fastf1', 'fia_pdf', 'manual', 'unknown'
ALTER TABLE results ADD COLUMN grid_confirmed BOOLEAN;  -- True if verified against FIA doc
ALTER TABLE results ADD COLUMN grid_penalty_positions INTEGER;  -- Positions lost to penalties
```

### 8.3 Feature Engineering Improvements

1. **Separate `q_position` and `grid` cleanly** — Already done, but ensure semantic clarity in docs
2. **Add `grid_penalty` feature** — Positions lost: `q_position - grid` (negative = penalty)
3. **Add `pit_lane_start` flag** — Binary: 1 if grid = field_n + 1
4. **Preserve original grid** — Store raw FastF1 value alongside cleaned value

### 8.4 Historical Grid Reconstruction Project

| Priority | Race | Effort | Value |
|----------|------|--------|-------|
| High | 2023–2025 penalty-heavy races | Medium | Fix training mismatch |
| Medium | 2018–2022 | High (FastF1 unreliable) | Limited by source data |
| Low | Pre-2018 | N/A | Not in dataset |

---

## 8. GRID DATA QUALITY SCORECARD

| Dimension | Score | Details |
|-----------|-------|---------|
| **Completeness** | 98% | 69/3898 rows anomalous |
| **Accuracy (vs official)** | 71.4% | 1111/3886 mismatches |
| **Consistency** | 99.8% | 7 qualifying ties only |
| **Timeliness** | Good | FastF1 updated post-race |
| **Provenance** | Partial | FastF1 only; no FIA doc linkage |
| **Usability for ML** | Medium | Semantic mismatch at forecast time |

---

*End of Grid Data Quality Report*