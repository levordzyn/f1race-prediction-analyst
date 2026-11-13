# Phase 7P: Production Validation — 2026 Season Tail (3 Races)

**Date:** 2026-11-10  
**Model:** XGBoost (phase7-xgboost-1.0)  
**Pre-registration:** `reports/phase7d_final.md` (XGBoost selected as final model)  
**Status:** Awaiting race weekends for R21, R22, R23

---

## Timeline

| Round | Event | Date | Format | Status |
|-------|-------|------|--------|--------|
| 21 | Las Vegas Grand Prix | 2026-11-21 | conventional | Pending |
| 22 | Qatar Grand Prix | 2026-11-29 | conventional | Pending |
| 23 | Abu Dhabi Grand Prix | 2026-12-06 | conventional | Pending |

---

## Model

**XGBoost (phase7-xgboost-1.0)** — selected in Phase 7D head-to-head

| Metric | Value |
|--------|-------|
| MAE (walk-forward) | 3.2376 |
| ΔMAE vs Ridge (delta of means) | -0.0409 |
| ΔMAE vs Ridge (mean of per-race deltas) | -0.0372 |
| Spearman ρ | 0.6715 |
| Winner hit | 95/173 = 54.91% |
| Podium hit (recall@3) | 355/519 = 68.40% |
| Overfit gap (train-test) | 0.0841 |
| Shuffled-label gap | 1.53 ✅ PASS |

---

## Per-Race Workflow

### 1. After Final Practice (Early Mode)

```powershell
python -m f1pred.cli --year 2026 --round <N> --fetch
python -m f1pred.cli --year 2026 --round <N> --mode early --save
```

- Uses 7 practice-only features
- No grid required
- Saves forecast with `created_at` before qualifying

### 2. After Qualifying + Grid File Ready (Full Mode)

```powershell
python -m f1pred.cli --year 2026 --round <N> --fetch
python -m f1pred.cli --year 2026 --round <N> --mode full --save --grid-file official_grid_2026_r<N>.csv
```

- Uses all 12 features (adds grid, q_position, q_gap_pct, no_q_time, on_pole)
- **Requires** `--grid-file` with official starting grid (after penalties)
- Grid file format: CSV with header `driver,grid_pos` (22 rows)

### 3. After Race (Scoring)

```powershell
python scripts\score_forecast.py --year 2026 --round <N> --mode auto --fetch
```

- Loads forecast, checks `created_at < race_start_utc` (no-peeking)
- Scores MAE, Spearman ρ, winner/podium hit rates vs baselines
- Writes scorecard to `reports/scorecard_2026_r<N>_<mode>.md`

---

## Grid File Sourcing

| Source | URL |
|--------|-----|
| FIA Doc 51 "Provisional Starting Grid" | https://www.fia.com/documents/... |
| formula1.com official grid | https://www.formula1.com/en/racing/... |

**Format:** CSV with header `driver,grid_pos` (22 rows, uppercase driver codes matching FastF1 abbreviations)

**Verification:** Before save, CLI compares `--grid-file` to qualifying order and warns on penalties.

---

## Timing Constraints

| Step | Deadline | Notes |
|------|----------|-------|
| Early forecast | After final practice, before qualifying start | Early mode only |
| Full forecast | After qualifying ends, grid file ready, before race start | Full mode requires `--grid-file` |
| Scoring | After race results published | Run `--fetch` to get results |

**Critical:** If a save window is missed, do NOT backdate `created_at`. Document in scorecard.

---

## Grid File Templates

```powershell
# R21 Las Vegas (Nov 21)
Set-Content official_grid_2026_r21.csv "driver,grid_pos"

# R22 Qatar (Nov 29)
Set-Content official_grid_2026_r22.csv "driver,grid_pos"

# R23 Abu Dhabi (Dec 6)
Set-Content official_grid_2026_r23.csv "driver,grid_pos"
```

**Verify:** `.gitignore` does NOT exclude `official_grid_*.csv`.

---

## Post-Race Report Template

Each race generates `reports/scorecard_2026_r<N>_<mode>.md` with:

1. Header: forecast time, race start, no-peeking verdict, model version, alpha, training races, features, note
2. Model vs baselines table: MAE, Spearman, winner%, podium% (n/a with explanation)
3. Improvement = model MAE − best baseline MAE (signed, % better/worse)
4. Predicted vs actual winner
5. Small-sample warning (mandatory)

**Addendum format** (post-race, never overwrites scorecards):
- `scorecard_2026_r<N>_addendum.md`: Rebuilds grid baseline from `grid_pred`
- `scorecard_2026_r<N>_addendum2.md`: Adds official-grid baseline from FIA Doc 51

---

## Phase 7P Summary

| Round | Event | Early Forecast | Full Forecast | Grid File | Scorecard |
|-------|-------|----------------|---------------|-----------|-----------|
| R21 | Las Vegas GP | ☐ | ☐ | `official_grid_2026_r21.csv` | `scorecard_2026_r21_*.md` |
| R22 | Qatar GP | ☐ | ☐ | `official_grid_2026_r22.csv` | `scorecard_2026_r22_*.md` |
| R23 | Abu Dhabi GP | ☐ | ☐ | `official_grid_2026_r23.csv` | `scorecard_2026_r23_*.md` |

---

*Pre-registration: `reports/phase7d_final.md` (XGBoost selected as final model)*  
*Generated: 2026-11-10*  
*Next action: Await R21 Las Vegas practice sessions to begin early-mode forecast.*