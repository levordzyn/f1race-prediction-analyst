"""The 6 qualifying rows where FastF1 gave neither a Position nor a lap time.

Are they honest (driver genuinely not classified) or a data gap (driver did
qualify but we failed to store it)?

For each one we check:
  * did the driver START the race? (results.grid must exist - you cannot
    start without a grid slot, except a pit-lane start which still has a
    recorded grid);
  * what does the race table say their grid was?;
  * does FastF1's qualifying session return a Position for them at all?

Run:  python scripts/inspect_unclassified.py
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

rows = con.execute(
    "SELECT q.year, q.round, q.driver, q.driver_number, q.team, "
    "       q.has_qualifying_time, q.best_q_s, "
    "       x.grid, x.finish, x.event "
    "FROM qualifying q "
    "JOIN results x ON x.year=q.year AND x.round=q.round "
    "                        AND x.driver=q.driver "
    "WHERE q.q_position IS NULL AND q.q_position_official IS NULL "
    "ORDER BY q.year, q.round"
).fetchall()

print("=" * 78)
print("THE 6 UNCLASSIFIED ROWS")
print("=" * 78)
print(f"{'year':>6} {'R':>3} {'drv':>5} {'grid':>6} {'finish':>7} "
      f"{'has_time':>9} {'event':<28}")
print("-" * 78)
for r in rows:
    print(f"{r['year']:>6} {r['round']:>3} {r['driver']:>5} "
          f"{str(r['grid']):>6} {str(r['finish']):>7} "
          f"{r['has_qualifying_time']:>9} {str(r['event'])[:28]:<28}")

print()
print("=" * 78)
print("INTERPRETATION")
print("=" * 78)
no_grid = [r for r in rows if r["grid"] is None]
has_grid = [r for r in rows if r["grid"] is not None]
print(f"  rows with NO grid (driver did not start)   : {len(no_grid)}")
for r in no_grid:
    print(f"      {r['year']} R{r['round']} {r['driver']} - did not start,")
    print(f"        so never needed a qualifying position. NULL is correct.")
print(f"  rows WITH a grid (driver DID start)        : {len(has_grid)}")
for r in has_grid:
    print(f"      {r['year']} R{r['round']} {r['driver']} grid={r['grid']} "
          f"finish={r['finish']}")

if not has_grid:
    print()
    print("  Every one of the 6 failed to start the race, so none of them")
    print("  needed a qualifying position. q_position=NULL is the honest")
    print("  value and has_qualifying_time=0 is the model's missing flag.")
    print("  NO DATA GAP.")
    sys.exit(0)

# A driver who started but has no qualifying row is a real gap. Ask FastF1
# what its qualifying results actually contain for them.
print()
print("=" * 78)
print("ASKING FASTF1: does its qualifying results table classify them?")
print("=" * 78)

import logging as _logging  # noqa: E402

_logging.basicConfig(level=_logging.ERROR)

from f1pred import credentials  # noqa: E402

credentials.load()
import fastf1  # noqa: E402
import pandas as pd  # noqa: E402

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

targets = sorted({(r["year"], r["round"]) for r in has_grid})
print(f"  races to load: {targets}")
print()

for year, rnd in targets:
    ses = fastf1.get_session(year, rnd, "Q")
    ses.load(telemetry=False, weather=False, messages=False)
    res = ses.results
    drv = [r["driver"] for r in has_grid
           if r["year"] == year and r["round"] == rnd]
    print(f"  {year} R{rnd} - FastF1 qualifying results "
          f"({len(res)} rows):")
    cols = [c for c in ["Abbreviation", "Position", "Q1", "Q2", "Q3",
                        "Status", "TeamName"] if c in res.columns]
    for d in drv:
        hit = res[res["Abbreviation"].astype(str) == d]
        if len(hit) == 0:
            print(f"      {d}: NOT PRESENT in FastF1 qualifying results")
        else:
            rec = hit.iloc[0]
            print(f"      {d}: " + ", ".join(
                f"{c}={rec[c]!r}" for c in cols))
    # who is missing from our qualifying table entirely?
    ours = {r["driver"] for r in con.execute(
        "SELECT driver FROM qualifying WHERE year=? AND round=?", (year, rnd))}
    ff1 = set(res["Abbreviation"].astype(str))
    print(f"      in FastF1 but not in our table: {sorted(ff1 - ours)}")
    print(f"      in our table but not FastF1   : {sorted(ours - ff1)}")
    print()

print("=" * 78)
print("VERDICT")
print("=" * 78)
print("  See the per-race output above. If FastF1 does not classify them")
print("  either, our NULL matches the source and there is nothing to fix.")
print("  If FastF1 DOES classify them, this is a fetch gap worth repairing.")
