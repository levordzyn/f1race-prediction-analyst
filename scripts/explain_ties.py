"""Are the 7 official-Position ties real ties, or penalty-shift artifacts?

For each tied (race, position) pair we print the drivers' official Position,
their race-session grid, and their best qualifying lap, plus how many drivers
in that race have grid != official (i.e. penalties / pit-lane starts).

WHY THIS MATTERS
----------------
If a race has a grid penalty, drivers behind the penalized car shift UP one
place in the starting grid. If FastF1's qualifying Position already reflects
that shift for the non-penalized drivers while keeping the penalized driver's
raw position, the classification gains a duplicate - which is exactly what a
"tie" would look like without two drivers ever setting the same time.

Two drivers cannot tie in F1 qualifying: times are recorded to 0.001s. So a
duplicate where the lap times DIFFER is a red flag worth understanding.

Run:  python scripts/explain_ties.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

ties = con.execute(
    """SELECT year, round, q_position, COUNT(*) n, GROUP_CONCAT(driver) drvs
       FROM qualifying WHERE q_position IS NOT NULL
       GROUP BY year, round, q_position HAVING COUNT(*) > 1
       ORDER BY year, round"""
).fetchall()

print("=" * 78)
print(f"OFFICIAL TIES IN THE DATA: {len(ties)} groups")
print("=" * 78)
print("  F1 qualifying times are recorded to 0.001s, so two drivers cannot")
print("  genuinely set the same time. A duplicate means something else.")
print()

for t in ties:
    y, r, pos = t["year"], t["round"], t["q_position"]
    print("-" * 78)
    print(f"{y} R{r}  official position {pos}  shared by {t['drvs']}")

    rows = con.execute(
        """SELECT q.driver, q.q_position, q.q_position_official, q.best_q_s,
                  x.grid, x.finish
           FROM qualifying q
           JOIN results x ON x.year=q.year AND x.round=q.round
                                AND x.driver=q.driver
           WHERE q.year=? AND q.round=?
           ORDER BY q.q_position IS NULL, q.q_position, q.driver""",
        (y, r)).fetchall()

    n_pen = sum(1 for x in rows
                if x["grid"] is not None and x["q_position"] is not None
                and float(x["grid"]) != float(x["q_position"]))
    print(f"  drivers in this race with grid != official: {n_pen} "
          f"(penalties or pit-lane starts)")
    print(f"  {'drv':>5} {'official':>9} {'grid':>6} {'best_q_s':>10} "
          f"{'finish':>7}")
    for x in rows:
        star = "  <-- tied" if x["q_position"] == pos else ""
        print(f"  {x['driver']:>5} {str(x['q_position']):>9} "
              f"{str(x['grid']):>6} {str(x['best_q_s']):>10} "
              f"{str(x['finish']):>7}{star}")

    # does the grid uniquely order the tied drivers?
    tied = [x for x in rows if x["q_position"] == pos]
    if len(tied) == 2:
        a, b = tied
        if a["best_q_s"] is not None and b["best_q_s"] is not None:
            faster = a if a["best_q_s"] < b["best_q_s"] else b
            slower = b if faster is a else a
            print(f"  by lap time: {faster['driver']} "
                  f"({faster['best_q_s']}) is FASTER than "
                  f"{slower['driver']} ({slower['best_q_s']})")
            print(f"  grid puts {faster['driver']}={faster['grid']} and "
                  f"{slower['driver']}={slower['grid']}")
            if float(faster["grid"]) < float(slower["grid"]):
                print("  -> grid agrees with lap time: the faster driver "
                      "starts ahead, so the official 'tie' hides a real")
                print("     order and FastF1's Position is suspect here.")
            else:
                print("  -> grid puts the SLOWER driver ahead, consistent "
                      "with a penalty on the faster one.")
    print()

print("=" * 78)
print("SUMMARY")
print("=" * 78)
print("  Read each block above. The question is whether the duplicate is")
print("  (a) a penalty-shift artifact - official reflects the shifted grid")
print("      for everyone except the penalized driver, or")
print("  (b) something else.")
print()
print("  Either way, q_position keeps the official value: it is what the")
print("  FIA published, it beats the lap rank 277:14 against the grid, and")
print("  mixing definitions across races would be worse than accepting a")
print("  rare duplicate that validate_positions(allow_ties=True) already")
print("  downgrades to a warning.")
