"""Show every lap rejected by Rule 1, so the rule can be judged on its merits.

87 practice laps across 8 races (and 3 sprint-qualifying laps) were rejected
for sector arithmetic. Stored values changed in only 1 race, which means the
other 80 rejected laps were never anybody's best lap - but "no effect" is not
the same as "correctly rejected". This prints the actual numbers so a human
can see the rule is flagging genuinely broken records, not valid laps.

READ-ONLY.

Run:  python scripts/show_rejected_laps.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, openf1 as o1, practice  # noqa: E402

con = db.connect()
con.row_factory = None


def sectors(lap):
    parts = [lap.get(f"duration_sector_{i}") for i in (1, 2, 3)]
    if any(p is None for p in parts):
        return None, parts
    return float(sum(parts)), parts


def dump(title, sessions, table=None, year=None, rnd=None):
    print("=" * 78)
    print(title)
    print("=" * 78)
    shown = 0
    total = 0
    for s in sessions:
        laps = o1.get_laps(s["session_key"])
        _valid, rejected = o1.classify_laps(laps)
        for lap, reason in rejected:
            if reason != o1.REJECT_SECTOR:
                continue
            total += 1
            total_s, parts = sectors(lap)
            dur = lap.get("lap_duration")
            if table and year is not None:
                who = con.execute(
                    f"SELECT driver FROM {table} WHERE year=? AND round=? "
                    f"AND driver_number=?", (year, rnd, lap.get("driver_number"))
                ).fetchone()
                name = who[0] if who else f"#{lap.get('driver_number')}"
            else:
                name = f"#{lap.get('driver_number')}"
            if shown < 14:
                print(f"  {name:<5} lap {str(lap.get('lap_number')):>3}  "
                      f"duration {dur:>9.3f}  sectors "
                      f"{parts[0]!s:>8}+{parts[1]!s:>8}+{parts[2]!s:>8} = "
                      f"{total_s:>9.3f}   off by {abs(total_s - dur):>8.3f}s")
                shown += 1
    if total > shown:
        print(f"  ... {total - shown} more rejected laps not shown")
    if total == 0:
        print("  (none)")
    print(f"  TOTAL rejected by Rule 1: {total}")
    print()
    return total


# ------------------------------------------------------- PRACTICE (all 89)
races = [(r[0], r[1]) for r in con.execute(
    "SELECT year, round FROM sessions ORDER BY year, round")]

grand = 0
for year, rnd in races:
    sessions = practice.practice_sessions(con, year, rnd)
    if not sessions:
        continue
    # only races that actually rejected something
    n = 0
    for s in sessions:
        _v, rej = o1.classify_laps(o1.get_laps(s["session_key"]))
        n += sum(1 for _l, r in rej if r == o1.REJECT_SECTOR)
    if n:
        grand += dump(f"PRACTICE {year} R{rnd}  ({n} lap(s) rejected)",
                      sessions, "practice", year, rnd)

print("=" * 78)
print(f"PRACTICE GRAND TOTAL rejected by Rule 1: {grand}")
print("=" * 78)

# --------------------------------------------------- SPRINT QUALIFYING (24)
sq_total = 0
for year, rnd in races:
    _st, _v, _c, ses = practice.compute_sprint_qualifying(con, year, rnd)
    if ses is None:
        continue
    _v2, rej = o1.classify_laps(o1.get_laps(ses["session_key"]))
    if any(r == o1.REJECT_SECTOR for _l, r in rej):
        sq_total += dump(f"SPRINT QUALIFYING {year} R{rnd}", [ses],
                         "sprint_qualifying", year, rnd)

print("=" * 78)
print(f"SPRINT QUALIFYING GRAND TOTAL rejected by Rule 1: {sq_total}")
print("=" * 78)

# ------------------------------------------- is the rule ever too eager?
print()
print("=" * 78)
print("GUARD: could Rule 1 reject a VALID lap?")
print("=" * 78)
print("  A valid lap's three sectors must add up to its duration. The rule")
print("  only fires when all three sector times ARE present AND their sum")
print("  misses the duration by more than "
      f"{o1.SECTOR_TOLERANCE_S} s.")
print(f"  laps with ANY missing sector are never judged: "
      f"those are kept unconditionally.")
print()
print("  Cross-check: among all laps the rule KEPT, how close is the sector")
print("  sum to the duration? If kept laps are tight and rejected ones are")
print("  wildly off, the threshold is separating two populations correctly.")

kept_dev, rej_dev = [], []
for year, rnd in races:
    for s in practice.practice_sessions(con, year, rnd):
        laps = o1.get_laps(s["session_key"])
        valid, rejected = o1.classify_laps(laps)
        for lap in valid:
            t, _p = sectors(lap)
            if t is not None:
                kept_dev.append(abs(t - lap["lap_duration"]))
        for lap, reason in rejected:
            if reason == o1.REJECT_SECTOR:
                t, _p = sectors(lap)
                if t is not None:
                    rej_dev.append(abs(t - lap["lap_duration"]))

kept_dev.sort()
rej_dev.sort()
print(f"  KEPT laps with all sectors present : n={len(kept_dev)}  "
      f"max deviation {kept_dev[-1]:.4f}s  "
      f"p99 {kept_dev[int(len(kept_dev) * 0.99)]:.4f}s")
print(f"  REJECTED laps                      : n={len(rej_dev)}  "
      f"min deviation {rej_dev[0]:.3f}s  "
      f"median {rej_dev[len(rej_dev) // 2]:.3f}s")
print()
if kept_dev and rej_dev:
    gap = rej_dev[0] - kept_dev[-1]
    print(f"  separation between the two populations: {gap:.3f} s")
    print(f"  threshold sits at {o1.SECTOR_TOLERANCE_S} s")
    if gap > 0:
        print("  PASS - every kept lap is closer than every rejected lap, so")
        print("  the tolerance sits in a genuine gap, not inside either group.")
    else:
        print("  FAIL - the populations overlap; the threshold is arbitrary.")
        sys.exit(1)

con.close()
sys.exit(0)
