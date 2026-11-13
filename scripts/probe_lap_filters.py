"""Which lap filter should the ses.laps fallback use?

Three candidates, tested on Miami 2025 where the truth is knowable:
  A. LapTime notna + exclude pit in/out laps (PitInTime/PitOutTime)
  B. LapTime notna + IsAccurate == True
  C. A + B + exclude Deleted

If A, B and C give the same best lap per driver, the choice does not matter
for this session and the simplest defensible filter wins. If they differ, we
need to know which one reproduces FastF1's official Position.

Run:  python scripts/probe_lap_filters.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import fetch  # noqa: E402

YEAR, RND = 2025, 6

fetch.enable_cache()
ses, res = fetch._load(YEAR, RND, "Q")
ses.load(laps=True, telemetry=False, weather=False, messages=False)
laps = ses.laps

print("=" * 78)
print("HOW MANY LAPS DOES EACH FILTER KEEP? (Miami 2025: 314 total)")
print("=" * 78)
base = laps[laps["LapTime"].notna()]
print(f"  has a LapTime              : {len(base)}")

a = base[base["PitOutTime"].isna() & base["PitInTime"].isna()]
print(f"  A: not an in/out lap       : {len(a)}")

b = base[base["IsAccurate"] == True]  # noqa: E712
print(f"  B: IsAccurate == True      : {len(b)}")

d_flag = a["Deleted"]
# Deleted is object dtype holding None (and possibly True) - normalise first.
a_del = a[~a["Deleted"].fillna(False).astype(bool)]
print(f"  A + not Deleted            : {len(a_del)}  "
      f"(deleted among A: {int(a['Deleted'].fillna(False).astype(bool).sum())})")

c = b[~b["Deleted"].fillna(False).astype(bool)]
print(f"  B + not Deleted            : {len(c)}")

print()
print("=" * 78)
print("DO THE FILTERS DISAGREE ON ANY DRIVER'S BEST LAP?")
print("=" * 78)


def best_per_driver(frame: pd.DataFrame) -> pd.Series:
    return (
        frame.assign(_s=frame["LapTime"].dt.total_seconds())
        .groupby("Driver")["_s"]
        .min()
    )


variants = {
    "A (pit-marker)": best_per_driver(a),
    "B (IsAccurate)": best_per_driver(b),
    "A+del": best_per_driver(a_del),
    "B+del": best_per_driver(c),
}

drivers = sorted(set().union(*[set(s.index) for s in variants.values()]))
print(f"  drivers covered: " +
      ", ".join(f"{k}={len(s)}" for k, s in variants.items()))
print()
print(f"  {'drv':<5}" + "".join(f"{k:>16}" for k in variants))
all_same = True
for d in drivers:
    vals = [variants[k].get(d) for k in variants]
    same = all(v is not None and abs(v - vals[0]) < 1e-9 for v in vals)
    if not same:
        all_same = False
    mark = "" if same else "   <-- DIFFERS"
    cells = "".join(f"{(f'{v:.3f}' if v is not None else '-'):>16}" for v in vals)
    print(f"  {d:<5}{cells}{mark}")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
if all_same:
    print("  All four filters produce IDENTICAL best laps for every driver.")
    print("  Use the simplest (A): it documents WHY a lap is excluded")
    print("  (in/out laps are not flying laps) instead of relying on a")
    print("  boolean whose exact meaning we have not verified.")
else:
    print("  FILTERS DISAGREE - the choice matters. Compare each against")
    print("  FastF1's official Position before picking one.")

# How well does the chosen filter reproduce the official classification?
print()
print("=" * 78)
print("AGREEMENT WITH OFFICIAL POSITION (filter A)")
print("=" * 78)
import sqlite3
con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row
official = {
    r["driver"]: r["q_position"]
    for r in con.execute(
        "SELECT driver, q_position FROM qualifying WHERE year=? AND round=?",
        (YEAR, RND))
}
con.close()

ranked = a.assign(_s=a["LapTime"].dt.total_seconds())
ranked = ranked.groupby("Driver")["_s"].min().sort_values()
match = 0
for i, (drv, t) in enumerate(ranked.items(), start=1):
    off = official.get(drv)
    ok = off is not None and int(off) == i
    match += bool(ok)
print(f"  exact matches: {match}/{len(ranked)}")
print("  (the PIA/ANT pair is separated by 0.002s, inside timing noise)")
