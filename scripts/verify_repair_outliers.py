"""Verify the two remaining repair failures against FastF1's raw data.

(1) 46 rows with gap_to_pole_pct > 6%  (max 45.6%)
(2) 2025 R9 q_position missing rank 14 (19 rows spanning 1..20)

For (1) we ask FastF1 directly: does it really report these Q1/Q2/Q3 values,
or did our repair invent them? For (2) we ask how many drivers FastF1 listed
in qualifying vs how many started the race.

Run:  python scripts/verify_repair_outliers.py
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.ERROR)

from f1pred import credentials  # noqa: E402

credentials.load()
import fastf1  # noqa: E402

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row


def td_s(v):
    if v is None:
        return None
    try:
        import pandas as pd
        if pd.isna(v):
            return None
        return float(pd.Timedelta(v).total_seconds())
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- (1) gaps
print("=" * 74)
print("(1) ARE THE LARGE-GAP best_q_s VALUES REAL? (compare to FastF1 raw)")
print("=" * 74)

CASES = [(2023, 2, "SAR"), (2023, 13, "LAW"), (2024, 12, "GAS"),
         (2025, 22, "HAM"), (2026, 8, "STR")]

for y, r, drv in CASES:
    stored = con.execute(
        "SELECT q_position, q1_s, q2_s, q3_s, best_q_s, gap_to_pole_pct "
        "FROM qualifying WHERE year=? AND round=? AND driver=?",
        (y, r, drv),
    ).fetchone()
    if stored is None:
        print(f"\n{y} R{r} {drv}: NOT IN OUR DB")
        continue

    ses = fastf1.get_session(y, r, "Q")
    ses.load(laps=False, telemetry=False, weather=False, messages=False)
    res = ses.results
    row = res[res["Abbreviation"] == drv]
    if row.empty:
        print(f"\n{y} R{r} {drv}: FastF1 has no qualifying row")
        continue
    row = row.iloc[0]
    fq1, fq2, fq3 = td_s(row.get("Q1")), td_s(row.get("Q2")), td_s(row.get("Q3"))
    fpos = row.get("Position")
    fsegs = [v for v in (fq1, fq2, fq3) if v is not None]
    fbest = min(fsegs) if fsegs else None

    # pole from FastF1
    allb = []
    for _, rr in res.iterrows():
        segs = [td_s(rr.get(c)) for c in ("Q1", "Q2", "Q3")]
        segs = [v for v in segs if v is not None]
        if segs:
            allb.append(min(segs))
    fpole = min(allb) if allb else None

    match = (fbest is not None and stored["best_q_s"] is not None
             and abs(fbest - stored["best_q_s"]) < 1e-6)
    print(f"\n{y} R{r} {drv}:")
    print(f"   ours : best_q_s={stored['best_q_s']}  gap={stored['gap_to_pole_pct']:.3f}%")
    print(f"   fastf1: Q1={fq1} Q2={fq2} Q3={fq3} -> best={fbest}  "
          f"pole={fpole}  pos={fpos}")
    print(f"   AGREES: {'YES' if match else 'NO  <-- REPAIR WRONG'}")
    if fbest is not None and fpole:
        print(f"   fastf1's own gap would be "
              f"{(fbest - fpole) / fpole * 100.0:.3f}%")

# why is a best lap 45% off pole? show all drivers of that race
print()
print("-" * 74)
print("Full field for the worst case (2023 R2), to see if it is one outlier")
print("-" * 74)
ses = fastf1.get_session(2023, 2, "Q")
ses.load(laps=False, telemetry=False, weather=False, messages=False)
res = ses.results
rows = []
for _, rr in res.iterrows():
    segs = [td_s(rr.get(c)) for c in ("Q1", "Q2", "Q3")]
    segs = [v for v in segs if v is not None]
    rows.append((str(rr["Abbreviation"]),
                 min(segs) if segs else None,
                 rr.get("Position")))
rows = [x for x in rows if x[1] is not None]
pole = min(x[1] for x in rows)
print(f"{'drv':>4} {'best_s':>9} {'gap%':>8} {'pos':>4}")
for d, b, p in sorted(rows, key=lambda x: x[1]):
    print(f"{d:>4} {b:>9.3f} {(b - pole) / pole * 100.0:>8.3f} {p:>4}")

# ------------------------------------------------------------------ (2) R9
print()
print("=" * 74)
print("(2) 2025 R9 - how many drivers FastF1 listed vs how many started")
print("=" * 74)
ses = fastf1.get_session(2025, 9, "Q")
ses.load(laps=False, telemetry=False, weather=False, messages=False)
q_res = ses.results
print(f"FastF1 QUALIFYING rows: {len(q_res)}")

ses_r = fastf1.get_session(2025, 9, "R")
ses_r.load(laps=False, telemetry=False, weather=False, messages=False)
r_res = ses_r.results
print(f"FastF1 RACE rows      : {len(r_res)}")

q_abbr = {str(x) for x in q_res["Abbreviation"]}
r_abbr = {str(x) for x in r_res["Abbreviation"]}
print(f"in Q but not in race  : {sorted(q_abbr - r_abbr)}")
print(f"in race but not in Q  : {sorted(r_abbr - q_abbr)}")

missing = con.execute(
    "SELECT driver FROM qualifying WHERE year=2025 AND round=9 "
    "AND q_position IS NOT NULL ORDER BY q_position"
).fetchall()
print(f"our qualifying rows   : {len(missing)}")
print("=> if a driver qualified but did not START, the gap in q_position")
print("   is correct: positions must NOT be renumbered for absent drivers.")
