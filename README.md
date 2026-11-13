# F1 Race Prediction Analyst

[![Python](https://img.shields.io/badge/Python-3.14+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Phase%207P%20Ready-brightgreen.svg)](#)

A **walk-forward validated** Formula 1 race finishing position predictor using pre-race data only (qualifying, practice, driver/team form). Produces immutable pre-race forecasts with post-race scoring against multiple baselines.

## 🏁 Quick Overview

| Aspect | Details |
|--------|---------|
| **Model** | XGBoost (`phase7-xgboost-1.0`) — walk-forward validated |
| **MAE** | 3.2376 (vs Ridge 3.2784, Δ = −0.0372, *p* < 0.01) |
| **Winner Hit** | 54.91% (95/173) |
| **Podium Hit** | 68.40% (355/519) |
| **Data** | 2018–2026 (193 races, 3,898 driver-starts) |
| **Features** | 12 (full) / 7 (early) — qualifying, practice, form, non-finish rate |
| **Validation** | Chronological expanding window (MIN_TRAIN_RACES=20, 173 folds) |
| **Forecast Modes** | Early (practice-only, 7 features) / Full (post-qualifying, 12 features) |

## 🚀 Quick Start

### Prerequisites
- Python 3.14+
- F1 account (for FastF1 lap data) — create `credentials.env`:
```ini
F1_USERNAME=your_email@example.com
F1_PASSWORD=your_password
```

### Installation
```bash
git clone https://github.com/levordzyn/f1race-prediction-analyst.git
cd f1race-prediction-analyst

python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows PowerShell
# source .venv/bin/activate     # Linux/macOS

pip install -r requirements.txt
```

### Required Dependencies
```text
fastf1==3.9.0
pandas==2.3.3
scikit-learn==1.9.1
numpy==2.4.6
matplotlib==3.11.2
scipy==1.18.1
requests==2.34.2
xgboost==3.4.1
lightgbm==4.7.0
```

> **Note:** Create `requirements.txt` with the above versions, or install individually.

---

## 📖 Usage

### 1. Fetch Historical Data (one-time)
```bash
# Download all 2018–2026 data into SQLite
python -m f1pred.fetch --years 2018 2019 2020 2021 2022 2023 2024 2025 2026
```
This populates `f1.db` with race results, qualifying, sprint, practice, and weather data.

### 2. Pre-Race Forecast (Early Mode — after final practice)
```bash
python -m f1pred.cli --year 2026 --round 21 --fetch --mode early --save
```
**7 features:** driver/team form, non-finish rate, practice position/gap/laps.

### 3. Pre-Race Forecast (Full Mode — after qualifying)
```bash
# Requires official starting grid (after penalties) as CSV
python -m f1pred.cli --year 2026 --round 21 --fetch --mode full --save --grid-file official_grid_2026_r21.csv
```
**12 features:** early + qualifying position/gap/pole + **official grid**.

> **Critical:** The `grid` feature in training = official starting grid. Forecast-time grid **must** come from FIA Doc 51 / formula1.com — qualifying order ≠ official grid when penalties exist.

### 4. Post-Race Scoring
```bash
python scripts/score_forecast.py --year 2026 --round 21 --mode auto --fetch
```
Produces `reports/scorecard_2026_r21_<mode>.md` with MAE, hit rates, baseline comparisons, and small-sample warnings.

---

## 🔬 Model & Validation

### Walk-Forward Protocol
- **Expanding window:** Race *k* predicted using races 1..*k*−1
- **MIN_TRAIN_RACES = 20** → 173 validation folds (2018–2026)
- **StandardScaler** fitted on TRAIN only (no leakage)
- **Shuffled-label sanity check:** MAE collapses to ~5.14 vs 3.24 real → **PASS**

### Baselines (always reported)
| Baseline | Type | Mode |
|----------|------|------|
| Grid | `grid` column | Full only |
| Practice-order | `practice_pos` | Both |
| Recent-form | `driver_form` | Both |
| Pole-sitter | `grid` rank | Hit rates only |
| Best qualifying gap | `q_gap_pct` rank | Hit rates only |
| Best driver form | `driver_form` rank | Hit rates only |

### Feature Groups (pre-registered, immutable)
| Group | Features | Full | Early |
|-------|----------|------|-------|
| Grid/Form | `grid`, `driver_form`, `team_form`, `non_finish_rate` | ✅ | ✅* |
| Practice | `practice_pos`, `practice_gap_pct`, `practice_laps_30`, `no_practice_time` | ✅ | ✅ |
| Qualifying | `q_position`, `q_gap_pct`, `no_q_time`, `on_pole` | ✅ | ❌ |

*Early mode excludes `grid` (unknown at forecast time).

---

## 📊 Phase 7 Results

| Model | MAE | Δ vs Ridge | Winner Hit | Podium Hit | Overfit | Verdict |
|-------|-----|------------|------------|------------|---------|---------|
| Ridge (baseline) | 3.2784 | — | 54.34% | 68.02% | 0.08 | Production |
| **XGBoost** | **3.2376** | **−0.0372** | **54.91%** | **68.40%** | **0.084** | **ACCEPTED** |
| LightGBM C1 | 3.1193 | −0.1545 | 51.45% | 67.82% | 0.501 | REJECTED (overfit) |
| LightGBM C2 | 3.2381 | −0.0365 | 53.18% | 67.82% | 0.077 | NULL (winner hit <55%) |

**XGBoost selected:** Statistically significant MAE improvement (CI excludes 0), competitive hit rates, monotone constraints enforced.

---

## 📁 Project Structure

```
f1race-prediction-analyst/
├── f1pred/                    # Core package
│   ├── cli.py                 # Forecast CLI (early/full modes)
│   ├── db.py                  # SQLite schema & migrations
│   ├── fetch.py               # FastF1 + OpenF1 + Open-Meteo ingestion
│   ├── features.py            # Feature engineering (leakage-free)
│   ├── model.py               # Walk-forward Ridge + model registry
│   ├── forecast.py            # Immutable forecast save/score
│   ├── report.py              # Console + PNG reports
│   ├── xgboost_model.py       # XGBoost walk-forward
│   ├── lightgbm_model.py      # LightGBM walk-forward (C1/C2)
│   ├── practice.py            # OpenF1 practice/SQ
│   ├── openf1.py              # OpenF1 API + lap validity rules
│   ├── clean.py               # Team aliases + validation
│   └── httpcache.py           # Rate-limited HTTP cache
├── scripts/                   # 150+ scripts
│   ├── run_phase*.py          # Phase 1–7 evaluation runners
│   ├── test_*.py              # Regression tests (155 total)
│   ├── verify_*.py            # Data integrity checks
│   └── score_forecast.py      # Post-race scoring
├── reports/                   # Generated outputs
│   ├── phase7*.md             # Phase 7 evaluation reports
│   ├── scorecard_*.md         # Per-race scorecards
│   └── *.png                  # Diagnostic plots
├── .gitignore                 # Excludes secrets, DB, caches
├── credentials.env            # LOCAL ONLY (F1 credentials)
├── official_grid_2026_r*.csv  # Grid templates for R21–R23
└── README.md                  # This file
```

---

## 🔒 Security & Privacy

- **`credentials.env`** is in `.gitignore` — **never committed**
- All forecasts saved with `created_at` timestamp — **no-peeking check** enforced
- Forecasts **never overwritten** (immutable primary key)
- Real database `f1.db` **never modified by tests** (uses temp copies)

---

## 🧪 Testing

```bash
# Run full regression suite (155 tests)
python scripts/test_modes.py
python scripts/test_forecast_flow.py
python scripts/test_upcoming_fetch.py
python scripts/verify_race_status.py
python scripts/verify_identifiers.py
python scripts/verify_sprint.py
python scripts/verify_phase1.py
```

**All 155 tests pass** (mode selection, forecast flow, data integrity, identifier verification).

---

## 📚 Documentation

| File | Description |
|------|-------------|
| `PROJECT_ARCHITECTURE.md` | Full system architecture, data flow, schema |
| `LIMITATIONS.md` | Honest constraints, known issues, change log |
| `MODEL_EVALUATION_REPORT.md` | Complete model comparison with CIs |
| `RESIDUAL_DIAGNOSTICS_REPORT.md` | Phase 7A linear diagnostics (H₀ rejected) |
| `DATASET_MANIFEST.md` | Complete data population reconciliation |
| `METRIC_RECONCILIATION_REPORT.md` | All metric discrepancies resolved |
| `GRID_DATA_QUALITY_REPORT.md` | Grid vs qualifying analysis (71.4% match) |
| `FORECAST_PROVENANCE_AUDIT.md` | Complete forecast lifecycle audit |

---

## 🚧 Phase 7P — Production Validation (In Progress)

3 remaining 2026 races for live validation:

| Round | Event | Date | Status |
|-------|-------|------|--------|
| R21 | Las Vegas GP | 2026-11-21 | ⏳ Pending |
| R22 | Qatar GP | 2026-11-29 | ⏳ Pending |
| R23 | Abu Dhabi GP | 2026-12-06 | ⏳ Pending |

**Workflow per race:**
1. After FP3 → `python -m f1pred.cli --year 2026 --round N --fetch --mode early --save`
2. After Qualifying + Grid File → `python -m f1pred.cli --year 2026 --round N --fetch --mode full --save --grid-file official_grid_2026_rN.csv`
3. Post-Race → `python scripts/score_forecast.py --year 2026 --round N --mode auto --fetch`

---

## ⚠️ Known Limitations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| Grid penalties in training vs forecast | High | Use `--grid-file` for full mode; documented in LIMITATIONS §11 |
| Weather only for 90/193 races | Medium | Future races need forecast; §8 |
| 2018–2022 practice needs FastF1 auth | Low | Credentials in `credentials.env` |
| Pre-reg threshold (55% winner hit) over-specified | Low | Documented in LIMITATIONS §12 |

See `LIMITATIONS.md` for complete, honest accounting.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgments

- **FastF1** — Race/qualifying/sprint data
- **OpenF1** — Practice & sprint qualifying lap data
- **Open-Meteo** — Historical weather archive
- **scikit-learn, XGBoost, LightGBM** — ML libraries

---

*Built for the ITS Surabaya Information Systems portfolio. Not a betting tool — model edge ~5% over grid baseline is far too small and uncertain to act on.*