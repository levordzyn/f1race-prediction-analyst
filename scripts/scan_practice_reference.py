"""Scan ALL 89 races for a corrupt practice reference lap.

Failure mode found at 2026 R4 (Miami): PIA's lap_duration was 60.351s while
the other 21 cars ran 89.3-93.0s. Because gap_to_best_pct is measured against
the fastest lap of the weekend, that single bad record corrupted the gap column
for all 22 cars and pushed practice_rank for 3 of them.

Signal used here (needs only the DB, no API calls): for each race compare the
fastest stored best_practice_s against the 2nd fastest. Across a normal weekend
the two are within a few tenths of a percent - median weekend spread is 2.6% -
so a large #1-vs-#2 gap means the reference lap itself is impossible.

Read-only. Prints every suspect race.

Run:  python scripts/scan_practice_reference.py
"""
from __future__ import annotations

import sqlite3

THRESHOLD = 0.05          # flag races where #1 beats #2 by more than 5%

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 78)
print(f"PRACTICE REFERENCE SCAN - fastest vs 2nd fastest lap, all 89 races")
print(f"(threshold: flag when the fastest lap beats the 2nd by >{THRESHOLD:.0%})")
print("=" * 78)

races = []
for r in con.execute(
        "SELECT year, round, COUNT(*) n, "
        "       SUM(CASE WHEN best_practice_s IS NULL THEN 1 ELSE 0 END) nul "
        "FROM practice GROUP BY year, round ORDER BY year, round"):
    times = sorted(x[0] for x in con.execute(
        "SELECT best_practice_s FROM practice WHERE year=? AND round=? "
        "AND best_practice_s IS NOT NULL", (r["year"], r["round"])))
    if len(times) < 2:
        continue
    fastest, second = times[0], times[1]
    gap12 = second / fastest - 1
    mx = con.execute(
        "SELECT MAX(gap_to_best_pct) FROM practice WHERE year=? AND round=?",
        (r["year"], r["round"])).fetchone()[0]
    races.append({"year": r["year"], "round": r["round"], "fastest": fastest,
                  "second": second, "gap12": gap12, "max_gap": mx,
                  "spread": times[-1] / fastest - 1})

races.sort(key=lambda x: -x["gap12"])

print(f"  {'race':<12} {'fastest':>9} {'2nd':>9} {'#1 vs #2':>9} "
      f"{'field spread':>13} {'max gap%':>9}")
for x in races[:12]:
    tag = "   <-- FLAGGED" if x["gap12"] > THRESHOLD else ""
    print(f"  {x['year']} R{x['round']:<7} {x['fastest']:>9.3f} "
          f"{x['second']:>9.3f} {x['gap12']:>8.1%} "
          f"{x['spread']:>12.1%} {x['max_gap']:>9.2f}{tag}")

flagged = [x for x in races if x["gap12"] > THRESHOLD]
print()
print("=" * 78)
print(f"RACES FLAGGED: {len(flagged)} of {len(races)}")
print("=" * 78)
for x in flagged:
    rows = con.execute(
        "SELECT driver, best_practice_s, gap_to_best_pct, practice_rank "
        "FROM practice WHERE year=? AND round=? ORDER BY best_practice_s",
        (x["year"], x["round"])).fetchall()
    print(f"\n  {x['year']} R{x['round']} - reference {x['fastest']:.3f}s, "
          f"next lap {x['second']:.3f}s ({x['gap12']:.1%} slower)")
    print(f"    fastest 3 stored: " +
          ", ".join(f"{r['driver']} {r['best_practice_s']:.3f}" for r in rows[:3]))
    print(f"    slowest stored  : {rows[-1]['driver']} "
          f"{rows[-1]['best_practice_s']:.3f}s")
    print(f"    gap_to_best_pct range: "
          f"{rows[0]['gap_to_best_pct']:.2f}% .. "
          f"{rows[-1]['gap_to_best_pct']:.2f}%")
    print(f"    -> {sum(1 for r in rows)} cars' gap column is measured "
          f"against a lap {x['gap12']:.0%} quicker than the entire field")

if not flagged:
    print("  none - every race's fastest lap is close to its 2nd fastest")

# ---- secondary signal: field-wide huge gaps --------------------------------
print()
print("=" * 78)
print("SECONDARY: races where ANY car's gap_to_best_pct exceeds 15%")
print("=" * 78)
n = 0
for x in sorted(races, key=lambda z: -z["max_gap"]):
    if x["max_gap"] is not None and x["max_gap"] > 15:
        n += 1
        suspect = "reference too FAST" if x["gap12"] > THRESHOLD else \
                  "one car simply slow (usually legitimate)"
        print(f"  {x['year']} R{x['round']:<7} max gap {x['max_gap']:>6.2f}%  "
              f"#1-vs-#2 {x['gap12']:>6.2%}  -> {suspect}")
if n == 0:
    print("  none")

con.close()
print()
print("=" * 78)
print(f"CONCLUSION: {len(flagged)} race(s) have an impossible reference lap.")
print("A wide field spread on its own is NOT proof of corruption - a driver")
print("who barely ran legitimately shows a large gap (2023 R12). The proof is")
print("the fastest lap itself being far ahead of the 2nd fastest.")
print("=" * 78)
