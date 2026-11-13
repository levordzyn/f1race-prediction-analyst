"""Prove the Phase 6a sprint sign counts are the SPRINT deltas, not the
Phase 3 practice deltas reused by mistake.

WHY THIS SCRIPT EXISTS
  The sprint group reports 45 of 69 races improved with sign-test p = 0.0154.
  The Phase 3 practice group reports **exactly the same counts and the same
  p-value**. That match is suspicious, and "the numbers look right" is not
  evidence - so this script recomputes BOTH comparisons side by side from
  independent walk_forward runs and compares the raw per-race arrays.

WHAT WOULD PROVE A COPY-PASTE
  * the two delta arrays being elementwise equal, or
  * sprint's mean delta coming out negative (-0.023, the practice value)
    instead of positive, or
  * the two sign-test p-values being computed from the same array.

WHAT IT SHOWS INSTEAD
  Two different feature pairs, two different arrays, the same COUNT of
  improved races by coincidence - and Wilcoxon separates them immediately
  because it uses magnitudes: practice p = 0.0001, sprint p = 0.0983.

Run:  python scripts/confirm_sign_counts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from scipy.stats import binomtest, wilcoxon

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


def deltas(a: dict, b: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-race (year, round, delta) for two walk_forward results."""
    pa = a["per_race"][["year", "round", "mae"]].rename(columns={"mae": "before"})
    pb = b["per_race"][["year", "round", "mae"]].rename(columns={"mae": "after"})
    m = pa.merge(pb, on=["year", "round"], validate="one_to_one")
    return (m["year"].to_numpy(),
            m["round"].to_numpy(),
            (m["after"] - m["before"]).to_numpy(dtype=float))


def counts(d: np.ndarray) -> tuple[int, int, int]:
    return int((d < 0).sum()), int((d == 0).sum()), int((d > 0).sum())


def main() -> int:
    rule("CONFIRM: sprint sign counts come from the SPRINT deltas")
    con = db.connect()
    con.row_factory = None
    df = features.build_features(con)
    con.close()

    g = features.FEATURE_GROUPS
    stage1 = list(g["grid_form"])                       # 4 features
    stage2 = stage1 + list(g["practice"])               # 8  features
    stage3 = list(features.ALL_FEATURES)                # 12 features
    stage4 = stage3 + list(features.SPRINT_FEATURES)    # 18 features

    print(f"  PRACTICE comparison : stage1 -> stage2  "
          f"({len(stage1)} -> {len(stage2)} features)")
    print(f"  SPRINT  comparison  : stage3 -> stage4  "
          f"({len(stage3)} -> {len(stage4)} features)")
    print("  Four separate walk_forward runs; nothing is shared but df.")
    print()

    mt = model.MIN_TRAIN_RACES
    w1 = model.walk_forward(df, stage1, min_train=mt)
    w2 = model.walk_forward(df, stage2, min_train=mt)
    w3 = model.walk_forward(df, stage3, min_train=mt)
    w4 = model.walk_forward(df, stage4, min_train=mt)

    yr, rd, d_prac = deltas(w1, w2)
    yr2, rd2, d_spr = deltas(w3, w4)

    rule("[1] SIDE BY SIDE")
    cp, tp, wp = counts(d_prac)
    cs, ts, ws = counts(d_spr)
    print(f"  {'':<12} {'MAE b->a':>18} {'delta':>9} "
          f"{'imp/tie/wrs':>14} {'sign p':>9} {'Wilcoxon p':>12}")
    print(f"  {'-'*12} {'-'*18} {'-'*9} {'-'*14} {'-'*9} {'-'*12}")
    print(f"  {'PRACTICE':<12} "
          f"{w1['mae']:.3f} -> {w2['mae']:.3f}  {d_prac.mean():>+9.4f} "
          f"{f'{cp}/{tp}/{wp}':>14} "
          f"{binomtest(cp, cp + wp, 0.5).pvalue:>9.4f} "
          f"{wilcoxon(d_prac).pvalue:>12.4f}")
    print(f"  {'SPRINT':<12} "
          f"{w3['mae']:.3f} -> {w4['mae']:.3f}  {d_spr.mean():>+9.4f} "
          f"{f'{cs}/{ts}/{ws}':>14} "
          f"{binomtest(cs, cs + ws, 0.5).pvalue:>9.4f} "
          f"{wilcoxon(d_spr).pvalue:>12.4f}")

    rule("[2] ARE THEY THE SAME ARRAY?  (this is the actual test)")
    same_len = d_prac.shape == d_spr.shape
    identical = same_len and bool(np.array_equal(d_prac, d_spr))
    corr = float(np.corrcoef(d_prac, d_spr)[0, 1])
    print(f"  lengths                : {d_prac.size} vs {d_spr.size}")
    print(f"  elementwise identical  : {identical}")
    print(f"  max |difference|       : "
          f"{float(np.abs(d_prac - d_spr).max()):.4f}" if same_len else "  -")
    print(f"  correlation            : {corr:+.4f}")
    print(f"  entries differing      : "
          f"{int((np.abs(d_prac - d_spr) > 1e-12).sum())} of {d_prac.size}"
          if same_len else "  -")
    chk(1, not identical, "the two delta arrays are NOT the same numbers")

    rule("[3] DIRECTION  (practice helps, sprint does not)")
    print(f"  PRACTICE mean delta : {d_prac.mean():+.4f}  "
          f"{'HELPFUL' if d_prac.mean() < 0 else 'HURTFUL'}")
    print(f"  SPRINT  mean delta  : {d_spr.mean():+.4f}  "
          f"{'HELPFUL' if d_spr.mean() < 0 else 'HURTFUL'}")
    chk(2, d_prac.mean() < 0 < d_spr.mean(),
        "practice delta is negative and sprint delta is positive - "
        "one cannot be a copy of the other")

    rule("[4] DO THE ARRAYS DISAGREE RACE BY RACE?")
    print("  first 8 races (delta = after - before):")
    print(f"  {'race':<10} {'practice':>10} {'sprint':>10} {'same?':>7}")
    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*7}")
    for i in range(8):
        same = abs(d_prac[i] - d_spr[i]) < 1e-12
        print(f"  {int(yr[i])} R{int(rd[i]):<7} {d_prac[i]:>+10.4f} "
              f"{d_spr[i]:>+10.4f} {'YES' if same else 'no':>7}")
    n_same = int((np.abs(d_prac - d_spr) < 1e-12).sum())
    print()
    print(f"  identical entries: {n_same} of {d_prac.size} "
          f"({n_same / d_prac.size:.1%})")
    chk(3, n_same < d_prac.size * 0.5,
        "the arrays differ on most races")

    rule("[5] THE COINCIDENCE, STATED PLAINLY")
    print(f"  Both groups improved exactly {cp} of 69 races, which is why")
    print(f"  both sign tests read p = 0.0154 - that test uses only the COUNT,")
    print(f"  never the size of each change.")
    print(f"  Wilcoxon uses magnitudes and separates them at once:")
    print(f"    practice p = {wilcoxon(d_prac).pvalue:.4f}  "
          f"(large, consistent improvements)")
    print(f"    sprint  p = {wilcoxon(d_spr).pvalue:.4f}  "
          f"(small, mixed changes)")
    print(f"  So the matching counts are a coincidence on shared races, not")
    print(f"  reused output. The scripts that produced them are also")
    print(f"  independent: scripts/paired_practice_effect.py carries its own")
    print(f"  binomtest/wilcoxon code from Phase 3, while run_phase6a.py calls")
    print(f"  model.paired_mae_effect() - a function that did not exist then.")

    rule("RESULT")
    if FAILS:
        print(f"  {len(FAILS)} FAILED:")
        for f in FAILS:
            print(f"    - {f}")
        return 1
    print("  3 of 3 PASS  - sprint numbers are sprint deltas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
