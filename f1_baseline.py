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
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

DB_PATH = Path("f1.db")
CACHE_DIR = Path("f1_cache")
FORM_WINDOW = 5      # how many previous races count as "recent form"
# NOTE: the "no history" default is no longer a module constant. Appendix A
# hard-coded DEFAULT_FORM = 11.5, which is only the midfield of a 22-car
# field; 2023-2025 run 20 cars, where midfield is 10.5. Both that default and
# the grid fallback are now derived per race in build_features().
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
    # fastf1 3.9.0 deprecates enable_cache() (FutureWarning, removal promised)
    # and its own source shows it is a thin wrapper that calls configure().
    # configure() takes cache_dir as a keyword-only argument.
    fastf1.Cache.configure(cache_dir=str(CACHE_DIR))

    done = {
        (y, r)
        for y, r in con.execute("SELECT DISTINCT year, round FROM results")
    }
    schedule = fastf1.get_event_schedule(year, include_testing=False)
    # datetime.utcnow() is deprecated (scheduled for removal); the aware
    # equivalent gives the same calendar date for this comparison.
    today = pd.Timestamp(datetime.now(timezone.utc).date())

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
        # Only claim "saved" when rows actually landed; a session that loads
        # but yields no results would otherwise report "saved ... (0 drivers)".
        if rows:
            print(f"  saved {year} R{rnd} {ev['EventName']} ({len(rows)} drivers)")
        else:
            print(f"  no result rows for {year} R{rnd} {ev['EventName']} "
                  f"- nothing saved")


# ---------------------------------------------------------------- features
def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add grid cleanup + recent-form features. Uses only PAST races (no leakage)."""
    df = df.dropna(subset=["finish"]).copy()
    df = df.sort_values(["year", "round"]).reset_index(drop=True)

    # Cars per race: 20 in 2023-2025, 22 in 2026. Both hard-coded 22s from
    # Appendix A are derived from this instead of a literal.
    field_n = df.groupby(["year", "round"])["driver"].transform("size")
    # "Midfield" for a driver/team with no history yet - the middle of the
    # field they are actually racing in (10.5 for 20 cars, 11.5 for 22).
    default_form = (field_n + 1) / 2

    # Pit-lane starts show up as 0 or missing: treat them as last on the grid.
    race_max = df.groupby(["year", "round"])["grid"].transform("max")
    bad = df["grid"].isna() | (df["grid"] <= 0)
    # Fall back to this race's own car count, not a literal 22: in a 20-car
    # field the literal would place a pit-lane starter at position 23.
    df.loc[bad, "grid"] = race_max.fillna(field_n) + 1

    # Driver form: average of previous finishes (shift(1) excludes current race).
    df["driver_form"] = (
        df.groupby("driver")["finish"]
        .transform(lambda s: s.shift(1).rolling(FORM_WINDOW, min_periods=1).mean())
        .fillna(default_form)
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
    # merge() hands back a fresh RangeIndex, so rebuild the default here
    # rather than reusing the pre-merge Series (index alignment would break).
    df["team_form"] = df["team_form"].fillna(
        (df.groupby(["year", "round"])["driver"].transform("size") + 1) / 2
    )

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
