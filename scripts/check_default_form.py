"""How often does the hard-coded DEFAULT_FORM = 11.5 actually get used?

Appendix A comments it as "midfield value (22-car grid)". Our field is 20 cars
in 2023-2025 and 22 in 2026, so 11.5 is wrong for three of four seasons.

fillna(DEFAULT_FORM) fires exactly when a driver has NO previous race in the
dataset - their first-ever row. This measures:

  1. how many rows that is (out of 1816)
  2. what the correct midfield value is per season
  3. whether 11.5 vs the season-correct value changes any prediction

Run:  python scripts/check_default_form.py
"""
from __future__ import annotations

import sqlite3

import pandas as pd

con = sqlite3.connect("f1.db")
df = pd.read_sql("SELECT * FROM results", con)

print("=" * 78)
print("(1) HOW MANY ROWS GET THE FALLBACK?")
print("=" * 78)
df = df.dropna(subset=["finish"]).copy()
df = df.sort_values(["year", "round"]).reset_index(drop=True)

# fillna fires on a driver's first race: no previous finish to shift into.
first_race = df.groupby("driver").cumcount() == 0
print(f"  rows total                      : {len(df)}")
print(f"  driver's first race in dataset  : {int(first_race.sum())}")
print(f"  share of rows using 11.5        : "
      f"{100 * first_race.mean():.2f}%")

print()
print("  breakdown by season:")
for y, g in df.groupby("year"):
    fr = (g.groupby("driver").cumcount() == 0).sum()
    print(f"      {y}: {fr}/{len(g)} rows")

print()
print("=" * 78)
print("(2) WHAT IS THE CORRECT MIDFIELD VALUE PER SEASON?")
print("=" * 78)
print("  midfield = (field_size + 1) / 2")
for y, g in df.groupby("year"):
    # field size = drivers per race (mode, in case of a 19-car race)
    per_race = g.groupby(["year", "round"]).size()
    field = int(per_race.mode().iloc[0])
    correct = (field + 1) / 2
    flag = "  <-- matches 11.5" if correct == 11.5 else "  <-- 11.5 is WRONG"
    print(f"      {y}: field={field:>2}  correct={correct:>5}  "
          f"default=11.5{flag}")

print()
print("=" * 78)
print("(3) DOES IT CHANGE A PREDICTION?")
print("=" * 78)
# A first race has no history, so BOTH driver_form and team_form fall back.
# The model's prediction for that row shifts by coef * (11.5 - correct).
# We read the actual coefficients the eval produced.
coefs = {"driver_form": 0.868, "team_form": 0.903}
scaler_note = ("  (standardized, so the raw shift is smaller than coef alone -")
print("  eval coefficients: driver_form=0.868, team_form=0.903 (standardized)")
print()
for y in sorted(df["year"].unique()):
    per_race = df[df["year"] == y].groupby(["year", "round"]).size()
    field = int(per_race.mode().iloc[0])
    correct = (field + 1) / 2
    delta = 11.5 - correct
    n = int((first_race & (df["year"] == y)).sum())
    # both features fall back on a first race, so both contribute
    raw = delta * (coefs["driver_form"] + coefs["team_form"])
    print(f"      {y}: {n} rows, default off by {delta:+.1f} "
          f"-> ~{abs(raw):.2f} positions of raw (pre-scaling) error")

print()
print("  Only a driver's FIRST race is affected, and only if that driver")
print("  never raced before in our window (newcomers, mid-season replacements).")
print("  Impact is small but the constant is factually wrong for 2023-2025.")

print()
print("=" * 78)
print("FIX")
print("=" * 78)
print("  Derive the fallback from the data instead of hard-coding 11.5:")
print("      default_form = (field_size + 1) / 2")
print("  where field_size is the modal number of drivers per race.")
print("  Same for fillna(22) in the grid cleanup - use the race's own")
print("  driver count rather than a literal 22.")
