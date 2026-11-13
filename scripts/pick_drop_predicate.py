"""Pick the right drop predicate for fetch_race, and check ClassifiedPosition.

Three candidate signals, tested against all 33 rows of 2026 R19:

  A. DriverNumber > 100        -> catches the FM/SC/MC placeholders only
  B. Status is null-ish        -> FastF1 stringifies NaN as 'nan', so this
                                  must strip strings, not just call pd.isna
  C. Position missing AND Status missing (null-ish)

Target: drop exactly 11 rows (10 placeholders + OCO, who took no part) and
keep 22 (the real participants, including HIR who has Status='Finished' but
no Position).

Also reports whether ClassifiedPosition/Time/Points/Laps rescue HIR's missing
P10 - if so we may not need to store a NULL finish at all.

Run:  python scripts/pick_drop_predicate.py
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

ses = fastf1.get_session(2026, 19, "R")
ses.load(laps=False, telemetry=False, weather=False, messages=False)
res = ses.results.copy()


def nullish(v) -> bool:
    """True for None/NaN AND for FastF1's stringified NaN ('nan'/'None')."""
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v).strip().lower() in ("", "nan", "none")


print("=" * 78)
print("DOES ClassifiedPosition RESCUE HIR'S MISSING P10?")
print("=" * 78)
cols = ["Abbreviation", "Position", "ClassifiedPosition", "GridPosition",
        "Status", "Time", "Points", "Laps"]
for abbr in ("HIR", "OCO", "FM1", "VER", "ALO"):
    row = res[res["Abbreviation"] == abbr]
    if row.empty:
        print(f"  {abbr}: absent")
        continue
    r = row.iloc[0]
    print(f"  {abbr}:")
    for c in cols:
        if c in res.columns:
            print(f"      {c:20} = {r[c]!r}")

# does ClassifiedPosition fill the gap that Position leaves?
pos_vals = sorted(int(v) for v in res["Position"].dropna())
cls_vals = sorted(int(v) for v in res["ClassifiedPosition"].dropna())
print(f"\n  Position values        : {pos_vals}")
print(f"  ClassifiedPosition vals: {cls_vals}")
print(f"  missing from Position  : "
      f"{sorted(set(range(1, 23)) - set(pos_vals))}")
print(f"  missing from Classified: "
      f"{sorted(set(range(1, 23)) - set(cls_vals))}")

print()
print("=" * 78)
print("PREDICATE COMPARISON  (target: drop 11, keep 22)")
print("=" * 78)


def finish_null(r):
    return pd.isna(r.get("Position"))


def A(r):
    n = r.get("DriverNumber")
    return pd.notna(n) and float(n) > 100


def B(r):
    return nullish(r.get("Status"))


def C(r):
    return finish_null(r) and nullish(r.get("Status"))


def D(r):          # team identity lost OR (no position AND no status)
    return nullish(r.get("TeamName")) or (finish_null(r) and nullish(r.get("Status")))


for name, fn in (("A  num>100", A), ("B  status nullish", B),
                 ("C  pos+status nullish", C),
                 ("D  team nullish OR (pos+status)", D)):
    dropped = [a for _, r in res.iterrows() if fn(r)
               for a in [r["Abbreviation"]]]
    kept = len(res) - len(dropped)
    print(f"  {name:30} drops {len(dropped):3}  keeps {kept:3}  "
          f"{'<== OK' if kept == 22 else ''}")
    if kept == 22:
        print(f"        dropped: {dropped}")

print()
print("=" * 78)
print("WOULD D DROP ANY REAL DRIVER? (FullName present + a real Status)")
print("=" * 78)
for _, r in res.iterrows():
    if D(r):
        real = not nullish(r.get("FullName")) and not nullish(r.get("Status"))
        if real:
            print(f"  WARNING real driver dropped: {r['Abbreviation']} "
                  f"FullName={r['FullName']!r} Status={r['Status']!r}")
print("  (no lines above = safe)")

print()
print("=" * 78)
print("AND THE PRE-RACE CASE: does D + n_classified guard both fire?")
print("=" * 78)
# simulate: what the filter does when every row has no Position and no Status
sim = res.copy()
sim["Position"] = float("nan")
sim["Status"] = "nan"
sim_dropped = [r["Abbreviation"] for _, r in sim.iterrows() if D(r)]
kept = len(sim) - len(sim_dropped)
classified = 0   # no rows carry a Position in this simulation
print(f"  simulated pre-race: dropped {len(sim_dropped)}, kept {kept}, "
      f"classified {classified}")
print(f"  -> n_classified==0 guard would "
      f"{'FIRE (correct: refuse to store)' if classified == 0 else 'NOT fire'}")
