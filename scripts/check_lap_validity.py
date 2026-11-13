"""Do the 2 'recoverable' laps actually COUNT for qualifying classification?

fetch_qualifying reads times from session.results (Q1/Q2/Q3). Two drivers have
NaN there but one timed lap in ses.laps:

    2026 R1  VER  1 lap  102.025s
    2026 R14 STR  1 lap  103.709s

Both are seconds off qualifying pace (Melbourne pole ~1:19, Barcelona ~1:16),
so they look like laps that were never valid for classification. If so, our
NULL is correct and there is nothing to recover. If they are valid, we have a
real gap.

Checks per lap: Deleted flag, DeletedReason, TrackStatus, IsPersonalBest,
IsAccurate, PitOutTime/PitInTime (an out-lap or in-lap is not a flying lap),
and every other lap the driver has (including untimed ones).

Run:  python scripts/check_lap_validity.py
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

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))


def pd_notna(v) -> bool:
    import pandas as pd
    try:
        return bool(pd.notna(v))
    except Exception:
        return v is not None


CASES = [(2026, 1, "VER"), (2026, 14, "STR")]

for year, rnd, drv in CASES:
    ses = fastf1.get_session(year, rnd, "Q")
    ses.load(laps=True, telemetry=False, weather=False, messages=False)
    laps = ses.laps
    res = ses.results

    print("=" * 78)
    print(f"{year} R{rnd}  {drv}")
    print("=" * 78)

    hit = res[res["Abbreviation"].astype(str) == drv]
    if len(hit):
        rec = hit.iloc[0]
        for col in ("Position", "Q1", "Q2", "Q3", "Status", "Time"):
            if col in rec.index:
                print(f"  results.{col:9} = {rec[col]!r}")

    g = laps[laps["Driver"].astype(str) == drv]
    print(f"  total laps in lap table      = {len(g)}")
    if not len(g):
        print()
        continue

    timed = g.dropna(subset=["LapTime"])
    print(f"  laps WITH a time             = {len(timed)}")
    print()
    print("  every lap, fastest first:")
    cols = [c for c in ("LapNumber", "LapTime", "Deleted", "DeletedReason",
                        "TrackStatus", "IsPersonalBest", "IsAccurate",
                        "PitOutTime", "PitInTime", "FreshTyre", "Stint")
            if c in g.columns]
    show = g.copy()
    show["_s"] = show["LapTime"].dt.total_seconds()
    show = show.sort_values("_s", na_position="last")
    for _, r in show.iterrows():
        parts = []
        for c in cols:
            if c == "LapTime":
                v = r[c]
                parts.append(f"LapTime={v}" if pd_notna(v) else "LapTime=NaT")
            else:
                parts.append(f"{c}={r[c]!r}")
        print("      " + "  ".join(parts))

    # verdict for this driver
    print()
    if not len(timed):
        print("  VERDICT: no timed laps -> NULL is correct.")
        continue

    best = timed.sort_values("LapTime").iloc[0]
    reasons = []
    if bool(best.get("Deleted")):
        reasons.append(f"Deleted={best.get('Deleted')!r} "
                       f"reason={best.get('DeletedReason')!r}")
    if str(best.get("TrackStatus")) not in ("1", "1.0"):
        reasons.append(f"TrackStatus={best.get('TrackStatus')!r} "
                       "(not green flag)")
    if pd_notna(best.get("PitOutTime")) or pd_notna(best.get("PitInTime")):
        reasons.append("lap has PitOutTime/PitInTime (in/out lap, "
                       "not a flying lap)")
    if len(timed) == 1 and len(g) > 1:
        reasons.append(f"only {len(timed)} of {len(g)} laps is timed")

    if reasons:
        print("  VERDICT: the lap does NOT count for classification:")
        for x in reasons:
            print(f"      - {x}")
        print("  Our NULL/has_qualifying_time=0 is CORRECT.")
    else:
        print("  VERDICT: the lap looks VALID and FastF1 still gives")
        print("  Position=nan / Q1=NaT - that is a genuine data gap in")
        print("  results, and ses.laps would be the fix.")
    print()
