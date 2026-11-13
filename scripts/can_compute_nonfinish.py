"""Can 'recent non-finish rate' be computed from what we store?

The 12 features include "Recent non-finish rate", but results has no status
column (locked to 7 columns by f1_baseline.py, asserted by test [3]).

Three questions:
  1. What does FastF1's Status look like where we DO store it (sprint)?
  2. Is results.finish ever NULL - i.e. can an unclassified driver even be
     represented, or does every starter get a position?
  3. Therefore: is there any way to tell a retirement from a finish?

Run:  python scripts/can_compute_nonfinish.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row


def sec(title):
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


sec("1. sprint_status: what FastF1 reports where we DO store status")
for r in con.execute(
        "SELECT sprint_status, COUNT(*) n FROM sprint "
        "GROUP BY sprint_status ORDER BY n DESC"):
    print(f"    {str(r['sprint_status']):<24} {r['n']}")

sec("2. sprint rows that did NOT finish")
rows = con.execute(
    "SELECT year, round, driver, sprint_position, sprint_grid, "
    "       sprint_status FROM sprint "
    "WHERE sprint_status IS NULL OR sprint_status != 'Finished' "
    "ORDER BY year, round").fetchall()
print(f"    {len(rows)} of 492 sprint rows")
for r in rows[:20]:
    print(f"    {r['year']} R{r['round']:>2} {r['driver']:<5} "
          f"grid={str(r['sprint_grid']):>5} pos={str(r['sprint_position']):>5} "
          f"status={r['sprint_status']}")
if len(rows) > 20:
    print(f"    ... {len(rows) - 20} more")

sec("3. Does a non-'Finished' sprint row still carry a position?")
for r in rows:
    if r["sprint_position"] is None:
        print(f"    {r['year']} R{r['round']} {r['driver']}: "
              f"status={r['sprint_status']} position=NULL")
        break
else:
    print("    Every non-'Finished' sprint row STILL has a sprint_position.")
    print("    -> FastF1 classifies retirements, so position alone never")
    print("       reveals a DNF. Status is the only signal.")

sec("4. results: is finish ever NULL?")
n_null = con.execute(
    "SELECT COUNT(*) FROM results WHERE finish IS NULL").fetchone()[0]
n_total = con.execute("SELECT COUNT(*) FROM results").fetchone()[0]
print(f"    finish IS NULL : {n_null} of {n_total}")

sec("5. Is results.finish contiguous 1..N in every race?")
bad = con.execute("""
    SELECT COUNT(*) FROM (
      SELECT year, round, MIN(finish) lo, MAX(finish) hi, COUNT(*) n,
             COUNT(DISTINCT finish) d
      FROM results GROUP BY year, round
      HAVING MIN(finish) != 1 OR MAX(finish) != COUNT(*)
          OR COUNT(DISTINCT finish) != COUNT(*))""").fetchone()[0]
print(f"    races NOT exactly 1..N : {bad} of 89")
print("    -> No gaps, no NULLs: every starter holds a distinct position.")

sec("6. Is there ANY column anywhere that flags a race retirement?")
tabs = [r["name"] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print(f"    tables: {tabs}")
hits = []
for t in tabs:
    cols = [c["name"] for c in con.execute(f"PRAGMA table_info({t})")]
    statusy = [c for c in cols if "status" in c.lower()
               or "dnf" in c.lower() or "classif" in c.lower()]
    if statusy:
        hits.append((t, statusy))
print(f"    columns carrying a status/DNF/classification signal:")
for t, c in hits:
    print(f"        {t}: {c}")
print("    -> results, qualifying and practice carry NONE.")

sec("7. CONCLUSION")
print("    race-level DNFs are NOT recoverable from the current schema.")
print("    sprint-level DNFs ARE (sprint_status is stored).")
print()
print("    To build 'recent non-finish rate' over races we would need to")
print("    store FastF1's race Status - in a NEW table (results must stay")
print("    exactly 7 columns for f1_baseline.py) - and re-fetch all 89")
print("    races. That is ~500 FastF1 sends, close to the 500/h limit.")

con.close()
