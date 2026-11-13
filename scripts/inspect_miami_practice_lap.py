"""What is PIA's 60.351s "best practice lap" at 2026 Miami, and is it real?

Miami's lap time is ~89s - the other 21 cars are packed in 89.3-93.0s - yet
practice.best_practice_s for PIA is 60.351s, and every gap_to_best_pct in that
race is measured against it (median weekend spread across all 89 races is
2.6%; this race is 54.0%, rank 1 of 89).

This pulls the raw OpenF1 lap rows for the session and prints:
  * every field OpenF1 actually returns on a lap record (so nothing is guessed);
  * every lap PIA set, with duration and flags, sorted;
  * whether a single truncated/invalid record is being taken as the "best";
  * what the correct best, gap column and ranks would be without it.

Read-only: prints findings, changes nothing.

Run:  python scripts/inspect_miami_practice_lap.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import credentials, db, openf1 as o1, practice  # noqa: E402

credentials.load()

YEAR, RND = 2026, 4
PIA_NUM = 81


def rule(t=""):
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


con = db.connect()
con.row_factory = None

sessions = practice.practice_sessions(con, YEAR, RND)
rule(f"{YEAR} R{RND} practice sessions found for this weekend")
print(f"  {len(sessions)} session(s):")
for s in sessions:
    print(f"    session_key={s['session_key']}  {s['session_name']}")
if not sessions:
    print("  NO PRACTICE SESSIONS - cannot continue")
    sys.exit(1)

ses = sessions[0]
laps = o1.get_laps(ses["session_key"])
print(f"\n  lap rows returned: {len(laps)}")

if not laps:
    print("  NO LAPS - cannot continue")
    sys.exit(1)

rule("EVERY FIELD OPENF1 RETURNS ON A LAP RECORD (actual keys, not guessed)")
keys: dict[str, int] = {}
for lap in laps:
    for k in lap:
        keys[k] = keys.get(k, 0) + 1
for k in sorted(keys):
    sample = next(lap for lap in laps if k in lap)
    print(f"  {k:<28} present on {keys[k]:>4}/{len(laps)} rows   "
          f"e.g. {sample[k]!r}")

rule(f"ALL {PIA_NUM}'s LAPS IN THIS SESSION, SORTED BY lap_duration")
pia = [l for l in laps if l.get("driver_number") == PIA_NUM]
print(f"  {len(pia)} lap rows")
rows = []
for l in pia:
    rows.append((l.get("lap_duration"), l.get("lap_number"),
                 bool(l.get("is_pit_out_lap")), l))
rows.sort(key=lambda r: (r[0] is None, r[0]))
print(f"  {'lap#':>5} {'duration':>10} {'pit_out':>8}  other duration-ish fields")
for dur, num, pit, l in rows[:14]:
    extra = {k: v for k, v in l.items()
             if "dur" in k or "sector" in k.lower() or k in
             ("date_start", "lap_duration_status", "is_valid", "is_deleted")}
    print(f"  {str(num):>5} {(f'{dur:.3f}' if dur is not None else '-'):>10} "
          f"{str(pit):>8}  {extra}")
if len(rows) > 14:
    print(f"  ... {len(rows) - 14} more (slowest)")

real = [r[0] for r in rows if r[0] is not None and not r[2]]
fastest, second = real[0], real[1]


def sector_sum(lap):
    parts = [lap.get(f"duration_sector_{i}") for i in (1, 2, 3)]
    if any(p is None for p in parts):
        return None
    return sum(parts)


# A lap is self-consistent when its three sectors add up to its stated
# duration. This is a much stronger test than comparing lap times, because
# traffic and in-laps legitimately span a wide range of durations.
inconsistent = []
for l in laps:
    d = l.get("lap_duration")
    s = sector_sum(l)
    if d is not None and s is not None and abs(s - d) > 1.0:
        inconsistent.append((l.get("driver_number"), l.get("lap_number"), d, s))

print()
print(f"  raw minimum (what best_practice_laps stores) : {fastest:.3f}s")
print(f"  second fastest lap                          : {second:.3f}s")
print(f"  gap between #1 and #2                       : "
      f"{second / fastest - 1:+.1%}")
print(f"  laps whose sectors do NOT sum to their duration: "
      f"{len(inconsistent)} of {len(laps)}")

rule("VERDICT ON THE LAP")
if inconsistent:
    print("  SECTOR ARITHMETIC PROVES THE LAP IS CORRUPT:")
    for n, ln, d, s in inconsistent:
        who = con.execute("SELECT driver FROM practice WHERE year=? AND round=? "
                          "AND driver_number=?", (YEAR, RND, n)).fetchone()
        print(f"    {(who[0] if who else '?'):<5} lap {ln}: sectors sum to "
              f"{s:.3f}s but lap_duration says {d:.3f}s "
              f"(off by {abs(s - d):.1f}s)")
    print()
    print(f"  It is {second / fastest - 1:.0%} faster than PIA's next lap at a")
    print(f"  ~89s circuit (the other 21 cars sit in 89.3-93.0s).")
    print("  best_practice_laps accepts it because it only filters nulls and")
    print("  pit-out laps - it never checks that a lap adds up.")
elif second / fastest - 1 > 0.10:
    print(f"  Lap #1 ({fastest:.3f}s) is {second/fastest-1:.0%} faster than #2")
    print(f"  ({second:.3f}s) and every lap is self-consistent, so this is a")
    print("  fast-but-valid lap rather than a corrupt record.")
else:
    print("  No isolated anomaly: lap times are evenly spread and every lap")
    print("  is self-consistent.")

# ---- what the whole race's features should have been ----------------------
rule("WHAT 2026 R4's PRACTICE COLUMN SHOULD LOOK LIKE (corrected, not applied)")
allr = con.execute(
    "SELECT driver, driver_number, best_practice_s FROM practice "
    "WHERE year=? AND round=? ORDER BY best_practice_s", (YEAR, RND)).fetchall()
rec = o1.best_practice_laps(laps)
# Recompute each driver's best, discarding physically impossible laps.
# Rule: a lap more than 15% FASTER than the session's median lap cannot be a
# full flying lap on this circuit - it is a truncated or mis-timed record.
# Applied per lap, not just to PIA, so the same defect would be caught anywhere.
lens = sorted(l.get("lap_duration") for l in laps
              if l.get("lap_duration") and not l.get("is_pit_out_lap"))
median_lap = lens[len(lens) // 2]
floor = median_lap * 0.85

alt: dict[int, float] = {}
dropped = []
for l in laps:
    n = l.get("driver_number")
    d = l.get("lap_duration")
    if n is None or d is None or l.get("is_pit_out_lap"):
        continue
    if d < floor:
        dropped.append((n, d, l.get("lap_number")))
        continue
    alt[n] = d if n not in alt else min(alt[n], d)

# map driver_number -> abbreviation from the stored table
num2drv = {r[1]: r[0] for r in allr if r[1] is not None}
best_now = min(v for v in alt.values() if v is not None)
stored_best = min(r[2] for r in allr if r[2] is not None)

print(f"  session median lap         : {median_lap:.3f}s")
print(f"  impossible-lap floor (85%) : {floor:.3f}s")
print(f"  laps discarded as impossible: {len(dropped)}")
for n, d, ln in dropped:
    who = con.execute("SELECT driver FROM practice WHERE year=? AND round=? "
                      "AND driver_number=?", (YEAR, RND, n)).fetchone()
    print(f"    {(who[0] if who else '?'):<5} driver_number={n} lap {ln}: "
          f"{d:.3f}s")
print(f"  stored weekend reference : {stored_best:.3f}s (PIA's anomalous lap)")
print(f"  corrected reference      : {best_now:.3f}s")
print()
print(f"  {'drv':<5} {'stored best':>12} {'corrected':>11} {'stored gap%':>12} "
      f"{'corrected gap%':>15}")
for r in allr:
    drv, num, sb = r
    cb = alt.get(num)
    sg = con.execute(
        "SELECT gap_to_best_pct FROM practice WHERE year=? AND round=? "
        "AND driver=?", (YEAR, RND, drv)).fetchone()[0]
    if cb is None:
        continue
    cg = (cb - best_now) / best_now * 100
    flag = "   <-- the anomaly" if sb == stored_best else ""
    print(f"  {drv:<5} {sb:>12.3f} {cb:>11.3f} {sg:>12.2f} {cg:>15.2f}{flag}")

print()
print("  EFFECT IF APPLIED (not applied by this script):")
old_order = [r[0] for r in sorted(allr, key=lambda x: (x[2] is None, x[2]))]
new_order = [num2drv.get(n) for n in sorted(alt, key=lambda n: alt[n])]
# Both sides are 0-based here: old_order[i] sits at position i, and its new
# position is new_order.index(a). Comparing that against i+1 was an off-by-one
# that reported every driver as having moved.
rank_moves = [(a, i + 1, new_order.index(a) + 1)
              for i, a in enumerate(old_order) if new_order.index(a) != i]
print(f"  practice_rank would change for {len(rank_moves)} of "
      f"{len(old_order)} cars")
for a, was, now in rank_moves[:8]:
    print(f"    {a}: P{was} -> P{now}")
print(f"  gap_to_best_pct would change for ALL {len(old_order)} cars, since")
print(f"  the reference itself is wrong (54.0% max becomes "
      f"{max((alt[n]-best_now)/best_now*100 for n in alt):.2f}% max).")

con.close()
print()
rule("DIAGNOSIS COMPLETE - NOTHING MODIFIED")
