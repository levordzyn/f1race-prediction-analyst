"""What does an OpenF1 /sessions response actually contain, and does OpenF1
have lap times for Miami 2025 (the one race where FastF1's Q1/Q2/Q3 are all
NaT)?

Run:  python scripts/diagnose_2025_r6.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from f1pred import openf1

print("=" * 74)
print("OpenF1 /sessions field names (one real sample)")
print("=" * 74)
sess = openf1.get_sessions(year=2025)
print("n sessions:", len(sess))
if sess:
    print("keys:", sorted(sess[0].keys()))
    print("\nsample:")
    for k in sorted(sess[0]):
        print(f"   {k:24} = {sess[0][k]!r}")

print("\n" + "=" * 74)
print("Which 2025 sessions mention Miami?")
print("=" * 74)
# print every distinct location/meeting name so we can see the real value
locs = sorted({str(s.get("location")) for s in sess})
meet = sorted({str(s.get("meeting_name")) for s in sess})
print("locations:", locs)
print("\nmeetings:", meet)

miami = [s for s in sess
         if "miami" in str(s.get("location", "")).lower()
         or "miami" in str(s.get("meeting_name", "")).lower()]
print("\nMiami matches:", len(miami))
for s in sorted(miami, key=lambda x: str(x.get("date_start"))):
    print(f"   {str(s.get('session_name')):22} start={s.get('date_start')} "
          f"type={s.get('session_type')} key={s.get('session_key')}")

qual = [s for s in miami if s.get("session_name") == "Qualifying"]
if not qual:
    print("\nNo session named exactly 'Qualifying'. Names present:",
          sorted({str(s.get('session_name')) for s in miami}))
else:
    key = qual[0]["session_key"]
    print(f"\nfetching laps for session_key={key} ...")
    laps = openf1.get_laps(session_key=key)
    print("lap rows:", len(laps))
    if len(laps):
        print("lap columns:", sorted(laps.columns))
        pit = laps["is_pit_out_lap"] if "is_pit_out_lap" in laps else None
        mask = laps["lap_duration"].notna()
        if pit is not None:
            mask &= ~pit.fillna(False).astype(bool)
        valid = laps[mask]
        print("valid laps:", len(valid))
        if len(valid):
            best = (valid.groupby("driver_number")["lap_duration"].min()
                    .sort_values())
            print("drivers with a valid lap:", len(best))
            print(best.to_string())
            # compare to FastF1's official positions for that race
            import sqlite3

            con = sqlite3.connect("f1.db")
            off = dict(con.execute(
                "SELECT driver, grid FROM results WHERE year=2025 AND round=6"
            ).fetchall())
            print("\nFastF1 grid vs OpenF1-derived pace rank:")
            # map driver_number -> abbreviation via driver_numbers table
            num2ab = {
                n: d for d, n in con.execute(
                    "SELECT driver, driver_number FROM driver_numbers "
                    "WHERE year=2025 AND round=6"
                ).fetchall()
            }
            for rank, (num, t) in enumerate(best.items(), start=1):
                ab = num2ab.get(int(num), f"#{num}")
                print(f"   pace {rank:2}  {ab:4} best={t:8.3f}  "
                      f"official grid={off.get(ab)}")
