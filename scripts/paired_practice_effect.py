"""Is the practice group's -0.023 MAE distinguishable from noise?

Stage 1 (grid + form) and stage 2 (+ practice) are evaluated on the IDENTICAL
69 walk-forward races, so the natural comparison is PAIRED: for each race take

        d_i = MAE(stage 2 on race i) - MAE(stage 1 on race i)

and ask whether the mean of the d_i is reliably below zero.

Three views, in order of how much they assume:
  * bootstrap over races (resample the 69 paired differences with
    replacement) -> 95% percentile CI on the mean. This is the requested
    interval and it makes no distributional assumption;
  * sign test -> only counts how many races improved, ignores magnitude;
  * Wilcoxon signed-rank -> uses magnitudes but assumes symmetry.

If the bootstrap CI contains 0 we must report the practice group as
INCONCLUSIVE regardless of what the other two say.

READ-ONLY: builds features and fits models, writes nothing to f1.db.

Run:  python scripts/paired_practice_effect.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.stats import binomtest, wilcoxon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model  # noqa: E402

B = 10_000          # bootstrap resamples
SEED = 0            # fixed so the interval is reproducible
ALPHA = 0.05        # 95% interval

con = db.connect()
con.row_factory = None
df = features.build_features(con)
con.close()


def rule(t=""):
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


stages = model.run_ladder(df)
s1 = stages[1]                      # grid + driver/team form + non-finish rate
s2 = stages[2]                      # + practice position, gap, laps, missing flag

a = s1["per_race"][["year", "round", "mae"]].rename(columns={"mae": "stage1"})
b = s2["per_race"][["year", "round", "mae"]].rename(columns={"mae": "stage2"})
m = a.merge(b, on=["year", "round"], validate="one_to_one")
m["d"] = m["stage2"] - m["stage1"]  # negative = practice helped

d = m["d"].to_numpy(float)
n = d.size

rule("PAIRED PER-RACE DIFFERENCE: practice group (stage 2 minus stage 1)")
print(f"  both stages scored on the SAME {n} walk-forward races, so the")
print(f"  comparison is paired race-by-race, not two independent means")
print(f"  d_i = MAE(stage 2, race i) - MAE(stage 1, race i)")
print()
print(f"  mean difference      : {d.mean():+.4f} positions MAE")
print(f"  median difference    : {np.median(d):+.4f}")
print(f"  std of differences   : {d.std(ddof=1):.4f}")
print(f"  races improved       : {int((d < 0).sum())} / {n}")
print(f"  races worsened       : {int((d > 0).sum())} / {n}")
print(f"  ties                 : {int((d == 0).sum())}")
print(f"  best single race     : {d.min():+.4f}")
print(f"  worst single race    : {d.max():+.4f}")

# ------------------------------------------------------------- bootstrap
rng = np.random.default_rng(SEED)
idx = rng.integers(0, n, size=(B, n))
boot_means = d[idx].mean(axis=1)
lo, hi = np.percentile(boot_means, [100 * ALPHA / 2, 100 * (1 - ALPHA / 2)])

print()
print("=" * 78)
print(f"BOOTSTRAP OVER RACES  (B={B:,} resamples, seed={SEED}, "
      f"{int((1-ALPHA)*100)}% interval)")
print("=" * 78)
print(f"  resample the {n} paired differences with replacement, take the mean,")
print(f"  repeat {B:,} times")
print()
print(f"  point estimate (observed mean) : {d.mean():+.4f}")
print(f"  95% CI                         : [{lo:+.4f}, {hi:+.4f}]")
print(f"  bootstrap SE                   : {boot_means.std(ddof=1):.4f}")

contains_zero = lo <= 0 <= hi
print()
if contains_zero:
    print("  VERDICT: the interval CONTAINS 0.")
    print("  The -0.023 improvement is NOT distinguishable from noise at the")
    print(f"  {int((1-ALPHA)*100)}% level. Report the practice group as")
    print("  INCONCLUSIVE - do not claim it helps.")
else:
    print("  VERDICT: the interval EXCLUDES 0.")
    print(f"  The improvement is statistically distinguishable from noise")
    print(f"  at the {int((1-ALPHA)*100)}% level under this resampling.")

# --------------------------------------------- sign test + Wilcoxon (extra)
print()
print("=" * 78)
print("CORROBORATING TESTS (same paired differences)")
print("=" * 78)

nonzero = d[d != 0]
k = int((nonzero < 0).sum())
nn = nonzero.size
p_sign = binomtest(k, nn, 0.5).pvalue
print(f"  sign test      : {k} of {nn} non-tied races improved, "
      f"two-sided p = {p_sign:.4f}")

try:
    w = wilcoxon(d)
    print(f"  Wilcoxon signed-rank : statistic = {w.statistic:.1f}, "
          f"two-sided p = {w.pvalue:.4f}")
except ValueError as exc:
    print(f"  Wilcoxon signed-rank : not computable ({exc})")

print()
print("  Both are two-sided tests of 'no effect'. They are reported for")
print("  context; the bootstrap interval above is the primary answer.")

# ------------------------------------------------- is it one bad race?
print()
print("=" * 78)
print("SENSITIVITY: does one race drive the result?")
print("=" * 78)
print(f"  {'excluded race':<16} {'mean of remaining':>18} {'improved':>10}")
worst = int(np.argmax(d))
best = int(np.argmin(d))
for label, drop in (
    ("none", None),
    (f"worst ({int(m.iloc[worst]['year'])} R{int(m.iloc[worst]['round'])})", worst),
    (f"best ({int(m.iloc[best]['year'])} R{int(m.iloc[best]['round'])})", best),
):
    sub = np.delete(d, drop) if drop is not None else d
    print(f"  {label:<16} {sub.mean():>+18.4f} "
          f"{int((sub < 0).sum()):>6}/{sub.size}")

print()
print("  If the sign flips when a single race is removed, the group's effect")
print("  is fragile and should be described as weak evidence either way.")

rule("SUMMARY")
print(f"  observed mean difference : {d.mean():+.4f} positions MAE")
print(f"  95% bootstrap CI         : [{lo:+.4f}, {hi:+.4f}]")
print(f"  excludes 0?              : {'YES' if not contains_zero else 'NO'}")
print(f"  sign test p              : {p_sign:.4f}")
print()
if contains_zero:
    print("  => PRACTICE GROUP: INCONCLUSIVE (CI includes 0).")
    print("     The point estimate favours keeping practice features, but the")
    print("     data cannot separate a real -0.023 from ordinary race-to-race")
    print("     variation. This is the honest reading and must be reported")
    print("     as such, not as 'practice improves MAE'.")
else:
    print("  => PRACTICE GROUP: improvement is distinguishable from noise.")
    print(f"     The interval [{lo:+.4f}, {hi:+.4f}] lies below 0.")

sys.exit(0)
