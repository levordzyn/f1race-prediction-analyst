"""Phase 6b companion: does the choice of Ridge alpha matter, and if we
CHOOSE it, do we choose it without ever looking at validation data?

WHY THIS EXISTS
  The project rule is: any regularization strength may only be chosen inside
  the walk-forward TRAINING window. The Phase 6 headline deliberately does
  NOT choose at all - alpha stays at the pre-registered RIDGE_ALPHA = 1.0 for
  every stage, so a before/after delta measures the feature group and nothing
  else. If stage 5 used a tuned alpha and stage 3 did not, the delta would be
  measuring a tune, not the weather.

  This script therefore answers the question honestly instead of dodging it:
  run a NESTED expanding-window selection, where for each outer fold the
  alpha is picked by inner CV over races strictly before that fold, then
  report (a) what the inner window picks and (b) whether it would actually
  beat the fixed 1.0 on the outer fold.

  Validation data is never consulted for the selection: the inner loop only
  ever sees races < the outer fold's race.

Run:  python scripts/check_alpha_window.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from f1pred import db, features, model

GRID = [0.01, 0.1, 1.0, 10.0, 100.0]
MIN_INNER_TRAIN = 12   # inner folds need some history before they start


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def _mae(pred: np.ndarray, act: np.ndarray) -> float:
    return float(np.mean(np.abs(pred - act)))


def pick_alpha(train_df, cols, grid=GRID):
    """Pick alpha by expanding-window CV using ONLY rows inside train_df.

    Returns (alpha_or_None, n_inner_folds). None means the window was too
    short to run even one inner fold.
    """
    races = np.sort(train_df["race_idx"].unique())
    idx = train_df["race_idx"].to_numpy()
    y = train_df[model.TARGET].to_numpy(dtype=float)
    X = train_df[cols].to_numpy(dtype=float)
    scores: dict[float, list[float]] = {a: [] for a in grid}
    for k in range(MIN_INNER_TRAIN, len(races)):
        te = races[k]
        m_tr, m_va = idx < te, idx == te
        if not m_tr.any() or not m_va.any():
            continue
        # scaler fitted on the INNER training rows only, so no inner
        # validation row's mean/scale leaks into the fit
        sc = StandardScaler().fit(X[m_tr])
        Ztr, Zva = sc.transform(X[m_tr]), sc.transform(X[m_va])
        for a in grid:
            mdl = Ridge(alpha=a).fit(Ztr, y[m_tr])
            scores[a].append(_mae(mdl.predict(Zva), y[m_va]))
    n = len(scores[grid[0]])
    if n == 0:
        return None, 0
    return min(grid, key=lambda a: float(np.mean(scores[a]))), n


def main() -> int:
    rule("PHASE 6b - REGULARIZATION CHOSEN ONLY INSIDE THE TRAINING WINDOW")
    con = db.connect()
    con.row_factory = None
    df = features.build_features(con)
    con.close()

    cols = list(features.PHASE6_FEATURES)
    min_train = model.MIN_TRAIN_RACES
    races = np.sort(df["race_idx"].unique())
    idx = df["race_idx"].to_numpy()

    print(f"  features                 : {len(cols)} (stage 5)")
    print(f"  outer folds              : races {min_train + 1}..{len(races)}"
          f"  ({len(races) - min_train} folds)")
    print(f"  alpha grid               : {GRID}")
    print(f"  inner folds start after  : {MIN_INNER_TRAIN} inner-training races")
    print(f"  pre-registered headline  : alpha = {model.RIDGE_ALPHA}, fixed for")
    print(f"                             EVERY stage so deltas measure features")
    print()
    print("  Selection rule: for outer race k, alpha is chosen by expanding")
    print("  CV over races strictly < k. The outer race's own result is never")
    print("  seen by the selection - only by the final score.")

    picked: list[float] = []
    per_race: list[dict] = []
    n_no_inner = 0

    for k in range(min_train, len(races)):
        te = races[k]
        m_tr, m_va = idx < te, idx == te
        tr, va = df[m_tr], df[m_va]
        if tr.empty or va.empty:
            continue
        a, _ = pick_alpha(tr, cols)
        if a is None:
            n_no_inner += 1
            a = model.RIDGE_ALPHA
        picked.append(a)

        Xtr = tr[cols].to_numpy(dtype=float)
        ytr = tr[model.TARGET].to_numpy(dtype=float)
        Xva = va[cols].to_numpy(dtype=float)
        act = va[model.TARGET].to_numpy(dtype=float)
        sc = StandardScaler().fit(Xtr)
        Ztr, Zva = sc.transform(Xtr), sc.transform(Xva)

        # same scaler, same rows, two alphas: only alpha differs
        tuned = Ridge(alpha=a).fit(Ztr, ytr).predict(Zva)
        fixed = Ridge(alpha=model.RIDGE_ALPHA).fit(Ztr, ytr).predict(Zva)
        per_race.append({
            "year": int(va["year"].iloc[0]), "round": int(va["round"].iloc[0]),
            "mae_tuned": _mae(tuned, act), "mae_fixed": _mae(fixed, act),
        })

    pr = pd.DataFrame(per_race)
    # walk_forward reports the UNWEIGHTED mean of per-race MAEs (model.py),
    # not a mean over all rows - races have 19 to 22 starters, so the two
    # definitions genuinely differ. Using the same one makes this comparable
    # with the headline stage-5 number.
    mae_tuned = float(pr["mae_tuned"].mean())
    mae_fixed = float(pr["mae_fixed"].mean())

    rule("[1] WHAT THE INNER TRAINING WINDOW PICKS")
    counts = Counter(picked)
    print(f"  folds scored                 : {len(pr)}")
    print(f"  folds with no usable inner CV: {n_no_inner}")
    for a in GRID:
        bar = "#" * counts.get(a, 0)
        print(f"    alpha {a:>6.2f} : {counts.get(a, 0):>3} folds  {bar}")
    print(f"  most common pick             : {counts.most_common(1)[0][0]}")

    rule("[2] INNER-ONLY TUNING vs THE PRE-REGISTERED alpha = 1.0")
    # Self-consistency: the fixed-alpha column here must reproduce the
    # headline stage-5 MAE exactly, otherwise this script is measuring
    # something other than what it claims to.
    ref = model.walk_forward(df, cols, min_train=min_train)["mae"]
    match = abs(mae_fixed - ref) < 1e-9
    print(f"  fixed-alpha MAE here                         : {mae_fixed:.6f}")
    print(f"  walk_forward stage-5 MAE (independent call)  : {ref:.6f}")
    print(f"  identical                                   : {match}")
    print()
    print(f"  MAE with alpha chosen inside each training window : {mae_tuned:.4f}")
    print(f"  MAE with fixed alpha {model.RIDGE_ALPHA:<6}                     : {mae_fixed:.4f}")
    print(f"  difference (tuned - fixed)                        : "
          f"{mae_tuned - mae_fixed:+.4f}")

    rule("[3] WHAT THIS DOES AND DOES NOT SAY")
    print("  * The headline Phase 6 numbers use the FIXED alpha 1.0 at every")
    print("    stage. That was decided before any stage-5 MAE existed, so a")
    print("    stage-4 -> stage-5 delta cannot be a tune in disguise.")
    print("  * The tuned column above selects alpha using only races strictly")
    print("    before each fold's race, which is the compliant way to choose.")
    print("    It is reported as a sensitivity, not adopted - adopting it now")
    print("    would make stages 0-4 and stage 5 incomparable.")
    print("  * If the two MAEs are close, alpha is not what is driving the")
    print("    Phase 6 result, and the feature-group deltas stand on their own.")
    print()
    print("  NOTE: this inner CV itself shares training data with the outer")
    print("  folds, so it is a sensitivity check, not an independent estimate.")

    rule("RESULT")
    ok_repro = match
    ok_close = abs(mae_tuned - mae_fixed) < 0.30
    if not ok_repro:
        print("  FAIL  this script does not reproduce walk_forward's stage-5")
        print("        MAE, so its numbers are not comparable to the headline")
        return 1
    print(f"  PASS  reproduces walk_forward exactly ({mae_fixed:.6f})")
    print(f"  PASS  alpha chosen inside the training window gives "
          f"{mae_tuned - mae_fixed:+.4f} vs the fixed alpha")
    if ok_close:
        print("        -> alpha is not driving the Phase 6 result, so the")
        print("           feature-group deltas stand on their own.")
    else:
        print("        -> alpha MATERIALLY affects MAE; see the counts above")
        print("           before trusting any feature-group delta.")
    return 0 if ok_close else 1


if __name__ == "__main__":
    sys.exit(main())
