"""Inspect Miami 2025 (2025 R6) qualifying BEFORE writing the ses.laps fallback.

fetch_qualifying reads results.Q1/Q2/Q3, which are all-NaT for this race, so
all 20 drivers got has_qualifying_time=0 even though FastF1's lap data holds
their laps. This prints the real structure so the fallback is written against
observed fields, not guesses.

Questions it answers:
  1. Are Q1/Q2/Q3 really all NaT for every driver?
  2. Does ses.laps have data, and which columns exist?
  3. How do in/out laps present themselves (PitInTime/PitOutTime)?
  4. What is each driver's best VALID lap?
  5. Does ranking the recovered times reproduce FastF1's official Position?

Run:  python scripts/inspect_miami_q.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import fetch  # noqa: E402

YEAR, RND = 2025, 6

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 60)

# Load F1 credentials + configure the project cache FIRST. Qualifying lap data
# requires an authenticated session; without this the lap fetch 401s. Skipping
# it also triggers FastF1's "DEFAULT CACHE ENABLED!" warning and writes into
# the system temp dir instead of f1_cache/.
fetch.enable_cache()

print("=" * 78)
print(f"STEP 1: load {YEAR} R{RND} qualifying the same way fetch_qualifying does")
print("=" * 78)
ses, res = fetch._load(YEAR, RND, "Q")
print(f"  session      : {ses}")
print(f"  results rows : {len(res)}")
# ses.laps RAISES DataNotLoadedError when _load used laps=False - it does not
# return an empty frame. The fallback therefore must call load(laps=True).
try:
    n = len(ses.laps)
    print(f"  lap rows already loaded? {n}")
except Exception as exc:  # noqa: BLE001 - the point of the probe
    print(f"  ses.laps before load(laps=True): {type(exc).__name__}: {exc}")

print()
print("=" * 78)
print("STEP 2: are Q1/Q2/Q3 really all NaT?")
print("=" * 78)
for col in ("Q1", "Q2", "Q3"):
    n_notna = int(res[col].notna().sum())
    print(f"  {col}: {n_notna}/{len(res)} non-NaT")
print()
print("  sample rows (Abbreviation, Position, Q1, Q2, Q3):")
print(res[["Abbreviation", "Position", "Q1", "Q2", "Q3"]].head(8).to_string(index=False))

print()
print("=" * 78)
print("STEP 3: load laps explicitly (this is what the fallback must do)")
print("=" * 78)
ses.load(laps=True, telemetry=False, weather=False, messages=False)
laps = ses.laps
print(f"  lap rows: {len(laps)}")
print(f"  columns : {list(laps.columns)}")

print()
print("=" * 78)
print("STEP 4: how do in/out laps present themselves?")
print("=" * 78)
print("  dtypes of the fields the fallback would filter on:")
for c in ("LapTime", "PitInTime", "PitOutTime", "IsAccurate",
          "IsPersonalBest", "Deleted", "TrackStatus", "Driver"):
    if c in laps.columns:
        print(f"    {c:<16} {laps[c].dtype}")
    else:
        print(f"    {c:<16} <ABSENT>")

n_pit = int(laps["PitOutTime"].notna().sum() + laps["PitInTime"].notna().sum())
print(f"\n  laps with a pit in/out marker: {n_pit}")
print("  sample of a lap WITH a pit marker vs a clean lap:")
with_pit = laps[laps["PitOutTime"].notna() | laps["PitInTime"].notna()]
clean = laps[laps["PitOutTime"].isna() & laps["PitInTime"].isna()]
cols_show = [c for c in ("Driver", "LapNumber", "LapTime", "PitOutTime",
                         "PitInTime", "IsAccurate", "IsPersonalBest",
                         "Deleted", "TrackStatus")
             if c in laps.columns]
print("  --- WITH pit marker ---")
print(with_pit[cols_show].head(4).to_string(index=False))
print("  --- clean laps ---")
print(clean[cols_show].head(4).to_string(index=False))

print()
print("=" * 78)
print("STEP 5: best VALID lap per driver (exclude in/out laps)")
print("=" * 78)
# A qualifying lap that counts is a flying lap: it has a LapTime, is not the
# lap on which the car pitted in or out, and was not deleted.
valid = laps[
    laps["LapTime"].notna()
    & laps["PitOutTime"].isna()
    & laps["PitInTime"].isna()
].copy()
if "Deleted" in valid.columns:
    n_del = int(valid["Deleted"].sum()) if valid["Deleted"].dtype != object else 0
    print(f"  laps remaining after in/out filter: {len(valid)} "
          f"(removed {len(laps) - len(valid)})")
    print(f"  of those, flagged Deleted: {n_del}")
else:
    print(f"  laps remaining after in/out filter: {len(valid)} "
          f"(removed {len(laps) - len(valid)})")

valid["best_s"] = valid["LapTime"].dt.total_seconds()
per_driver = (
    valid.groupby("Driver")["best_s"]
    .min()
    .sort_values()
)
print(f"\n  drivers with a recovered lap: {len(per_driver)}")
print("  recovered order (fastest first):")
for i, (drv, t) in enumerate(per_driver.items(), start=1):
    print(f"    P{i:>2}  {drv:<5} {t:.3f}s")

print()
print("=" * 78)
print("STEP 6: does the recovered order match FastF1's official Position?")
print("=" * 78)
# Compare the recovered rank against the official Position already stored.
import sqlite3
con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row
stored = {
    r["driver"]: (r["q_position"], r["has_qualifying_time"])
    for r in con.execute(
        "SELECT driver, q_position, has_qualifying_time FROM qualifying "
        "WHERE year=? AND round=?", (YEAR, RND)
    )
}
con.close()

match = mismatch = 0
print(f"  {'drv':<5} {'recovered':>9} {'official':>8}  verdict")
for rank, (drv, t) in enumerate(per_driver.items(), start=1):
    # FastF1 lap 'Driver' is the abbreviation; stored key is also abbreviation
    off = stored.get(drv, (None, None))[0]
    if off is None:
        verdict = "no official position stored"
        mismatch += 1
    elif int(off) == rank:
        verdict = "match"
        match += 1
    else:
        verdict = f"DIFFERS (official P{int(off)})"
        mismatch += 1
    print(f"  {drv:<5} {t:>9.3f} {str(off):>8}  {verdict}")

print()
print(f"  exact position matches: {match}/{len(per_driver)}")
print("  A high match rate means the recovered times are real qualifying")
print("  laps and the fallback is sound. Remaining differences are expected:")
print("  FastF1's official Position can carry grid/penalty effects (the")
print("  documented tie issue) and lap rank is not the classification.")

print()
print("=" * 78)
print("STEP 7: sanity bounds on recovered times")
print("=" * 78)
if len(per_driver):
    print(f"  min: {per_driver.min():.3f}s   max: {per_driver.max():.3f}s")
    print(f"  spread: {per_driver.max() - per_driver.min():.3f}s")
    # Miami is a street circuit; laps are ~87s. A wildly different value
    # would mean the filter picked up an out-lap or a different session.
    plausible = 70 <= per_driver.min() <= 100
    print(f"  within a plausible street-circuit range (70-100s): "
          f"{'YES' if plausible else 'NO - INVESTIGATE'}")
