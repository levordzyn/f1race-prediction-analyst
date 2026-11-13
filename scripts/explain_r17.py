"""Why is SAI official P2 in 2025 R17 when his fastest lap ranks 8th?

F1 qualifying classification IS ordering by best lap time, so these two
statements cannot both be true:
    official Position : SAI = 2
    fastest lap       : SAI = 101.595 -> 8th of 20

Candidates:
  A. SAI set a faster lap that was DELETED (track limits / red flag) and the
     FastF1 Q1/Q2/Q3 summary columns do not reflect the deletion, while the
     official classification does. Then official is right and lap-rank - which
     reads those summary columns - is built on a lap that never counted.
  B. FastF1's Position/Driver mapping is misaligned for this session, so
     official (and grid, which derives from it) are scrambled while the lap
     times are fine.

Test: dump SAI's and NOR's raw laps for the session, including deleted ones,
with TrackStatus, and show each driver's top-5 laps. If SAI has a faster lap
marked deleted, A wins. If his best is genuinely 101.595 with nothing
deleted, then P2 cannot come from lap time and B (or a source quirk) wins.

Run:  python scripts/explain_r17.py
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

YEAR, RND = 2025, 17

ses = fastf1.get_session(YEAR, RND, "Q")
ses.load(laps=True, telemetry=False, weather=False, messages=False)
laps = ses.laps
res = ses.results

print("=" * 78)
print(f"{YEAR} R{RND} - FastF1 official Position vs fastest lap")
print("=" * 78)
rows = []
for _, r in res.iterrows():
    a = str(r.get("Abbreviation"))
    pos = r.get("Position")
    rows.append((a, float(pos) if pd.notna(pos) else None))

# fastest lap per driver, from raw laps (no deletion filter)
d = laps.dropna(subset=["LapTime"]).copy()
fastest = {}
for drv, grp in d.groupby("Driver"):
    fastest[str(drv)] = grp["LapTime"].min().total_seconds()

order = sorted(
    [(a, p, fastest.get(a)) for a, p in rows if fastest.get(a) is not None],
    key=lambda x: x[2],
)
lap_rank = {a: i + 1 for i, (a, _p, _t) in enumerate(order)}

print(f"{'drv':>4} {'Position':>9} {'laprank':>8} {'fastest':>9}  "
      f"{'Position-laprank':>17}")
scramble = []
for a, p in sorted(rows, key=lambda x: (x[1] is None, x[1] or 0)):
    lr = lap_rank.get(a)
    f = fastest.get(a)
    diff = "" if (p is None or lr is None) else f"{p - lr:+.0f}"
    if p is not None and lr is not None and p != lr:
        scramble.append((a, p, lr))
    print(f"{a:>4} {('-' if p is None else f'{p:.0f}'):>9} "
          f"{('-' if lr is None else str(lr)):>8} "
          f"{('-' if f is None else f'{f:.3f}'):>9}  {diff:>17}")

print()
print(f"  drivers whose Position != lap rank: {len(scramble)}")
for a, p, lr in scramble:
    print(f"      {a}: Position {p}, lap rank {lr}")

print()
print("=" * 78)
print("RAW LAPS for SAI and NOR (the two most scrambled drivers)")
print("=" * 78)
for target in ("SAI", "NOR"):
    g = d[d["Driver"] == target].copy()
    print(f"\n  {target}: {len(g)} timed laps")
    g["secs"] = g["LapTime"].dt.total_seconds()
    g = g.sort_values("secs")
    show = [c for c in ("LapNumber", "secs", "Deleted", "DeletedReason",
                        "TrackStatus", "IsPersonalBest", "Compound", "Stint")
            if c in g.columns]
    print("    top 6 laps (fastest first):")
    for _, r in g.head(6).iterrows():
        print("      " + "  ".join(f"{c}={r[c]}" for c in show))
    n_del = int(g["Deleted"].fillna(False).sum()) if "Deleted" in g.columns else -1
    print(f"    laps flagged Deleted: {n_del}")
    if "DeletedReason" in g.columns:
        reasons = g["DeletedReason"].dropna().unique().tolist()
        print(f"    DeletedReason values: {reasons}")

print()
print("=" * 78)
print("WERE ANY FASTER LAPS DELETED FOR SAI?")
print("=" * 78)
sai = d[d["Driver"] == "SAI"].copy()
if len(sai) and "Deleted" in sai.columns:
    sai["secs"] = sai["LapTime"].dt.total_seconds()
    dele = sai[sai["Deleted"].fillna(False)]  # noqa: E712
    print(f"  SAI deleted laps: {len(dele)}")
    for _, r in dele.sort_values("secs").iterrows():
        print(f"      lap {r['LapNumber']:.0f} = {r['secs']:.3f}s "
              f"reason={r.get('DeletedReason')} status={r.get('TrackStatus')}")
    if len(dele):
        best_del = dele["secs"].min()
        best_ok = sai[~sai["Deleted"].fillna(False)]["secs"].min()  # noqa: E712
        print(f"\n  best DELETED lap : {best_del:.3f}s")
        print(f"  best KEPT lap    : {best_ok:.3f}s")
        print("  If best deleted lap would put SAI in the top 2, official P2 is")
        print("  explained by deletions and lap-rank (which reads Q1/Q2/Q3")
        print("  summary columns) is the one that is wrong.")
    else:
        print("  No deleted laps for SAI.")
        print("  His best lap really is the one shown, so official P2 cannot be")
        print("  derived from lap time - the Position field reflects something")
        print("  the lap times do not.")
else:
    print("  could not read Deleted flag")

print()
print("=" * 78)
print("DOES THE QUALIFYING SESSION HAVE A 'GRIDPOSITION'-LIKE COLUMN?")
print("=" * 78)
print("  results columns:", list(res.columns))
for c in ("GridPosition", "Position", "ClassifiedPosition"):
    if c in res.columns:
        vals = res[c].head(6).tolist()
        print(f"    {c}: {vals}")
