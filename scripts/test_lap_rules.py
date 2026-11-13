"""Unit tests for the two lap-validity rules, on SYNTHETIC lap records.

Why this exists
---------------
Rule 2 (implausible speed) rejected 0 laps on real data - rule 1 catches the
corrupt laps first. That leaves rule 2 as untested insurance: nothing proves it
would ever fire. These tests construct lap records by hand so both rules are
exercised directly, including the exact 90% boundary.

All lap records below are fabricated; no network and no database are touched.

Run:  python scripts/test_lap_rules.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import openf1 as o1  # noqa: E402

FAILED = 0


def make_lap(driver: float, dur: float, lap_no: int = 1,
             sectors: bool = True, pit_out: bool = False) -> dict:
    """A lap record whose three sectors sum to `dur` (within float noise).

    With sectors=False every sector time is None, which is how a lap record
    that simply has no sector data arrives.
    """
    if sectors:
        s1 = round(dur * 0.40, 3)
        s2 = round(dur * 0.35, 3)
        s3 = round(dur - s1 - s2, 3)
    else:
        s1 = s2 = s3 = None
    return {
        "driver_number": driver,
        "lap_duration": dur,
        "lap_number": lap_no,
        "is_pit_out_lap": pit_out,
        "duration_sector_1": s1,
        "duration_sector_2": s2,
        "duration_sector_3": s3,
    }


def normal_field(n: int = 11, base: float = 90.0) -> list[dict]:
    """n well-behaved laps, 0.5 s apart, all sector-consistent."""
    return [make_lap(i + 1, base + 0.5 * i, lap_no=i + 1)
            for i in range(n)]


def check(n: int, cond: bool, label: str, detail: str = "") -> None:
    global FAILED
    if not cond:
        FAILED += 1
    print(f"  [{n}] {label:<64} {'PASS' if cond else 'FAIL'}{detail}")


def reasons(laps):
    _valid, rejected = o1.classify_laps(laps)
    return [(l.get("driver_number"), r) for l, r in rejected]


def rule(title: str) -> None:
    print("=" * 78)
    print(title)
    print("=" * 78)


# ============================================================ RULE 2 FIRES
rule("RULE 2 (implausible speed) - does it actually trigger?")

fast = make_lap(99, 70.0, lap_no=12)          # 22% quicker than the field
field = normal_field(11)                       # 90.0 .. 95.0
laps = field + [fast]

rej = reasons(laps)
print(f"  session: 11 normal laps (90.000..95.000 s) + one 70.000 s lap")
print(f"  reference = 2nd fastest = 90.000 s, "
      f"floor = 90.000 * {o1.MIN_LAP_FRACTION:.0%} = "
      f"{90.0 * o1.MIN_LAP_FRACTION:.3f} s")
print(f"  rejections: {rej}")
print()

check(1, (99, o1.REJECT_FAST) in rej,
      "the 70.000 s lap IS rejected by rule 2",
      " (this is the case that never occurred in real data)")
check(2, all(r == o1.REJECT_FAST for _d, r in rej) and len(rej) == 1,
      "exactly one lap rejected, and by rule 2 only",
      f" ({len(rej)})")
check(3, not any(r == o1.REJECT_SECTOR for _d, r in rej),
      "rule 1 stays silent (all sectors add up)")

# what best_practice_laps then stores for that driver
best = o1.best_practice_laps(laps)
check(4, best[99]["best_lap_s"] is None,
      "driver 99 gets best_lap_s = None (their only lap was rejected)")
check(5, best[99]["lap_count"] == 1,
      "but lap_count still counts the rejected lap",
      f" ({best[99]['lap_count']}) - the driver did drive it")
check(6, best[1]["best_lap_s"] == 90.0,
      "an untouched driver still records 90.000 s")

# ====================================================== RULE 2 GUARDED
rule("RULE 2 is guarded - it must NOT fire where the reference is untrustworthy")

small = [make_lap(99, 70.0, lap_no=1)] + [make_lap(i + 1, 90.0 + i, i + 2)
                                           for i in range(4)]
rej_small = reasons(small)
print(f"  session with only {len(small)} usable laps "
      f"(threshold is {o1.MIN_LAPS_FOR_REFERENCE})")
print(f"  rejections: {rej_small}")
print()
check(7, not any(r == o1.REJECT_FAST for _d, r in rej_small),
      "rule 2 is SKIPPED below MIN_LAPS_FOR_REFERENCE",
      f" ({len(small)} < {o1.MIN_LAPS_FOR_REFERENCE} laps)")

slow = normal_field(11) + [make_lap(50, 150.0, lap_no=12)]
rej_slow = reasons(slow)
check(8, not any(r == o1.REJECT_FAST for _d, r in rej_slow),
      "a very SLOW lap (150 s) is never rejected by rule 2",
      f" ({[r for _d, r in rej_slow]})")

# ========================================================= BOUNDARY TEST
rule("RULE 2 boundary - the 90% cutoff exactly")

kept_at = []
rej_just_below = []
for dur in (81.0, 80.999):                     # floor = 90.0 * 0.90 = 81.000
    laps_b = normal_field(11) + [make_lap(99, dur, lap_no=12)]
    _v, r = o1.classify_laps(laps_b)
    hit = any(l.get("driver_number") == 99 and reason == o1.REJECT_FAST
              for l, reason in r)
    if dur == 81.0:
        kept_at.append(not hit)
    else:
        rej_just_below.append(hit)

print(f"  reference 90.000 s -> floor exactly {90.0 * o1.MIN_LAP_FRACTION:.6f} s")
print(f"    lap at  81.000 s : {'KEPT' if kept_at[0] else 'rejected'}")
print(f"    lap at  80.999 s : {'rejected' if rej_just_below[0] else 'KEPT'}")
print()
check(9, kept_at[0],
      "a lap exactly AT the floor is kept (comparison is strict <)")
check(10, rej_just_below[0],
      "a lap 0.001 s BELOW the floor is rejected")

# ============================================================ RULE 1 TESTS
rule("RULE 1 (sector arithmetic) - both directions")

bad = make_lap(81, 60.351, lap_no=35)
bad.update({"duration_sector_1": 69.447, "duration_sector_2": 37.656,
            "duration_sector_3": 95.517})       # real Miami record: sums 202.620
rej_bad = reasons(normal_field(11) + [bad])
check(11, (81, o1.REJECT_SECTOR) in rej_bad,
      "Miami's 60.351 s record (sectors sum 202.620) IS rejected",
      f" off by {abs(69.447 + 37.656 + 95.517 - 60.351):.3f} s")

no_sec = make_lap(77, 92.0, lap_no=3, sectors=False)
rej_ns = reasons(normal_field(11) + [no_sec])
print(f"  lap with ALL sector times missing: "
      f"rejections for driver 77 = "
      f"{[r for d, r in rej_ns if d == 77]}")
check(12, not any(d == 77 for d, _r in rej_ns),
      "a lap with MISSING sectors is never rejected by rule 1",
      " (no evidence = no verdict, it is kept)")

near = make_lap(78, 92.0, lap_no=3)
near.update({"duration_sector_1": 30.0, "duration_sector_2": 30.0,
             "duration_sector_3": 31.9})         # sums 91.9, off by 0.100
rej_near = reasons(normal_field(11) + [near])
hit_near = any(d == 78 and r == o1.REJECT_SECTOR for d, r in rej_near)
print(f"  lap whose sectors miss by exactly {o1.SECTOR_TOLERANCE_S} s: "
      f"{'rejected' if hit_near else 'kept'}")
check(13, not hit_near,
      "an offset within tolerance is kept (boundary is >, not >=)")

# ==================================================== SUMMARY
print()
rule("RESULT")
if FAILED:
    print(f"  {FAILED} TEST(S) FAILED")
else:
    print("  ALL TESTS PASSED")
print(f"  rules under test: SECTOR_TOLERANCE_S={o1.SECTOR_TOLERANCE_S} s, "
      f"MIN_LAP_FRACTION={o1.MIN_LAP_FRACTION:.2f}, "
      f"MIN_LAPS_FOR_REFERENCE={o1.MIN_LAPS_FOR_REFERENCE}")
sys.exit(1 if FAILED else 0)
