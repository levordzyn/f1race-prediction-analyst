"""Is 2026 R4's practice best-lap reference itself broken?

The race shows 21 of 22 cars with practice_gap_pct far outside every other
race (up to 54%). gap = (driver_best - weekend_best) / weekend_best, so a
field-wide 50% gap means the REFERENCE lap - the weekend's fastest practice
lap - is not comparable to everyone else's laps.

Prints the raw best_practice_s for the race, the resulting implied gap, and
compares against the same venue's other years where possible, to decide
whether one lap is corrupting the whole weekend's feature column.

Run:  python scripts/check_practice_outlier_2026_r4.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

YEAR, RND = 2026, 4


def rule(t=""):
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


ev = con.execute("SELECT event, n_starters, expected_size FROM sessions "
                 "WHERE year=? AND round=?", (YEAR, RND)).fetchone()
rule(f"{YEAR} R{RND}: {ev['event']}")
print(f"  starters {ev['n_starters']}, expected {ev['expected_size']}")

rows = con.execute(
    "SELECT driver, n_sessions, best_practice_s, gap_to_best_pct, "
    "       practice_rank, laps_completed, has_practice_lap "
    "FROM practice WHERE year=? AND round=? ORDER BY best_practice_s",
    (YEAR, RND)).fetchall()

print()
print(f"  {'drv':<5} {'sessions':>8} {'best_s':>10} {'gap%':>9} "
      f"{'rank':>5} {'laps':>5}")
for r in rows:
    bs = "-" if r["best_practice_s"] is None else f"{r['best_practice_s']:.3f}"
    gp = "-" if r["gap_to_best_pct"] is None else f"{r['gap_to_best_pct']:.2f}"
    rk = "-" if r["practice_rank"] is None else str(int(r["practice_rank"]))
    print(f"  {r['driver']:<5} {r['n_sessions']:>8} {bs:>10} {gp:>9} "
          f"{rk:>5} {r['laps_completed']:>5}")

times = [r["best_practice_s"] for r in rows if r["best_practice_s"]]
fast, slow = min(times), max(times)
print()
print(f"  fastest weekend practice lap : {fast:.3f}s")
print(f"  slowest weekend practice lap : {slow:.3f}s")
print(f"  spread                       : {slow / fast - 1:+.1%}")
print(f"  gap_to_best_pct max stored   : "
      f"{max(r['gap_to_best_pct'] for r in rows if r['gap_to_best_pct']):.2f}%")

# ---- is this plausible compared to every other race? ----------------------
rule("WEEKEND PRACTICE PACE SPREAD ACROSS EVERY RACE")
stats = []
for r in con.execute(
        "SELECT year, round, MIN(best_practice_s) lo, MAX(best_practice_s) hi "
        "FROM practice WHERE best_practice_s IS NOT NULL "
        "GROUP BY year, round"):
    spread = r["hi"] / r["lo"] - 1
    stats.append((r["year"], r["round"], r["lo"], r["hi"], spread))
stats.sort(key=lambda s: -s[4])
print(f"  {'race':<12} {'fastest':>9} {'slowest':>9} {'spread':>9}")
print("  --- the 8 widest pace spreads of 89 races ---")
for y, rd, lo, hi, sp in stats[:8]:
    tag = "   <-- THIS RACE" if (y, rd) == (YEAR, RND) else ""
    print(f"  {y} R{rd:<7} {lo:>9.3f} {hi:>9.3f} {sp:>8.1%}{tag}")
print(f"\n  median spread across all 89 races: "
      f"{sorted(s[4] for s in stats)[len(stats)//2]:.1%}")
print(f"  rank of {YEAR} R{RND}: "
      f"{next(i for i, s in enumerate(stats, 1) if (s[0], s[1]) == (YEAR, RND))}"
      f" of {len(stats)} (1 = most extreme)")

# ---- what would the gap be if the reference were sane? --------------------
rule("WHAT THE GAP WOULD LOOK LIKE WITH A SANE REFERENCE")
# If the fastest lap is an anomaly, compare everyone to the 2nd fastest, the
# 3rd fastest, etc. A field where 21 cars are 50% off ONE lap but normal off
# the next few means that single lap is the corrupt one.
ordered = sorted(times)
print(f"  rank of laps: " + ", ".join(f"#{i+1}={t:.3f}" for i, t in enumerate(ordered[:6])))
for ref_rank in (1, 2, 3):
    ref = ordered[ref_rank - 1]
    worst = (slow - ref) / ref * 100
    print(f"  if reference = lap #{ref_rank} ({ref:.3f}s): "
          f"field-wide worst gap = {worst:.1f}%")

print()
print("  NOTE: if lap #1 is far faster than #2 while #2..#22 are tightly")
print("  packed, lap #1 is the anomaly and the whole gap column for this")
print("  race is measured against a corrupt reference.")

rule("SAME VENUE, OTHER YEARS (is this venue normally this slow?)")
name = ev["event"]
print(f"  event name: {name}")
same = con.execute(
    "SELECT p.year, p.round, MIN(p.best_practice_s) lo, "
    "       MAX(p.gap_to_best_pct) gap, s.event "
    "FROM practice p JOIN sessions s ON s.year=p.year AND s.round=p.round "
    "WHERE p.best_practice_s IS NOT NULL "
    "GROUP BY p.year, p.round ORDER BY p.year, p.round").fetchall()
# find races with a similar fastest lap (same circuit characteristics)
lo_ref = fast
print(f"\n  races whose fastest practice lap is within 5% of {fast:.3f}s:")
n = 0
for r in same:
    if abs(r["lo"] - lo_ref) / lo_ref <= 0.05:
        n += 1
        print(f"    {r['year']} R{r['round']:<2} fastest {r['lo']:.3f}s  "
              f"max gap {r['gap']:.2f}%  {r['event']}")
if n == 0:
    print("    NONE - no other race has a fastest practice lap this quick,")
    print(f"    which makes {fast:.3f}s itself the suspect value.")

con.close()
print()
rule("DONE")
