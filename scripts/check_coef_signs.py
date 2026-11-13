"""Is non_finish_rate's negative Ridge coefficient a bug or collinearity?

The coefficient chart shows non_finish_rate at -0.47, which reads as "a driver
who retires more often is predicted to finish BETTER". That is backwards on
its face, so before accepting the chart we need to know which of two stories
is true:

  A. DATA/FORMULA BUG  - the feature is built wrong, and its raw (marginal)
     relationship with finishing position is also backwards;
  B. COLLINEARITY      - the raw relationship is sensible (more retirements =
     worse finish), but Ridge splits weight between correlated predictors
     (driver_form, team_form, non_finish_rate all describe recent performance)
     and assigns a residual sign that contradicts the marginal one.

This compares, for every feature, the sign of the plain Spearman correlation
against finishing position with the sign of the Ridge coefficient from the
walk-forward model. Disagreement is only a problem if it happens for a feature
whose marginal relationship is ALSO wrong.

READ-ONLY.

Run:  python scripts/check_coef_signs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features, model  # noqa: E402

con = db.connect()
con.row_factory = None
df = features.build_features(con)
con.close()

# coefficients from the SAME walk-forward run the report uses
wf = model.walk_forward(df, list(features.ALL_FEATURES))
coef = wf["coef_mean"]


def rule(t=""):
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


rule("MARGINAL CORRELATION vs RIDGE COEFFICIENT, all 12 features")
print(f"  marginal = Spearman(feature, finish) over all {len(df)} rows;")
print(f"  finish is 1 = best, so a POSITIVE marginal correlation means the")
print(f"  feature rises with a WORSE finish - the intuitive direction for a")
print(f"  'bad' feature.")
print()
print(f"  {'feature':<20} {'marginal rho':>13} {'sign':>6}   "
      f"{'ridge coef':>11} {'sign':>6}   agree?")

rows = []
for name in features.ALL_FEATURES:
    rho = float(spearmanr(df[name].to_numpy(float),
                          df["finish"].to_numpy(float))[0])
    c = coef[name]
    m_sign = "+" if rho > 0 else "-"
    c_sign = "+" if c > 0 else "-"
    agree = m_sign == c_sign
    rows.append((name, rho, c, agree))
    print(f"  {name:<20} {rho:>+13.4f} {m_sign:>6}   {c:>+11.4f} "
          f"{c_sign:>6}   {'yes' if agree else 'NO'}")

print()
disagree = [r for r in rows if not r[3]]
print(f"  features where the two signs DISAGREE: {len(disagree)}")
for name, rho, c, _ in disagree:
    print(f"    {name}: marginal {rho:+.4f} ({'worse' if rho > 0 else 'better'}"
          f" finish) vs ridge {c:+.4f}")

# ------------------------------------------- is non_finish_rate correlated?
rule("IS non_finish_rate COLLINEAR WITH THE OTHER FORM FEATURES?")
for other in ("driver_form", "team_form", "grid", "q_position"):
    r = float(spearmanr(df["non_finish_rate"].to_numpy(float),
                        df[other].to_numpy(float))[0])
    print(f"  Spearman(non_finish_rate, {other:<12}) = {r:+.4f}")

print()
print("  A strong correlation with driver_form/team_form means the three")
print("  carry overlapping information. Ridge then divides the shared signal")
print("  among them and the leftover (residual) coefficient can take a sign")
print("  that contradicts the raw relationship.")

# ------------------------------------------ does the raw relationship hold?
rule("THE RAW RELATIONSHIP: average finish by non_finish_rate band")
print(f"  {'non_finish_rate band':<26} {'rows':>6} {'mean finish':>12}")
bands = [(0.0, 0.0), (0.0, 0.4), (0.4, 0.8), (0.8, 1.01)]
labels = ["0.0 (no DNFs)", "(0.0, 0.4)", "[0.4, 0.8)", "[0.8, 1.0]"]
for (lo, hi), lab in zip(bands, labels):
    if lo == 0.0 and hi == 0.0:
        sub = df[df["non_finish_rate"] == 0.0]
    else:
        sub = df[(df["non_finish_rate"] >= lo) & (df["non_finish_rate"] < hi)]
    if len(sub) == 0:
        print(f"  {lab:<26} {0:>6} {'-':>12}")
        continue
    print(f"  {lab:<26} {len(sub):>6} {sub['finish'].mean():>12.3f}")

print()
raw_r = float(spearmanr(df["non_finish_rate"].to_numpy(float),
                        df["finish"].to_numpy(float))[0])
print(f"  marginal Spearman(non_finish_rate, finish) = {raw_r:+.4f}")
print()
if raw_r > 0:
    print("  VERDICT: the RAW relationship is correct - more retirements over")
    print("  the last 5 races goes with a WORSE (higher-numbered) finish.")
    print("  So the feature is built correctly and there is no data bug.")
    print("  The negative Ridge coefficient is a COLLINEARITY artefact: with")
    print("  driver_form and team_form already in the model, the residual")
    print("  slice of non_finish_rate is small and flips sign.")
    print()
    print("  HOW TO REPORT IT: do not read individual coefficient signs as")
    print("  causal effects when predictors overlap. Report the group as a")
    print("  whole (the ladder already shows grid_form's combined effect) and")
    print("  say plainly that non_finish_rate's sign is not interpretable on")
    print("  its own.")
else:
    print("  VERDICT: the RAW relationship is ALSO backwards, which means the")
    print("  feature itself is suspect - investigate the formula before")
    print("  trusting any chart that includes it.")

sys.exit(0)
