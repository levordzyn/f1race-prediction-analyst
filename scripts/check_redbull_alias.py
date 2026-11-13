"""Is "Red Bull Racing" the same team as "Red Bull" in our data?

TEAM_ALIASES maps "red bull" -> "Red Bull" but has no entry for
"red bull racing", so clean_team_name() leaves that one unchanged and
groupby("team") would treat the two labels as different teams.

Before adding an alias we confirm they are the same constructor: same
drivers, overlapping rounds, same entry.

Run:  python scripts/check_redbull_alias.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 78)
print("WHERE DOES EACH LABEL APPEAR?")
print("=" * 78)
for r in con.execute(
        "SELECT team, year, COUNT(*) n, GROUP_CONCAT(DISTINCT round) rounds "
        "FROM results WHERE team IN ('Red Bull','Red Bull Racing') "
        "GROUP BY team, year ORDER BY year, team"):
    print(f"  {r['team']:<18} {r['year']}  rows={r['n']:<4} "
          f"rounds={r['rounds']}")

print()
print("=" * 78)
print("WHO DRIVES UNDER EACH LABEL?")
print("=" * 78)
for r in con.execute(
        "SELECT team, GROUP_CONCAT(DISTINCT driver) drivers "
        "FROM results WHERE team IN ('Red Bull','Red Bull Racing') "
        "GROUP BY team"):
    print(f"  {r['team']:<18} {r['drivers']}")

print()
print("=" * 78)
print("DO THE TWO LABELS EVER SHARE A ROUND? (same team, same weekend)")
print("=" * 78)
both = con.execute(
    "SELECT year, round, "
    "       GROUP_CONCAT(DISTINCT team) teams, COUNT(*) n "
    "FROM results WHERE team IN ('Red Bull','Red Bull Racing') "
    "GROUP BY year, round HAVING COUNT(DISTINCT team) > 1"
).fetchall()
print(f"  rounds where BOTH labels appear: {len(both)}")
for r in both:
    print(f"      {r['year']} R{r['round']}: {r['teams']} ({r['n']} rows)")

print()
print("=" * 78)
print("DO THEY SHARE DRIVERS ACROSS ROUNDS? (continuity check)")
print("=" * 78)
rb = {r["driver"] for r in con.execute(
    "SELECT DISTINCT driver FROM results WHERE team='Red Bull'")}
rr = {r["driver"] for r in con.execute(
    "SELECT DISTINCT driver FROM results WHERE team='Red Bull Racing'")}
print(f"  drivers under 'Red Bull'         : {sorted(rb)}")
print(f"  drivers under 'Red Bull Racing'  : {sorted(rr)}")
print(f"  shared drivers                   : {sorted(rb & rr)}")

# does any driver hold BOTH labels in the same season?
print()
print("  drivers who appear under BOTH labels in one season:")
rows = con.execute(
    "SELECT year, driver, GROUP_CONCAT(DISTINCT team) teams "
    "FROM results WHERE team IN ('Red Bull','Red Bull Racing') "
    "GROUP BY year, driver HAVING COUNT(DISTINCT team) > 1").fetchall()
if rows:
    for r in rows:
        print(f"      {r['year']} {r['driver']}: {r['teams']}")
else:
    print("      none")

print()
print("=" * 78)
print("CONSEQUENCE IF THE ALIAS STAYS MISSING")
print("=" * 78)
n_rb = con.execute(
    "SELECT COUNT(*) FROM results WHERE team='Red Bull'").fetchone()[0]
n_rr = con.execute(
    "SELECT COUNT(*) FROM results WHERE team='Red Bull Racing'").fetchone()[0]
print(f"  'Red Bull' rows         : {n_rb}")
print(f"  'Red Bull Racing' rows  : {n_rr}")
print("  groupby('team') would create TWO teams, so team_form for the")
print("  'Red Bull Racing' rows would fall back to DEFAULT_FORM instead of")
print("  using the constructor's real history - a silent feature bug for")
print("  4 of 20 constructors (Red Bull, Racing Bulls, Sauber, Alpine).")
print()
print("  FIX: add the alias to TEAM_ALIASES, and run every team value")
print("  through clean_team_name() when the Phase 3 feature frame is built.")
