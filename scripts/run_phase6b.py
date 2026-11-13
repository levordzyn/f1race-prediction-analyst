"""Phase 6b driver: add the WEATHER group as ladder stage 5 and measure it.

WHAT THIS REPORTS (spec lines 64 and 91)
  1. the data, including what the observed weather actually looks like
  2. ladder stages 0..5 - weather is added ON TOP of sprint, one group at a
     time, so stage 5's delta measures weather and nothing else
  3. the paired per-race effect of the weather group alone: MAE before/after,
     a bootstrap 95% interval over the paired race differences, sign test and
     Wilcoxon
  4. baselines, for context
  5. a shuffled-label control on the same 25-feature set
  6. the honest verdict, including the case where the interval contains 0

ALPHA IS NOT TUNED HERE. It stays at the pre-registered RIDGE_ALPHA = 1.0 at
every stage; scripts/check_alpha_window.py separately demonstrates that any
alpha choice would have to happen inside the training window.

Run:  python scripts/run_phase6b.py
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


rule("PHASE 6b - WEATHER FEATURE GROUP (spec lines 64 and 91)")

# ---------------------------------------------------------------- [1] data
rule("[1] DATA AND THE OBSERVED WEATHER ITSELF")
con = db.connect()
con.row_factory = None
df = features.build_features(con)
wx = con.execute(
    "SELECT COUNT(*), SUM(rain_mm > 0), MIN(temp_c), MAX(temp_c), "
    "MIN(humidity_pct), MAX(humidity_pct), MAX(rain_mm), MAX(wind_kmh) "
    "FROM weather").fetchone()
con.close()

if "rain_mm" not in df.columns:
    print("  WEATHER COLUMNS ARE ABSENT FROM THE FEATURE FRAME.")
    print("  build_features omits them when a race in the frame has no")
    print("  observed weather - that only happens for a date that has not")
    print("  passed yet, and fabricating a value would be a lie.")
    print("  Run scripts/fetch_weather.py first.")
    FAILS.append("weather columns missing from build_features output")
    rule("RESULT")
    print("  FAIL")
    sys.exit(1)

min_train = model.MIN_TRAIN_RACES
races = sorted(df["race_idx"].unique())
val = [r for r in races if r > min_train]
n_rows = int(df["race_idx"].isin(val).sum())

print(f"  rows                        : {len(df)}")
print(f"  races                       : {len(races)} "
      f"({min_train} train, {len(val)} validation, {n_rows} val rows)")
print(f"  weather rows                : {wx[0]}")
print(f"  race days with rain         : {wx[1]} of {wx[0]}")
print(f"  temperature                 : {wx[2]:.1f} .. {wx[3]:.1f} deg C")
print(f"  humidity                    : {wx[4]:.0f} .. {wx[5]:.0f} %")
print(f"  wettest day                 : {wx[6]:.1f} mm")
print(f"  strongest 10 m wind         : {wx[7]:.1f} km/h")
print()
print(f"  features  before (stage 4)  : {len(features.PHASE6_FEATURES) - len(features.WEATHER_FEATURES)}")
print(f"  features  after  (stage 5)  : {len(features.PHASE6_FEATURES)}")
print(f"  weather group               : {', '.join(features.WEATHER_FEATURES)}")
print(f"  Ridge alpha                 : {model.RIDGE_ALPHA} "
      f"(fixed at every stage)")
chk(1, len(df) == 1816 and len(races) == 89 and len(val) == 69,
    "89 races, 69 validation, 1816 rows")
chk(2, all(c in df.columns for c in features.WEATHER_FEATURES),
    "all 7 weather features present")

# --------------------------------------------------------------- [2] ladder
rule("[2] LADDER - ONE GROUP AT A TIME (stage 5 = weather)")
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
s4, s5 = stages[4], stages[5]
chk(3, abs((s5["mae"] - s4["mae"]) - s5["delta"]) < 1e-12,
    "stage 5's delta is exactly its own MAE minus stage 4's")
chk(4, s5["n_races"] == s4["n_races"] == 69,
    "both stages scored the same 69 races, so they are comparable")

# ------------------------------------------------------- [3] paired effect
rule("[3] PAIRED PER-RACE EFFECT OF THE WEATHER GROUP")
eff = model.paired_mae_effect(s4, s5)
print(f"  races paired                : {eff['n_races']}")
print(f"  MAE before (18 features)    : {eff['mae_before']:.4f}")
print(f"  MAE after  (18 + weather)   : {eff['mae_after']:.4f}")
print(f"  delta (after - before)      : {eff['delta']:+.4f} positions")
print(f"  relative change             : {eff['pct']:+.3f}% "
      f"({'improvement' if eff['delta'] < 0 else 'regression'})")
print(f"  bootstrap 95% CI (10000 resamples)  : "
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
pr = eff["per_race"].copy()
q = pr["delta"].quantile([0.0, 0.05, 0.5, 0.95, 1.0])
n_better = int((pr["delta"] < 0).sum())
worse = pr[pr["delta"] > 0].sort_values("delta", ascending=False)
print("  distribution of the 69 paired differences (after - before):")
print(f"    min {q[0.0]:+.4f}   p5 {q[0.05]:+.4f}   median {q[0.5]:+.4f}   "
      f"p95 {q[0.95]:+.4f}   max {q[1.0]:+.4f}")
print(f"    mean {pr['delta'].mean():+.4f}   "
      f"the {len(worse)} worse are worth {worse['delta'].sum():+.4f}, "
      f"the {n_better} better are worth "
      f"{pr.loc[pr['delta'] < 0, 'delta'].sum():+.4f}")
print()
print("  worst 3 races for the weather group:")
for _, r in worse.head(3).iterrows():
    print(f"    {int(r['year'])} R{int(r['round'])}  "
          f"MAE {r['mae_before']:.3f} -> {r['mae_after']:.3f}  "
          f"({r['delta']:+.3f})")
print()
print("  The interval treats races as independent. Walk-forward folds SHARE")
print("  training data, so this CI is optimistic - stated in LIMITATIONS.md.")

# ---------------------------------------------------------- [4] baselines
rule("[4] RANKING BASELINES FOR CONTEXT")
bl = model.run_baselines(df)
print(f"  {'ranking':<40} {'MAE':>7} {'Spearman':>9}")
print(f"  {'-'*40} {'-'*7} {'-'*9}")
print(f"  {'MODEL (18 + weather, stage 5)':<40} "
      f"{s5['mae']:>7.3f} {s5['rho']:>9.4f}")
print(f"  {'MODEL (18 features, stage 4)':<40} "
      f"{s4['mae']:>7.3f} {s4['rho']:>9.4f}")
print(f"  {'MODEL (12 features, stage 3)':<40} "
      f"{stages[3]['mae']:>7.3f} {stages[3]['rho']:>9.4f}")
for label, b in bl.items():
    print(f"  {label:<40} {b['mae']:>7.3f} {b['rho']:>9.4f}")
best = min(b["mae"] for b in bl.values())
best_label = min(bl, key=lambda k: bl[k]["mae"])
print(f"  {'-'*40} {'-'*7} {'-'*9}")
print(f"  {'best baseline':<40} {best:>7.3f}   ({best_label})")
d_best = s5["mae"] - best
print(f"  {'MODEL - best baseline':<40} {d_best:>+7.3f}   "
      f"({'beats it' if d_best < 0 else 'does NOT beat it'})")
chk(5, d_best < 0, "the weather-extended model still beats the best baseline")

# ------------------------------------------------- [5] shuffled-label control
rule("[5] SHUFFLED-LABEL CONTROL ON THE SAME 25 FEATURES")
shuf = model.walk_forward(df, list(features.PHASE6_FEATURES),
                         shuffle=True, seed=0)
print(f"  real labels   MAE {s5['mae']:.4f}   Spearman {s5['rho']:.4f}")
print(f"  shuffled      MAE {shuf['mae']:.4f}   Spearman {shuf['rho']:.4f}")
print(f"  shuffle penalty: {shuf['mae'] - s5['mae']:+.4f} positions")
chk(6, shuf["mae"] > s5["mae"] + 1.0,
    "shuffling the targets destroys performance (>= +1.0 worse)")

# ------------------------------------------------------------- [6] verdict
rule("[6] VERDICT")
print(f"  weather group moved MAE {s4['mae']:.3f} -> {s5['mae']:.3f} "
      f"({eff['delta']:+.3f})")
if eff["excludes_zero"] and eff["delta"] < 0:
    print(f"  and the 95% interval [{eff['ci_low']:+.4f}, "
          f"{eff['ci_high']:+.4f}] excludes 0 -> weather genuinely helps;")
    print(f"  {eff['n_improved']} of {eff['n_races']} races improved.")
elif eff["excludes_zero"] and eff["delta"] > 0:
    print(f"  but the 95% interval [{eff['ci_low']:+.4f}, "
          f"{eff['ci_high']:+.4f}] excludes 0 -> weather HURTS.")
else:
    print(f"  the 95% interval [{eff['ci_low']:+.4f}, "
          f"{eff['ci_high']:+.4f}] CONTAINS 0, so on this evidence the")
    print(f"  weather group has NOT been shown to help. It must be reported as")
    print(f"  'no measurable effect', not as an improvement.")
print()
print("  Two mismatches are recorded in LIMITATIONS.md rather than glossed")
print("  over: observed historical weather is not the weather forecast a")
print("  real prediction would use, and these are whole-DAY totals rather")
print("  than race-time readings (2023 Spain: a rainy day, a dry race).")

rule("RESULT")
if FAILS:
    print(f"  {len(FAILS)} FAILED:")
    for f in FAILS:
        print(f"    - {f}")
    sys.exit(1)
print("  all checks PASS")
sys.exit(0)
