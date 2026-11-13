# PROMPT: Build an F1 Race Prediction Project (modeled on a series of reference videos). Paste everything below into the AI.

## 1. Your role
You are a patient senior data engineer and ML mentor helping a beginner build a portfolio project step by step. Prioritize **correctness and verifiability over speed**. Never invent facts, library functions, API fields, column names, or numbers. If unsure, say "I am not sure" and tell me how to check.

## 2. About me
- University student, Information Systems (technical + business-oriented), ITS Surabaya. Beginner in Python/ML.
- Optional hardware (not needed for the core project): ESP32-WROOM-32D, STM32F401RCT6, two LM2596.
- Goal: a clean, honest, documented portfolio project (README, data dictionary, evaluation, limitations).

## 3. Reference: the project I want to recreate (from a series of short social-media videos)
I will build **my own version** (original code, not a copy) of a project shown in short videos by one creator. Each video covers a different Grand Prix, but it is the **same project** (for example, the Austin video is titled roughly "Let's build an ML model to predict the Austin GP winner", 2026 United States GP at Circuit of the Americas; the creator's folder also has scripts for Baku, Madrid, and Singapore). Items below come from on-screen frames plus the creator's spoken explanation (typed out by me) and are **observed** unless marked *(inferred)*.

**Creator's explanation (spoken narration, paraphrased)**
- Goal: predict the **winner** of the Grand Prix.
- All data is pulled from the **FastF1 API**: qualifying, **sprint qualifying**, and the **sprint race**.
- Sprint qualifying matters because it is another measure of each driver's one-lap speed.
- **Weather** is included as a feature.
- She tested both **XGBoost** and **Ridge regression**; Ridge performed better, by **14%**. What the 14% measures (MAE? accuracy? relative to which baseline?) was not stated, so treat it as unknown.
- **Qualifying time** is still the most important feature for predicting who wins.
- It is an ongoing series ("if you've been following along"), so the features were built up over earlier videos.

**Project structure (observed)**
- Folder `2026f1preds` with one script per iteration (`prediction1.py` ... `prediction12.py`), plus a `data/` folder, an `f1_cache/` folder, `.env.example`, and per-race outputs (Baku, Madrid, Singapore, Austin forecasts/models/CSV-like files). Later scripts import from earlier ones (`from prediction10 import ...`).
- Python 3.14, VS Code. Imports: `argparse`, `ThreadPoolExecutor`, `hashlib`, `json`, `pathlib`, `numpy`, `pandas`, `requests`, `fastf1`, scikit-learn (`Ridge`, `make_pipeline`, `StandardScaler`).
- Data is cached to disk: a JSON inputs cache per race and a FastF1 cache directory.

**Data inputs (observed)**
- Official results tables per race, fetched via `requests` from formula1.com results pages (a `TARGET` URL for the race, with sub-tables for practice/3, qualifying, and starting-grid). *(The narration says the data comes from the FastF1 API, so use FastF1 as the primary source (FP1/FP2/FP3/Q/SQ/S/R sessions) and skip formula1.com scraping unless FastF1 lacks something. Check formula1.com's terms and robots rules before scraping anything.)*
- Circuit coordinates + race-start UTC hour per venue, used to fetch weather. Weather variables used: temperature_2m, relative_humidity_2m, precipitation, wind_speed_10m. *(inferred: these names match the Open-Meteo API. VERIFY.)*
- Sprint-weekend handling: a set of sprint venues for 2026 and sprint features (has_sprint, sprint-qualifying position, sprint position, sprint DNF, sprint gain).
- Validation helpers: rows are checked (e.g., practice position must be 1..22 and lap count >= 0; qualifying positions must be 1..22) and the code raises a clear error otherwise. A `clean_team_name` function normalizes team names.

**Features (observed from the coefficient chart labels)**
Starting grid; Qualifying position; Qualifying gap (%) to fastest lap; No qualifying time (missing flag); Recent driver form; Recent team form; Recent non-finish rate; Practice position; Practice gap (%); Practice laps / 30; No practice time (missing flag); Qualified on pole.
Seen in code: practice position is normalized as (position-1)/21; practice gap is capped (about 10%) and set to 0 when missing; practice laps divided by 30.

**Two forecast modes (observed)**
1. **Early / practice-based provisional forecast** (before qualifying exists): uses practice + recent-form features.
2. **Full forecast** (after qualifying/starting grid is published): adds qualifying and grid features and the pole effect.
The script prints which mode it used and warns when qualifying/grid is unavailable.

**Model and evaluation (observed)**
- Ridge regression in a scikit-learn pipeline with StandardScaler, predicting finishing position. Per the narration, XGBoost was also tested and Ridge won, so Ridge is the final model.
- **Chronological, walk-forward validation.** Console line on screen: "Trained on 17 completed races | 11 chronological validation races". Reports **walk-forward MAE** (in positions) for the model versus baselines: practice-order baseline and recent-form baseline (early mode), starting-grid baseline (full mode).
- A code comment notes that shared race weather alone shifts all drivers' scores equally in a linear model, so weather only matters through **interaction terms** with driver/team features.

**Outputs (observed)**
- Top-3 predicted finishers printed with medals, plus the full predicted order table.
- Scatter plot: qualifying (or practice) gap to fastest lap (%) on x versus predicted finishing position on y (inverted axis, 22 cars), each point labeled with the driver code. Saved as PNG.
- Horizontal bar chart of Ridge coefficients, titled "ridge feature coefficients (positive = worse finish)", x-axis "predicted finish change per feature standard deviation (positions)". In the video, practice position, qualifying position, and recent team form had the largest positive coefficients, and "qualified on pole" was negative. Treat these as her results, not as targets I must reproduce.

**Not visible or unknown (do not assume):** what the "14% better" refers to, the XGBoost settings, the exact formulas for "recent form" and "non-finish rate", the exact interaction terms, how drivers without history are handled, the predicted winner of each race, and her accuracy beyond what is on screen.

## 4. My project goal
Build my own pipeline that, for any completed 2026 race (and later for an upcoming one), produces the same kinds of outputs as above: the predicted **winner** and full finishing order, top 3, walk-forward MAE versus baselines, the gap-vs-prediction scatter plot, and the coefficient chart. Also compare Ridge against XGBoost under identical conditions.

Scope: completed historical races (2023-2026 where data exists) for training and validation; "forecast" mode for the next race only if the required session data is already published. The grid has **22 cars in 2026**. Do not hard-code 20.

## 5. Data sources, facts, and limits
Treat **[VERIFY]** items as unconfirmed. Before writing parsing code, fetch ONE real sample and print its actual columns/keys. Do not guess field names.
- **FastF1** (Python, primary source): `fastf1.get_session(year, round_or_name, identifier)` with identifiers such as FP1, FP2, FP3, Q, SQ, S, R **[VERIFY against installed version]**. Sprint weekends have a different session set (sprint qualifying and a sprint race), so check each event's format before requesting sessions. `session.results` has columns such as Abbreviation, TeamName, GridPosition, Position **[VERIFY]**. Lap counts and best lap times need laps loaded. Enable its cache; first downloads are slow. Qualifying times are in Q1/Q2/Q3 columns **[VERIFY]**.
- **OpenF1** (REST, https://api.openf1.org/v1): data from 2023; historical needs no auth; free rate limit about 3 req/s and 30 req/min **[VERIFY]**. Useful later for tyre `/stints` and `/pit`. `/car_data` is ~3.7 Hz and large; never fetch it for a whole race.
- **Weather:** a free historical/forecast weather API keyed by latitude, longitude, and race-start hour **[VERIFY provider, variables, and rate limits]**.
- **Not in public data:** battery/ERS state of charge, engine temperature, power output, fuel load. Never imply otherwise.

## 6. Architecture
- Python 3.10+, SQLite (or Parquet/CSV if simpler), pandas, scikit-learn, matplotlib; `xgboost` only for the model comparison. Minimal dependencies.
- Modules: `fetch` (sessions, weather), `clean` (team-name normalization, validation), `features`, `model` (Ridge + walk-forward), `report` (console + plots), `cli` (argparse: choose year/round/mode).
- Fetching must be **idempotent**, cached, rate-limit-aware (backoff on HTTP 429), and tolerant of missing data (log and skip, do not crash). Use parallel fetching (e.g., ThreadPoolExecutor) only after the sequential version works.
- Keep a `data dictionary` documenting every column and feature definition.

## 7. ML rules (strict)
- **No leakage:** a race's features may only use information available before that race, or at the forecast time for that mode (practice-only for early mode; practice + qualifying + grid for full mode). Rolling form features must exclude the target race.
- **Walk-forward (expanding-window) validation only:** for each validation race, train on all earlier races and predict that race. Never random-split.
- **Always report baselines** next to the model: practice-order, recent-form, and starting-grid baselines. If the model does not beat them, say so plainly.
- Report MAE (positions) and Spearman rank correlation per race (averaged), plus the number of races and rows used.
- Because the goal is "predict the winner", also report **winner hit rate** (top-1), **podium hit rate**, and the rank the model gave the actual winner, with a clear warning that the number of races is small.
- **Model comparison (Ridge vs XGBoost):** use identical features and identical walk-forward splits. Report MAE for both and the relative improvement, stating the exact formula (for example (MAE_xgb - MAE_ridge) / MAE_xgb). Keep XGBoost modest (shallow trees, few estimators) given the small number of races. Do not assume Ridge wins; show it with numbers.
- **Feature importance:** Ridge standardized coefficients, and XGBoost feature importance or permutation importance. Check whether qualifying time/position is the top feature, as the creator claims.
- Define features explicitly and document edge cases: missing practice/qualifying times (use a missing flag plus a documented fill), DNFs, pit-lane starts (grid 0 or missing), sprint weekends (different session structure), team renames/new teams across seasons, drivers with no history.
- Add feature groups **one at a time** and show before/after MAE: (1) grid, driver form, team form; (2) practice; (3) qualifying + pole; (4) sprint features; (5) weather with interaction terms.
- F1 is noisy (safety cars, strategy, reliability). Do not overclaim; with ~17 training races, treat results as weak evidence. Suggest sanity checks (e.g., randomly shuffled labels should destroy performance).

## 8. Phased roadmap (finish and verify each phase before the next)
1. **Data:** fetch results, grid, qualifying, practice, and sprint data for completed races into SQLite. Accept: about 22 drivers per race, re-running adds nothing, no crashes on missing data.
2. **Baselines:** compute grid, practice-order, and recent-form baselines and their MAE.
3. **Features + Ridge:** build the 12 features; walk-forward evaluation; compare to baselines.
4. **Reports:** top-3 printout, predicted-order table, scatter plot, coefficient bar chart (saved as PNG).
5. **Modes + CLI:** early (practice-only) and full (after qualifying) modes; clear messages when data is missing.
6. **Weather + sprint features:** add sprint qualifying (a second one-lap-speed measure), sprint race results, and weather (with interaction terms); report whether MAE improved after each.
7. **Model comparison:** Ridge vs XGBoost with identical walk-forward validation; winner/podium hit rates; feature importance.
8. **Documentation:** README, architecture diagram, data dictionary, evaluation method, limitations.
9. *(Optional extensions for my IS portfolio)* tyre strategy analysis from OpenF1 `/stints` and `/pit`; a Streamlit dashboard tracking prediction accuracy per race; an ESP32 display showing the predicted podium from a local JSON endpoint (prediction always runs on the laptop).

## 9. Rules for how you respond
1. Work **one phase at a time**, starting at the earliest unfinished phase.
2. Before code that depends on an API/library, list the exact functions/fields you rely on and how I can verify them (print one sample).
3. Give **complete, runnable code** (no "...rest of code"), say which file it belongs in, and keep my existing working code unless there is a concrete bug.
4. After each code block give: the exact run command, what correct output looks like, and the 2-3 most likely errors with fixes.
5. Keep explanations short and beginner-friendly in bullets; explain WHY, not just what.
6. If results look too good, investigate leakage first and tell me.
7. Point out mistakes or weak design honestly, including in code I paste.
8. If a request is ambiguous, ask ONE focused question; otherwise state your assumption and continue.
9. Do not add features I did not ask for.
10. Respond in English (or Bahasa Indonesia if I ask).

## 10. First task
I have a simple starter script (Appendix A) that loads race results with FastF1 into SQLite and compares a Ridge model (grid + driver form + team form) against the "finish = grid" baseline. Its logic was tested only on synthetic data, never on real FastF1 downloads. It does NOT yet include practice, qualifying, weather, sprint features, modes, or plots.

Your first job:
1. Review Appendix A for bugs, leakage, and FastF1 misuse; list issues by severity.
2. Tell me how to run it on real data and what sanity checks to expect.
3. Then propose the exact Phase 1 extension to fetch practice (FP3 or the last practice) and qualifying data, with the fields you will rely on.
Do not start Phase 3 until I confirm Phases 1-2 work.

---

## Appendix A: starter script (`f1_baseline.py`)

```python
"""
F1 finishing-position baseline (beginner starter)

Steps:
  1. fetch  -> download race results with FastF1 and store them in SQLite
  2. eval   -> compare baseline (finish = grid) vs a Ridge model

Setup:
  pip install fastf1 pandas scikit-learn

Usage:
  python f1_baseline.py fetch --years 2023 2024 2025 2026
  python f1_baseline.py eval --test-races 5
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DB_PATH = Path("f1.db")
CACHE_DIR = Path("f1_cache")
FORM_WINDOW = 5      # how many previous races count as "recent form"
DEFAULT_FORM = 11.5  # midfield value (22-car grid) when a driver/team has no history
FEATURES = ["grid", "driver_form", "team_form"]


# ---------------------------------------------------------------- database
def init_db(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS results (
            year   INTEGER,
            round  INTEGER,
            event  TEXT,
            driver TEXT,
            team   TEXT,
            grid   REAL,
            finish REAL,
            PRIMARY KEY (year, round, driver)
        )
        """
    )
    con.commit()


# ------------------------------------------------------------------- fetch
def fetch_season(year: int, con: sqlite3.Connection) -> None:
    import fastf1  # imported here so `eval` works without FastF1 installed

    CACHE_DIR.mkdir(exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))

    done = {
        (y, r)
        for y, r in con.execute("SELECT DISTINCT year, round FROM results")
    }
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    today = pd.Timestamp(datetime.utcnow().date())

    for _, ev in schedule.iterrows():
        rnd = int(ev["RoundNumber"])
        if (year, rnd) in done:
            continue
        if pd.Timestamp(ev["EventDate"]).tz_localize(None) > today:
            continue  # race has not happened yet

        try:
            session = fastf1.get_session(year, rnd, "R")
            session.load(laps=False, telemetry=False, weather=False, messages=False)
            res = session.results
        except Exception as exc:  # network errors, missing data, etc.
            print(f"  skip {year} R{rnd}: {exc}")
            continue

        rows = [
            (
                year,
                rnd,
                str(ev["EventName"]),
                str(r["Abbreviation"]),
                str(r["TeamName"]),
                float(r["GridPosition"]) if pd.notna(r["GridPosition"]) else None,
                float(r["Position"]) if pd.notna(r["Position"]) else None,
            )
            for _, r in res.iterrows()
        ]
        con.executemany(
            "INSERT OR REPLACE INTO results VALUES (?,?,?,?,?,?,?)", rows
        )
        con.commit()
        print(f"  saved {year} R{rnd} {ev['EventName']} ({len(rows)} drivers)")


# ---------------------------------------------------------------- features
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add grid cleanup + recent-form features. Uses only PAST races (no leakage)."""
    df = df.dropna(subset=["finish"]).copy()
    df = df.sort_values(["year", "round"]).reset_index(drop=True)

    # Pit-lane starts show up as 0 or missing: treat them as last on the grid.
    race_max = df.groupby(["year", "round"])["grid"].transform("max")
    bad = df["grid"].isna() | (df["grid"] <= 0)
    df.loc[bad, "grid"] = race_max.fillna(22) + 1

    # Driver form: average of previous finishes (shift(1) excludes current race).
    df["driver_form"] = (
        df.groupby("driver")["finish"]
        .transform(lambda s: s.shift(1).rolling(FORM_WINDOW, min_periods=1).mean())
        .fillna(DEFAULT_FORM)
    )

    # Team form: team's average finish per race, then rolling over previous races.
    team_race = (
        df.groupby(["team", "year", "round"], as_index=False)["finish"]
        .mean()
        .sort_values(["team", "year", "round"])
    )
    team_race["team_form"] = team_race.groupby("team")["finish"].transform(
        lambda s: s.shift(1).rolling(FORM_WINDOW, min_periods=1).mean()
    )
    df = df.merge(
        team_race[["team", "year", "round", "team_form"]],
        on=["team", "year", "round"],
        how="left",
    )
    df["team_form"] = df["team_form"].fillna(DEFAULT_FORM)

    # One id per race, in time order.
    df["race_id"] = df.groupby(["year", "round"]).ngroup()
    return df


# -------------------------------------------------------------- evaluation
def spearman_per_race(df: pd.DataFrame, pred_col: str) -> float:
    vals = [
        g[pred_col].corr(g["finish"], method="spearman")
        for _, g in df.groupby("race_id")
    ]
    return float(np.nanmean(vals))


def evaluate(df: pd.DataFrame, test_races: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Time-based split: train on older races, test on the most recent ones."""
    cutoff = df["race_id"].max() - test_races + 1
    train = df[df["race_id"] < cutoff].copy()
    test = df[df["race_id"] >= cutoff].copy()
    if train.empty or test.empty:
        raise SystemExit("Not enough races. Fetch more seasons or lower --test-races.")

    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    model.fit(train[FEATURES], train["finish"])

    test["pred_baseline"] = test["grid"]
    test["pred_model"] = model.predict(test[FEATURES])

    print(f"Train rows: {len(train)} | Test rows: {len(test)} "
          f"| Test races: {test['race_id'].nunique()}")
    print("\n                      MAE (lower=better)   Spearman (higher=better)")
    for name, col in [("Baseline (grid)", "pred_baseline"), ("Ridge model", "pred_model")]:
        mae = (test[col] - test["finish"]).abs().mean()
        rho = spearman_per_race(test, col)
        print(f"{name:<22}{mae:>10.3f}{rho:>25.3f}")

    coefs = dict(zip(FEATURES, model.named_steps["ridge"].coef_))
    print("\nModel weights (standardized):",
          {k: round(float(v), 3) for k, v in coefs.items()})
    return train, test


def show_last_race(test: pd.DataFrame) -> None:
    last = test[test["race_id"] == test["race_id"].max()].copy()
    last["pred_order"] = last["pred_model"].rank(method="first").astype(int)
    last = last.sort_values("pred_order")
    print(f"\nPredicted vs actual: {last['year'].iloc[0]} {last['event'].iloc[0]}")
    print(last[["pred_order", "driver", "grid", "finish"]].head(10).to_string(index=False))


# --------------------------------------------------------------------- cli
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="download race results into SQLite")
    f.add_argument("--years", type=int, nargs="+", required=True)

    e = sub.add_parser("eval", help="compare baseline vs Ridge model")
    e.add_argument("--test-races", type=int, default=5)

    args = ap.parse_args()
    con = sqlite3.connect(DB_PATH)
    init_db(con)

    if args.cmd == "fetch":
        for y in args.years:
            print(f"Fetching {y} ...")
            fetch_season(y, con)
    else:
        df = pd.read_sql("SELECT * FROM results", con)
        if df.empty:
            raise SystemExit("Database is empty. Run `fetch` first.")
        df = build_features(df)
        _, test = evaluate(df, args.test_races)
        show_last_race(test)

    con.close()


if __name__ == "__main__":
    main()
```
