"""2025 R6 (Miami) qualifying: FastF1's results Q1/Q2/Q3 are all NaT.

Does FastF1's own LAP data still have the times? If yes we stay inside one
source (FastF1) instead of mixing in OpenF1.

Run:  python scripts/check_fastf1_laps_2025_r6.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import fastf1

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

YEAR, RND = 2025, 6

ses = fastf1.get_session(YEAR, RND, "Q")
print("event:", ses.event["EventName"], "| session:", ses.name)

try:
    # load laps only (the results were already fine, just missing Q times)
    ses.load(laps=True, telemetry=False, weather=False, messages=False)
except Exception as exc:  # noqa: BLE001
    print("LOAD RAISED:", type(exc).__name__, exc)

try:
    laps = ses.laps
except Exception as exc:  # noqa: BLE001
    print("laps unavailable:", type(exc).__name__, exc)
    sys.exit(0)

print("lap rows:", len(laps))
print("columns :", sorted(laps.columns))
if not len(laps):
    sys.exit(0)

lt = laps["LapTime"]
print("LapTime not-null:", int(lt.notna().sum()), "of", len(laps))

if lt.notna().any():
    # best lap per driver, excluding pit-out laps if the flag exists
    work = laps[laps["LapTime"].notna()].copy()
    if "PitOutLap" in work.columns:
        before = len(work)
        work = work[~work["PitOutLap"].fillna(False).astype(bool)]
        print(f"dropped {before - len(work)} pit-out laps")

    work["s"] = work["LapTime"].dt.total_seconds()
    best = work.groupby("Driver")["s"].min().sort_values()
    print("\nbest lap per driver (FastF1 laps):")
    print(best.to_string())

    # compare against FastF1's official qualifying Position for this race
    res = ses.results
    off = dict(zip(res["Abbreviation"], res["Position"]))
    print("\n pace  driver  best_s   official_Position  agree?")
    print("-" * 56)
    bad = 0
    for rank, (d, t) in enumerate(best.items(), start=1):
        p = off.get(d)
        ok = p is not None and int(p) == rank
        if not ok:
            bad += 1
        print(f"  {rank:2}   {d:4}   {t:7.3f}   {p!s:>10}        "
              f"{'OK' if ok else 'DIFF'}")
    print(f"\nmismatches: {bad} of {len(best)}")
else:
    print("\nFastF1 lap data has NO lap times either -> genuine source gap.")
