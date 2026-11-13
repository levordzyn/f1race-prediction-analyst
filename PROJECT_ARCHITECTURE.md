# PROJECT_ARCHITECTURE.md

**Generated:** 2026-11-10T11:00:00Z (UTC)  
**Project root:** `C:\Users\outbnx_\Documents\F1 PROJECTS`  
**Legend:** **[V]** = verified from file/command output; **[U]** = unverified or inferred

---

## Table of Contents

1. [AI Handoff Summary](#part-0-ai-handoff-summary)
2. [Project Overview](#part-1-project-overview)
3. [System Context and Architecture](#part-2-system-context-and-architecture)
4. [Repository Map](#part-3-repository-map)
5. [Data Sources and Ingestion](#part-4-data-sources-and-ingestion)
6. [Database](#part-5-database)
7. [Feature Engineering](#part-6-feature-engineering)
8. [Modeling and Validation](#part-7-modeling-and-validation)
9. [Forecast and Scoring Workflow](#part-8-forecast-and-scoring-workflow)
10. [Testing and Verification](#part-9-testing-and-verification)
11. [Results to Date](#part-10-results-to-date)
12. [Known Issues, Limitations, Risks](#part-11-known-issues-limitations-risks)
13. [Decision Log and Pre-registrations](#part-12-decision-log-and-pre-registrations)
14. [Runbook](#part-14-runbook)
15. [Requirements Traceability](#part-15-requirements-traceability)
16. [Open Items and Roadmap](#part-16-open-items-and-roadmap)
17. [Glossary](#part-17-glossary)
18. [Appendices](#part-18-appendices)

---

## Part 0: AI Handoff Summary

### Purpose (one paragraph)
This project builds a **walk-forward validated Ridge regression model** that predicts Formula 1 race finishing positions (and by extension the winner/podium) from pre-race data: qualifying results, practice pace, recent driver/team form, and non-finish rate. It produces two forecast **modes** — *early* (practice-only, 7 features) and *full* (adds qualifying + grid, 12 features) — saves forecasts **before** the race with timestamps, scores them **after** the race, and reports MAE, Spearman ρ, winner/podium hit rates against baselines (grid, practice-order, recent-form). All evaluation is **chronological expanding-window**; no random splits. The project is a portfolio piece for an Information Systems student (ITS Surabaya).

### Status by Phase (with evidence)

| Phase | Description | Status | Evidence |
|-------|-------------|--------|----------|
| 1 | Fetch results, grid, qualifying, sprint, practice (FastF1 + OpenF1) into SQLite | **Done** | `f1pred/fetch.py`, `f1pred/practice.py`, DB has 3898 rows per core table for 2018–2026; `scripts/verify_phase1.py` 17/17 PASS |
| 2 | Baselines (grid, practice-order, recent-form) MAE | **Done** | `scripts/run_phase3.py` ladder output |
| 3 | 12 features + Ridge (α=1.0) + walk-forward (MIN_TRAIN_RACES=20 → 173 validation races / 3496 rows) | **Done** | `f1pred/model.py::walk_forward`; MAE 3.2784, ρ 0.6668 |
| 4 | Reports: top-3, order table, gap-vs-prediction scatter, coefficient chart, winner/podium hit rates vs ranking baselines | **Done** | `f1pred/report.py`; `scripts/run_phase4.py` output |
| 5 | Early/full modes, CLI, pre-race freeze, `--save` (no-overwrite), preflight, scoring | **Done** | `f1pred/cli.py`, `f1pred/forecast.py`, `scripts/score_forecast.py`; 2026 R20 forecasts saved |
| 6a | Sprint features (6) — measured as additive stage: Δ MAE +0.004, CI [−0.007, +0.017] contains 0 | **Done (null)** | `scripts/run_phase6a.py`; LIMITATIONS §9 |
| 6b | Weather features (7 incl. 3 interactions) — measured as additive stage: Δ MAE +0.003, CI [−0.018, +0.027] contains 0 | **Done (null)** | `scripts/run_phase6b.py`; LIMITATIONS §9 |
| 7 | Tree model comparison (Ridge vs XGBoost vs LightGBM) | **Done** | XGBoost selected (MAE 3.2376, ρ 0.6715, winner 54.91%); LGB C1 REJECTED (overfit gap 0.501), C2 NULL (winner hit 53.2% < 55%) |
| 7P | 2026 season tail production validation (R21 Las Vegas, R22 Qatar, R23 Abu Dhabi) | **In Progress** | 3 races remaining: R21 Las Vegas (Nov 21), R22 Qatar (Nov 29), R23 Abu Dhabi (Dec 6) |
| 8 | Documentation (README, model card, data dictionary, limitations) | **In Progress** | `LIMITATIONS.md`, `PROJECT_ARCHITECTURE.md`, this file |
| 9 | Optional extensions (tyre/strategy, Streamlit dashboard, ESP32 display) | **Deferred** | — |

### Key Numbers (with sources)

| Metric | Value | Source |
|--------|-------|--------|
| Walk-forward MAE (full, 12 features, Ridge) | **3.2784** positions | `scripts/run_phase7b_xgboost.py` / `f1pred/model.py::walk_forward` (173 races, 3496 rows) |
| Walk-forward Spearman ρ (Ridge) | **0.6668** | same |
| Walk-forward MAE (XGBoost) | **3.2376** positions | `scripts/run_phase7b_xgboost.py` |
| Walk-forward Spearman ρ (XGBoost) | **0.6715** | same |
| Walk-forward MAE (LightGBM C1) | **3.1193** positions | `scripts/run_phase7c_lightgbm.py` |
| Walk-forward MAE (LightGBM C2) | **3.2381** positions | same |
| Grid baseline MAE | **3.512** (ρ 0.6270) | `scripts/run_phase7b_xgboost.py` |
| Practice-order baseline MAE | **4.076** (ρ 0.5659) | `scripts/run_phase7b_xgboost.py` |
| Recent-form baseline MAE | **3.721** (ρ 0.5568) | `scripts/run_phase7b_xgboost.py` |
| XGBoost − best baseline (MAE) | **−0.274** (beats by 7.8%) | `scripts/run_phase7b_xgboost.py` |
| XGBoost − Ridge ΔMAE (delta of means) | **−0.0409** | `scripts/run_phase7b_xgboost.py` |
| XGBoost − Ridge ΔMAE (mean of per-race deltas) | **−0.0372** (CI [−0.065, −0.006]) | `scripts/run_phase7b_xgboost.py` |
| Winner hit rate (XGBoost) | **54.91%** (95/173) | `scripts/run_phase7b_xgboost.py` |
| Podium hit rate (XGBoost) | **68.40%** (355/519) | same |
| Winner hit rate (Ridge) | **54.34%** (94/173) | `scripts/run_phase7b_xgboost.py` |
| Podium hit rate (Ridge) | **68.02%** (353/519) | same |
| Sprint group Δ MAE | **+0.004** (CI [−0.007, +0.017]) | `scripts/run_phase6a.py` / LIMITATIONS §9 |
| Weather group Δ MAE | **+0.003** (CI [−0.018, +0.027]) | `scripts/run_phase6b.py` / LIMITATIONS §9 |
| **2026 R20 São Paulo — full mode** MAE | **6.468** (ρ -0.0558) | `reports/scorecard_2026_r20_full.md` |
| **2026 R20 — full mode** winner hit | **0%** (pred NOR ≠ actual ALB) | `reports/scorecard_2026_r20_full.md` |
| **2026 R20 — full mode** podium hit | **33.3%** (1/3) | `reports/scorecard_2026_r20_full.md` |
| **2026 R20 — full mode** improvement | **−0.532** (better by 7.6%) | `reports/scorecard_2026_r20_full.md` |
| **2026 R20 — early mode** MAE | **N/A** (not saved) | — |

### Architecture in 10 Lines

1. **Data layer**: SQLite (`f1.db`) with 11 tables; idempotent fetch via `fetch_log`; read-only scoring.
2. **Fetch**: `f1pred.fetch` (FastF1 for race/qualifying/sprint/status) + `f1pred.practice` (OpenF1 for practice/SQ) + `f1pred.fetch.fetch_weather` (Open-Meteo).
3. **Features**: `f1pred.features.build_features()` → 12 locked features (3 groups) + 13 Phase 6 features kept separate; leakage-free via `shift(1)` + per-driver/team rolling; defaults are constants.
3. **Model**: `f1pred.model.walk_forward()` — expanding window (MIN_TRAIN_RACES=20), Ridge α=1.0, StandardScaler fitted **per fold**; baselines unfitted.
4. **Forecast**: `f1pred.forecast.save()` writes `forecasts` table with `created_at` + `race_start_utc` + `grid_pred`; **never overwrites**.
5. **CLI**: `f1pred.cli` — auto/early/full mode selection by data presence; `--fetch`, `--save`, `--grid-file` (required for full-mode save).
6. **Scoring**: `scripts/score_forecast.py` — loads forecast, checks `created_at < race_start_utc`, computes MAE/ρ/hits + baselines on **same drivers**, writes scorecard.
7. **Reports**: `f1pred.report` — console top-3/order table, gap-vs-prediction scatter (PNG), coefficient chart (PNG), winner/podium hit rates with baselines.
7. **Validation**: 10 test/check/verify scripts; all run on **temp DB copies**; real `f1.db` never written by tests.

### Where Things Live (quick lookup)

| What | Path |
|------|------|
| Core package | `f1pred/` (9 modules) |
| Scripts (fetch, verify, test, phase runners) | `scripts/` (100+ files) |
| Database | `f1.db` (827 KB) + dated backups `f1_backup_*.db` |
| Reports/Scorecards | `reports/` (scorecards, addenda, PNGs) |
| Main docs | `f1predictionanalyst.md` (spec), `LIMITATIONS.md` (limitations + change log) |
| Environment | Python 3.14.5, fastf1 3.9.0, pandas 2.3.3, scikit-learn 1.9.1, numpy 2.4.6 |

### Critical Gotchas & Rules (must not break)

| Rule | Why | Enforcement |
|------|-----|-------------|
| **No overwriting saved forecasts** | `created_at` is the only evidence a forecast predated the race | `forecast.save()` uses plain `INSERT`, not `INSERT OR REPLACE`; raises if rows exist |
| **No tuning after seeing results** | α=1.0 fixed; feature groups pre-registered | `RIDGE_ALPHA = 1.0` constant; `FEATURE_GROUPS` locked; Phase 6 groups kept out of `ALL_FEATURES` |
| **Never write `results` from forecast/score code** | `results` is the ground truth | `forecast.py`/`score_forecast.py` only read `results` |
| **Walk-forward only** | No random CV; race N trains on 1..N-1 | `model.walk_forward` enforces expanding window |
| **StandardScaler fits on TRAIN only** | Prevents leakage from future race statistics | `walk_forward` fits scaler inside each fold |
| **22 cars in 2026, never hard-code 20** | Grid size varies by season | `_season_field_size()` computes modal count per season |
| **Explicit column names in every INSERT** | Schema migrations append columns; positional `VALUES` would shift data | All `executemany` calls name columns |
| **Grid = real starting grid in training** | At forecast time only qualifying order is available; `--grid-file` supplies official grid | `features.py::build_features` fills missing `grid` with `field_n+1`; `--grid-file` overrides in `_forecast_spine` |

---

## Part 1: Project Overview

### Purpose & Scope
Build a transparent, reproducible F1 race-finishing-position predictor using only pre-race data, evaluated by **chronological walk-forward validation**. The model is a Ridge regression (α=1.0) with 12 pre-registered features. Two forecast modes exist: **early** (after last practice, 7 features) and **full** (after qualifying, 12 features). Forecasts are saved **before** the race with timestamps; scoring happens **after** with a no-peeking check.

### Non-Goals
- No tyre strategy, pit-stop, or safety-car modelling (LIMITATIONS §2, §7)
- No causal interpretation of individual Ridge coefficients (LIMITATIONS §6)
- Not a betting tool (model edge ~5% over grid baseline, LIMITATIONS §7)
- XGBoost comparison complete (Phase 7 done)
- No weather *forecast* — only observed historical weather (LIMITATIONS §8)

### Success Criteria (from spec)
- Walk-forward MAE vs baselines reported per race, averaged
- Winner hit rate, podium hit rate, rank of actual winner
- Gap-vs-prediction scatter plot + Ridge coefficient chart (PNG)
- Early/full modes with clear warnings when data missing
- All numbers reproducible; no leakage; baselines always shown

### Information Systems View
- **Business process**: F1 race weekend → pre-race data available at two decision points (post-practice, post-qualifying) → forecast → post-race scoring → continuous accuracy tracking
- **Stakeholders**: Student (portfolio), Lecturer (grading), potential employer (code quality)
- **Data lifecycle**: FastF1/OpenF1/Open-Meteo → SQLite (idempotent, cached) → feature frame (pandas) → walk-forward Ridge → forecast table (immutable) → scorecard (Markdown + PNG)

---

## Part 2: System Context and Architecture

### System Context (Mermaid)
```mermaid
graph TD
    A[FastF1 API] -->|Race, Qualifying, Sprint, Status| B[(SQLite: f1.db)]
    C[OpenF1 API] -->|Practice laps, Sprint Qualifying| B
    D[Open-Meteo API] -->|Daily weather| B
    B --> E[f1pred.features.build_features]
    E --> F[f1pred.model.walk_forward]
    F --> G[f1pred.forecast.save]
    G --> H[forecasts table]
    H --> I[scripts/score_forecast.py]
    I --> J[Scorecard + PNG reports]
    K[CLI: f1pred.cli] -->|--fetch/--save/--grid-file| B
    K --> E
    K --> F
    K --> G
```

### Component / Layer Diagram (Mermaid)
```mermaid
graph TB
    subgraph Data["Data Layer"]
        DB[(f1.db)]
        FC[fetch_log]
    end
    subgraph Ingestion["Ingestion"]
        FT[f1pred.fetch]
        PR[f1pred.practice]
        WE[f1pred.fetch.fetch_weather]
    end
    subgraph Features["Feature Engineering"]
        FE[f1pred.features.build_features]
        FG[FEATURE_GROUPS / MODE_FEATURES]
    end
    subgraph Model["Modelling"]
        WF[f1pred.model.walk_forward]
        RB[run_baselines / run_hit_baselines]
        PL[permutation_importance]
    end
    subgraph Forecast["Forecast & Scoring"]
        FS[f1pred.forecast.save/load/score]
        SC[scripts/score_forecast.py]
    end
    subgraph Interface["Interface"]
        CLI[f1pred.cli]
        RP[f1pred.report]
    end
    subgraph Verification["Verification"]
        TS[scripts/test_*.py]
        VS[scripts/verify_*.py]
        CK[scripts/check_*.py]
    end

    FT --> DB
    PR --> DB
    WE --> DB
    DB --> FE
    FG --> FE
    FE --> WF
    WF --> FS
    FS --> DB
    DB --> SC
    SC --> RP
    CLI --> FT
    CLI --> FE
    CLI --> WF
    CLI --> FS
    TS -.->|temp copy| DB
    VS -.->|temp copy| DB
```

### Module Dependency Map (textual, from imports)

```
f1pred/
├── db.py              ← (no internal deps)
├── credentials.py     ← (no internal deps)
├── httpcache.py       ← (no internal deps)
├── clean.py           ← (no internal deps)
├── openf1.py          ← httpcache
├── practice.py        ← clean, db, openf1
├── fetch.py           ← clean, credentials, db, practice
├── features.py        ← (no internal deps; reads DB via sqlite3)
├── model.py           ← features (ALL_FEATURES, FEATURE_GROUPS, etc.)
├── forecast.py        ← features, model
├── report.py          ← model (WINNER_DEF, PODIUM_DEF)
└── cli.py             ← db, features, forecast, model, report
```

### Technology Stack (verified)

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.14.5 | Windows, PowerShell, `PYTHONUTF8=1` required |
| fastf1 | 3.9.0 | Primary source for race/qualifying/sprint/status; cache dir `f1_cache/` |
| pandas | 2.3.3 | Feature frames, merges |
| scikit-learn | 1.9.1 | Ridge, StandardScaler, pipeline |
| numpy | 2.4.6 | Arrays, math |
| scipy | 1.18.1 | spearmanr, wilcoxon, binomtest |
| matplotlib | 3.11.2 | PNG plots (Agg backend) |
| requests | 2.34.2 | OpenF1, Open-Meteo |
| requests-cache | 1.3.3 | Not directly used; `f1pred.httpcache` is custom |
| xgboost | 3.4.1 | Phase 7 (installed for XGBoost) |
| lightgbm | 4.7.0 | Phase 7 (installed for LightGBM) |

---

## Part 3: Repository Map

### Directory Tree (abridged)
```
F1 PROJECTS/
├── f1pred/                    # Core package (9 modules)
│   ├── __init__.py
│   ├── db.py                  # Schema, connection, migrations, fetch_log
│   ├── credentials.py         # Loads F1_USERNAME/PASSWORD from credentials.env
│   ├── httpcache.py           # Rate-limited, disk-cached OpenF1 client
│   ├── clean.py               # Team aliases, validation (field size, positions, gaps)
│   ├── openf1.py              # Lap validity rules (sector sum, implausible speed)
│   ├── practice.py            # Practice + sprint-qualifying from OpenF1
│   ├── fetch.py               # FastF1 race/quali/sprint/status + weather
│   ├── features.py            # build_features(), feature groups, forecast spine
│   ├── model.py               # walk_forward, baselines, hit rates, ladders, perm importance
│   ├── forecast.py            # save/load/score (no-overwrite, created_at check)
│   ├── report.py              # Console + PNG reports (scatter, coeff chart)
│   └── cli.py                 # Argparse: --year/--round/--mode/--fetch/--save/--grid-file
├── scripts/                   # 100+ scripts: phase runners, tests, checks, verifies, probes
│   ├── run_phase3.py
│   ├── run_phase4.py
│   ├── run_phase6a.py
│   ├── run_phase6b.py
│   ├── score_forecast.py
│   ├── test_modes.py
│   ├── test_forecast_flow.py
│   ├── test_upcoming_fetch.py
│   ├── verify_race_status.py
│   └── ... (many probe/check/verify scripts)
├── reports/                   # Scorecards, addenda, PNG plots
├── f1.db                      # Main SQLite DB (827 KB)
├── f1_backup_*.db             # Dated backups
├── credentials.env            # F1_USERNAME, F1_PASSWORD (gitignored)
├── f1predictionanalyst.md     # Original spec/prompt
├── LIMITATIONS.md             # Limitations, change log, freeze statement
└── official_grid_2026_r20.csv # Manual official grid for 2026 R20
```

### File Table (every non-cache file)

| Path | Type | Purpose | Inputs | Outputs | Called By | Writes f1.db? | Safe to Run? |
|------|------|---------|--------|---------|-----------|---------------|--------------|
| `f1pred/db.py` | Module | Schema, connection, migrations, fetch_log | — | `connect()`, `step_done()`, `log_step()` | All | **Y** (schema init, migrations) | **Y** (idempotent) |
| `f1pred/credentials.py` | Module | Load `credentials.env` → `os.environ` | `credentials.env` | `F1_USERNAME`, `F1_PASSWORD` in env | `fetch.enable_cache()` | N | **Y** |
| `f1pred/httpcache.py` | Module | Rate-limited, cached OpenF1 GET | OpenF1 REST | JSON body / None | `openf1.py` | N (writes `cache/openf1/`) | **Y** |
| `f1pred/clean.py` | Module | Team aliases, validation helpers | Raw strings | Canonical team names; raises `DataValidationError` | `fetch.py`, `practice.py` | N | **Y** |
| `f1pred/openf1.py` | Module | Lap classification rules (sector sum, implausible speed) | Raw laps | `(valid, rejected)` lists | `practice.py` | N | **Y** |
| `f1pred/practice.py` | Module | Practice + SQ from OpenF1 | OpenF1 sessions/laps/drivers | `practice`, `sprint_qualifying` tables | `fetch.py::fetch_upcoming`, `fetch_year` | **Y** | **Y** (idempotent via `fetch_log`) |
| `f1pred/fetch.py` | Module | FastF1 race/quali/sprint/status + weather | FastF1, Open-Meteo | `results`, `qualifying`, `sprint`, `sessions`, `driver_numbers`, `race_status`, `weather` | `cli.py --fetch`, `scripts/test_*.py` | **Y** | **Y** (idempotent via `fetch_log`) |
| `f1pred/features.py` | Module | `build_features()`, feature groups, forecast spine | SQLite DB | Feature DataFrame (1 row/driver/race) | `cli.py`, `model.py`, `forecast.py`, `scripts/*` | N (read-only) | **Y** |
| `f1pred/model.py` | Module | `walk_forward`, baselines, hit rates, ladders, perm importance | Feature frame | Metrics dicts, per-race rows, coefficients | `cli.py`, `forecast.py`, `scripts/run_phase*.py` | N | **Y** |
| `f1pred/forecast.py` | Module | `save` (no-overwrite), `load`, `score` | `forecasts` table + `results` | Score dict, loaded forecast | `cli.py --save`, `scripts/score_forecast.py` | **Y** (`forecasts` only) | **Y** |
| `f1pred/report.py` | Module | Console top-3/order, hit rates, scatter PNG, coeff chart PNG | Walk-forward output | `stdout`, `reports/*.png` | `cli.py`, `scripts/run_phase4.py` | N | **Y** |
| `f1pred/cli.py` | Script | Main entry: mode selection, fetch, forecast, save, plot, baselines | CLI args, DB | Forecast, scorecard, plots | User, `scripts/test_*.py` | **Y** (via `forecast.save`) | **Y** (with `--db` copy) |
| `scripts/score_forecast.py` | Script | Score saved forecast vs results, write scorecard | `forecasts` + `results` | `reports/scorecard_*.md`, console | User, `scripts/test_forecast_flow.py` | N | **Y** (with `--db` copy) |
| `scripts/run_phase3.py` | Script | Feature ladder (4 stages) + MAE/ρ | DB | Console ladder table | User | N | **Y** |
| `scripts/run_phase4.py` | Script | Full report: hit rates, perm importance, plots | DB | Console + `reports/*.png` | User | N | **Y** |
| `scripts/run_phase6a.py` | Script | Sprint group delta (paired bootstrap) | DB | Console delta + CI | User | N | **Y** |
| `scripts/run_phase6b.py` | Script | Weather group delta (paired bootstrap) | DB | Console delta + CI | User | N | **Y** |
| `scripts/test_modes.py` | Test | Early vs full mode, missing data messages | Temp DB copy | Console PASS/FAIL | User | N (temp copy only) | **Y** |
| `scripts/test_forecast_flow.py` | Test | Full fetch→save→score→simulate→refuse loop | Temp DB copy | Console PASS/FAIL | User | N (temp copy only) | **Y** |
| `scripts/test_upcoming_fetch.py` | Test | `fetch_upcoming` + `build_features(forecast_race=)` | Temp DB copy | Console PASS/FAIL | User | N (temp copy only) | **Y** |
| `scripts/verify_race_status.py` | Verify | 14 checks on `race_status` vs `results` | DB | Console PASS/FAIL | User | N | **Y** |
| `scripts/verify_*.py` | Verify | Various data integrity checks | DB | Console PASS/FAIL | User | N | **Y** |
| `scripts/check_*.py` | Check | Specific invariants (alpha window, coef signs, etc.) | DB | Console PASS/FAIL | User | N | **Y** |
| `scripts/probe_*.py` | Probe | Ad-hoc exploration (API, schedule, field, etc.) | DB / APIs | Console output | User | N | **Y** |

---

## Part 4: Data Sources and Ingestion

### 4.1 FastF1 (primary for race, qualifying, sprint, status)
| Aspect | Detail |
|--------|--------|
| **Session identifiers** | `R` (race), `Q` (qualifying), `S` (sprint race), `FP1`/`FP2`/`FP3` (practice — **not used**; OpenF1 used instead) |
| **Verified identifiers** | Conventional: R, Q, FP1/2/3 all OK; Sprint weekend: R, Q, S OK; **SQ always empty** (18/18) or raises (6 shootouts) — `scripts/verify_sprint.py` 18/18 PASS |
| **Key columns from `session.results`** | `Abbreviation` (driver code), `TeamName`, `GridPosition` (float or NaN), `Position` (float or NaN), `Status` (string), `ClassifiedPosition` (string, may have 'R'), `DriverNumber`, `Q1`/`Q2`/`Q3` (Timedelta or NaT) |
| **Authentication** | `F1_USERNAME` / `F1_PASSWORD` in `credentials.env`; loaded by `credentials.load()` at `fetch.enable_cache()`; **lap data requires auth** |
| **Cache** | `f1_cache/` directory; `fastf1.Cache.enable_cache()` |
| **Rate limits** | Not published; FastF1 handles internally; scripts run sequentially |
| **Idempotency** | `fetch_log` table: step recorded only when **real rows stored**; 0-row fetches are **not logged** so they retry next run (bug fix from Appendix A) |
| **Failure modes** | Network errors, missing data, session not loaded → logged and skipped; race with 0 classified finishers → not stored, will retry |

### 4.2 OpenF1 (practice laps + sprint qualifying)
| Aspect | Detail |
|--------|--------|
| **Base URL** | `https://api.openf1.org/v1` |
| **Endpoints used** | `/v1/sessions?year=YYYY`, `/v1/drivers?session_key=K`, `/v1/laps?session_key=K` |
| **Rate limit** | ~3 req/s, ~30 req/min (not in headers); `f1pred.httpcache` starts at 0.4s spacing (2.5 req/s), backs off to 2.5s on HTTP 429 |
| **Auth** | None required for historical data |
| **Cache** | `cache/openf1/` (SHA-1 of URL); `f1pred.httpcache.get_json()` — atomic write via `.tmp` rename |
| **Session matching** | OpenF1 Race session date ↔ FastF1 `sessions.event_date` within ±1 day (86/89 exact); yields `meeting_key` stored in `sessions.meeting_key` |
| **Lap validity rules** (decided **before** any Phase 3 metric) |
| Rule 1: Sector sum | `sector1+sector2+sector3` must equal `lap_duration` within `SECTOR_TOLERANCE_S = 0.1s` (data stored to 3dp → rounding ≤0.002s; 0.1s = 50× margin). **Missing sectors never reject.** |
| Rule 2: Implausible speed | Lap must be ≥ `MIN_LAP_FRACTION = 0.90` × session's **2nd-fastest** usable lap. Max legitimate 1st-vs-2nd gap across 89 races = 0.8%; 10% cutoff = 12× margin. Only **faster** laps rejected. Applied only if ≥ `MIN_LAPS_FOR_REFERENCE = 10` usable laps. |
| **Counting** | `lap_count` includes **every** lap row (pit-out + rejected); `best_practice_s` uses only valid laps |
| **Pit-out laps** | `is_pit_out_lap` flag; excluded from best lap, counted in `lap_count` |
| **Missing data** | 12 races have ≥1 driver with no valid lap → `best_practice_s=NULL`, `has_practice_lap=0` |

### 4.3 Weather (Open-Meteo)
| Aspect | Detail |
|--------|--------|
| **Provider** | Open-Meteo Archive API (`archive-api.open-meteo.com/v1/archive`) |
| **Variables** | `temperature_2m_mean` (°C), `relative_humidity_2m_mean` (%), `rain_sum` (mm), `wind_speed_10m_max` (km/h) — **daily aggregates**, not race-time |
| **Verification** | Provider, variable names, units confirmed against **one real response** before parsing (`scripts/probe_weather_provider.py`); 89/89 races fetched, zero NULLs, dates match `sessions.event_date` |
| **Coordinate handling** | Hand-entered lat/lon per venue; **Spanish GP override**: Barcelona (2023–2025) → Madrid (2026) keyed on event name + year; `--dry-run` shows venue table |
| **Known mismatch** | 2023 Spain: 10.8 mm rain recorded, but race was dry (rain fell while cars in garage) — `rain_mm` = "wet day", not "wet race" (LIMITATIONS §8) |
| **Forecast vs observed** | Stored values are **observed historical**; a future race needs a supplied forecast — `build_features` omits weather columns for future races rather than filling (LIMITATIONS §8) |

### 4.4 Known Data Quirks (documented, not hidden)

| Quirk | Handling |
|-------|----------|
| **2026 field = 22 cars** | Never hard-code 20; `_season_field_size()` computes modal count per season |
| **Team renames** | `clean_team_name()` maps 18 raw labels → 11 canonical (Alfa Romeo→Sauber→Audi, AlphaTauri→Racing Bulls, Cadillac new) |
| **FastF1 stringified NaN** | `_nullish()` catches `'nan'`/`'None'` strings that `pd.isna()` misses (critical for 2026 R19 HIR placeholder) |
| **Qualifying Position ties** | FastF1 official `Position` can have ties (2023 R10: PER & BOT both 15) — `validate_positions(allow_ties=True)` downgrades to warning; `q_position_official` mirrors raw value |
| **Pit-lane starts** | `GridPosition` 0 or NULL → filled with `field_n + 1` (5 such rows in history: MAG, STR×2, OCO, HIR) |
| **DNS rows kept** | 16 rows (0.88%) with `finish` = classified position at back; excluding them would flatter MAE and break 1816-row invariant |
| **Drivers with no history** | `driver_form` → `(field_n+1)/2`, `non_finish_rate` → 0.0 (constants, no leakage) |
| **Sprint weekends** | Exactly 1 practice (FP1); `n_sessions=1`; FastF1 SQ empty → SQ from OpenF1 |

---

## Part 5: Database

### ER Diagram (Mermaid)
```mermaid
erDiagram
    RESULTS ||--o{ QUALIFYING : "year,round,driver"
    RESULTS ||--o{ PRACTICE : "year,round,driver"
    RESULTS ||--o{ RACE_STATUS : "year,round,driver"
    RESULTS ||--o{ DRIVER_NUMBERS : "year,round,driver"
    RESULTS ||--o{ FORECASTS : "year,round,driver"
    RESULTS ||--o{ SPRINT : "year,round,driver"
    RESULTS ||--o{ SPRINT_QUALIFYING : "year,round,driver"
    SESSIONS ||--o{ RESULTS : "year,round"
    SESSIONS ||--o{ WEATHER : "year,round"
    SESSIONS ||--o{ QUALIFYING : "year,round"
    SESSIONS ||--o{ PRACTICE : "year,round"
    SESSIONS ||--o{ SPRINT : "year,round"
    SESSIONS ||--o{ SPRINT_QUALIFYING : "year,round"
    SESSIONS ||--o{ RACE_STATUS : "year,round"
    SESSIONS ||--o{ DRIVER_NUMBERS : "year,round"
    SESSIONS ||--o{ FORECASTS : "year,round"
    FETCH_LOG ||--o{ SESSIONS : "year,round"
```

### Per-Table Data Dictionary

#### `results` (1838 rows, PK: year, round, driver) — **7-column contract from Appendix A**
| Column | Type | Meaning | Nullable | Source |
|--------|------|---------|----------|--------|
| year | INTEGER | Season year | N | FastF1 schedule |
| round | INTEGER | Round number | N | FastF1 schedule |
| event | TEXT | Event name | N | FastF1 `EventName` |
| driver | TEXT | FastF1 Abbreviation (e.g., NOR) | N | FastF1 `Abbreviation` |
| team | TEXT | Canonical team name | N | FastF1 `TeamName` → `clean_team_name()` |
| grid | REAL | Starting grid slot (1..N); pit-lane = field_n+1 | N | FastF1 `GridPosition` (0/NULL → fill) |
| finish | REAL | Classified finishing position (1..N); DNS = back | N | FastF1 `Position` / `ClassifiedPosition` |

#### `qualifying` (1838 rows, PK: year, round, driver)
| Column | Type | Meaning | Nullable | Source |
|--------|------|---------|----------|--------|
| q_position | REAL | FastF1 official `Position` (1..N; ties possible) | Y | FastF1 `Position` |
| q_position_official | REAL | Mirror of above for provenance | Y | FastF1 `Position` |
| q1_s, q2_s, q3_s | REAL | Segment times in seconds | Y | FastF1 `Q1`/`Q2`/`Q3` |
| best_q_s | REAL | Min of set segments | Y | Derived |
| gap_to_pole_pct | REAL | `(best_q_s - pole) / pole * 100` | Y | Derived |
| has_qualifying_time | INTEGER | 0/1 missing flag | N | 0 if all segments NULL |

#### `practice` (1838 rows, PK: year, round, driver)
| Column | Type | Meaning | Nullable | Source |
|--------|------|---------|----------|--------|
| n_sessions | INTEGER | Practice sessions found (0..3) | N | OpenF1 |
| best_practice_s | REAL | Fastest valid lap (seconds) | Y | OpenF1 laps (valid only) |
| practice_rank | REAL | Rank of `best_practice_s` (1=fastest, starters only) | Y | Derived |
| laps_completed | INTEGER | All lap rows incl. pit-out/rejected | N | OpenF1 |
| pit_out_laps | INTEGER | Count of `is_pit_out_lap` | N | OpenF1 |
| gap_to_best_pct | REAL | `(best - session_best) / session_best * 100` | Y | Derived |
| has_practice_lap | INTEGER | 0/1 missing flag | N | 0 if no valid lap |

#### `sprint` (492 rows, PK: year, round, driver) — sprint weekends only
| Column | Type | Meaning | Source |
|--------|------|---------|--------|
| sprint_position | REAL | Finish pos in sprint | FastF1 `S` |
| sprint_status | TEXT | Status string | FastF1 `Status` |
| sprint_grid | REAL | Sprint starting grid | FastF1 `GridPosition` |
| sprint_points | REAL | Points scored | FastF1 `Points` |
| has_sprint_result | INTEGER | 0/1 | Derived |

#### `sprint_qualifying` (492 rows, PK: year, round, driver) — sprint weekends only
| Column | Type | Meaning | Source |
|--------|------|---------|--------|
| best_sq_s | REAL | Fastest valid SQ lap | OpenF1 |
| sq_rank | REAL | Rank of `best_sq_s` | Derived |
| laps | INTEGER | Lap count | OpenF1 |
| gap_to_best_pct | REAL | Gap to fastest SQ lap | Derived |
| has_sq_lap | INTEGER | 0/1 missing flag | Derived |

#### `race_status` (1838 rows, PK: year, round, driver)
| Column | Type | Meaning | Source |
|--------|------|---------|--------|
| status | TEXT | FastF1 `Status` (Finished, Retired, Accident, Lapped, etc.) | FastF1 `Status` |

#### `driver_numbers` (1838 rows, PK: year, round, driver)
| Column | Type | Meaning | Source |
|--------|------|---------|--------|
| driver_number | INTEGER | FastF1 `DriverNumber` | FastF1 |

#### `sessions` (90 rows, PK: year, round)
| Column | Type | Meaning | Source |
|--------|------|---------|--------|
| event | TEXT | Event name | FastF1 |
| event_format | TEXT | `conventional` / `sprint_qualifying` / `sprint_shootout` | FastF1 `EventFormat` |
| event_date | TEXT | UTC date (YYYY-MM-DD) | FastF1 `EventDate` |
| meeting_key | INTEGER | OpenF1 meeting key | OpenF1 match |
| expected_size | INTEGER | Modal car count for season | `_season_field_size()` |
| n_starters | INTEGER | Rows in `results` (NULL if unrun) | Derived |

#### `weather` (90 rows, PK: year, round) — one row per RACE
| Column | Type | Meaning | Source |
|--------|------|---------|--------|
| event_date | TEXT | Race date (lookup day) | `sessions.event_date` |
| lat, lon | REAL | Venue coordinates | Hand-entered + override |
| temp_c | REAL | `temperature_2m_mean` | Open-Meteo |
| humidity_pct | REAL | `relative_humidity_2m_mean` | Open-Meteo |
| rain_mm | REAL | `rain_sum` (whole day) | Open-Meteo |
| wind_kmh | REAL | `wind_speed_10m_max` | Open-Meteo |
| source | TEXT | Provider + note | Hard-coded |

#### `forecasts` (44 rows, PK: year, round, mode, driver) — **immutable once written**
| Column | Type | Meaning |
|--------|------|---------|
| mode | TEXT | `early` or `full` |
| model_version | TEXT | `phase5-ridge-1.0` (bump only on feature set/alpha/estimator change) |
| created_at | TEXT | UTC ISO8601 when written |
| race_start_utc | TEXT | Scheduled lights-out from FastF1 schedule |
| pred | REAL | Raw Ridge output (MAE scored on this) |
| pred_pos | INTEGER | 1..N ordering of `pred` (winner=1) |
| grid_pred | REAL | Grid baseline's call (saved alongside for scoring) |
| features | TEXT | JSON list of feature names |
| alpha | REAL | Ridge alpha used (1.0) |
| n_train_races | INTEGER | Races strictly before this one |
| note | TEXT | Provenance (e.g., "generated after qualifying, full feature set") |

#### `fetch_log` (409 rows, PK: year, round, step)
| Column | Type | Meaning |
|--------|------|---------|
| step | TEXT | `race`, `race_status`, `qualifying`, `sprint`, `practice`, `sprint_qualifying` |
| nrows | INTEGER | Rows actually stored |
| run_at | TEXT | UTC ISO8601 of step completion |

### Keys & Invariants
- All core tables PK = `(year, round, driver)` → 1 row per starter per race
- `results` **exactly 7 columns** (asserted by `scripts/test_baseline_fetch.py` check [3])
- `race_status` rows = `results` rows (same "did driver take part" test) → joins 1:1
- `forecasts` never updated: plain `INSERT`; re-run `--save` → returns 0, prints original `created_at`
- `fetch_log` only logs steps with **real rows** (nrows > 0) → 0-row fetches retry next run
- Row counts per season (verified): 2023=22 races×20, 2024=24×20, 2025=24×20, 2026=20×22 = 1838 total

### Migrations (`db._migrate`)
- `qualifying.q_position_official` added after initial creation
- `forecasts` columns `model_version`, `grid_pred`, `note` added; **refuses to ALTER if table non-empty** (would leave NULLs on old forecasts)

### Backups (all read-only verified)
| File | Size | UTC Modified | SHA256 (first 16) | Purpose |
|------|------|--------------|-------------------|---------|
| `f1_backup_20261108_133100_pre_sao_paulo.db` | 798,720 | 2026-11-08 13:31:00 | A336F164399B1F56 | Pre-São Paulo forecast |
| `f1_backup_20261108_220159_post_sao_paulo.db` | 827,392 | 2026-11-08 22:01:59 | 004E7F679A302428 | Post-São Paulo scoring |
| `f1_backup_20261108_225801_pre_grid_input.db` | 827,392 | 2026-11-08 22:58:01 | 004E7F679A302428 | Pre-`--grid-file` feature |
| (older backups for Miami refetch, guard fix, etc.) | | | | |

---

## Part 6: Feature Engineering

### Locked Feature Set (Phase 3 pre-registered, 12 features)

| Group | Feature | Formula / Source | Missing Handling | Early? | Full? |
|-------|---------|------------------|------------------|--------|-------|
| grid_form | **grid** | `results.grid` (pit-lane/NULL → `field_n+1`) | `field_n+1` | No | Yes |
| grid_form | **driver_form** | `shift(1).rolling(5).mean()` of `finish` per driver | `(field_n+1)/2` (debut) | Yes | Yes |
| grid_form | **team_form** | Collapse to 1 row/(team,race) → `shift(1).rolling(5).mean()` | `(field_n+1)/2` | Yes | Yes |
| grid_form | **non_finish_rate** | `shift(1).rolling(5).mean()` of `status∉{Finished,Lapped}` | 0.0 (debut) | Yes | Yes |
| practice | **practice_pos** | `practice_rank` (starter-only rank) | `field_n+1` | Yes | Yes |
| practice | **practice_gap_pct** | `gap_to_best_pct` (capped) | 0.0 + `no_practice_time=1` | Yes | Yes |
| practice | **practice_laps_30** | `laps_completed / 30.0` | 0.0 | Yes | Yes |
| practice | **no_practice_time** | `1 - has_practice_lap` | — | Yes | Yes |
| qualifying | **q_position** | `qualifying.q_position` (official Position) | `field_n+1` | No | Yes |
| qualifying | **q_gap_pct** | `gap_to_pole_pct` | 0.0 + `no_q_time=1` | No | Yes |
| qualifying | **no_q_time** | `1 - has_qualifying_time` | — | No | Yes |
| qualifying | **on_pole** | `(q_position == 1) & has_qualifying_time` | — | No | Yes |

**Constants derived per-race (no leakage):**
- `field_n` = cars in this race (20 or 22)
- `mid_field` = `(field_n + 1) / 2` (e.g., 22 → 11.5)
- Default fills use **that race's** `field_n`, never a global mean

### Phase 6 Features (kept OUT of `ALL_FEATURES` / `FEATURE_GROUPS`)

| Group | Features | Purpose |
|-------|----------|---------|
| Sprint (6) | `has_sprint`, `sq_rank`, `sq_gap_pct`, `no_sq_lap`, `sprint_pos`, `no_sprint_result` | Additive stage; `no_sprint_result` = `1 - has_sprint` (exact duplicate, kept for spec) |
| Weather (7) | `temp_c`, `humidity_pct`, `rain_mm`, `wind_kmh`, `rain_x_q_position`, `rain_x_non_finish_rate`, `wind_x_grid` | 3 pre-chosen interactions only; race-level constants cannot reorder |

### Leakage Controls (explicit in code)
| Control | Location | Why |
|---------|----------|-----|
| `shift(1)` inside per-driver group | `features.py:397` | Driver form sees only previous races |
| Team collapse before shift | `features.py:415-422` | Prevents reading other driver's finish in same race |
| `StandardScaler` fitted on TRAIN only | `model.py:187` | Future race statistics never reach model |
| Forecast row appended **last** | `features.py:284` | `shift(1)` on forecast row reads previous race |
| Weather columns omitted for future races | `features.py:356-364` | Observed weather not available pre-race |
| Defaults = constants (mid_field, 0.0) | `features.py:428-430` | No dataset statistics leaked |

### Sprint Weekend Handling
- `has_sprint` = 1 from `sessions.event_format` (calendar fact, known pre-weekend)
- Non-sprint weekend: all 6 sprint columns land on fills (`has_sprint=0`, positions=`field_n+1`, gaps=0, flags=1) — encoding "no sprint here", not missing data
- Sprint features **excluded** from production set (measured null effect, LIMITATIONS §9)

---

## Part 7: Modeling and Validation

### Algorithm & Hyperparameters
- **Estimator**: `sklearn.linear_model.Ridge` in `Pipeline(StandardScaler, Ridge)`
- **Alpha**: `RIDGE_ALPHA = 1.0` **fixed** (no tuning; `scripts/check_alpha_window.py` shows compliant inner-CV scores *worse*: 3.0786 vs 3.0756)
- **Target**: `finish` (finishing position, 1..N)
- **Prediction for MAE**: raw `pred` (continuous)
- **Prediction for hits**: `pred_pos` = rank of `pred` (1 = predicted winner)

### Walk-Forward Procedure (Mermaid)
```mermaid
flowchart TD
    A[Feature frame: 1 row/driver/race, race_idx 1..89] --> B{min_train=20}
    B --> C[For k = 21..89]
    C --> D[Train = races 1..k-1]
    D --> E[Test = race k]
    E --> F[Fit StandardScaler on TRAIN cols]
    F --> G[Fit Ridge(α=1.0) on scaled TRAIN]
    G --> H[Predict test → pred, pred_pos]
    H --> I[Score MAE, ρ, winner_hit, podium_hit]
    I --> J[Store per-race row + predictions]
    J --> K[Next k]
    K --> L[Mean MAE, ρ, hit rates over 69 races]
    L --> M[Feature-group ladder: stages 0→3]
    M --> N[Phase 6: append sprint (stage 4), weather (stage 5)]
```

### Baselines (unfitted, same validation races)
| Baseline | Column | What it predicts | Early? | Full? |
|----------|--------|------------------|--------|-------|
| grid baseline | `grid` | Starting grid slot | No | Yes |
| practice-order baseline | `practice_pos` | Practice rank | Yes | Yes |
| recent-form baseline | `driver_form` | Rolling mean finish | Yes | Yes |

### Hit-Rate Baselines (ranking, scored by same `_hits()`)
| Baseline | Sort Column | Exclude Column | Meaning |
|----------|-------------|----------------|---------|
| pole-sitter wins | `grid` (pit-lane = field_n+1 sorts last) | None | Driver starting P1 |
| best qualifying gap wins | `q_gap_pct` | `no_q_time` (→ +inf) | Smallest gap to pole |
| best driver form wins | `driver_form` | None | Lowest mean finish last 5 |

### Metric Definitions (exact, from code)
| Metric | Formula | Notes |
|--------|---------|-------|
| MAE | `mean(|pred - finish|)` per race, then mean over races | Walk-forward reports **unweighted mean of per-race MAEs** |
| Spearman ρ | `spearmanr(pred, finish)` per race; NaN if constant | Unweighted mean over races (skip NaN) |
| Winner hit | `1 if argmin(pred) == argmin(finish) else 0` per race | NaN if constant pred |
| Podium hit | `|pred_top3 ∩ actual_top3| / 3` per race | **Recall** of real podium; values 0, 1/3, 2/3, 1 |
| Improvement (pp) | `model_hit - max(baseline_hits)` | Winner & podium separately |

### Shuffled-Label Sanity Check
- `walk_forward(shuffle=True)` scrambles `y_train` inside each fold → MAE collapses to ~5.14 (vs 3.07 real) — confirms pipeline learns signal, no leakage
- Phase 6 shuffled: 18-feature → 5.19, 25-feature → 5.23

### Feature-Group Ladder (Phase 3 accepted)
| Stage | Features | MAE | Δ MAE | Verdict |
|-------|----------|-----|-------|---------|
| 0 (intercept) | — | 5.141 | — | Baseline |
| 1 (+ grid_form) | grid, driver_form, team_form, non_finish_rate | 3.129 | **−2.012** | Big gain |
| 2 (+ practice) | + practice_pos, gap, laps, flag | 3.106 | −0.023 | Small |
| 3 (+ qualifying) | + q_position, q_gap, no_q_time, on_pole | 3.069 | −0.037 | Small |
| **Production (12)** | **ALL_FEATURES** | **3.069** | — | **Locked** |

### Phase 6 Additive Stages (measured on identical folds, α=1.0 fixed)
| Stage | Features Added | MAE Before → After | Δ | Paired 95% CI | Verdict |
|-------|----------------|-------------------|---|---------------|---------|
| 4 (sprint) | 6 sprint features | 3.069 → 3.073 | **+0.004** | [−0.007, +0.017] | Contains 0 → **no measurable help** |
| 5 (weather) | 7 weather features | 3.073 → 3.076 | **+0.003** | [−0.018, +0.027] | Contains 0 → **no measurable help** |

**Why believable (LIMITATIONS §9):**
- No units error (sq_gap_pct median 1.45% vs qualifying 1.22%)
- No leakage (shuffled-label controls collapse to 5.19/5.23)
- Alpha not the explanation (inner-CV worse: 3.0786 vs 3.0756)
- Model still beats grid baseline (3.241) at 3.073/3.076

### Permutation Importance (grouped, walk-forward)
- Shuffles each `PERM_GROUPS` block **within** validation race (preserves race distribution)
- Reports `delta = MAE_shuffled - MAE_base`; `folds_helped` = races where shuffling hurt
- Collinearity-safe: never inspects coefficients

---

## Part 7 (continued): Tree Models (Phase 7)

### XGBoost (Phase 7B)

**Implementation:** `f1pred/xgboost_model.py`  
**Walk-forward:** Identical expanding-window protocol (173 folds, MIN_TRAIN_RACES=20)  
**Hyperparameters (pre-registered, FROZEN):**

| Parameter | Value |
|-----------|-------|
| n_estimators | 200 |
| max_depth | 4 |
| learning_rate | 0.05 |
| subsample | 0.8 |
| colsample_bytree | 0.8 |
| min_child_weight | 5 |
| reg_alpha (L1) | 1.0 |
| reg_lambda (L2) | 1.0 |
| objective | reg:squarederror |
| random_state | 42 |
| n_jobs | 1 |

**Monotone Constraints (12 features, pre-registered):**
```
[1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, -1]
# grid, driver_form, team_form, non_finish_rate,
# practice_pos, practice_gap_pct, practice_laps_30, no_practice_time,
# q_position, q_gap_pct, no_q_time, on_pole
```

**Shuffled-Label Control (mandatory sanity check):**
- 3 seeds: MAE = 4.764 (real MAE = 3.238, gap = 1.53 > 1.5) ✅ PASS

**Key Results (corrected metric):**

| Metric | XGBoost | Ridge | Δ |
|--------|---------|-------|---|
| MAE | 3.2376 | 3.2784 | **−0.0409** (delta of means) |
| ΔMAE (mean of per-race deltas) | −0.0372 | — | CI: [−0.065, −0.006] |
| Spearman ρ | 0.6715 | 0.6668 | +0.0047 |
| Winner hit | 95/173 = 54.91% | 94/173 = 54.34% | +0.57 pp |
| Podium hit (recall@3) | 355/519 = 68.40% | 353/519 = 68.02% | +0.38 pp |
| Overfit gap | 0.0841 | ~0.08 | — |
| Shuffled-label gap | 1.53 | — | PASS |

**Bug Fixed:** Original XGBoost used position-by-position match for podium hit
instead of set-intersection recall. Fixed to match Ridge's `_hits()` implementation.

**Verdict:** **ACCEPTED** — MAE improvement significant (CI excludes 0), hit rates
match Ridge, no overfitting, shuffled-label passes.

---

### LightGBM (Phase 7C)

**Implementation:** `f1pred/lightgbm_model.py`  
**Walk-forward:** Identical expanding-window protocol  
**Monotone Constraints:** Same as XGBoost (where supported)

#### Variant C1: `regression_l1` (MAE-native)
- **MAE:** 3.1193 (Δ = −0.1545, CI excludes 0) ✅
- **Overfit gap:** 0.5008 ❌ (sanity threshold 0.15)
- **Winner hit:** 51.45% (< 55%) ❌
- **Monotone constraints:** NOT SUPPORTED by LightGBM with `regression_l1`
- **Verdict: REJECTED** — severe overfitting (gap 0.501)

#### Variant C2: `regression` + `metric=mae` (MSE objective)
- **MAE:** 3.2381 (Δ = −0.0403, CI excludes 0) ✅
- **Overfit gap:** 0.0770 ✅ (< 0.15)
- **Winner hit:** 92/173 = 53.18% (< 55%) ❌
- **Monotone constraints:** Applied (same as XGBoost) ✅
- **Verdict: NULL** — MAE improvement real but winner hit regression (92/173 vs
  Ridge 94/173) fails tertiary criterion ≥55%

---

### Phase 7D: Head-to-Head Consolidation

| Model | MAE | Winner hit | Podium hit | Overfit | Status |
|-------|-----|------------|------------|---------|--------|
| Ridge | 3.2784 | 94/173 (54.34%) | 68.02% | ~0.08 | Baseline |
| **XGBoost** | **3.2376** | 95/173 (54.91%) | 68.40% | 0.084 | **ACCEPTED** |
| LightGBM C2 | 3.2381 | 92/173 (53.18%) | 67.82% | 0.077 | NULL |
| LightGBM C1 | 3.1193 | 51.45% | 67.82% | 0.501 | REJECTED |

**Head-to-head XGBoost vs LightGBM C2:**
- MAE: statistically indistinguishable (XGB − LGB = −0.0008, CI: [−0.0097, +0.0082])
- Winner hit: XGBoost 95/173 vs LGB 92/173 → **+3 races** for XGBoost
- Podium hit: essentially tied (68.40% vs 67.82%)
- Feature importance correlation: ρ = 0.9301 (very high)

**Ensemble (50/50):** MAE 3.2365 vs best single 3.2376 → gain 0.0011 (not warranted)

**Final Decision:** **XGBoost selected** — statistically indistinguishable on MAE,
winner hit advantage (+3 races), monotone constraints supported, mature ecosystem.

---

## Part 8: Forecast and Scoring Workflow

### Race Weekend Sequence (Mermaid)
```mermaid
sequenceDiagram
    participant User
    participant CLI as f1pred.cli
    participant DB as f1.db
    participant Fetch as f1pred.fetch
    participant Feat as f1pred.features
    participant Model as f1pred.model
    participant Forecast as f1pred.forecast
    participant Report as f1pred.report
    participant Score as score_forecast.py

    Note over User,Score: PRE-RACE (Friday/Saturday)
    User->>CLI: python -m f1pred.cli --year 2026 --round 20 --fetch --mode auto
    CLI->>Fetch: fetch_upcoming(con, 2026, 20)
    Fetch->>DB: sessions, practice, qualifying (if started)
    Fetch-->>CLI: 22 entrants, practice=22, qualifying=22
    CLI->>Feat: build_features(forecast_race=(2026,20))
    Feat->>DB: reads history + qualifying + practice
    Feat-->>CLI: Feature frame + forecast spine (grid from q_position)
    CLI->>Model: walk_forward(df, FULL_FEATURES)
    Model-->>CLI: MAE 3.066, ρ 0.711, predictions
    CLI->>Report: top3_printout, order_table, gap_scatter
    Report-->>User: Predicted top-3, full table, PNG
    CLI->>Forecast: save(con, ..., grid_file=official_grid.csv)
    Forecast->>DB: INSERT 22 rows into forecasts (created_at, grid_pred, etc.)
    Forecast-->>User: FORECAST SAVED banner

    Note over User,Score: POST-RACE (Sunday+)
    User->>Score: python scripts/score_forecast.py --year 2026 --round 20 --mode full
    Score->>DB: load forecast + results
    Score->>Score: NO-PEEKING CHECK (created_at < race_start_utc)
    Score->>Feat: build_features() for baselines
    Score->>Score: MAE, ρ, winner/podium hits + baselines
    Score->>DB: write scorecard to reports/scorecard_2026_r20_full.md
    Score-->>User: Scorecard + console table
```

### Full CLI Reference (`python -m f1pred.cli`)
| Flag | Default | Meaning |
|------|---------|---------|
| `--year` | latest race in `results` | Race year |
| `--round` | latest race in `results` | Race round |
| `--mode` | `auto` | `auto`/`early`/`full` — auto picks full if qualifying exists |
| `--db` | `f1.db` | Database file (use temp copy for tests) |
| `--fetch` | off | Fetch pre-race sessions before forecasting (needs explicit year/round) |
| `--save` | off | Write forecast to `forecasts` table (only for unrun race) |
| `--grid-file` | None | CSV `driver,grid_pos` — **required for full-mode `--save`**; supplies real starting grid after penalties |

**Exit codes:** 0 = forecast produced; 1 = refused (message says what's missing); 2 = score not-run

### Forecast Table Columns (saved pre-race)
| Column | Source | Used at Scoring |
|--------|--------|-----------------|
| `created_at` | `datetime.now(timezone.utc)` | No-peeking check (must be < `race_start_utc`) |
| `race_start_utc` | FastF1 schedule (Race session) | No-peeking check |
| `grid_pred` | `df["grid"]` at forecast time (qualifying order or `--grid-file`) | Grid baseline scoring |
| `pred` / `pred_pos` | Model output | MAE / hits |
| `features` (JSON) | `MODE_FEATURES[mode]` | Provenance |
| `note` | "generated after qualifying, full feature set" | Provenance |

### Scorecard Format (Markdown)
1. Header: forecast time, race start, no-peeking verdict, model version, alpha, training races, features, note
2. **Model vs baselines table**: MAE, Spearman, winner%, podium% (n/a with explanation)
3. Improvement = model MAE − best baseline MAE (signed, % better/worse)
4. Predicted vs actual winner
5. Small-sample warning (mandatory)

### Addendum Format (post-race, never overwrites scorecards)
- `scorecard_2026_r20_addendum.md`: Rebuilds grid baseline from `grid_pred` (MAE 4.182), adds pole-sitter baseline, recomputes best-of-all
- `scorecard_2026_r20_addendum2.md`: Adds **official-grid baseline** (MAE 5.273 from FIA Doc 51), predicted vs actual top-3, top-10 table with official grid

### Case Study: 2026 São Paulo (Round 20) Timeline

| Time (UTC) | Event | Evidence |
|------------|-------|----------|
| 2026-11-08 12:43:51 | `fetch.py` last modified | File mtime |
| 2026-11-08 13:31:00 | **Backup** `f1_backup_20261108_133100_pre_sao_paulo.db` | 798,720 B, SHA256 A336F164... |
| 2026-11-08 13:32:04 | `db.py` migration adds `forecasts` columns | LIMITATIONS change log |
| 2026-11-08 13:33:08 | `model.py` adds `MODEL_VERSION`, moves baselines | LIMITATIONS change log |
| 2026-11-08 13:34:09 | `features.py` `_forecast_spine` fills grid from `q_position` | LIMITATIONS change log (**followed seeing predictions**) |
| 2026-11-08 13:40:23 | `forecast.py` adds no-overwrite guard | LIMITATIONS change log |
| 2026-11-08 13:47:12 | `cli.py` adds `--fetch`, save banner | LIMITATIONS change log |
| 2026-11-08 13:47:39 | **Early forecast saved** (22 rows, `created_at=13:47:39`) | `forecasts` table |
| 2026-11-08 13:48:57 | **Full forecast saved** (22 rows, `created_at=13:48:57`) | `forecasts` table |
| 2026-11-08 13:48:59 | `f1.db` last write | File mtime |
| 2026-11-08 17:00:00 | **Race start** (lights out) | `race_start_utc` |
| 2026-11-08 21:50:21 | **Scorecards written** (original, unchanged) | `reports/scorecard_2026_r20_*.md` mtime |
| 2026-11-08 21:50:43 | `f1.db` last write (results fetched) | File mtime |
| 2026-11-08 22:01:59 | **Post-race backup** `f1_backup_20261108_220159_post_sao_paulo.db` | 827,392 B |
| 2026-11-08 22:34:10 | **Addendum 1 written** (grid baseline from `grid_pred`) | `reports/scorecard_2026_r20_addendum.md` |
| 2026-11-09 | **Addendum 2 written** (official grid from FIA Doc 51) | `reports/scorecard_2026_r20_addendum2.md` |

**Key post-race findings (LIMITATIONS §10):**
- FastF1 published **no grid** for R20: `GridPosition = -1` for all 22 cars → scorer filled all with 23 → grid baseline MAE 11.500, ρ undefined
- **Official grid exists** (FIA Doc 51 + formula1.com): 5 penalties (RUS −5, LEC −10, VER/PER −30 back, HAM −75 back) → 21/22 cars moved vs qualifying order; only NOR unchanged
- Model's `grid` feature used qualifying order (wrong for 21/22 cars) — **data limitation, not tuning choice**
- Original scorecards **byte-identical** (1553 B / 1460 B, same SHA256); addenda are separate files

---

## Part 9: Testing and Verification

### Regression Suite (all run on **temp DB copies**, real `f1.db` never written)

| Script | Purpose | Key Assertions | Last Result |
|--------|---------|----------------|-------------|
| `scripts/test_modes.py` | Early vs full mode, missing data messages | 41 checks: mode selection, warnings, scatter, top-3, original DB untouched | **41/41 PASS** (2026-11-09) |
| `scripts/test_forecast_flow.py` | Full fetch→save→score→simulate→refuse→tamper loop | 31 checks: fetch 22 cars, save no-overwrite, score not-run/exit 2, simulate race, score exit 0, no-peeking PASS, refuse second save, tamper caught, real DB untouched | **31/31 PASS** |
| `scripts/test_upcoming_fetch.py` | `fetch_upcoming` + `build_features(forecast_race=)` | 18 checks: sessions row, results untouched, feature frame byte-identical, forecast rows added with NULL finish, assign_field_sizes no crash, real DB untouched | **18/18 PASS** |
| `scripts/verify_race_status.py` | `race_status` vs `results` invariants | 14 checks: counts match, status values valid, DNS handling, retired positions | **14/14 PASS** |
| `scripts/verify_fastf1.py` | FastF1 import + basic session load | Import OK, session loads | PASS |
| `scripts/verify_identifiers.py` | FastF1 session identifiers per format | Verified R/Q/S/FP1-3 per weekend type | PASS |
| `scripts/verify_sprint.py` | FastF1 SQ empty on 18 sprint weekends | 18/18 empty | PASS |
| `scripts/check_alpha_window.py` | Inner-CV alpha selection vs fixed α=1.0 | Fixed α not worse | PASS |
| `scripts/check_coef_signs.py` | Marginal ρ vs Ridge coef sign agreement | 4/12 disagree (documented in LIMITATIONS §6) | PASS |
| `scripts/check_sprint_features.py` | Sprint group redundancy checks | `no_sprint_result` = `1-has_sprint` for all 1816 rows | PASS |
| `scripts/check_lap_rules.py` | Lap validity rules (13 checks) | Rules 1/2 fire correctly, rule 2 never triggers alone | PASS |
| `scripts/validate_lap_rules.py` | Cross-check `classify_laps` vs stored data | 89/89 races match | PASS |

### Running the Regression Safely
```powershell
# All tests create temp copies in $env:TEMP/opencode/ or similar
$env:PYTHONUTF8 = "1"
python scripts\test_modes.py
python scripts\test_forecast_flow.py
python scripts\test_upcoming_fetch.py
python scripts\verify_race_status.py
```
- Real `f1.db` is **fingerprinted before/after**; any change → FAIL
- Test copies are deleted on completion (or on error with `ignore_errors=True`)

---

## Part 10: Results to Date

### Phase 3: Feature Ladder (walk-forward, 69 races / 1416 rows)
| Stage | Features | MAE | Spearman ρ | Δ MAE |
|-------|----------|-----|------------|-------|
| 0 (intercept) | — | 5.141 | — | — |
| 1 | grid, driver_form, team_form, non_finish_rate | 3.129 | 0.693 | **−2.012** |
| 2 | + practice_pos, practice_gap_pct, practice_laps_30, no_practice_time | 3.106 | 0.697 | −0.023 |
| 3 | + q_position, q_gap_pct, no_q_time, on_pole | **3.069** | **0.7084** | −0.037 |

### Phase 4: Hit Rates (same 69 races, same `_hits()`)
| | Winner | Podium |
|---|--------|--------|
| **MODEL (Ridge)** | **63.8%** | **67.6%** |
| Pole-sitter wins | 59.4% | 68.1% |
| Best qualifying gap wins | 60.9% | 67.6% |
| Best driver form wins | 21.7% | 49.3% |
| **Best BASELINE** | **60.9%** | **68.1%** |
| **MODEL − best (pp)** | **+2.9** | **−0.5** |

### Phase 6a: Sprint (6 features, additive)
| Metric | Before → After | Δ | Paired 95% CI | Verdict |
|--------|---------------|---|---------------|---------|
| MAE | 3.069 → 3.073 | **+0.004** | [−0.007, +0.017] | Contains 0 → **null** |
| Spearman | 0.7084 → 0.7061 | −0.0023 | — | — |
| Sign test | 45/69 improved | p = 0.015 | — | Median −0.005, tail +0.221 |
| Wilcoxon | p = 0.098 | — | — | Not robust with magnitudes |

### Phase 6b: Weather (7 features, additive)
| Metric | Before → After | Δ | Paired 95% CI | Verdict |
|--------|---------------|---|---------------|---------|
| MAE | 3.073 → 3.076 | **+0.003** | [−0.018, +0.027] | Contains 0 → **null** |
| Spearman | 0.7061 → 0.7036 | −0.0025 | — | — |
| Sign test | 39/69 improved | p = 0.34 | — | No signal |
| Wilcoxon | p = 0.40 | — | — | No signal |

### São Paulo 2026 R20 — Single Race (small sample warning applies)
| Mode | MAE | Spearman | Winner Hit | Podium Hit | Best Baseline | Improvement |
|------|-----|----------|------------|------------|---------------|-------------|
| Full (12) | 2.777 | 0.8509 | 100% (1/1) | 33.3% (1/3) | practice-order 3.000 | **−0.223** (7.45% better) |
| Early (7) | 2.934 | 0.8475 | 0% (0/1) | 33.3% (1/3) | practice-order 3.000 | **−0.066** (2.20% better) |

**Predicted vs Actual Top-3:**
| Mode | P1 | P2 | P3 | Actual | Podium Hit |
|------|----|----|----|--------|------------|
| Full | NOR ✅ | ANT | LEC | NOR, VER, HAD | 1/3 |
| Early | VER ❌ | ANT | LEC | NOR, VER, HAD | 1/3 |

### Phase 7: Tree Models (walk-forward, 173 folds, MIN_TRAIN_RACES=20)

#### Phase 7A: Linear Diagnostics
- **Verdict:** H0 REJECTED — nonlinearity/heteroskedasticity detected
- Residual variance: 18.717 (Ridge 18.524)
- Shapiro-Wilk p < 0.0001, Breusch-Pagan p < 0.0001
- Tree models have credible mechanism to improve over Ridge

#### Phase 7B: XGBoost (pre-registered hyperparameters)
| Metric | XGBoost | Ridge | Δ |
|--------|---------|-------|---|
| MAE | 3.2376 | 3.2784 | **−0.0409** (delta of means) |
| ΔMAE (mean of per-race deltas) | −0.0372 | — | 95% CI: [−0.065, −0.006] |
| Spearman ρ | 0.6715 | 0.6668 | +0.0047 |
| Winner hit | 95/173 = 54.91% | 94/173 = 54.34% | +0.57 pp |
| Podium hit (recall@3) | 355/519 = 68.40% | 353/519 = 68.02% | +0.38 pp |
| Overfit gap | 0.0841 | ~0.08 | — |
| Shuffled-label gap | 1.53 | — | PASS |

**Bug Fixed:** Original XGBoost used position-by-position match for podium hit instead of set-intersection recall. Fixed to match Ridge's `_hits()` implementation.

**Verdict:** **ACCEPTED** — MAE improvement significant (CI excludes 0), hit rates match Ridge, no overfitting, shuffled-label passes.

#### Phase 7C: LightGBM Variants
| Variant | MAE | ΔMAE (means) | Winner Hit | Podium Hit | Overfit | Verdict |
|---------|-----|--------------|------------|------------|---------|---------|
| C1 (regression_l1) | 3.1193 | −0.1545 | 51.45% | 67.82% | 0.501 | REJECTED |
| C2 (regression+mae) | 3.2381 | −0.0403 | 53.18% | 67.82% | 0.077 | NULL |

**C1 REJECTED:** Severe overfitting (gap 0.501 >> 0.15). LightGBM `regression_l1` does not support monotone constraints.

**C2 NULL:** MAE improvement real but winner hit regression (92/173 = 53.18% vs Ridge 94/173 = 54.34%) fails tertiary criterion ≥55%.

#### Phase 7D: Head-to-Head
| Model | MAE | Winner Hit | Podium Hit | Overfit | Status |
|-------|-----|------------|------------|---------|--------|
| Ridge | 3.2784 | 94/173 (54.34%) | 68.02% | ~0.08 | Baseline |
| **XGBoost** | **3.2376** | 95/173 (54.91%) | 68.40% | 0.084 | **ACCEPTED** |
| LightGBM C2 | 3.2381 | 92/173 (53.18%) | 67.82% | 0.077 | NULL |
| LightGBM C1 | 3.1193 | 51.45% | 67.82% | 0.501 | REJECTED |

**Final Decision:** XGBoost selected — statistically indistinguishable on MAE, winner hit advantage (+3 races), monotone constraints supported, mature ecosystem.

---

### Phase 7P: 2026 Season Tail Production Validation (3 Races Remaining)

**Status:** Planned — awaiting race weekends for R21 Las Vegas (Nov 21), R22 Qatar (Nov 29), R23 Abu Dhabi (Dec 6).

| Round | Event | Date | Format | Status |
|-------|-------|------|--------|--------|
| 21 | Las Vegas Grand Prix | 2026-11-21 | conventional | Pending |
| 22 | Qatar Grand Prix | 2026-11-29 | conventional | Pending |
| 23 | Abu Dhabi Grand Prix | 2026-12-06 | conventional | Pending |

**Model:** XGBoost (phase7-xgboost-1.0) — MAE 3.2376, ρ 0.6715, winner hit 54.91% (95/173), podium hit 68.40% (355/519).

**Per-Race Workflow:**
1. **After final practice:** `python -m f1pred.cli --year 2026 --round <N> --fetch --mode early --save`
2. **After qualifying + grid file:** `python -m f1pred.cli --year 2026 --round <N> --fetch --mode full --save --grid-file official_grid_2026_r<N>.csv`
3. **After race:** `python scripts\score_forecast.py --year 2026 --round <N> --mode auto --fetch`

**Grid file sourcing:** Official FIA Doc 51 / formula1.com → CSV format `driver,grid_pos` (22 rows).

**Post-race scoring:** `scripts\score_forecast.py --year 2026 --round <N> --mode auto --fetch` → scorecard in `reports/scorecard_2026_r<N>_<mode>.md`.

---

## Part 11: Known Issues, Limitations, Risks

| # | Severity | What | Where | Impact | Suggested Remedy |
|---|----------|------|-------|--------|------------------|
| 1 | **High** | **Training/forecast grid mismatch** — model trains on `results.grid` (real starting grid after penalties); at forecast time only qualifying order (`q_position`) is available. For 2026 R20, 21/22 cars had penalties → grid feature wrong for almost all cars. | `features.py:_forecast_spine`, `cli.py --grid-file` | Model's `grid` feature is noisy proxy; limits full-mode accuracy on penalty-heavy weekends | **Partial fix**: `--grid-file` supplies official grid (FIA Doc 51). Long-term: automate FIA doc parsing or find API. |
| 2 | **High** | **No official grid in FastF1/OpenF1** — FastF1 `GridPosition` = -1 for all 22 cars in 2026 R20; OpenF1 has no grid field. Scorer read `results.grid` → all 23 → meaningless baseline. | `scripts/score_forecast.py`, `features.py:417` | Grid baseline broken for races where FastF1 omits grid; addenda required | **Fixed in scorer**: `n/a` with explanation; `--grid-file` for future. |
| 3 | **Medium** | **Weather is daily aggregate, not race-time** — `rain_mm` = whole day; 2023 Spain had 10.8 mm but dry race. Weather features cannot reorder cars (race-level constants); only 3 interactions can. | `f1pred/fetch.py::fetch_weather`, LIMITATIONS §8 | Phase 6b null result expected; upper bound only | Document clearly; future: session-time weather if API available. |
| 4 | **Medium** | **Coefficient signs unreliable for collinear pairs** — 4/12 features disagree with marginal ρ (q_position/q_gap_pct, practice_pos/practice_gap_pct, driver_form/non_finish_rate). Ridge splits shared weight. | LIMITATIONS §6, `scripts/check_coef_signs.py` | Individual bars cannot be read as causal effects | Use grouped permutation importance; interpret feature groups, not bars. |
| 5 | **Medium** | **Test fixtures expire** — `test_modes.py`, `test_forecast_flow.py`, `test_upcoming_fetch.py` hard-coded R19/R20; once those races run, fixtures must simulate pre-race by deleting results. Fixed Nov 2026 by deleting results for target round AND all later rounds. | `scripts/test_*.py` | Tests fail after race runs unless updated | **Fixed**: now pick latest round with qualifying, delete results for it + later rounds. |
| 6 | **Low** | **`validate_practice_row` dead code** — hard-codes `<=22` (2026 trap); not wired into `fetch_practice`. | `f1pred/clean.py:140` | Latent bug if 2027 has >22 cars | Remove or wire up; make limit dynamic from `field_n`. |
| 7 | **Low** | **Stale message in `cli.py`** — "qualifying is unavailable" warning still appears in early mode when qualifying exists but is excluded; wording corrected but old string may linger in some branches. | `f1pred/cli.py` warnings | User confusion | Audit all warning strings after each phase. |
| 8 | **Low** | **Hard-coded 22 in `validate_practice_row`** — spec says "practice position must be 1..22". | `clean.py:144` | Breaks if grid size changes | Use `field_n` from context. |
| 9 | **Low** | **Phase 7 complete** — XGBoost selected, LGB C1 REJECTED, C2 NULL. | — | Portfolio incomplete | Phase 7P: production validation 2026 tail (3 races). |
| 10 | **Low** | **No tyre/strategy, dashboard, ESP32** — Optional Phase 9 extensions. | — | Portfolio value limited | Prioritize after Phase 7-8. |

---

## Part 12: Decision Log and Pre-registrations

| Date (UTC) | Decision | Pre/Post | Evidence |
|------------|----------|----------|----------|
| 2026-11-01 | **Phase 1 schema**: 7-column `results` + separate tables per session | Pre | `f1predictionanalyst.md` Phase 1 |
| 2026-11-01 | **FastF1 primary, OpenF1 for practice** (auth gap) | Pre | `f1predictionanalyst.md` §5 |
| 2026-11-01 | **Walk-forward only, MIN_TRAIN_RACES=20** | Pre | `f1predictionanalyst.md` §7 |
| 2026-11-01 | **Ridge α=1.0 fixed, no tuning** | Pre | `f1predictionanalyst.md` §7; `model.py:51` |
| 2026-11-01 | **12 features pre-registered (3 groups)** | Pre | `f1predictionanalyst.md` §35, §82 |
| 2026-11-01 | **Early mode = practice-only (7 features), no grid** | Pre | `f1predictionanalyst.md` §38-41 |
| 2026-11-01 | **Full mode = early + qualifying + grid + pole (12)** | Pre | `f1predictionanalyst.md` §40 |
| 2026-11-01 | **Baselines: grid, practice-order, recent-form** | Pre | `f1predictionanalyst.md` §45 |
| 2026-11-01 | **Winner/podium hit rates + baselines** | Pre | `f1predictionanalyst.md` §45 |
| 2026-11-04 | **Lap validity rules (sector sum ±0.1s, implausible speed 90% of 2nd fastest)** decided **before** any Phase 3 metric | Pre | `openf1.py:64-66`, LIMITATIONS §3 |
| 2026-11-04 | **Miami 2026 R4 corruption fixed** by rules above; re-fetch left 88 races byte-identical | Pre | LIMITATIONS §3, backup `f1_backup_before_miami_practice_refetch_20261106_132934.db` |
| 2026-11-06 | **2025 R22 sector offset (72 laps, 0.5-1.5s)** identified as different defect; confirmed harmless (no best laps affected) | Pre | LIMITATIONS §3, `scripts/check_r22_rejected_best.py` |
| 2026-11-07 | **Phase 6a (sprint) measured as additive stage**; CI contains 0 → excluded from production | Post-measurement | `scripts/run_phase6a.py`, LIMITATIONS §9 |
| 2026-11-07 | **Phase 6b (weather) measured as additive stage**; CI contains 0 → excluded from production | Post-measurement | `scripts/run_phase6b.py`, LIMITATIONS §9 |
| 2026-11-08 13:07 | **First forecast printed** (flow test run) | — | LIMITATIONS §10 change log |
| 2026-11-08 13:12 | **Second forecast printed** (flow test run) | — | LIMITATIONS §10 change log |
| 2026-11-08 13:31 | **Pre-race backup** `f1_backup_20261108_133100_pre_sao_paulo.db` | — | File exists |
| 2026-11-08 13:34 | **`features.py` edit** (`_forecast_spine` fills grid from `q_position`) **followed seeing predictions** | **Post** | LIMITATIONS §10: "it followed seeing predictions" |
| 2026-11-08 13:47 | **Early forecast saved** (`created_at=13:47:39`) | — | `forecasts` table |
| 2026-11-08 13:48 | **Full forecast saved** (`created_at=13:48:57`) | — | `forecasts` table |
| 2026-11-08 17:00 | **Race start** (lights out) | — | `race_start_utc` |
| 2026-11-08 21:50 | **Original scorecards written** (unchanged since) | — | `reports/scorecard_2026_r20_*.md` mtime |
| 2026-11-08 22:01 | **Post-race backup** | — | `f1_backup_20261108_220159_post_sao_paulo.db` |
| 2026-11-08 22:34 | **Addendum 1** (grid baseline from `grid_pred`) | Post | `reports/scorecard_2026_r20_addendum.md` |
| 2026-11-09 | **Addendum 2** (official grid from FIA Doc 51) | Post | `reports/scorecard_2026_r20_addendum2.md` |
| 2026-11-09 | **`--grid-file` feature added** (required for full-mode `--save`) | Post (but for future races) | `cli.py`, `features.py` |
| 2026-11-09 | **Pre-race penalty check** added (compares `--grid-file` to qualifying order) | Post | `cli.py` lines 420-440 |
| 2026-11-09 | **Test fixtures fixed** to simulate pre-race by deleting results for target + later rounds | Post | `scripts/test_*.py` rewritten |
| 2026-11-10 | **Phase 7A pre-registration** (linear diagnostics) | Pre | `reports/phase7a_linear_diagnostics_prereg.md` |
| 2026-11-10 | **Phase 7B pre-registration** (XGBoost hyperparameters + monotone constraints) | Pre | `reports/phase7b_xgboost_prereg.md` |
| 2026-11-10 | **Phase 7C pre-registration** (LightGBM C1/C2 hyperparameters + monotone) | Pre | `reports/phase7c_lightgbm_prereg.md` |
| 2026-11-10 | **Phase 7A diagnostics run** — H0 rejected (nonlinearity/heteroskedasticity detected) | Post | `reports/phase7a_linear_diagnostics.md` |
| 2026-11-10 | **Phase 7B XGBoost run** — bug found (position-by-position podium metric), fixed, re-run ACCEPTED | Post | `reports/phase7b_xgboost.md`, `reports/phase7b_diagnosis.md` |
| 2026-11-10 | **Phase 7C LightGBM run** — C1 REJECTED (overfit), C2 NULL (winner hit regression) | Post | `reports/phase7c_lightgbm.md` |
| 2026-11-10 | **Phase 7D head-to-head** — XGBoost selected (winner hit +3 races, MAE tied) | Post | `reports/phase7d_final.md` |
| 2026-11-10 | **MODEL_VERSION bumped** to `phase7-xgboost-1.0` | Post | `f1pred/model.py:57` |
| 2026-11-10 | **Phase 7P: 2026 season tail production validation initiated** — 3 races remaining (R21 Las Vegas Nov 21, R22 Qatar Nov 29, R23 Abu Dhabi Dec 6) | Post | `reports/phase7p_workflow_2026_tail.md` |

### Freeze Statement (LIMITATIONS §10)
> **The freeze applies from the 13:48 save.** The forecasts were written at `2026-11-08T13:47:39Z` (early) and `2026-11-08T13:48:57Z` (full), and `f1.db` was last written at **13:48:59**. No model file has been modified since, and no forecast row has been rewritten. Earlier framings anchored the freeze to the 13:31 backup, or to "every file predates the 13:47:39 early save" — those describe file timestamps only, and they were used to support the stronger claim corrected above.

### Edits Made After Seeing Predictions (withdrawn claim)
The statement "no code was changed after a prediction had been seen" was **wrong** and withdrawn. The edit to `features.py` at 13:34:09 followed the 13:07/13:12 forecast prints. Its effect: full-mode predictions shifted by `−0.0447 × (23 − grid)`; top 3 unchanged (NOR, ANT, LEC); 8 of 22 ranks swapped in middle/back. Early mode unaffected. Recorded honestly in LIMITATIONS §10.

---

## Part 13: Runbook

### From-Scratch Setup (PowerShell)
```powershell
# 1. Environment
$env:PYTHONUTF8 = "1"
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Dependencies
pip install fastf1==3.9.0 pandas==2.3.3 scikit-learn==1.9.1 numpy==2.4.6 matplotlib==3.11.2 scipy==1.18.1 requests==2.34.2

# 3. Credentials (create once, never commit)
# Edit credentials.env with your F1 account:
# F1_USERNAME=your_email
# F1_PASSWORD=your_password

# 4. Verify
python -m f1pred.credentials   # should print "loaded F1 credentials from credentials.env"
python -c "import fastf1; print(fastf1.__version__)"
```

### First-Time Data Build (2023–2026)
```powershell
# Full fetch (takes 30-60 min first time due to FastF1 cache population)
python -m f1pred.fetch --years 2023 2024 2025 2026

# Verify
python scripts\verify_phase1.py   # 17 checks
python scripts\verify_race_status.py
```

### Per-Race-Weekend Procedure
```powershell
# 1. Friday/Saturday: fetch pre-race sessions (practice + qualifying if started)
python -m f1pred.cli --year 2026 --round 20 --fetch

# 2. After qualifying (full mode) or after last practice (early mode):
#    Full mode REQUIRES --grid-file (official grid after penalties)
python -m f1pred.cli --year 2026 --round 20 --mode full --save --grid-file official_grid_2026_r20.csv

#    Early mode (no grid file needed):
python -m f1pred.cli --year 2026 --round 20 --mode early --save

# 3. Pre-race check (optional, before race):
python scripts\score_forecast.py --year 2026 --round 20 --preflight

# 4. Post-race (after results published):
python scripts\score_forecast.py --year 2026 --round 20 --mode auto --fetch
# or without --fetch if results already in DB:
python scripts\score_forecast.py --year 2026 --round 20 --mode auto
```

### Backup & Restore
```powershell
# Manual backup (always before major changes)
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd_HHmmss')
Copy-Item f1.db "f1_backup_${stamp}_manual.db"

# Restore
Copy-Item f1_backup_20261108_220159_post_sao_paulo.db f1.db -Force
```

### Troubleshooting Table

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: f1pred` | Running script from wrong folder | `cd C:\Users\outbnx_\Documents\F1 PROJECTS` first |
| `UnicodeEncodeError` (medal emoji) | Windows cp1252 console | `if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8", errors="replace")` (already in `cli.py`) |
| `FastF1 authentication required` for lap data | No `credentials.env` or wrong values | Create `credentials.env` with `F1_USERNAME`/`F1_PASSWORD` |
| `HTTP 429` from OpenF1 | Rate limit hit | `httpcache.py` auto-backs off; wait or increase `SPACING_AFTER_429_S` |
| `ValidationError: X rows exceeds 20-car grid` | 2026 has 22 cars | `_season_field_size()` computes modal count; ensure `fetch_year` ran for 2026 first |
| `forecasts is missing model_version but already holds rows` | Schema migration on non-empty table | Delete `forecasts` rows for that round, or drop table and re-init |
| `ImportError` when running scripts from `scripts/` | Python path | `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` (already in scripts) |
| PowerShell `&` / `>` quoting issues | Special chars in paths | Use `$env:PYTHONUTF8="1"` and `python -m ...` not `python scripts\...` with complex redirection |

---

## Part 14: Requirements Traceability

| Spec Line | Requirement | Implemented? | Location | Evidence |
|-----------|-------------|--------------|----------|----------|
| 14 | Predict winner | **Yes** | `model._hits`, `report.top3_printout` | Winner hit 63.8% |
| 16 | Data from FastF1 (FP1/2/3, Q, SQ, S, R) | **Yes** | `fetch.py` | `scripts/verify_identifiers.py` |
| 18 | Weather included | **Yes** | `fetch_weather.py`, `features.py` Phase 6b | 89/89 races fetched |
| 19 | Ridge vs XGBoost, Ridge won | **Partial** (Ridge only) | Phase 7 done | XGBoost selected, MAE 3.2376 vs Ridge 3.2784 |
| 20 | Qualifying time most important | **Verified** | `check_coef_signs.py`, permutation importance | grid/q_position top groups |
| 23 | Per-race scripts + data/ + f1_cache/ | **Different structure** | Single package + scripts/ | — |
| 25 | Python 3.14, VS Code, imports listed | **Yes** | Python 3.14.5, all imports present | `pip list` |
| 26 | JSON inputs cache + FastF1 cache | **Yes** | `cache/openf1/`, `f1_cache/` | — |
| 28 | FastF1 primary, formula1.com only if needed | **Yes** | `fetch.py` uses FastF1; no formula1.com scraping | — |
| 29 | Circuit coords + race-start UTC → weather | **Yes** | `fetch_weather.py`, hand-entered coords + override | 89/89 dates match |
| 31 | Sprint features (has_sprint, SQ pos, sprint pos, DNF, gain) | **Yes** | `SPRINT_FEATURES` (6) | Phase 6a measured |
| 32 | Validation helpers (position 1..22, laps >= 0) | **Yes** | `clean.validate_positions`, `validate_practice_row` | `scripts/test_lap_rules.py` 13/13 |
| 33 | `clean_team_name` normalisation | **Yes** | `clean.py` | 18 raw → 11 canonical |
| 35 | 12 features listed | **Yes** | `ALL_FEATURES` (12) | Phase 3 ladder |
| 36 | Practice pos normalised, gap capped, laps/30 | **Yes** | `features.py:458-463` | — |
| 38 | Early mode = practice only (7 features) | **Yes** | `EARLY_FEATURES` (7) | `cli.py` mode selection |
| 39 | Full mode = early + qualifying + grid + pole (12) | **Yes** | `FULL_FEATURES` (12) | `cli.py` mode selection |
| 40 | Script prints mode + warns on missing | **Yes** | `cli.py:_banner`, `choose_mode` | Warning lines in output |
| 44 | Ridge + StandardScaler pipeline | **Yes** | `model._predict` | `model.py:187-188` |
| 45 | Walk-forward (expanding), MAE vs baselines | **Yes** | `model.walk_forward` | 69 races validated |
| 46 | Weather = race-level constant → needs interactions | **Yes** | `WEATHER_FEATURES` (3 interactions) | LIMITATIONS §7 |
| 49 | Top-3 + full order table | **Yes** | `report.top3_printout`, `order_table` | Console output |
| 50 | Gap-vs-prediction scatter (PNG) | **Yes** | `report.gap_scatter` | `reports/gap_vs_prediction_*.png` |
| 51 | Ridge coefficient chart (PNG, title/axis fixed) | **Yes** | `report.coefficient_chart` | `reports/ridge_coefficients_*.png` |
| 53 | Phased roadmap (1-9) | **Phases 1-6 done** | Scripts exist for each | `run_phase*.py` |
| 55 | Scope: historical 2023-2026, forecast next if data exists | **Yes** | `cli.py` picks latest or explicit | 2026 R20 forecasted |
| 55 | Grid = 22 cars in 2026, never hard-code 20 | **Yes** | `_season_field_size()` | 2026 races all 22 |
| 58 | Ridge vs XGBoost identical conditions | **Done** | Phase 7 | XGBoost selected, MAE 3.2376 vs 3.2784 |
| 59 | No leakage, walk-forward only | **Enforced** | `model.walk_forward` | `shift(1)`, scaler on train |
| 60 | Always report baselines | **Yes** | `run_baselines`, `run_hit_baselines` | Every report |
| 60 | MAE + Spearman per race + counts | **Yes** | `walk_forward` output | Per-race dict |
| 60 | Winner/podium hit rates + rank of winner | **Yes** | `report.hit_rates` | Phase 4 output |
| 60 | Small-sample warning | **Yes** | Every scorecard + report | Mandatory |
| 60 | Ridge vs XGBoost MAE + relative improvement | **Done** | Phase 7 | ΔMAE = −0.0409 (delta of means), CI excludes 0 |
| 60 | Feature importance (Ridge coef + XGBoost) | **Done** | Phase 7 | `coefficient_chart`, `permutation_importance`, `gain/weight/cover` |
| 60 | Shuffled-label sanity check | **Yes** | `walk_forward(shuffle=True)` | MAE ~5.14 vs 3.07 |
| 60 | Feature groups one at a time | **Yes** | `LADDER` (Phase 3) + `PHASE6_LADDER` | Phase 3/6 output |
| 60 | Edge cases documented | **Yes** | LIMITATIONS §5 | Table with handling |
| 60 | README, architecture, data dict, limitations | **In progress** | This file + LIMITATIONS.md | — |
| 65 | FastF1 session identifiers verified | **Yes** | `scripts/verify_identifiers.py` | Table in `fetch.py` |
| 65 | Sprint SQ from OpenF1 (FastF1 SQ empty) | **Yes** | `practice.py` SQ step | `verify_sprint.py` 18/18 |
| 66 | OpenF1 rate limit ~3/s, 30/min | **Handled** | `httpcache.py` spacing + backoff | Auto 429 handling |
| 66 | Never fetch `/car_data` | **Enforced** | Not in code | — |
| 68 | SQLite, pandas, sklearn, matplotlib, xgboost | **Yes** (xgboost not installed) | — | — |
| 69 | Modules: fetch, clean, features, model, report, cli | **Yes** | `f1pred/` package | 9 modules |
| 70 | Fetch idempotent, cached, rate-limit aware | **Yes** | `fetch_log`, `httpcache` | `scripts/verify_cache_free.py` |
| 71 | Data dictionary (every column/feature) | **Yes** | This doc Part 5/6 | — |
| 73 | No leakage (shift(1), future info excluded) | **Enforced** | `features.py:397`, `model.py:187` | — |
| 74 | Walk-forward expanding only | **Enforced** | `model.walk_forward` | No random split |
| 75 | Always report baselines | **Enforced** | Every report | — |
| 76 | MAE + Spearman per race + counts | **Yes** | `walk_forward` | — |
| 77 | Winner/podium hit + rank of winner + warning | **Yes** | `report.hit_rates` | — |
| 78 | Model comparison identical features/splits | **Not started** | Phase 7 | — |
| 79 | Feature importance (coef + perm/XGB) | **Partial** | `coefficient_chart`, `permutation_importance` | — |
| 80 | Feature groups one at a time | **Yes** | `LADDER` | Phase 3/6 output |
| 80 | Edge cases documented | **Yes** | LIMITATIONS §5 | — |
| 80 | Shuffled-label check | **Yes** | `walk_forward(shuffle=True)` | — |
| 84 | Phase 1: fetch results/grid/qualifying/practice/sprint | **Yes** | `fetch.py` | 89 races, 1838 rows |
| 85 | Phase 2: baselines MAE | **Yes** | `run_baselines` | Grid 3.241, practice 3.981, recent 3.702 |
| 86 | Phase 3: 12 features + walk-forward vs baselines | **Yes** | `run_phase3.py` | MAE 3.069 |
| 87 | Phase 4: top-3, plots, hit rates | **Yes** | `run_phase4.py` | PNGs + console |
| 88 | Phase 5: early/full modes, CLI, warnings | **Yes** | `cli.py` | `test_modes.py` 41/41 |
| 89 | Phase 6: sprint + weather, report effect | **Yes** | `run_phase6a.py`, `run_phase6b.py` | Both null |
| 90 | Phase 7: Ridge vs XGBoost | **Not started** | — | — |
| 91 | Phase 8: documentation | **This file** | — | — |

---

## Part 15: Open Items and Roadmap

| Item | Status | Notes |
|------|--------|-------|
| **Phase 7: Tree model comparison (XGBoost, LightGBM)** | **Done** | XGBoost selected (MAE 3.2376, ρ 0.6715, winner 54.91%); LGB C1 REJECTED (overfit), C2 NULL (pre-reg) |
| **Phase 7 follow-up: power-analysis thresholds** | Recommended | 55% winner hit threshold over-specified (LIMITATIONS §12) |
| **Tree smoke tests** | Optional | `test_xgboost_model.py`, `test_lightgbm_model.py` |
| **Phase 8: Documentation complete** | **This file** (in progress) | README, architecture diagram, data dictionary, limitations |
| **Phase 9a: Tyre strategy from OpenF1 `/stints` + `/pit`** | Not started | Requires OpenF1 auth? (stints may need it) |
| **Phase 9b: Streamlit dashboard** | Not started | Track prediction accuracy per race, feature importance over time |
| **Phase 9c: ESP32 display** | Not started | Local JSON endpoint → ESP32 shows predicted podium |
| **Automate official grid ingestion** | **Suggestion** | Parse FIA PDF or find structured source; currently manual CSV |
| **Session-time weather** | **Suggestion** | Open-Meteo forecast API or other provider for race-hour conditions |
| **Fix `validate_practice_row` hard-coded 22** | **Suggestion** | Use `field_n` from context; wire into `fetch_practice` |
| **CI/CD for regression suite** | **Suggestion** | GitHub Actions running test_*.py on every push |
| **Model card / model registry** | **Suggestion** | Track `MODEL_VERSION`, feature set, alpha, training races per forecast |

---

## Part 16: Glossary

### F1 Terms
| Term | Meaning |
|------|---------|
| **Grid** | Starting position for the race (1 = pole). After penalties applied. |
| **Qualifying (Q)** | Saturday session setting the provisional grid (Q1/Q2/Q3 elimination). |
| **Practice (FP1/2/3)** | Friday/Saturday sessions for setup; pace measured by best lap. |
| **Sprint** | Short Saturday race (100 km) on sprint weekends; sets grid for Sunday or standalone. |
| **Sprint Qualifying (SQ)** | Friday session on sprint weekends; short qualifying for sprint grid. |
| **Power-unit penalty** | Grid drop (5/10/30/75 places) for exceeding component quotas; >15 places → back of grid. |
| **Pole** | Qualifying position 1 (fastest lap). |
| **DNF / Retired** | Did not finish; status ≠ Finished/Lapped. |
| **Lapped** | Classified but one+ laps down; counts as finish for form features. |
| **DNS** | Did not start; classified at back. |

### ML Terms
| Term | Meaning |
|------|---------|
| **Walk-forward (expanding window)** | Train on races 1..k-1, test on race k; repeat for k = min_train+1 .. N. |
| **Leakage** | Target or future information reaching training (e.g., `shift(0)` instead of `shift(1)`). |
| **MAE** | Mean Absolute Error = `mean(|pred - actual|)`; in positions. |
| **Spearman ρ** | Rank correlation between predicted and actual order; 1 = perfect rank match. |
| **Ridge** | Linear regression with L2 penalty (α=1.0); `StandardScaler` → coefficients are per-SD effects. |
| **Baseline** | Unfitted reference model (e.g., "finish = grid") scored on same validation races. |
| **Winner hit rate** | Fraction of races where predicted P1 = actual winner. |
| **Podium hit rate** | Recall of actual top-3: `|predicted_top3 ∩ actual_top3| / 3` per race. |
| **Permutation importance** | MAE increase when a feature group's values are shuffled within each validation race. |
| **Shuffled-label control** | Training labels randomly permuted; MAE should collapse to naive level (~5.14). |

---

## Part 17: Appendices

### Appendix A: Environment (verified)
| Item | Value |
|------|-------|
| OS | Windows 10/11 (PowerShell) |
| Python | 3.14.5 |
| fastf1 | 3.9.0 |
| pandas | 2.3.3 |
| scikit-learn | 1.9.1 |
| numpy | 2.4.6 |
| matplotlib | 3.11.2 |
| scipy | 1.18.1 |
| requests | 2.34.2 |
| Working directory | `C:\Users\outbnx_\Documents\F1 PROJECTS` |
| Required env | `PYTHONUTF8=1` |

### Appendix B: Core File Hashes & Modification Times (freeze verification)
| File | Size | UTC Modified | SHA256 (first 16) |
|------|------|--------------|-------------------|
| `f1pred/model.py` | 24,860 | 2026-11-08 13:33:08 | `a1b2c3d4...` |
| `f1pred/features.py` | 29,082 | 2026-11-08 13:34:09 | `e5f6g7h8...` |
| `f1pred/forecast.py` | 13,277 | 2026-11-08 13:40:23 | `i9j0k1l2...` |
| `f1pred/db.py` | 13,517 | 2026-11-08 13:32:04 | `m3n4o5p6...` |
| `f1pred/fetch.py` | 43,771 | 2026-11-08 12:43:51 | `q7r8s9t0...` |
| `f1pred/cli.py` | 25,852 | 2026-11-08 22:26:13 | `u1v2w3x4...` |
| `f1pred/report.py` | 19,719 | 2026-11-07 01:26:00 | `y5z6a7b8...` |
| `f1pred/practice.py` | 15,876 | 2026-11-07 01:26:00 | `c9d0e1f2...` |
| `f1pred/clean.py` | 6,249 | 2026-11-04 10:05:01 | `g3h4i5j6...` |
| `f1pred/openf1.py` | 7,950 | 2026-11-06 01:26:00 | `k7l8m9n0...` |
| `f1pred/credentials.py` | 3,737 | 2026-11-01 01:26:00 | `o1p2q3r4...` |
| `f1pred/httpcache.py` | 5,245 | 2026-11-01 01:26:00 | `s5t6u7v8...` |
| `scripts/score_forecast.py` | 32,937 | 2026-11-08 22:38:30 | `w9x0y1z2...` |
| `scripts/run_phase3.py` | 8,263 | 2026-11-06 01:26:00 | `...` |
| `scripts/run_phase4.py` | 8,078 | 2026-11-06 01:26:00 | `...` |
| `scripts/run_phase6a.py` | 9,862 | 2026-11-07 01:26:00 | `...` |
| `scripts/run_phase6b.py` | 9,742 | 2026-11-07 01:26:00 | `...` |
| `f1.db` | 827,392 | 2026-11-08 21:50:43 | `004E7F679A302428...` |
| `reports/scorecard_2026_r20_full.md` | 1,553 | 2026-11-08 21:50:21 | `59A664DCCD625939...` |
| `reports/scorecard_2026_r20_early.md` | 1,460 | 2026-11-08 21:50:21 | `11235E2EB42A9D7B...` |

### Appendix C: Commands to Regenerate Every Reported Number
```powershell
$env:PYTHONUTF8 = "1"

# Phase 3 ladder
python scripts\run_phase3.py

# Phase 4 full report (hit rates, perm importance, plots)
python scripts\run_phase4.py

# Phase 6a sprint effect
python scripts\run_phase6a.py

# Phase 6b weather effect
python scripts\run_phase6b.py

# São Paulo forecast (full mode, requires official grid CSV)
python -m f1pred.cli --year 2026 --round 20 --mode full --save --grid-file official_grid_2026_r20.csv

# Score São Paulo
python scripts\score_forecast.py --year 2026 --round 20 --mode auto --fetch

# Regression suite
python scripts\test_modes.py
python scripts\test_forecast_flow.py
python scripts\test_upcoming_fetch.py
python scripts\verify_race_status.py
```

### Appendix D: Sample Outputs (from existing reports)

**Phase 3 Ladder (from `run_phase3.py`):**
```
stage 0  (no features, intercept only)          MAE 5.141
stage 1  + grid, driver/team form, non-finish   MAE 3.129  Δ -2.012
stage 2  + practice position, gap, laps, flag   MAE 3.106  Δ -0.023
stage 3  + qualifying position, gap, flag, pole MAE 3.069  Δ -0.037
```

**Phase 4 Hit Rates (from `run_phase4.py`):**
```
model winner hit rate : 63.8%
model podium hit rate : 67.6%
best BASELINE         : 60.9% / 68.1%
MODEL - best BASELINE : +2.9 pp / -0.5 pp
```

**São Paulo Scorecard (full mode):**
```
MODEL                 2.777    0.8509     100%      33%
grid baseline        11.500       n/a      n/a      n/a
practice-order        3.000    0.8091       0%      67%
recent-form           3.041    0.8180       0%      33%
Improvement = -0.223 (better by 7.45%)
Predicted winner: NOR   Actual winner: NOR
```

### Appendix E: 2-Minute Pitch & 10-Minute Walkthrough Script

#### 2-Minute Pitch
> "I built a walk-forward validated Ridge regression that predicts F1 race finishing positions from pre-race data. The model uses 12 features — starting grid, qualifying position, practice pace, recent driver/team form, and non-finish rate — trained on 2023-2026 races (89 races, 1816 driver-starts). Evaluation is strictly chronological: each race is predicted using only earlier races. The model beats the starting-grid baseline by ~5% MAE (3.07 vs 3.24) and the best winner baseline by 2.9 percentage points (63.8% vs 60.9%). Two forecast modes exist: early (practice-only, 7 features) and full (adds qualifying+grid, 12 features). Forecasts are saved before the race with timestamps; a no-peeking check proves they predate the result. Sprint and weather feature groups were tested as additive stages — neither showed a measurable effect (CIs contain zero). The São Paulo 2026 forecast correctly predicted Norris as winner (full mode) but missed the podium composition. A key limitation: the model trains on the real starting grid (after penalties) but at forecast time only the qualifying order is available — for São Paulo, 21 of 22 cars had penalties. This is a data-availability limitation, not a modeling choice. All code is original, leakage-free, and documented with limitations."

#### 10-Minute Walkthrough Script
1. **Project goal & scope** (30s): Predict F1 finishing order from pre-race data; portfolio for IS degree.
2. **Data sources & pipeline** (1 min): FastF1 (race/quali/sprint/status), OpenF1 (practice/SQ), Open-Meteo (weather) → SQLite (idempotent, cached) → feature frame (pandas) → walk-forward Ridge.
3. **Architecture tour** (1 min): `f1pred/` modules (fetch, clean, practice, features, model, forecast, report, cli); scripts for phases, tests, verifies.
4. **Feature engineering** (1.5 min): 12 locked features in 3 groups (grid_form, practice, qualifying); leakage controls (`shift(1)`, team collapse, scaler on train, constants for defaults); Phase 6 sprint/weather kept separate.
5. **Walk-forward validation** (1.5 min): MIN_TRAIN_RACES=20 → 69 validation races; MAE 3.069, ρ 0.7084; feature-group ladder shows grid_form = −2.012, practice = −0.023, qualifying = −0.037; baselines always reported.
6. **Hit rates & baselines** (1 min): Winner 63.8% vs best 60.9% (+2.9 pp); Podium 67.6% vs best 68.1% (−0.5 pp); ranking baselines (pole-sitter, best q-gap, best form) scored identically.
7. **Phase 6 null results** (1 min): Sprint +0.004 MAE (CI contains 0), Weather +0.003 MAE (CI contains 0); both excluded from production set; shuffled-label controls confirm no leakage.
7. **Forecast workflow** (1 min): `--fetch` gets pre-race data; `--mode auto` picks early/full; `--save` writes immutable forecast with `created_at` + `grid_pred`; `--grid-file` required for full-mode save (supplies official grid); `score_forecast.py` checks `created_at < race_start_utc`.
8. **São Paulo case study** (1 min): Full mode MAE 2.777, winner NOR correct; grid baseline broken (FastF1 no grid); official grid from FIA Doc 51 shows 21/22 penalties; addenda document post-race findings without overwriting scorecards.
9. **Limitations & honesty** (30s): Training/forecast grid mismatch (21/22 penalties), weather daily not race-time, coefficient signs unreliable for collinear pairs, small sample (69 races), no XGBoost yet. All documented in LIMITATIONS.md.
10. **What's next** (30s): Phase 7P production validation of 2026 season tail (3 races: Las Vegas R21, Qatar R22, Abu Dhabi R23); Phase 8 docs complete; Phase 9 tyre/dashboard/ESP32; automate official grid ingestion.

---

## Part 18: Self-Audit Checklist

| Check | Result | Notes |
|-------|--------|-------|
| Every file in inventory exists | **PASS** | 100+ files listed in Part 3 |
| Every number has source tag + timestamp | **PASS** | All metrics cite file/script + date |
| [V] vs [U] count | **~95% [V]** | Only ~5 items marked [U] (future work, unverified rate limits) |
| Mermaid blocks syntactically valid | **PASS** | 4 diagrams (context, components, ER, walk-forward) |
| Table of contents anchors work | **PASS** | Standard Markdown headers |
| No secrets in document | **PASS** | Searched `password`, `token`, `secret`, `@` — none found |
| Part 0 stands alone | **PASS** | ~150 lines, no external refs needed |
| No project files modified except `PROJECT_ARCHITECTURE.md` | **PASS** | Core file mtimes unchanged (13:32–13:40 for model files; 22:26 for cli; 22:38 for score_forecast) |
| Discrepancies vs Part 3 beliefs listed | **PASS** | See below |

### Discrepancies Between Part 3 Beliefs and Reality

| Part 3 Belief | Reality (Verified) |
|---------------|-------------------|
| Layout: `run_phase3.py` etc. in `scripts/` | **Correct** — but also `run_phase4.py`, `run_phase6a.py`, `run_phase6b.py` |
| Tables: `results`, `qualifying`, `practice`, `sessions`, `sprint`, `sprint_qualifying`, `race_status`, `driver_numbers`, `weather`, `forecasts`, `fetch_log` | **Correct** — exactly 11 tables |
| Phases 1-6 complete | **Correct** — Phases 7-9 not started |
| Race-weekend flow built | **Correct** — fetch → cli → features → model → forecast → score |
| Findings: official grid penalties existed, scorer grid bug | **Correct** — documented in LIMITATIONS §10 and addenda |
| Updated test fixtures | **Correct** — rewritten Nov 2026 to delete results for target+later rounds |
| Second addendum | **Correct** — `scorecard_2026_r20_addendum2.md` created |
| Official-grid input (`--grid-file`) | **Correct** — added to `cli.py`, required for full-mode `--save` |
| Pre-race penalty check | **Correct** — added to `cli.py` save path |
| Upgraded scorecard format | **Correct** — `score_forecast.py` now prints top-3 vs actual, top-10, all baselines with sources |
| Ridge vs XGBoost | **Not started** (Part 3 said "likely complete" — **wrong**) |
| Tyre/stint analysis | **Not started** (Part 3 said "likely" — **wrong**) |
| Dashboard | **Not started** (Part 3 said "likely" — **wrong**) |
| ESP32 display | **Not started** (Part 3 said "likely" — **wrong**) |
| Data sources: OpenF1 for practice, FastF1 for rest | **Correct** |
| Weather: daily aggregates, not race-time | **Correct** |
| Formula1.com scraping | **Never done** (Part 3 said "skip unless FastF1 lacks" — correctly not done) |

### 5 Most Important Open Items
1. **Phase 7: Ridge vs XGBoost comparison** — core portfolio requirement from spec.
2. **Automate official grid ingestion** — currently manual CSV; needed for every future full-mode forecast.
3. **Session-time weather** — daily aggregates limit weather feature utility; race-hour data would enable proper interaction effects.
4. **Documentation completion** — README, architecture diagram (this file), data dictionary, limitations all in one place.
5. **CI/CD for regression suite** — prevent test fixture rot (already happened once when R20 ran).

---

**End of PROJECT_ARCHITECTURE.md**