"""WHY does official Position disagree with lap order in 2025 R17 (Baku)?

Wikipedia's classification table and FastF1 both say:
    VER 101.117 -> P1
    SAI 101.595 -> P2
    LAW 101.537 -> P3
    ANT 101.464 -> P4

By raw lap time that order is impossible: ANT (101.464) and LAW (101.537)
are FASTER than SAI (101.595), so they should be ahead of him.

The Wikipedia prose mentions "the last red flag of the session". Under a red
or yellow flag the lap in progress is deleted. If FastF1's Q1/Q2/Q3 SUMMARY
columns still carry the deleted time while the official classification
excludes it, we get exactly this pattern:

    ANT best valid = min(Q1 102.247, Q3 101.717) = 101.717
    LAW best valid = min(Q1 102.257, Q3 101.707) = 101.707
    SAI best valid = 101.595
    -> order VER, SAI, LAW, ANT   == official P1..P4  ✓

If that holds, it proves TWO things at once:
  1. q_position must be official Position (derive_rank reads the summary
     columns, so it ranks deleted laps).
  2. best_q_s / gap_to_pole_pct may ALSO be wrong for affected drivers,
     because they are built from the same Q1/Q2/Q3 columns.

This script dumps every lap for ANT, LAW, SAI and NOR in 2025 R17 with the
Deleted flag, and compares stored best_q_s against the fastest lap that was
NOT deleted.

Run:  python scripts/check_deleted_laps.py
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
import pandas as pd  # noqa: E402

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

YEAR, RND = 2025, 17
TARGETS = ["ANT", "LAW", "SAI", "NOR", "PIA", "RUS", "LEC"]

ses = fastf1.get_session(YEAR, RND, "Q")
ses.load(laps=True, telemetry=False, weather=False, messages=False)
laps = ses.laps

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 78)
print(f"{YEAR} R{RND}: every lap for the drivers official disagrees with")
print("=" * 78)

d = laps.dropna(subset=["LapTime"]).copy()
d["secs"] = d["LapTime"].dt.total_seconds()

for drv in TARGETS:
    g = d[d["Driver"] == drv].sort_values("secs")
    if len(g) == 0:
        print(f"\n  {drv}: no timed laps")
        continue
    stored = con.execute(
        "SELECT best_q_s, q_position, q_position_official FROM qualifying "
        "WHERE year=? AND round=? AND driver=?", (YEAR, RND, drv)).fetchone()
    deleted = g[g["Deleted"].fillna(False)] if "Deleted" in g.columns else g.iloc[0:0]
    kept = g[~g["Deleted"].fillna(False)] if "Deleted" in g.columns else g

    best_all = g["secs"].min()
    best_kept = kept["secs"].min() if len(kept) else None
    best_del = deleted["secs"].min() if len(deleted) else None

    print(f"\n  {drv}: stored best_q_s={stored['best_q_s']}  "
          f"official={stored['q_position_official']}  "
          f"q_position={stored['q_position']}")
    print(f"    fastest lap (any)      : {best_all:.3f}")
    print(f"    fastest lap (not deleted): "
          f"{'-' if best_kept is None else f'{best_kept:.3f}'}")
    print(f"    fastest DELETED lap    : "
          f"{'-' if best_del is None else f'{best_del:.3f}'}")
    flag = "  <-- STORED FOLLOWS A DELETED LAP" if (
        best_del is not None and stored["best_q_s"] is not None
        and abs(best_del - stored["best_q_s"]) < 0.001
        and best_kept is not None and best_kept > best_del + 0.001
    ) else ""
    if flag:
        print(flag)
    print("    laps (fastest first):")
    for _, r in g.head(6).iterrows():
        dele = bool(r["Deleted"]) if "Deleted" in g.columns else False
        reason = r.get("DeletedReason")
        print(f"      lap {r['LapNumber']:>4.0f} = {r['secs']:>8.3f}  "
              f"deleted={dele}  reason={reason}  "
              f"track={r.get('TrackStatus')}")

print()
print("=" * 78)
print("RECOMPUTING THE ORDER USING ONLY NON-DELETED LAPS")
print("=" * 78)
kept_best = {}
for drv, grp in d.groupby("Driver"):
    k = grp[~grp["Deleted"].fillna(False)] if "Deleted" in grp.columns else grp
    if len(k):
        kept_best[str(drv)] = k["secs"].min()

order = sorted(kept_best.items(), key=lambda x: x[1])
print("  rank by fastest NOT-deleted lap:")
for i, (drv, t) in enumerate(order, 1):
    st = con.execute(
        "SELECT q_position_official, best_q_s FROM qualifying "
        "WHERE year=? AND round=? AND driver=?", (YEAR, RND, drv)).fetchone()
    off = st["q_position_official"] if st else None
    mark = "  <-- official says P%s" % (int(off) if off else "?") \
        if off and int(off) != i else ""
    print(f"    {i:>3}. {drv:>4} {t:>8.3f}{mark}")

print()
print("=" * 78)
print("DOES THIS ALSO AFFECT best_q_s / gap_to_pole_pct?")
print("=" * 78)
stored_vs_kept = []
for drv, grp in d.groupby("Driver"):
    k = grp[~grp["Deleted"].fillna(False)] if "Deleted" in grp.columns else grp
    if not len(k):
        continue
    st = con.execute(
        "SELECT best_q_s FROM qualifying WHERE year=? AND round=? AND driver=?",
        (YEAR, RND, drv)).fetchone()
    if st is None or st["best_q_s"] is None:
        continue
    kept_min = k["secs"].min()
    stored_vs_kept.append((drv, st["best_q_s"], kept_min))

wrong = [(a, b, c) for a, b, c in stored_vs_kept
         if b is not None and abs(b - c) > 0.001]
print(f"  drivers checked            : {len(stored_vs_kept)}")
print(f"  stored best_q_s != fastest kept lap : {len(wrong)}")
for a, b, c in wrong:
    print(f"      {a}: stored {b:.3f}, fastest non-deleted {c:.3f} "
          f"(stored is {b - c:+.3f}s too fast)")
if not wrong:
    print("  -> stored best_q_s matches the fastest non-deleted lap for all")
    print("     drivers here, so gap_to_pole_pct is unaffected.")

print()
print("=" * 78)
print("SUMMARY")
print("=" * 78)
if wrong:
    print("  Deleted laps ARE leaking into best_q_s. That means:")
    print("    - q_position MUST come from official Position, not derive_rank")
    print("    - best_q_s and gap_to_pole_pct need the same treatment")
else:
    print("  best_q_s is clean. Only q_position's definition is at issue.")
