"""Phase 6a driver: add the SPRINT group as one ladder stage and measure it.

WHAT THIS REPORTS (spec line 91)
  1. the data actually being used
  2. ladder stages 0..4, each with its predecessor's MAE as "before"
  3. the paired per-race effect of the sprint group alone: MAE before/after,
     a bootstrap 95% interval over the 69 paired race differences, a sign
     test and Wilcoxon as cross-checks
  4. the ranking baselines, for context - a feature group that does not beat
     a free baseline has not earned its place
  5. a shuffled-label control on the SAME 18-feature set: if scrambling the
     targets leaves MAE near the real number, sprint leaked the answer
  6. the verdict, including the honest reading if the interval contains 0

WHY THIS SHAPE
  * one group at a time, never all at once - otherwise a regression cannot
    be attributed to anything
  * paired, because both walks share every training window
  * alpha stays at RIDGE_ALPHA for every stage, so the delta measures the
    FEATURE GROUP and nothing else; no alpha is ever chosen using
    validation data

Run:  python scripts/run_phase6a.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model

FAILS: list[str] = []


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def chk(n: int, cond: bool, msg: str) -> None:
    print(f"  [{n:>2}] {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        FAILS.append(msg)


rule("PHASE 6a - SPRINT FEATURE GROUP (spec line 91)")

# ---------------------------------------------------------------- [1] data
rule("[1] DATA")
con = db.connect()
con.row_factory = None
df = features.build_features(con)
con.close()

min_train = model.MIN_TRAIN_RACES
races = sorted(df["race_idx"].unique())
val = [r for r in races if r > min_train]
n_rows = int(df["race_idx"].isin(val).sum())
sprint_races = df.loc[df["has_sprint"] == 1, ["year", "round"]] \
    .drop_duplicates().shape[0]
sprint_set = {(int(y), int(r)) for y, r in
              df.loc[df["has_sprint"] == 1, ["year", "round"]]
              .drop_duplicates().itertuples(index=False)}

print(f"  rows                        : {len(df)}")
print(f"  races                       : {len(races)} "
      f"({min_train} train, {len(val)} validation, {n_rows} val rows)")
print(f"  sprint weekends             : {sprint_races} of {len(races)}")
print(f"  features  before            : {len(features.ALL_FEATURES)} "
      f"(stage 3)")
print(f"  features  after             : {len(features.BUILT_FEATURES)} "
      f"(stage 4 = 12 + {len(features.SPRINT_FEATURES)} sprint)")
print(f"  sprint group                : {', '.join(features.SPRINT_FEATURES)}")
print(f"  Ridge alpha                 : {model.RIDGE_ALPHA} "
      f"(fixed for every stage - the delta measures the group, not a tune)")
chk(1, len(df) == 1816 and len(races) == 89 and len(val) == 69,
    "89 races, 69 validation, 1816 rows")

# --------------------------------------------------------------- [2] ladder
rule("[2] LADDER - ONE GROUP AT A TIME")
stages = model.run_ladder(df, min_train=min_train,
                          ladder=model.PHASE6_LADDER)
print(f"  {'stage':<58} {'MAE':>7} {'vs prev':>9}")
print(f"  {'-'*58} {'-'*7} {'-'*9}")
for s in stages:
    d = "     -" if s["before"] is None else f"{s['delta']:>+9.3f}"
    print(f"  {s['name']:<58} {s['mae']:>7.3f} {d:>9}")

print()
print(f"  n_races = {stages[-1]['n_races']}, "
      f"n_rows = {stages[-1]['n_rows']}, "
      f"alpha = {model.RIDGE_ALPHA} at every stage")
s3, s4 = stages[3], stages[4]
chk(2, abs((s4["mae"] - s3["mae"]) - s4["delta"]) < 1e-12,
    "stage 4's delta is exactly its own MAE minus stage 3's")
chk(3, s4["n_races"] == s3["n_races"] == 69,
    "both stages scored the same 69 races, so they are comparable")

# ------------------------------------------------------- [3] paired effect
rule("[3] PAIRED PER-RACE EFFECT OF THE SPRINT GROUP")
eff = model.paired_mae_effect(s3, s4)
print(f"  races paired                : {eff['n_races']}")
print(f"  MAE before (12 features)    : {eff['mae_before']:.4f}")
print(f"  MAE after  (12 + sprint)    : {eff['mae_after']:.4f}")
print(f"  delta (after - before)      : {eff['delta']:+.4f} positions")
print(f"  relative change             : {eff['pct']:+.3f}% "
      f"({'improvement' if eff['delta'] < 0 else 'regression'})")
print(f"  bootstrap 95% CI ({10_000} resamples)  : "
      f"[{eff['ci_low']:+.4f}, {eff['ci_high']:+.4f}]")
print(f"  CI excludes 0               : {eff['excludes_zero']}")
print(f"  races improved / tied / worse: "
      f"{eff['n_improved']} / {eff['n_tied']} / {eff['n_worse']}")
print(f"  sign test  (2-sided)        : p = {eff['p_sign']:.4f}")
print(f"  Wilcoxon signed-rank        : p = {eff['p_wilcoxon']:.4f}")
print()
print(f"  improvement formula: "
      f"({eff['mae_before']:.4f} - {eff['mae_after']:.4f}) / "
      f"{eff['mae_before']:.4f} x 100 = "
      f"{(eff['mae_before'] - eff['mae_after']) / eff['mae_before'] * 100:+.3f}%")
print()
# The sign test (45 of 69 improved) and the mean (positive) disagree, which
# means a minority of races got worse by MORE than the majority improved by.
# That asymmetry is the real story, so print it rather than quoting only
# whichever single statistic flatters the group.
pr = eff["per_race"].copy()
pr["is_sprint"] = [1 if ((int(y), int(r)) in sprint_set) else 0
                   for y, r in zip(pr["year"], pr["round"])]
q = pr["delta"].quantile([0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0])
n_better = int((pr["delta"] < 0).sum())
worse = pr[pr["delta"] > 0].sort_values("delta", ascending=False)
print("  distribution of the 69 paired differences (after - before):")
print(f"    min {q[0.0]:+.4f}   p5 {q[0.05]:+.4f}   p25 {q[0.25]:+.4f}   "
      f"median {q[0.5]:+.4f}   p75 {q[0.75]:+.4f}   p95 {q[0.95]:+.4f}   "
      f"max {q[1.0]:+.4f}")
print(f"    mean {pr['delta'].mean():+.4f}  - the mean is pulled by the tail; "
      f"the median is {pr['delta'].median():+.4f}")
print(f"    the {len(worse)} races that got worse are worth "
      f"{worse['delta'].sum():+.4f} on their own,")
print(f"    the {n_better} that improved are worth "
      f"{pr.loc[pr['delta'] < 0, 'delta'].sum():+.4f}")
print(f"    sprint weekends among the worse: {int(worse['is_sprint'].sum())} "
      f"of {len(worse)}  ({int(pr['is_sprint'].sum())} sprint weekends in "
      f"the 69 validation races)")
print()
print("  worst 3 races for the sprint group:")
for _, r in worse.head(3).iterrows():
    print(f"    {int(r['year'])} R{int(r['round'])}  "
          f"MAE {r['mae_before']:.3f} -> {r['mae_after']:.3f}  "
          f"({r['delta']:+.3f})  "
          f"{'SPRINT weekend' if r['is_sprint'] else 'conventional weekend'}")
print()
print("  The interval treats races as independent. Walk-forward folds SHARE")
print("  training data, so this CI is optimistic - stated in LIMITATIONS.md.")

# ---------------------------------------------------------- [4] baselines
rule("[4] RANKING BASELINES FOR CONTEXT")
bl = model.run_baselines(df)
print(f"  {'ranking':<40} {'MAE':>7} {'Spearman':>9}")
print(f"  {'-'*40} {'-'*7} {'-'*9}")
print(f"  {'MODEL (12 + sprint features)':<40} "
      f"{s4['mae']:>7.3f} {s4['rho']:>9.4f}")
print(f"  {'MODEL (12 features, stage 3)':<40} "
      f"{s3['mae']:>7.3f} {s3['rho']:>9.4f}")
for label, b in bl.items():
    print(f"  {label:<40} {b['mae']:>7.3f} {b['rho']:>9.4f}")
best = min(b["mae"] for b in bl.values())
best_label = min(bl, key=lambda k: bl[k]["mae"])
print(f"  {'-'*40} {'-'*7} {'-'*9}")
print(f"  {'best baseline':<40} {best:>7.3f}   ({best_label})")
d_best = s4["mae"] - best
print(f"  {'MODEL - best baseline':<40} {d_best:>+7.3f}   "
      f"({'beats it' if d_best < 0 else 'does NOT beat it'})")
chk(4, d_best < 0, "the sprint-extended model still beats the best baseline")

# ------------------------------------------------- [5] shuffled-label control
rule("[5] SHUFFLED-LABEL CONTROL ON THE SAME 18 FEATURES")
shuf = model.walk_forward(df, list(features.BUILT_FEATURES),
                         shuffle=True, seed=0)
print(f"  real labels   MAE {s4['mae']:.4f}   Spearman {s4['rho']:.4f}")
print(f"  shuffled      MAE {shuf['mae']:.4f}   Spearman {shuf['rho']:.4f}")
print(f"  shuffle penalty: {shuf['mae'] - s4['mae']:+.4f} positions")
chk(5, shuf["mae"] > s4["mae"] + 1.0,
    "shuffling the targets destroys performance (>= +1.0 worse)")

# ------------------------------------------------------------- [6] verdict
rule("[6] VERDICT")
print(f"  sprint group moved MAE {s3['mae']:.3f} -> {s4['mae']:.3f} "
      f"({eff['delta']:+.3f})")
if eff["excludes_zero"] and eff["delta"] < 0:
    print(f"  and the 95% interval [{eff['ci_low']:+.4f}, "
          f"{eff['ci_high']:+.4f}] excludes 0 -> the sprint group")
    print(f"  genuinely helps; {eff['n_improved']} of {eff['n_races']} races "
          f"improved.")
elif eff["excludes_zero"] and eff["delta"] > 0:
    print(f"  but the 95% interval [{eff['ci_low']:+.4f}, "
          f"{eff['ci_high']:+.4f}] excludes 0 -> sprint HURTS.")
else:
    print(f"  the 95% interval [{eff['ci_low']:+.4f}, "
          f"{eff['ci_high']:+.4f}] CONTAINS 0, so on this evidence the")
    print(f"  sprint group has NOT been shown to help. It must be reported as")
    print(f"  'no measurable effect', not as an improvement.")
print()
print(f"  documented limitation: no_sprint_result is an exact duplicate of")
print(f"  (1 - has_sprint) across all {len(df)} rows, so Ridge cannot separate")
print(f"  the two weights. Reported rather than silently dropped.")

rule("RESULT")
if FAILS:
    print(f"  {len(FAILS)} FAILED:")
    for f in FAILS:
        print(f"    - {f}")
    sys.exit(1)
print("  all checks PASS")
sys.exit(0)
