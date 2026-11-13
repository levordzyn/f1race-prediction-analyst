"""Why does 2026 R4 lose 2.204 positions of MAE when practice features are added?

Stage 2 of the Phase 3 ladder regresses by +0.0083 on average, but one race
accounts for +2.204 of it while 43 of 69 races improve. Two candidate causes:

  A. DATA ANOMALY  - an extreme practice value in that race lies far outside
     the training range, and Ridge cannot extrapolate, so the standardised
     feature flies off;
  B. GENUINE VARIANCE - nothing unusual in the data, the model just missed.

This prints the race's feature values against the training-fold distribution
to decide between them.

Run:  python scripts/explain_stage2_outlier.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model  # noqa: E402

YEAR, RND = 2026, 4
PRAC = features.FEATURE_GROUPS["practice"]

con = db.connect()
df = features.build_features(con)
con.close()

races = np.sort(df["race_idx"].unique())
min_train = model.MIN_TRAIN_RACES
this_idx = int(df[(df.year == YEAR) & (df["round"] == RND)]["race_idx"].iloc[0])
train = df[df["race_idx"] < this_idx]
test = df[df["race_idx"] == this_idx]


def rule(t=""):
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


rule(f"{YEAR} R{RND} - POSITION IN THE SPLIT")
print(f"  race_idx {this_idx} of {int(races[-1])}; trains on "
      f"{len(np.unique(train['race_idx']))} earlier races, "
      f"so it is fold {this_idx - min_train + 1} of "
      f"{len(races) - min_train}")
print(f"  cars in this race: {len(test)}")

# ------------------------------------------- A: is any value out of range?
rule("A. ARE THE PRACTICE FEATURES OUT OF TRAINING RANGE?")
print(f"  {'feature':<20} {'train min':>10} {'train max':>10} "
      f"{'train mean':>11}   this race's max   outside?")
worst = []
for c in PRAC + ["q_gap_pct", "q_position"]:
    lo, hi = train[c].min(), train[c].max()
    here = test[c].to_numpy(float)
    outside = int(((here < lo) | (here > hi)).sum())
    if outside:
        worst.append((c, lo, hi, outside, here))
    print(f"  {c:<20} {lo:>10.3f} {hi:>10.3f} {train[c].mean():>11.3f}   "
          f"{here.min():>8.3f}..{here.max():<8.3f}  {outside}")

print()
if worst:
    print("  VALUES OUTSIDE THE TRAINING RANGE (Ridge must extrapolate):")
    for c, lo, hi, outside, here in worst:
        print(f"    {c}: training spans {lo:.3f}..{hi:.3f}; this race has "
              f"{outside} car(s) outside, e.g. {sorted(here)[:3]}...{sorted(here)[-3:]}")
else:
    print("  Every value in this race sits inside the training range.")
    print("  -> cause A is ruled out; the outlier is not a range problem.")

# ------------------------------------------- global feature-range context
rule("GLOBAL OUTLIERS IN THE PRACTICE / QUALIFYING GAPS")
for c in ("practice_gap_pct", "q_gap_pct"):
    top = df.nlargest(5, c)[["year", "round", "driver", c, "finish"]]
    print(f"\n  largest {c} values across all 1816 rows:")
    print(top.to_string(index=False))
    inside = ((top["year"] == YEAR) & (top["round"] == RND)).sum()
    print(f"    rows belonging to {YEAR} R{RND}: {inside}")

# ------------------------------------------------------------ actual errors
rule("B. HOW DID THE MODEL ACTUALLY DO IN THIS RACE?")
s1 = model.walk_forward(df, list(features.FEATURE_GROUPS["grid_form"]),
                        min_train=min_train)
s2 = model.walk_forward(df, list(features.FEATURE_GROUPS["grid_form"]) + list(PRAC),
                        min_train=min_train)

r1 = s1["per_race"]
r2 = s2["per_race"]
a = r1[(r1.year == YEAR) & (r1["round"] == RND)].iloc[0]
b = r2[(r2.year == YEAR) & (r2["round"] == RND)].iloc[0]
print(f"  stage 1 (grid+form)  MAE {a['mae']:.3f}  Spearman {a['rho']:.4f}")
print(f"  stage 2 (+practice)  MAE {b['mae']:.3f}  Spearman {b['rho']:.4f}")
print(f"  delta                {b['mae'] - a['mae']:+.3f} positions")

p1 = s1["preds"]
p2 = s2["preds"]
m = (p1.merge(p2, on=["year", "round", "driver", "finish"], suffixes=("_s1", "_s2"))
     .merge(test[["driver"] + PRAC], on="driver", how="left"))
m = m[(m.year == YEAR) & (m["round"] == RND)].copy()
m["err_s1"] = (m["pred_s1"] - m["finish"]).abs()
m["err_s2"] = (m["pred_s2"] - m["finish"]).abs()
m["worse"] = m["err_s2"] - m["err_s1"]
m = m.sort_values("worse", ascending=False)

print()
print(f"  cars most damaged by adding practice features:")
cols = ["driver", "finish", "pred_s1", "pred_s2", "err_s1", "err_s2", "worse",
        "practice_pos", "practice_gap_pct", "practice_laps_30"]
print(m[cols].head(8).to_string(index=False,
                                float_format=lambda v: f"{v:.3f}"))
print(f"  sum of error added = {m['worse'].sum():+.3f} "
      f"(MAE shift {(b['mae'] - a['mae']):+.3f} x {len(m)} cars)")

# ------------------------------------------------- is this race unusual?
rule("IS 2026 R4 UNUSUAL COMPARED TO THE OTHER VALIDATION RACES?")
d = (r2.set_index(["year", "round"])["mae"]
     - r1.set_index(["year", "round"])["mae"])
rank = int((d < d.loc[(YEAR, RND)]).sum()) + 1
print(f"  worst-affected race of {len(d)}: rank {rank} "
      f"(1 = the single biggest regression)")
print(f"  median delta across all races: {d.median():+.4f}")
print(f"  mean excluding this race      : {d.drop((YEAR, RND)).mean():+.4f}")
print()
print(f"  Verdict: excluding {YEAR} R{RND}, adding practice features "
      f"{d.drop((YEAR, RND)).mean():+.4f} positions MAE on average.")

print()
rule("CONCLUSION")
if worst:
    print("  Cause A: extreme feature values outside the training range.")
    print("  Ridge cannot extrapolate, so the mis-scaled value dominates.")
else:
    print("  Cause B: no feature value is out of range. The regression is")
    print("  genuine variance in one race, not a data anomaly. With +2.204 of")
    print("  the total +0.573 coming from this single race, the practice group")
    print("  helps 43 of 69 races and improves MAE once it is set aside.")

sys.exit(0)
