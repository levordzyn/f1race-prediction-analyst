"""For the 6 unclassified drivers: does FastF1's LAP data exist even though
its results table says Position=nan / Q1..Q3=NaT?

WHY THIS MATTERS
----------------
fetch_qualifying reads times from session.results (Q1/Q2/Q3 columns). If a
driver has laps in ses.laps but NaN in results, we store has_qualifying_time=0
and best_q_s=NULL even though the lap exists - the same known gap as Miami
2025. This script says exactly how many drivers that affects, so we can decide
whether it is worth closing.

Run:  python scripts/check_recoverable_laps.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.ERROR)

from f1pred import credentials  # noqa: E402

credentials.load()
import fastf1  # noqa: E402
import pandas as pd  # noqa: E402

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

import sqlite3  # noqa: E402

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

targets = con.execute(
    "SELECT year, round, driver FROM qualifying "
    "WHERE q_position IS NULL AND q_position_official IS NULL "
    "ORDER BY year, round"
).fetchall()

by_race: dict[tuple[int, int], list[str]] = {}
for t in targets:
    by_race.setdefault((t["year"], t["round"]), []).append(t["driver"])

print("=" * 78)
print("DO LAP TIMES EXIST FOR THE UNCLASSIFIED DRIVERS?")
print("=" * 78)

recoverable = []
for (year, rnd), drivers in sorted(by_race.items()):
    ses = fastf1.get_session(year, rnd, "Q")
    ses.load(laps=True, telemetry=False, weather=False, messages=False)
    laps = ses.laps
    res = ses.results

    print(f"\n  {year} R{rnd}:")
    for d in drivers:
        # results table (what fetch_qualifying reads)
        hit = res[res["Abbreviation"].astype(str) == d]
        if len(hit):
            rec = hit.iloc[0]
            r_pos, r_q1 = rec.get("Position"), rec.get("Q1")
        else:
            r_pos, r_q1 = "MISSING-ROW", "MISSING-ROW"

        # lap table (what fetch_qualifying does NOT read)
        g = laps[laps["Driver"].astype(str) == d]
        timed = g.dropna(subset=["LapTime"]) if len(g) else g

        if len(timed):
            best = timed["LapTime"].dt.total_seconds().min()
            n = len(timed)
            recoverable.append((year, rnd, d, best, n))
            print(f"      {d}: results Position={r_pos} Q1={r_q1}  "
                  f"| BUT {n} timed laps, best={best:.3f}s  <-- RECOVERABLE")
        else:
            print(f"      {d}: results Position={r_pos} Q1={r_q1}  "
                  f"| laps={len(g)}, timed=0  -> genuinely no lap")

print()
print("=" * 78)
print("SUMMARY")
print("=" * 78)
print(f"  unclassified drivers inspected : "
      f"{sum(len(v) for v in by_race.values())}")
print(f"  with recoverable lap times     : {len(recoverable)}")
for y, r, d, b, n in recoverable:
    print(f"      {y} R{r} {d}: best={b:.3f}s over {n} laps")
if not recoverable:
    print("  None. results and laps agree that these drivers set no time,")
    print("  so our NULLs are correct and nothing needs repairing.")
else:
    print()
    print("  fetch_qualifying reads results.Q1/Q2/Q3 only, so these laps")
    print("  are invisible to it. Closing this needs a ses.laps fallback -")
    print("  the same optional fix already noted for Miami 2025.")
