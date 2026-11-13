"""Why does stored q_position disagree with derive_rank(best_q_s)?

161 rows across 29 races disagree. Two competing explanations:

  H1: the 40 pre-migration races stored FastF1's RAW Position, while the 48
      fetched after db._migrate store the DERIVED rank - so the column means
      two different things depending on when the row was written.
  H2: best_q_s itself is wrong for some rows, so derive_rank is wrong.

Distinguishing test: split the mismatches by whether the race has
q_position_official populated (only post-migration rows do). If H1 is right,
mismatches should fall almost entirely in the official-IS-NULL races.

Also prints one race verbatim, side by side with FastF1's own Position and
Q1/Q2/Q3, so the stored values can be checked against the source.

Run:  python scripts/diagnose_q_mismatch.py
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import clean  # noqa: E402

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row


def mismatches_for(year, rnd):
    rows = con.execute(
        "SELECT driver, q_position, q_position_official, best_q_s, "
        "has_qualifying_time FROM qualifying "
        "WHERE year=? AND round=? ORDER BY driver", (year, rnd)
    ).fetchall()
    bests = {r["driver"]: r["best_q_s"] for r in rows}
    if all(v is None for v in bests.values()):
        return rows, None
    derived = clean.derive_rank(bests)
    bad = [r for r in rows if derived.get(r["driver"]) != r["q_position"]]
    return rows, derived, bad


print("=" * 78)
print("(1) SPLIT mismatches by whether q_position_official is populated")
print("=" * 78)
with_off = without_off = 0
races_with_off = set()
races_without_off = set()
race_rows = con.execute(
    "SELECT DISTINCT year, round FROM qualifying ORDER BY year, round"
).fetchall()

for rr in race_rows:
    res = mismatches_for(rr["year"], rr["round"])
    if res[1] is None:
        continue
    derived, bad = res[1], res[2]
    if not bad:
        continue
    has_off = con.execute(
        "SELECT COUNT(*) FROM qualifying WHERE year=? AND round=? "
        "AND q_position_official IS NOT NULL", (rr["year"], rr["round"])
    ).fetchone()[0]
    if has_off:
        with_off += len(bad)
        races_with_off.add((rr["year"], rr["round"]))
    else:
        without_off += len(bad)
        races_without_off.add((rr["year"], rr["round"]))

print(f"  mismatches in races WITH official    : {with_off}  "
      f"({len(races_with_off)} races)")
print(f"  mismatches in races WITHOUT official : {without_off}  "
      f"({len(races_without_off)} races)")
print()
if without_off and not with_off:
    print("  -> supports H1: only pre-migration rows disagree.")
elif with_off and not without_off:
    print("  -> supports H2: only post-migration rows disagree.")
else:
    print("  -> BOTH groups disagree; neither hypothesis alone explains it.")

print()
print("=" * 78)
print("(2) 2023 R2 - full table, source vs stored")
print("=" * 78)
res = mismatches_for(2023, 2)
rows, derived, bad = res
print(f"{'drv':>4} {'stored_q':>9} {'derived':>8} {'official':>9} "
      f"{'best_q_s':>10} {'flag':>5}   verdict")
for r in sorted(rows, key=lambda x: (x["q_position"] is None,
                                     x["q_position"] or 0)):
    d = derived.get(r["driver"])
    v = "OK" if d == r["q_position"] else "** MISMATCH"
    print(f"{r['driver']:>4} {str(r['q_position']):>9} {str(d):>8} "
          f"{str(r['q_position_official']):>9} "
          f"{str(r['best_q_s']):>10} {str(r['has_qualifying_time']):>5}   {v}")
print(f"\n  mismatches: {len(bad)}")

# is stored q_position simply the rank of best_q_s, or the rank of something
# else? test: does sorting by best_q_s reproduce stored order at all?
timed = [r for r in rows if r["best_q_s"] is not None]
by_time = sorted(timed, key=lambda r: r["best_q_s"])
print("\n  order by best_q_s (fastest first):")
print("     " + " ".join(f"{r['driver']}({r['best_q_s']})" for r in by_time))
print("\n  order by stored q_position:")
print("     " + " ".join(
    f"{r['driver']}({int(r['q_position'])})"
    for r in sorted(timed, key=lambda r: r["q_position"] or 99)))

print()
print("=" * 78)
print("(3) check FastF1's raw qualifying Position for 2023 R2")
print("=" * 78)
logging.basicConfig(level=logging.ERROR)
from f1pred import credentials  # noqa: E402

credentials.load()
import fastf1  # noqa: E402
import pandas as pd  # noqa: E402

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))


def td_s(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
        return float(pd.Timedelta(v).total_seconds())
    except Exception:  # noqa: BLE001
        return None


ses = fastf1.get_session(2023, 2, "Q")
ses.load(laps=False, telemetry=False, weather=False, messages=False)
res_df = ses.results
print(f"{'drv':>4} {'F1_Position':>12} {'Q1':>9} {'Q2':>9} {'Q3':>9} "
      f"{'min_seg':>9} {'stored_q':>9}")
src = {}
for _, r in res_df.iterrows():
    a = str(r["Abbreviation"])
    q1, q2, q3 = td_s(r.get("Q1")), td_s(r.get("Q2")), td_s(r.get("Q3"))
    segs = [v for v in (q1, q2, q3) if v is not None]
    mn = min(segs) if segs else None
    src[a] = (r.get("Position"), mn)
    print(f"{a:>4} {str(r.get('Position')):>12} "
          f"{str(round(q1, 3) if q1 else '-'):>9} "
          f"{str(round(q2, 3) if q2 else '-'):>9} "
          f"{str(round(q3, 3) if q3 else '-'):>9} "
          f"{str(round(mn, 3) if mn else '-'):>9} "
          f"{str(next((x['q_position'] for x in rows if x['driver'] == a), '-')):>9}")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
# does stored q_position equal FastF1 Position, or the rank of min(Q1,Q2,Q3)?
eq_pos = eq_rank = 0
for r in rows:
    a = r["driver"]
    if a not in src:
        continue
    f1pos, mn = src[a]
    if f1pos is not None and r["q_position"] is not None \
            and float(f1pos) == float(r["q_position"]):
        eq_pos += 1
timed_sorted = sorted(
    [r for r in rows if r["best_q_s"] is not None],
    key=lambda r: r["best_q_s"])
rank_of = {r["driver"]: i + 1 for i, r in enumerate(timed_sorted)}
for r in rows:
    if rank_of.get(r["driver"]) == r["q_position"]:
        eq_rank += 1
n = len(rows)
print(f"  stored q_position == FastF1 raw Position : {eq_pos}/{n}")
print(f"  stored q_position == rank of best_q_s    : {eq_rank}/{n}")
