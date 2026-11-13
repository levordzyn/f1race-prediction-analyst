"""Walk-forward (expanding-window) evaluation for Phase 3.

WHY THIS SHAPE
--------------
* **Expanding window, never random CV.** Race N is predicted using only races
  1..N-1. A shuffled split would let 2026 races train a model that then
  "predicts" 2023, which is future information. This is the whole point of
  Phase 3 (spec line 82).
* **Scaler fits on TRAIN only.** StandardScaler is fitted inside each fold, so
  the mean/scale of a future race never reaches the model.
* **Baselines are unfitted.** grid / practice-order / recent-form are raw
  columns evaluated on exactly the same validation races, so their MAE is
  directly comparable to the Ridge ladder.
* **Labels can be shuffled** to prove the pipeline actually learns: if
  scrambled training labels score about as well as real ones, something is
  leaking.

WHAT IT REPORTS (spec line 85 + the project's ML rules)
--------------------------------------------------------
MAE and Spearman per race, averaged over races; race and row counts; winner
and podium hit rate with a small-sample note; standardized Ridge coefficients;
the feature-group ladder with MAE before and after each group.

ASSUMPTIONS (spec line 53 says these are unknown - stated, not buried)
----------------------------------------------------------------------
* min training window = MIN_TRAIN_RACES races before validation starts
* Ridge alpha fixed at RIDGE_ALPHA (no tuning inside Phase 3)
* podium hit = fraction of the real top-3 that appear in the predicted top-3
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from scipy.stats import binomtest, spearmanr, wilcoxon
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from .features import (ALL_FEATURES, EARLY_FEATURES, FEATURE_GROUPS, PHASE6_FEATURES,
                       SPRINT_FEATURES, TARGET)

log = logging.getLogger(__name__)

# One season of races before we start scoring (2023 had 22; 20 is a round
# number that leaves 69 validation races of 89).
MIN_TRAIN_RACES = 20

# Fixed for Phase 3. Tuning alpha on the same walk-forward folds would be
# fitting to the test set, so it is deliberately not done here.
RIDGE_ALPHA = 1.0

# Label written into every saved forecast so a later scorecard can say
# exactly which estimator produced it. Bump it ONLY when the feature set,
# alpha or the estimator itself changes - under the freeze agreed for the
# Sao Paulo forecast, that means not before it has been scored.
MODEL_VERSION = "phase7-xgboost-1.0"

# Estimator registry - maps MODEL_VERSION prefix to implementation
def get_walk_forward_fn():
    """Return the walk-forward function for the current MODEL_VERSION."""
    if MODEL_VERSION.startswith("phase7-xgboost"):
        from .xgboost_model import walk_forward_xgboost
        
        # Monotone constraints for full feature set (12 features)
        MONOTONE_FULL = [1, 1, 1, 1, 1, 1, -1, 1, 1, 1, 1, -1]
        # Monotone constraints for early feature set (7 features: driver_form, team_form, non_finish_rate, practice_pos, practice_gap_pct, practice_laps_30, no_practice_time)
        MONOTONE_EARLY = [1, 1, 1, 1, 1, -1, 1]
        
        def xgb_walk_forward(df, cols, min_train=MIN_TRAIN_RACES, shuffle=False, seed=0):
            # Select appropriate monotone constraints based on feature set
            if set(cols) == set(EARLY_FEATURES):
                monotone = MONOTONE_EARLY
            else:
                monotone = MONOTONE_FULL
                
            result = walk_forward_xgboost(
                df, cols, min_train_races=min_train,
                shuffle=shuffle, monotone_constraints=monotone
            )
            # Convert XGBoost result format to match Ridge's walk_forward output
            preds_df = result["predictions"].copy()
            # Ensure pred_pos is computed
            preds_df["pred_pos"] = preds_df.groupby("race_idx")["pred"].rank(method="first", ascending=True).astype(int)
            
            # Compute per-race metrics
            import numpy as np
            from scipy.stats import spearmanr
            
            def _mae(pred, act):
                return float(np.mean(np.abs(pred - act)))
            
            def _rho(pred, act):
                if np.unique(act).size < 2 or np.unique(pred).size < 2:
                    return float("nan")
                r, _ = spearmanr(pred, act)
                return float(r)
            
            def _hits(pred, act):
                if np.unique(pred).size < 2:
                    return float("nan"), float("nan")
                win = float(int(np.argmin(pred) == np.argmin(act)))
                k = min(3, act.size)
                pred_top = set(np.argsort(pred)[:k])
                act_top = set(np.argsort(act)[:k])
                return win, len(pred_top & act_top) / k
            
            per_race_list = []
            for race_idx, group in preds_df.groupby("race_idx"):
                act = group["finish"].to_numpy(dtype=float)
                pred = group["pred"].to_numpy(dtype=float)
                if not np.isfinite(act).all():
                    continue
                win, pod = _hits(pred, act)
                year = int(group["year"].iloc[0])
                round_ = int(group["round"].iloc[0])
                per_race_list.append({
                    "year": year,
                    "round": round_,
                    "n": int(len(group)),
                    "mae": _mae(pred, act),
                    "rho": _rho(pred, act),
                    "winner_hit": win,
                    "podium_hit": pod,
                })
            
            per_race_df = pd.DataFrame(per_race_list)
            
            return {
                "n_races": int(len(per_race_df)),
                "n_rows": int(per_race_df["n"].sum()),
                "mae": result["mae"],
                "rho": result["spearman"],
                "winner_hit": result["winner_hit"],
                "podium_hit": result["podium_hit"],
                "per_race": per_race_df,
                "preds": preds_df[["year", "round", "race_idx", "driver", "pred", "finish", "pred_pos"]].reset_index(drop=True),
                "cols": list(cols),
            }
        return xgb_walk_forward
    else:
        # Default: Ridge (phase5-ridge, phase6-ridge, etc.)
        from .model import walk_forward
        return walk_forward

# Unfitted reference models, evaluated on the identical validation races.
BASELINES: dict[str, str] = {
    "grid baseline": "grid",
    "practice-order baseline": "practice_pos",
    "recent-form baseline": "driver_form",
}

# Which baselines each mode may compete against. Early mode cannot know the
# published grid at forecast time, so scoring it against the grid baseline
# would be an unfair claim - it is simply not in the list. These live here
# rather than in cli.py so forecast scoring can use the identical label
# lists without importing cli (cli imports forecast for --save).
EARLY_BASELINES: list[str] = ["practice-order baseline", "recent-form baseline"]
FULL_BASELINES: list[str] = list(BASELINES)

# Baselines for WINNER / PODIUM hit rate. Unlike BASELINES, which predict a
# finishing POSITION and are scored by MAE, these rank the whole field by one
# pre-race quantity and that ranking IS the prediction - so they are scored
# with the same hit functions the model uses, on the identical races.
#
# value = (column to sort ascending, column marking rows that must NOT win)
#   * pole-sitter        -> starting grid; pit-lane starts already carry
#                           field_n+1 so they sort last, not first.
#   * best qualifying gap-> smallest gap_to_pole_pct. `no_q_time` rows are
#                           filled with 0.0 for the model, which would make a
#                           driver who set NO lap look fastest, so they are
#                           pushed to +inf here instead.
#   * best driver form   -> smallest mean finish over the last 5 races.
# grid and q_gap_pct are genuinely different baselines: penalties can move the
# pole sitter away from whoever set the fastest qualifying lap.
HIT_BASELINES: dict[str, tuple[str, str | None]] = {
    "pole-sitter wins": ("grid", None),
    "best qualifying gap wins": ("q_gap_pct", "no_q_time"),
    "best driver form wins": ("driver_form", None),
}

# Printed verbatim by report.hit_rates so the definition and the number can
# never drift apart. `_hits()` below is the implementation of these two lines.
WINNER_DEF = (
    "winner hit rate = for each race, 1 if the single car the ranking puts "
    "first is the car that actually won, else 0; the headline number is the "
    "mean over the N validation races. Random floor = 1/field, i.e. 4.5% for "
    "22 cars."
)
PODIUM_DEF = (
    "podium hit rate = for each race, |P ∩ A| / 3 where A is the set of 3 "
    "drivers with the smallest `finish` and P is the set of 3 drivers the "
    "ranking puts first. It is the RECALL of the real podium, so it takes "
    "exactly the values 0, 1/3, 2/3 or 1 per race, and the headline number is "
    "the mean over the N validation races. It is NOT 'all three were right' "
    "and NOT precision. A blind 3-car pick from a 22-car field averages "
    "3/22 = 13.6%, because each real podium driver is drawn with "
    "probability 3/22."
)

# Cumulative feature sets: stage k uses every group up to k.
LADDER: list[tuple[str, list[str]]] = [
    ("stage 0  (no features, intercept only)", []),
    ("stage 1  + grid, driver/team form, non-finish rate",
     list(FEATURE_GROUPS["grid_form"])),
    ("stage 2  + practice position, gap, laps, missing flag",
     list(FEATURE_GROUPS["grid_form"]) + list(FEATURE_GROUPS["practice"])),
    ("stage 3  + qualifying position, gap, missing flag, pole",
     list(ALL_FEATURES)),
]

# ---- PHASE 6: the ladder extended (spec line 91) ---------------------------
# `LADDER` above deliberately stops at 4 stages: run_phase3.py and
# paired_practice_effect.py consume it and their already-accepted output
# shows exactly those stages. Phase 6 appends one group at a time on top of
# the same 12 features, so each delta measures ONLY the new group.
#   stage 4 = sprint (Phase 6a)
#   stage 5 = weather + a few pre-chosen interactions (Phase 6b)
PHASE6_LADDER: list[tuple[str, list[str]]] = list(LADDER) + [
    ("stage 4  + sprint qualifying position/gap, sprint result, "
     "has-sprint flag, missing flags",
     list(ALL_FEATURES) + list(SPRINT_FEATURES)),
    ("stage 5  + temperature, humidity, rain, wind + 3 interactions",
     list(PHASE6_FEATURES)),
]


# --------------------------------------------------------------------- utils
def _mae(pred: np.ndarray, act: np.ndarray) -> float:
    return float(np.mean(np.abs(pred - act)))


def _rho(pred: np.ndarray, act: np.ndarray) -> float:
    """Per-race Spearman; NaN if either side is constant (then undefined)."""
    if np.unique(act).size < 2 or np.unique(pred).size < 2:
        return float("nan")
    r, _p = spearmanr(pred, act)          # SignificanceResult unpacks as a pair
    return float(r)


def _hits(pred: np.ndarray, act: np.ndarray) -> tuple[float, float]:
    """(won 0/1, podium recall 0..1) for one race, or NaN if undefined.

    A constant prediction (the intercept-only stage) has no winner: argmin
    would just return whichever row comes first, which is an artifact of row
    ordering, not a forecast. Reporting NaN here matches how _rho already
    treats a constant prediction - the honest answer is "not defined".
    """
    if np.unique(pred).size < 2:
        return float("nan"), float("nan")
    win = float(int(np.argmin(pred) == np.argmin(act)))
    k = min(3, act.size)
    pred_top = set(np.argsort(pred)[:k])
    act_top = set(np.argsort(act)[:k])
    return win, len(pred_top & act_top) / k


def _predict(train: pd.DataFrame, test: pd.DataFrame, cols: list[str],
              rng: np.random.Generator | None) -> tuple[np.ndarray, np.ndarray | None]:
    """Fit on `train` (scaler inside the fold) and predict `test`.

    `rng` not None => training labels are shuffled first. That is the sanity
    check: the features stay put and only the target is scrambled, so a
    pipeline with any leakage would still look fine while this collapses.
    """
    # Filter out rows with NaN finish (DNS drivers) from training data
    train_finite = train[np.isfinite(train[TARGET])]
    ytr = train_finite[TARGET].to_numpy(dtype=float)
    if rng is not None:
        rng.shuffle(ytr)

    if not cols:
        # Intercept-only reference: always predicts the training mean.
        return np.full(len(test), ytr.mean()), None

    scaler = StandardScaler().fit(train_finite[cols])      # TRAIN statistics only
    model = Ridge(alpha=RIDGE_ALPHA).fit(scaler.transform(train_finite[cols]), ytr)
    return model.predict(scaler.transform(test[cols])), model.coef_.copy()


# ---------------------------------------------------------------- walk-forward
def walk_forward(df: pd.DataFrame, cols: list[str],
                 min_train: int = MIN_TRAIN_RACES,
                 shuffle: bool = False, seed: int = 0) -> dict:
    """Expanding-window evaluation of one feature set.

    Returns a dict with averaged metrics, per-race rows, predictions and the
    mean standardized coefficients across folds.
    """
    rng = np.random.default_rng(seed) if shuffle else None
    races = np.sort(df["race_idx"].unique())
    if min_train >= len(races):
        raise ValueError(f"min_train={min_train} leaves no race to validate")

    idx = df["race_idx"].to_numpy()
    per_race: list[dict] = []
    n_unscored: list[tuple[int, int]] = []
    rows = df[["year", "round", "race_idx", "driver", TARGET]].copy()
    rows["pred"] = np.nan
    coefs: list[np.ndarray] = []

    for k in range(min_train, len(races)):
        te = races[k]
        # expanding: every race strictly before te trains, te alone tests
        train = df[idx < te]
        test = df[idx == te]
        if train.empty or test.empty:
            continue
        pred, coef = _predict(train, test, cols, rng)
        if coef is not None:
            coefs.append(coef)

        y_, r_ = int(test["year"].iloc[0]), int(test["round"].iloc[0])
        act = test[TARGET].to_numpy(dtype=float)
        # TRUE FORECAST: a race that has not run yet has a NULL target. It is
        # still PREDICTED (that is the entire point of forecast mode) but it
        # is never SCORED - a not-yet-run race must not be able to push MAE
        # toward NaN or feed an undefined argmin into the hit rates. The
        # prediction still lands in `rows` below.
        if np.isfinite(act).all():
            win, pod = _hits(pred, act)
            per_race.append({
                "year": y_,
                "round": r_,
                "n": int(len(test)),
                "mae": _mae(pred, act),
                "rho": _rho(pred, act),
                "winner_hit": win,
                "podium_hit": pod,
            })
        else:
            n_unscored.append((y_, r_))
        mask = (rows["year"] == y_) & (rows["round"] == r_)
        rows.loc[mask, "pred"] = pred

    pr = pd.DataFrame(per_race)
    if pr.empty:
        raise RuntimeError("no race was validated - check min_train")

    out: dict = {
        "n_races": int(len(pr)),
        # races predicted but not scored (forecast rows); 0 in normal runs
        "n_unscored": [f"{y} R{r}" for y, r in n_unscored],
        "n_rows": int(pr["n"].sum()),
        "mae": float(pr["mae"].mean()),
        "rho": float(pr["rho"].mean(skipna=True)),
        "rho_races": int(pr["rho"].notna().sum()),
        "winner_hit": float(pr["winner_hit"].mean()),
        "podium_hit": float(pr["podium_hit"].mean()),
        "per_race": pr,
        "preds": rows.dropna(subset=["pred"]).reset_index(drop=True),
        "cols": list(cols),
    }
    if coefs:
        arr = np.vstack(coefs)
        out["coef_mean"] = dict(zip(cols, arr.mean(axis=0)))
        out["coef_std"] = dict(zip(cols, arr.std(axis=0)))
        out["n_folds"] = int(arr.shape[0])
    else:
        out["coef_mean"] = None
        out["n_folds"] = out["n_races"]
    return out


def run_baselines(df: pd.DataFrame, min_train: int = MIN_TRAIN_RACES,
                  labels: list[str] | None = None) -> dict:
    """Unfitted baselines on the same validation races as the ladder.

    `labels` restricts which baselines run. Early mode has no published grid,
    so its grid baseline would be scored with information the forecast is not
    allowed to have; callers pass labels=["practice-order baseline",
    "recent-form baseline"] for that mode (spec line 45).
    """
    races = np.sort(df["race_idx"].unique())
    idx = df["race_idx"].to_numpy()
    out = {}
    for label, col in BASELINES.items():
        if labels is not None and label not in labels:
            continue
        if col not in df.columns:
            log.warning("run_baselines: %r needs column %r, which is absent "
                        "- skipped", label, col)
            continue
        per = []
        for k in range(min_train, len(races)):
            te = races[k]
            test = df[idx == te]
            act = test[TARGET].to_numpy(dtype=float)
            if not np.isfinite(act).all():
                continue          # forecast race: predict, do not score
            pred = test[col].to_numpy(dtype=float)
            win, pod = _hits(pred, act)
            per.append({"n": len(test), "mae": _mae(pred, act),
                        "rho": _rho(pred, act), "winner_hit": win,
                        "podium_hit": pod})
        p = pd.DataFrame(per)
        if p.empty:
            continue
        out[label] = {
            "n_races": int(len(p)), "n_rows": int(p["n"].sum()),
            "mae": float(p["mae"].mean()),
            "rho": float(p["rho"].mean(skipna=True)),
            "winner_hit": float(p["winner_hit"].mean()),
            "podium_hit": float(p["podium_hit"].mean()),
            "per_race": p, "cols": [col],
        }
    return out


def run_ladder(df: pd.DataFrame, min_train: int = MIN_TRAIN_RACES,
               ladder: list[tuple[str, list[str]]] | None = None) -> list[dict]:
    """Feature groups added one at a time; each stage carries its predecessor's
    MAE as 'before' so the effect of the group is unambiguous.

    `ladder` defaults to LADDER (the accepted 4-stage Phase 3 ladder). Phase 6
    passes PHASE6_LADDER to append the sprint and weather stages without
    changing what run_phase3.py prints.
    """
    stages = []
    for name, cols in (LADDER if ladder is None else ladder):
        res = walk_forward(df, cols, min_train=min_train)
        res["name"] = name
        stages.append(res)
    for i, s in enumerate(stages):
        s["before"] = stages[i - 1]["mae"] if i else None
        s["delta"] = (s["mae"] - s["before"]) if i else None
    return stages


# ------------------------------------------------- paired group effect (P6)
def paired_mae_effect(before: dict, after: dict,
                      n_boot: int = 10_000, seed: int = 0) -> dict:
    """How much did ONE feature group change walk-forward MAE, per race?

    WHY PAIRED: `before` and `after` must be two `walk_forward` results on the
    SAME frame with the SAME min_train, so race k is scored against the same
    20..k-1 training races in both. Comparing two independently-computed
    averages would throw that away and widen the interval; pairing subtracts
    the two MAEs race by race and resamples only the differences.

    Returns the two MAEs, the delta, a bootstrap percentile CI on the mean
    difference, a sign test and a Wilcoxon signed-rank cross-check.

    delta = MAE_after - MAE_before, so NEGATIVE means the group helped.

    CAVEAT (also stated in LIMITATIONS.md): walk-forward folds share training
    data, so treating races as independent makes this interval optimistic.
    """
    pa = before["per_race"][["year", "round", "mae"]].rename(
        columns={"mae": "mae_before"})
    pb = after["per_race"][["year", "round", "mae"]].rename(
        columns={"mae": "mae_after"})
    m = pa.merge(pb, on=["year", "round"], validate="one_to_one")
    d = (m["mae_after"] - m["mae_before"]).to_numpy(dtype=float)
    n = int(d.size)
    if n == 0:
        raise RuntimeError("no race was scored in both walks")
    if before["n_races"] != after["n_races"]:
        raise ValueError(
            f"the two walks scored a different number of races "
            f"({before['n_races']} vs {after['n_races']}); they are not "
            f"paired and any interval would be meaningless")

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    boots = d[idx].mean(axis=1)
    lo, hi = (float(v) for v in np.percentile(boots, [2.5, 97.5]))

    non_tied = d[d != 0]
    k_improved = int((non_tied < 0).sum())
    p_sign = float(binomtest(k_improved, int(non_tied.size), 0.5).pvalue) \
        if non_tied.size else float("nan")
    try:
        p_wilcoxon = float(wilcoxon(d).pvalue)
    except ValueError:          # all differences are exactly zero
        p_wilcoxon = float("nan")

    mae_b = float(m["mae_before"].mean())
    mae_a = float(m["mae_after"].mean())
    return {
        "n_races": n,
        "mae_before": mae_b,
        "mae_after": mae_a,
        "delta": float(d.mean()),
        # relative change against the before-stage MAE, as a percentage
        "pct": float(d.mean() / mae_b * 100.0) if mae_b else float("nan"),
        "ci_low": lo, "ci_high": hi,
        "excludes_zero": bool(lo > 0 or hi < 0),
        "n_improved": k_improved,
        "n_worse": int((non_tied > 0).sum()),
        "n_tied": int((d == 0).sum()),
        "p_sign": p_sign,
        "p_wilcoxon": p_wilcoxon,
        "per_race": m.assign(delta=d),
    }


# ----------------------------------------------------- hit-rate baselines
def run_hit_baselines(df: pd.DataFrame,
                      min_train: int = MIN_TRAIN_RACES) -> dict:
    """Winner/podium hit rates for three simple ranking baselines.

    Every baseline is scored on the SAME validation races as the model, with
    the SAME _hits() function, so the comparison is like-for-like. Each
    baseline 'predicts' by ranking the field with one column and taking the
    top car (winner) or top three (podium).

    Returns {label: {"per_race", "winner_hit", "podium_hit", "n_races",
    "n_rows", "col"}}. per_race carries `year` so reports can split by
    season.
    """
    races = np.sort(df["race_idx"].unique())
    idx = df["race_idx"].to_numpy()
    out: dict[str, dict] = {}

    for label, (col, exclude) in HIT_BASELINES.items():
        if col not in df.columns:
            log.warning("run_hit_baselines: %r needs %r, absent - skipped",
                        label, col)
            continue
        per: list[dict] = []
        for k in range(min_train, len(races)):
            te = races[k]
            test = df[idx == te]
            if test.empty:
                continue
            act = test[TARGET].to_numpy(dtype=float)
            if not np.isfinite(act).all():
                continue          # forecast race: predict, do not score
            score = test[col].to_numpy(dtype=float).copy()
            if exclude is not None:
                # A row excluded here can never be ranked first: +inf sorts
                # last under argmin/argsort and is never a valid prediction.
                bad = test[exclude].to_numpy(dtype=float) != 0
                score[bad] = np.inf
            win, pod = _hits(score, act)
            per.append({"year": int(test["year"].iloc[0]),
                        "round": int(test["round"].iloc[0]),
                        "n": int(len(test)),
                        "winner_hit": win, "podium_hit": pod})

        p = pd.DataFrame(per)
        if p.empty:
            continue
        out[label] = {
            "n_races": int(len(p)), "n_rows": int(p["n"].sum()),
            "winner_hit": float(p["winner_hit"].mean()),
            "podium_hit": float(p["podium_hit"].mean()),
            "per_race": p, "col": col,
        }
    return out


# ------------------------------------------- grouped permutation importance
def permutation_importance(df: pd.DataFrame, cols: list[str],
                           groups: dict[str, list[str]],
                           min_train: int = MIN_TRAIN_RACES,
                           n_repeats: int = 5, seed: int = 0) -> pd.DataFrame:
    """Walk-forward MAE increase when each feature GROUP is shuffled away.

    WHY THIS AND NOT THE COEFFICIENTS
    ---------------------------------
    Ridge standardized coefficients split weight between correlated
    predictors: q_position and q_gap_pct carry the same qualifying pace, so
    one can keep the magnitude while the other flips sign. Individual bars
    therefore cannot be read as effects (scripts/check_coef_signs.py). Grouped
    permutation importance sidesteps that: it never inspects a coefficient, it
    measures what the model LOSES when a whole block of information is
    destroyed.

    HOW
    ---
    Identical expanding-window folds to walk_forward(). Inside each fold:
      1. fit scaler + Ridge on train (train statistics only, no leakage);
      2. score the untouched validation race -> mae_base;
      3. for each group, for n_repeats: shuffle that group's ROWS across the
         validation race (one permutation shared by every column in the group,
         so within-row relationships survive) and re-score -> mae_perm;
      4. delta = mae_perm - mae_base.
    Because each fold predicts exactly ONE race, the shuffle is automatically
    WITHIN that race - the field's size, spread and distribution are untouched
    and only the mapping between those values and the drivers is broken.

    Groups whose columns are not in `cols` are skipped, so the same function
    serves early mode (no qualifying) and full mode.
    """
    rng = np.random.default_rng(seed)

    groups = {g: [c for c in cs if c in cols] for g, cs in groups.items()}
    groups = {g: cs for g, cs in groups.items() if cs}
    if not groups:
        raise ValueError("permutation_importance: no group has a column "
                         f"present in cols={cols}")

    races = np.sort(df["race_idx"].unique())
    idx = df["race_idx"].to_numpy()

    base_per_fold: list[float] = []
    deltas: dict[str, list[np.ndarray]] = {g: [] for g in groups}

    for k in range(min_train, len(races)):
        te = races[k]
        train = df[idx < te]
        test = df[idx == te]
        if train.empty or test.empty or len(test) < 2:
            continue

        scaler = StandardScaler().fit(train[cols])          # TRAIN only
        mdl = Ridge(alpha=RIDGE_ALPHA).fit(
            scaler.transform(train[cols]), train[TARGET].to_numpy(dtype=float))

        X = scaler.transform(test[cols])                    # one validation race
        y = test[TARGET].to_numpy(dtype=float)
        mae0 = _mae(mdl.predict(X), y)
        base_per_fold.append(mae0)

        for gname, gcols in groups.items():
            pos = [cols.index(c) for c in gcols]
            reps = np.empty(n_repeats, dtype=float)
            for r in range(n_repeats):
                perm = rng.permutation(len(X))              # within this race
                Xp = X.copy()
                Xp[:, pos] = X[perm][:, pos]
                # the DIFFERENCE, not the shuffled MAE: the aggregator treats
                # these as deltas, and storing the raw MAE made every group
                # look as if it cost a full ~3-4 positions (it also made
                # folds_helped report 69/69 for every group, because a raw
                # MAE is always > 0).
                reps[r] = _mae(mdl.predict(Xp), y) - mae0
            deltas[gname].append(reps)

    if not base_per_fold:
        raise RuntimeError("permutation_importance: no fold was evaluated - "
                           "check min_train")

    rows = []
    base = float(np.mean(base_per_fold))
    for gname, per_fold in deltas.items():
        if not per_fold:
            continue
        all_d = np.concatenate(per_fold)
        fold_means = np.array([r.mean() for r in per_fold])
        rows.append({
            "group": gname,
            "n_features": len(groups[gname]),
            "mae_base": base,
            "mae_perm": base + float(all_d.mean()),
            "delta": float(all_d.mean()),
            "pct_increase": 100.0 * float(all_d.mean()) / base,
            "fold_std": float(fold_means.std(ddof=1)) if fold_means.size > 1
            else 0.0,
            "folds_helped": int((fold_means > 0).sum()),
            "n_folds": len(per_fold),
            "n_repeats": n_repeats,
        })
    out = pd.DataFrame(rows).sort_values("delta", ascending=False)
    return out.reset_index(drop=True)
