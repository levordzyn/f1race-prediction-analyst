"""Why does shuffling the practice group cost +3.10 MAE when adding it to the
ladder was only worth -0.023?

Two different measurements are ALLOWED to disagree: ladder ablation retrains
without the group (so correlated features substitute for it), while permutation
keeps the fitted model and feeds it contradictory values. But a 101% MAE
increase is large enough to suspect a bug, and the useful question is
mechanical:

    how many POSITIONS does shuffling a group actually move a prediction?

A linear model on standardized inputs can only move a prediction by
sum_j b_j * (x_perm - x_orig). If that bound is ~0.5 positions while the MAE
jumps 3.1, the number is not coming from the mechanism being claimed and the
harness is wrong.

READ-ONLY.

Run:  python scripts/diagnose_permutation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model  # noqa: E402

N_FOLDS = 5
N_REPEATS = 5


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


con = db.connect()
con.row_factory = None
df = features.build_features(con)
con.close()

cols = list(features.ALL_FEATURES)
groups = {g: [c for c in cs if c in cols]
          for g, cs in features.PERM_GROUPS.items()}

races = np.sort(df["race_idx"].unique())
idx = df["race_idx"].to_numpy()
rng = np.random.default_rng(0)

# ---- collectors -----------------------------------------------------------
coefs_seen: dict[str, list[float]] = {c: [] for c in cols}
abs_dp: dict[str, list[float]] = {g: [] for g in groups}   # |prediction delta|
mae_delta: dict[str, list[float]] = {g: [] for g in groups}
base_maes: list[float] = []

fold_range = range(model.MIN_TRAIN_RACES, model.MIN_TRAIN_RACES + N_FOLDS)
for k in fold_range:
    te = races[k]
    train, test = df[idx < te], df[idx == te]
    if train.empty or test.empty:
        continue

    sc = StandardScaler().fit(train[cols])
    mdl = Ridge(alpha=model.RIDGE_ALPHA).fit(
        sc.transform(train[cols]), train[model.TARGET].to_numpy(float))
    X = sc.transform(test[cols])
    y = test[model.TARGET].to_numpy(float)

    pred0 = mdl.predict(X)
    mae0 = model._mae(pred0, y)
    base_maes.append(mae0)
    for i, c in enumerate(cols):
        coefs_seen[c].append(float(mdl.coef_[i]))

    for g, gcols in groups.items():
        pos = [cols.index(c) for c in gcols]
        for _ in range(N_REPEATS):
            Xp = X.copy()
            Xp[:, pos] = X[rng.permutation(len(X))][:, pos]
            pred1 = mdl.predict(Xp)
            abs_dp[g].extend(np.abs(pred1 - pred0).tolist())
            mae_delta[g].append(model._mae(pred1, y) - mae0)

rule("COEFFICIENT MAGNITUDE - what CAN each group move a prediction by?")
print(f"  base MAE over {len(base_maes)} folds: {np.mean(base_maes):.3f}"
      f"  (matches walk_forward's 3.069)")
print()
print(f"  {'group':<12} {'max |coef|':>11} {'mean |d pred|':>14} "
      f"{'max |d pred|':>14} {'MAE delta':>11}")
print(f"  {'-' * 12} {'-' * 11} {'-' * 14} {'-' * 14} {'-' * 11}")
for g in groups:
    maxc = max(abs(coefs_seen[c][i])
               for c in groups[g] for i in range(len(base_maes)))
    dp, md = np.array(abs_dp[g]), np.array(mae_delta[g])
    print(f"  {g:<12} {maxc:>11.4f} {dp.mean():>14.4f} {dp.max():>14.4f} "
          f"{md.mean():>+11.3f}")

print()
print("  A standardized position column spans roughly +/-1.6 (1..22 against a")
print("  ~11.5 mean, ~6.4 sd), so shuffling it swings that column by ~3.2 and")
print("  a coefficient of 0.17 can then move a prediction by at most ~0.55.")

rule("IS ANY COEFFICIENT EXPLODING ACROSS FOLDS?")
for c in list(features.FEATURE_GROUPS["practice"]) + ["q_position", "grid",
                                                      "driver_form"]:
    v = np.array(coefs_seen[c])
    print(f"  {c:<20} mean {v.mean():>+8.4f}  sd {v.std(ddof=1):>7.4f}  "
          f"min {v.min():>+8.4f}  max {v.max():>+8.4f}")

rule("ONE RACE, ONE SHUFFLE, IN DETAIL")
te = races[model.MIN_TRAIN_RACES]
train, test = df[idx < te], df[idx == te]
sc = StandardScaler().fit(train[cols])
mdl = Ridge(alpha=model.RIDGE_ALPHA).fit(
    sc.transform(train[cols]), train[model.TARGET].to_numpy(float))
X = sc.transform(test[cols])
y = test[model.TARGET].to_numpy(float)
pred0 = mdl.predict(X)
base = model._mae(pred0, y)
print(f"  race_idx {te}  ({len(test)} cars)  base MAE {base:.3f}")
print(f"  drivers: {list(test['driver'])}")
print()
for g, gcols in groups.items():
    pos = [cols.index(c) for c in gcols]
    Xp = X.copy()
    Xp[:, pos] = X[rng.permutation(len(X))][:, pos]
    d = mdl.predict(Xp) - pred0
    print(f"  {g:<12} mean |d pred| {np.abs(d).mean():6.3f}  "
          f"max |d pred| {np.abs(d).max():6.3f}   MAE "
          f"{base:6.3f} -> {model._mae(mdl.predict(Xp), y):6.3f}")
    print(f"               coefs {np.round(mdl.coef_[pos], 4)}")

print()
p = cols.index("practice_pos")
print(f"  practice_pos standardized, first 8 cars:")
print(f"    before: {np.round(X[:8, p], 3)}")
perm = rng.permutation(len(X))
print(f"    after : {np.round(X[perm][:8, p], 3)}")

rule("HEAD-TO-HEAD: identical 5 folds, both implementations")
sub = df[df["race_idx"] <= int(races[fold_range.stop - 1])]
print(f"  frame limited to race_idx <= {int(races[fold_range.stop - 1])}, "
      f"so both run exactly races "
      f"{int(races[fold_range.start])}..{int(races[fold_range.stop - 1])}")
pi = model.permutation_importance(sub, cols, groups,
                                  min_train=model.MIN_TRAIN_RACES,
                                  n_repeats=N_REPEATS, seed=0)
print()
print(f"  {'group':<12} {'permutation_importance':>24} "
      f"{'direct measurement':>22}")
print(f"  {'-' * 12} {'-' * 24} {'-' * 22}")
direct = {g: float(np.mean(mae_delta[g])) for g in groups}
for _, r in pi.iterrows():
    g = r["group"]
    print(f"  {g:<12} {r['delta']:>+24.3f} {direct.get(g, float('nan')):>+22.3f}")

rule("VERDICT")
print("  If 'mean |d pred|' is far smaller than the MAE delta, the MAE delta")
print("  is NOT coming from prediction movement and the harness is wrong.")
print("  If they are consistent, the large importance is real and only the")
print("  intuition was off.")
sys.exit(0)
