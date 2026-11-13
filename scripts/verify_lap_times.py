"""Settle q_position using FASTF1'S ACTUAL LAP TIMES - independent of both
Position and the Q1/Q2/Q3 summary columns.

WHY THIS IS NEEDED
------------------
The grid test was circular: grid = official Position + penalties, so grid
naturally sides with official. It cannot prove official is correct.

The real conflict is internal to FastF1 for 2023 R2 VER:
    Position      = 15
    min(Q1,Q2,Q3) = 88.761  -> ranks 4th fastest
    Q2 lap        = 109.953 (a failing car)
Both cannot describe his qualifying result. He actually started P15.

derive_rank() ranks min(Q1,Q2,Q3). If those SEGMENT COLUMNS disagree with the
session's real lap times, derive_rank is built on bad input - which would
explain why it loses to official.

THIS SCRIPT
-----------
For 2023 R2 (and a few other races) load the actual laps, compute each
driver's genuine fastest lap, and compare three ways:
    A. min(Q1,Q2,Q3)      - what derive_rank uses today
    B. fastest actual lap - ground truth from the timing feed
    C. official Position  - FastF1's classification

If A != B for any driver, the segment columns are unreliable.
If B's ranking matches C, then official is right and derive_rank's input is
the bug.

Run:  python scripts/verify_lap_times.py
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


def seg_best(res_row) -> float | None:
    """min(Q1,Q2,Q3) - exactly what fetch_qualifying stores as best_q_s."""
    vals = []
    for c in ("Q1", "Q2", "Q3"):
        v = res_row.get(c)
        if v is None:
            continue
        try:
            if pd.isna(v):
                continue
            vals.append(float(pd.Timedelta(v).total_seconds()))
        except (TypeError, ValueError):
            continue
    return min(vals) if vals else None


def check(year: int, rnd: int, drivers: list[str] | None = None) -> None:
    ses = fastf1.get_session(year, rnd, "Q")
    ses.load(laps=True, telemetry=False, weather=False, messages=False)
    res = ses.results
    laps = ses.laps

    # Ground truth: fastest actual lap per driver.
    # Real FastF1 lap columns (verified by printing them): PitOutTime marks the
    # out-lap, Deleted marks laps removed by the stewards, LapTime is NaT when
    # no time was set. IsPitOutLap is an OpenF1 name and does not exist here.
    d = laps.dropna(subset=["LapTime"]).copy()
    if "PitOutTime" in d.columns:
        d = d[d["PitOutTime"].isna()]
    if "Deleted" in d.columns:
        d = d[d["Deleted"].fillna(False) != True]  # noqa: E712
    fast = {}
    for drv, grp in d.groupby("Driver"):
        if len(grp) == 0:
            continue
        fast[str(drv)] = grp["LapTime"].min().total_seconds()

    print("=" * 78)
    print(f"{year} R{rnd}: segment columns vs actual lap times vs Position")
    print("=" * 78)
    print(f"{'drv':>4} {'Q1/Q2/Q3':>9} {'real lap':>9} {'same?':>6} "
          f"{'rankSeg':>8} {'rankReal':>9} {'Position':>9}")

    rows = []
    for _, r in res.iterrows():
        a = str(r.get("Abbreviation"))
        if drivers and a not in drivers:
            continue
        seg = seg_best(r)
        real = fast.get(a)
        pos = r.get("Position")
        pos = float(pos) if pd.notna(pos) else None
        rows.append((a, seg, real, pos))

    # rank by each method among the drivers shown
    seg_ranked = sorted(
        [x for x in rows if x[1] is not None], key=lambda x: x[1])
    real_ranked = sorted(
        [x for x in rows if x[2] is not None], key=lambda x: x[2])
    seg_rank = {x[0]: i + 1 for i, x in enumerate(seg_ranked)}
    real_rank = {x[0]: i + 1 for i, x in enumerate(real_ranked)}

    disagree = []
    for a, seg, real, pos in rows:
        same = (
            "n/a" if seg is None or real is None
            else ("YES" if abs(seg - real) < 0.001 else "** NO")
        )
        if same == "** NO":
            disagree.append((a, seg, real))
        print(f"{a:>4} "
              f"{('-' if seg is None else f'{seg:.3f}'):>9} "
              f"{('-' if real is None else f'{real:.3f}'):>9} "
              f"{same:>6} "
              f"{seg_rank.get(a, '-'):>8} "
              f"{real_rank.get(a, '-'):>9} "
              f"{('-' if pos is None else f'{pos:.0f}'):>9}")

    print()
    if disagree:
        print(f"  SEGMENT COLUMNS DISAGREE WITH REAL LAPS for {len(disagree)} "
              f"driver(s):")
        for a, seg, real in disagree:
            print(f"      {a}: Q1/Q2/Q3 says {seg:.3f}, real fastest lap "
                  f"{real:.3f}  (diff {seg - real:+.3f}s)")
    else:
        print("  segment columns match real lap times for every driver shown")

    # does ranking by REAL laps reproduce Position?
    ok = bad = 0
    detail = []
    for a, seg, real, pos in rows:
        if pos is None:
            continue
        rr = real_rank.get(a)
        if rr is None:
            continue
        if rr == int(pos):
            ok += 1
        else:
            bad += 1
            detail.append((a, rr, int(pos)))
    print()
    print(f"  rank by REAL lap vs official Position: {ok} agree, {bad} differ")
    for a, rr, pp in detail[:12]:
        print(f"      {a}: real-lap rank {rr}, Position {pp}")

    ok2 = bad2 = 0
    for a, seg, real, pos in rows:
        if pos is None:
            continue
        sr = seg_rank.get(a)
        if sr is None:
            continue
        if sr == int(pos):
            ok2 += 1
        else:
            bad2 += 1
    print(f"  rank by SEGMENT vs official Position:  {ok2} agree, {bad2} differ")


# the disputed race, plus controls
check(2023, 2, ["VER", "PER", "LEC", "ALO", "RUS", "BOT", "TSU"])
check(2024, 15)
check(2025, 17)
