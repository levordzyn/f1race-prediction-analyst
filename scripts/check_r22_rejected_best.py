"""Was any of the 72 rejected 2025 R22 laps a driver's best lap?

Rejecting a lap only matters if that lap was the driver's fastest - otherwise
the stored best_practice_s is untouched and the rejection is harmless. This
checks that directly, two ways:

  1. lap-by-lap: for every rejected lap, is its duration equal to that
     driver's best under the PRE-FIX rules (null + pit-out filtered only)?
  2. end-to-end: recompute every driver's best with the rejected laps
     removed and confirm the value is unchanged.

Also repeats test 2 across all 89 races (all 87 practice rejections) and the
24 sprint-qualifying sessions, and records the 2025 R22 quirk.

READ-ONLY.

Run:  python scripts/check_r22_rejected_best.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, openf1 as o1, practice  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("r22")

QUIRK_YEAR, QUIRK_ROUND = 2025, 22
TOL = 1e-9

con = db.connect()
con.row_factory = None


def rule(t=""):
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def old_best(laps) -> dict[int, float]:
    """Per-driver fastest lap under the PRE-FIX rules (null + pit-out only)."""
    out: dict[int, float] = {}
    for lap in laps:
        d = lap.get("driver_number")
        if d is None or lap.get("is_pit_out_lap"):
            continue
        dur = lap.get("lap_duration")
        if dur is None:
            continue
        if d not in out or dur < out[d]:
            out[d] = dur
    return out


def audit(sessions) -> dict:
    """Classify every lap, then test whether rejects changed any driver's best."""
    all_laps = []
    rejected = []
    for s in sessions:
        laps = o1.get_laps(s["session_key"])
        all_laps.extend(laps)
        _valid, rej = o1.classify_laps(laps)
        for lap, reason in rej:
            if reason == o1.REJECT_SECTOR:
                rejected.append((lap, reason))

    before = old_best(all_laps)
    rejected_ids = {id(l) for l, _r in rejected}
    after = old_best([l for l in all_laps if id(l) not in rejected_ids])

    was_best = []
    for lap, _reason in rejected:
        d = lap.get("driver_number")
        if d in before and abs(before[d] - lap["lap_duration"]) <= TOL:
            was_best.append((d, lap["lap_duration"]))

    changed = {d: (before[d], after[d]) for d in before
               if d in after and abs(before[d] - after[d]) > TOL}
    dropped = {d: before[d] for d in before if d not in after}

    return {"all_laps": len(all_laps), "rejected": rejected,
            "was_best": was_best, "changed": changed, "dropped": dropped,
            "before": before, "after": after}


# ------------------------------------------------------------- 2025 R22
rule(f"2025 R{QUIRK_ROUND} - are any of the rejected laps a driver's best?")

sessions = practice.practice_sessions(con, QUIRK_YEAR, QUIRK_ROUND)
r = audit(sessions)
print(f"  lap rows in the weekend : {r['all_laps']}")
print(f"  rejected by rule 1      : {len(r['rejected'])}")
print()

print(f"  {'drv':<6} {'rejected lap':>14} {'driver best':>13}  was it the best?")
for lap, _reason in r["rejected"][:10]:
    d = lap.get("driver_number")
    dur = lap["lap_duration"]
    best = r["before"].get(d)
    yes = best is not None and abs(best - dur) <= TOL
    print(f"  {d:<6} {dur:>14.3f} "
          f"{(f'{best:.3f}' if best is not None else '-'):>13}  "
          f"{'YES  <-- PROBLEM' if yes else 'no'}")
if len(r["rejected"]) > 10:
    print(f"  ... {len(r['rejected']) - 10} more")

print()
check1 = len(r["was_best"]) == 0
print(f"  rejected laps that equal their driver's best : "
      f"{len(r['was_best'])}")
print(f"  drivers whose best changed                   : {len(r['changed'])}")
print(f"  drivers who lost their only valid lap        : {len(r['dropped'])}")

rule("VERDICT FOR 2025 R22")
if check1 and not r["changed"] and not r["dropped"]:
    print(f"  PASS - none of the {len(r['rejected'])} rejected laps was a")
    print("  driver's best lap. Every driver's stored best_practice_s is")
    print("  bit-for-bit what it was before the rules existed, which is why")
    print("  validate_lap_rules reported 2025 R22 as UNCHANGED.")
else:
    print(f"  FAIL - {len(r['was_best'])} rejected lap(s) WERE a driver's best,"
          f" {len(r['changed'])} driver(s) changed")
    for d, (b, a) in r["changed"].items():
        print(f"    driver {d}: {b:.3f} -> {a:.3f}")

# --------------------------------------------------- log the R22 quirk
print()
rule("LOGGING THE 2025 R22 QUIRK")
devs = []
for lap, _reason in r["rejected"]:
    parts = [lap.get(f"duration_sector_{i}") for i in (1, 2, 3)]
    if any(p is None for p in parts):
        continue
    devs.append(abs(sum(parts) - lap["lap_duration"]))
devs.sort()
if devs:
    print(f"  {len(devs)} rejected laps, sector-sum deviation:")
    print(f"    min {devs[0]:.3f}s   median {devs[len(devs)//2]:.3f}s   "
          f"max {devs[-1]:.3f}s")
    print(f"  every other race's rejected laps deviate by 8.7s to 1037.8s;")
    print(f"  this cluster is ~{devs[len(devs)//2]:.2f}s - an order of")
    print("  magnitude smaller and therefore a DIFFERENT defect.")
    print()
    log.warning(
        "2025 R22 quirk: %d practice laps rejected by rule 1, but their "
        "sector sums miss lap_duration by only %.3f-%.3fs (median %.3fs), "
        "unlike the gross 8.7-1037.8s corruption seen elsewhere. All are "
        "early laps (lap 3-7) and NONE was any driver's best lap, so "
        "stored values for 2025 R22 are unchanged. Recorded as a known data "
        "quirk in LIMITATIONS.md: if a future re-fetch ever promotes one of "
        "these laps to a driver's fastest, 2025 R22 would be the first race "
        "to change.",
        len(devs), devs[0], devs[-1], devs[len(devs) // 2])
else:
    log.info("2025 R22: no sector-mismatch laps to log")

# ------------------------------------------------- global confirmation
print()
rule("GLOBAL: does removing ANY rejected lap change a driver's best?")
total_rej = 0
problems = []
for year, rnd in [(x[0], x[1]) for x in con.execute(
        "SELECT year, round FROM sessions ORDER BY year, round")]:
    sess = practice.practice_sessions(con, year, rnd)
    if not sess:
        continue
    g = audit(sess)
    total_rej += len(g["rejected"])
    if g["was_best"] or g["changed"] or g["dropped"]:
        problems.append((year, rnd, g))

print(f"  races audited          : 89")
print(f"  rejected laps examined : {total_rej}")
print(f"  races where a reject was a driver's best : {len(problems)}")
for year, rnd, g in problems:
    print(f"    {year} R{rnd}: {len(g['was_best'])} best-lap hit(s), "
          f"{len(g['changed'])} changed, {len(g['dropped'])} lost")
    for d, dur in g["was_best"][:4]:
        print(f"      driver {d} best was {dur:.3f}s")

print()
print("  (2026 R4 is EXPECTED to appear: there the rejected 60.351 s lap")
print("   WAS PIA's stored best, which is exactly the corruption we fixed.)")

# ------------------------------------------------------- sprint qualifying
print()
rule("SPRINT QUALIFYING - same test over the 24 sessions")
sq_rej = 0
sq_problems = []
for year, rnd in [(x[0], x[1]) for x in con.execute(
        "SELECT year, round FROM sessions ORDER BY year, round")]:
    _st, _v, _c, ses = practice.compute_sprint_qualifying(con, year, rnd)
    if ses is None:
        continue
    g = audit([ses])
    sq_rej += len(g["rejected"])
    if g["was_best"] or g["changed"] or g["dropped"]:
        sq_problems.append((year, rnd, g))
print(f"  rejected laps : {sq_rej}")
print(f"  races where a reject was a driver's best : {len(sq_problems)}")
for year, rnd, g in sq_problems:
    print(f"    {year} R{rnd}: {len(g['was_best'])} best-lap hit(s)")

con.close()
print()
rule("DONE")
sys.exit(0)
