"""How many stored qualifying rows are missing lap times, and does FastF1's
authenticated lap data fill them?

Run:  python scripts/audit_missing_q_times.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

con = sqlite3.connect("f1.db")

print("=" * 74)
print("STORED QUALIFYING ROWS MISSING LAP TIMES")
print("=" * 74)
rows = con.execute(
    """SELECT year, round,
              COUNT(*) AS n,
              SUM(CASE WHEN has_qualifying_time=0 THEN 1 ELSE 0 END) AS no_time
       FROM qualifying GROUP BY year, round
       HAVING no_time > 0
       ORDER BY year, round"""
).fetchall()
print(f"{'year':>6} {'round':>6} {'rows':>6} {'no_time':>8}")
for y, r, n, nt in rows:
    print(f"{y:>6} {r:>6} {n:>6} {nt:>8}")
print(f"\nraces affected: {len(rows)}")

tot = con.execute(
    "SELECT COUNT(*), SUM(has_qualifying_time) FROM qualifying"
).fetchone()
print(f"total qualifying rows : {tot[0]}")
print(f"rows WITH a lap time  : {tot[1]}")
print(f"rows WITHOUT          : {tot[0] - tot[1]}")

# Does FastF1 (authenticated) have lap data for those races?
print()
print("=" * 74)
print("DOES FASTF1 LAP DATA FILL THEM? (authenticated)")
print("=" * 74)

import logging  # noqa: E402

logging.basicConfig(level=logging.ERROR)

from f1pred import credentials  # noqa: E402

credentials.load()
import fastf1  # noqa: E402

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

for y, r, n, nt in rows[:10]:
    ses = fastf1.get_session(y, r, "Q")
    try:
        ses.load(laps=True, telemetry=False, weather=False, messages=False)
    except Exception as exc:  # noqa: BLE001
        print(f"{y} R{r}: load failed {type(exc).__name__}: {exc}")
        continue
    res = ses.results
    q_notnull = int(res["Q1"].notna().sum()) if "Q1" in res else -1
    laps = ses.laps
    n_laps = len(laps)
    timed = int(laps["LapTime"].notna().sum()) if n_laps else 0
    # drivers with at least one timed lap
    drivers = 0
    if timed:
        drivers = laps[laps["LapTime"].notna()]["Driver"].nunique()
    print(f"{y} R{r}: results.Q1 not-null={q_notnull:2}/{n:2}  "
          f"lap rows={n_laps:4} timed={timed:4} drivers_with_time={drivers:2}")
