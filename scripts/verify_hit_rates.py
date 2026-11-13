"""Independently recompute Phase 3's winner / podium / MAE / Spearman metrics.

The hit rates in run_phase3.py depend on argmin/argsort over a test frame, so
they are worth checking against a from-scratch computation that uses no model
code at all:

  * grid baseline winner hit = fraction of validation races where the car
    starting P1 (grid == 1) actually won;
  * grid baseline podium hit = |{grid 1,2,3} inter {finish 1,2,3}| / 3;
  * grid baseline MAE and Spearman recomputed per race and averaged.

Also asserts that a constant prediction now reports NaN instead of a fake
100% hit rate, and that rows inside a race are ordered by driver, not finish.

Run:  python scripts/verify_hit_rates.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model  # noqa: E402

con = db.connect()
df = features.build_features(con)
con.close()

ok = True


def chk(n, cond, label, detail="") -> None:
    global ok
    ok &= bool(cond)
    print(f"  [{n}] {label:<56} {'PASS' if cond else 'FAIL'}{detail}")


races = np.sort(df["race_idx"].unique())
min_train = model.MIN_TRAIN_RACES
val = df[df["race_idx"].isin(races[min_train:])].copy()
n_val = len(np.unique(val["race_idx"]))

print("=" * 78)
print(f"VALIDATION SET: {n_val} races, {len(val)} rows (race_idx "
      f"{int(races[min_train])}..{int(races[-1])})")
print("=" * 78)

# ------------------------------------------------- independent grid metrics
wins = 0
pod = 0.0
mae_list = []
rho_list = []

for _, grp in val.groupby("race_idx"):
    act = grp["finish"].to_numpy(float)
    prd = grp["grid"].to_numpy(float)

    wins += int(int(np.argmin(prd)) == int(np.argmin(act)))
    top_p = set(np.argsort(prd)[:3])
    top_a = set(np.argsort(act)[:3])
    pod += len(top_p & top_a) / 3

    mae_list.append(float(np.mean(np.abs(prd - act))))
    rho_list.append(float(spearmanr(prd, act)[0]))

ind_winner = wins / n_val
ind_podium = pod / n_val
ind_mae = float(np.mean(mae_list))
ind_rho = float(np.mean(rho_list))

print()
print("=" * 78)
print("INDEPENDENT RECOMPUTATION vs run_phase3.py OUTPUT")
print("=" * 78)
print(f"  grid baseline winner hit : {ind_winner:>7.1%}")
print(f"  grid baseline podium hit : {ind_podium:>7.1%}")
print(f"  grid baseline MAE        : {ind_mae:>7.4f}")
print(f"  grid baseline Spearman   : {ind_rho:>7.4f}")
print()

# what run_phase3.py produced last run
REPORTED = {"winner_hit": 0.5942028985507246,
            "podium_hit": 0.6811594202898551,
            "mae": 3.241, "rho": 0.6779}

chk(1, abs(ind_mae - REPORTED["mae"]) < 0.005,
    "grid MAE matches the reported value",
    f" ({ind_mae:.4f} vs {REPORTED['mae']:.3f})")
chk(2, abs(ind_rho - REPORTED["rho"]) < 0.005,
    "grid Spearman matches the reported value",
    f" ({ind_rho:.4f} vs {REPORTED['rho']:.4f})")
chk(3, abs(ind_winner - REPORTED["winner_hit"]) < 0.01,
    "grid winner hit matches the reported value",
    f" ({ind_winner:.4f} vs {REPORTED['winner_hit']:.4f})")
chk(4, abs(ind_podium - REPORTED["podium_hit"]) < 0.01,
    "grid podium hit matches the reported value",
    f" ({ind_podium:.4f} vs {REPORTED['podium_hit']:.4f})")

# ------------------------------------- constant prediction must be NaN now
print()
print("=" * 78)
print("CONSTANT PREDICTION: winner/podium must be undefined, not 100%")
print("=" * 78)
grp0 = val[val["race_idx"] == races[min_train]]
const = np.full(len(grp0), grp0["finish"].mean())
w0, p0 = model._hits(const, grp0["finish"].to_numpy(float))
print(f"  stage-0 prediction: constant {const[0]:.4f} over {len(grp0)} cars")
print(f"  _hits returns      : winner={w0} podium={p0}")
chk(5, np.isnan(w0) and np.isnan(p0),
    "constant prediction reports NaN, not a fake 100%",
    f" (was 100%/100% before the fix)")
r0 = model.walk_forward(df, [], min_train=min_train)
print(f"  walk_forward stage 0: MAE={r0['mae']:.3f} "
      f"winner={r0['winner_hit']} podium={r0['podium_hit']} "
      f"Spearman={r0['rho']}")
chk(6, np.isnan(r0["winner_hit"]) and np.isnan(r0["podium_hit"]),
    "stage 0 now reports n/a for hit rates")
chk(7, r0["mae"] > 5.0, "stage 0 MAE still the honest constant ~5.1",
    f" ({r0['mae']:.3f})")

# --------------------------------------------- row order is not the target
print()
print("=" * 78)
print("ROW ORDER WITHIN A RACE MUST NOT DEPEND ON finish")
print("=" * 78)
offending = 0
for _, grp in df.groupby("race_idx"):
    d = grp["driver"].tolist()
    if d != sorted(d):
        offending += 1
chk(8, offending == 0,
    "every race's rows are ordered by driver, not by finish",
    f" ({offending} races out of order)")
sample = df[df["race_idx"] == races[min_train]]
print(f"  first 6 drivers of race_idx {int(races[min_train])}: "
      f"{sample['driver'].tolist()[:6]}")
print(f"  their finishing positions        : "
      f"{sample['finish'].astype(int).tolist()[:6]}")
print("  (if rows were sorted by finish this list would read 1,2,3,4,5,6)")

con = None
print()
print("=" * 78)
print("HIT-RATE METRICS VERIFIED" if ok else "HIT-RATE METRICS FAILED")
print("=" * 78)
sys.exit(0 if ok else 1)
