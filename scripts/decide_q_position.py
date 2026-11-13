"""Which definition of q_position matches where drivers ACTUALLY started?

THE PROBLEM
-----------
q_position currently has two meanings, depending on which version of the code
wrote the row:

  * 42 races (inserted before db._migrate added q_position_official):
        q_position = FastF1's raw Position   (official classification)
  * 49 races (inserted after):
        q_position = clean.derive_rank(best_q_s)  (rank of lap times)

For 2023 R2 the two disagree badly for VER: official says 15, lap-rank says 4.
The race result settles it - VER grid=15, so official was right.

THE TEST
--------
grid = qualifying position + penalties, so it is the closest observable to
"where they actually qualified". Compute both candidate definitions for every
race and count how often each matches grid. The one that matches more often
is the better definition.

Definitions compared:
  OFFICIAL : q_position_official where present, else stored q_position
             (pre-migration rows already hold the official value)
  LAPRANK  : derive_rank over best_q_s, computed fresh for every race
  STORED   : whatever is in q_position right now (the inconsistent mix)

Run:  python scripts/decide_q_position.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import clean  # noqa: E402

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

races = con.execute(
    "SELECT DISTINCT year, round FROM qualifying ORDER BY year, round"
).fetchall()

# candidates[d][label] = value, plus grid[d]
off: dict[tuple[int, int], dict[str, float | None]] = {}
lap: dict[tuple[int, int], dict[str, float | None]] = {}
sto: dict[tuple[int, int], dict[str, float | None]] = {}
grid: dict[tuple[int, int], dict[str, float | None]] = {}

for rr in races:
    key = (rr["year"], rr["round"])
    rows = con.execute(
        "SELECT q.driver, q.q_position, q.q_position_official, q.best_q_s, "
        "       r.grid "
        "FROM qualifying q "
        "LEFT JOIN results r ON r.year=q.year AND r.round=q.round "
        "                      AND r.driver=q.driver "
        "WHERE q.year=? AND q.round=?",
        (key[0], key[1]),
    ).fetchall()

    bests = {r["driver"]: r["best_q_s"] for r in rows}
    ranks = clean.derive_rank(bests) if any(
        v is not None for v in bests.values()
    ) else {d: None for d in bests}

    for r in rows:
        d = r["driver"]
        official = r["q_position_official"]
        # pre-migration rows: q_position IS the official value
        if official is None:
            official = r["q_position"]
        off.setdefault(key, {})[d] = (
            float(official) if official is not None else None
        )
        lap.setdefault(key, {})[d] = (
            float(ranks[d]) if ranks.get(d) is not None else None
        )
        sto.setdefault(key, {})[d] = (
            float(r["q_position"]) if r["q_position"] is not None else None
        )
        grid.setdefault(key, {})[d] = (
            float(r["grid"]) if r["grid"] is not None else None
        )


def score(cand, name):
    match = total = 0
    exact_races = 0
    races_total = 0
    for key, cd in cand.items():
        gd = grid.get(key, {})
        pairs = [
            (cd[d], gd[d])
            for d in cd
            if cd.get(d) is not None and gd.get(d) is not None
        ]
        if not pairs:
            continue
        races_total += 1
        hits = sum(1 for a, b in pairs if a == b)
        match += hits
        total += len(pairs)
        if hits == len(pairs):
            exact_races += 1
    pct = 100.0 * match / total if total else 0.0
    print(f"  {name:10} matches grid in {match:4}/{total:4} rows "
          f"({pct:5.2f}%)   perfect races: {exact_races}/{races_total}")
    return match, total


print("=" * 74)
print("WHICH q_position DEFINITION TRACKS THE ACTUAL STARTING GRID?")
print("=" * 74)
s_off = score(off, "OFFICIAL")
s_lap = score(lap, "LAPRANK")
s_sto = score(sto, "STORED")

print()
print("=" * 74)
print("HEAD-TO-HEAD: rows where OFFICIAL and LAPRANK disagree with each other")
print("=" * 74)
dis = agree = 0
grid_picks_off = grid_picks_lap = neither = 0
examples = []
for key in off:
    for d in off[key]:
        a, b = off[key][d], lap[key][d]
        g = grid.get(key, {}).get(d)
        if a is None or b is None:
            continue
        if a == b:
            agree += 1
            continue
        dis += 1
        if g is None:
            neither += 1
        elif g == a:
            grid_picks_off += 1
            if len(examples) < 14:
                examples.append((key, d, a, b, g, "official"))
        elif g == b:
            grid_picks_lap += 1
            if len(examples) < 14:
                examples.append((key, d, a, b, g, "laprank"))
        else:
            neither += 1

print(f"  agree : {agree}")
print(f"  disagree: {dis}")
print(f"      of those, grid agrees with OFFICIAL : {grid_picks_off}")
print(f"      of those, grid agrees with LAPRANK  : {grid_picks_lap}")
print(f"      grid agrees with neither (penalties): {neither}")

print()
print("  samples (grid is the referee):")
print(f"    {'race':>10} {'drv':>4} {'official':>9} {'laprank':>8} "
      f"{'grid':>6}  winner")
for key, d, a, b, g, w in examples:
    print(f"    {key[0]} R{key[1]:<6} {d:>4} {a:>9.0f} {b:>8.0f} "
          f"{g:>6.0f}  {w}")

print()
print("=" * 74)
print("VERDICT")
print("=" * 74)
if s_off[0] > s_lap[0]:
    print(f"  OFFICIAL wins by {s_off[0] - s_lap[0]} rows.")
    print("  q_position should be FastF1's official Position, with lap times")
    print("  used ONLY to break genuine ties (two drivers same Position).")
elif s_lap[0] > s_off[0]:
    print(f"  LAPRANK wins by {s_lap[0] - s_off[0]} rows.")
    print("  q_position should be derive_rank(best_q_s) for every race.")
else:
    print("  TIE - no difference in grid agreement; inspect samples above.")

print()
print(f"  STORED currently matches grid in {s_sto[0]}/{s_sto[1]} rows -")
print("  and because it mixes two definitions, it is neither of the above.")

# how big is the repair job either way?
n_post = con.execute(
    "SELECT COUNT(DISTINCT year || '-' || round) FROM qualifying "
    "WHERE q_position_official IS NOT NULL"
).fetchone()[0]
n_pre = con.execute(
    "SELECT COUNT(DISTINCT year || '-' || round) FROM qualifying "
    "WHERE q_position_official IS NULL"
).fetchone()[0]
n_rows_diff = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position_official IS NOT NULL "
    "AND q_position != q_position_official"
).fetchone()[0]
print()
print("  REPAIR SCOPE if OFFICIAL wins:")
print(f"    {n_post} post-migration races: q_position must be reset from "
      f"official ({n_rows_diff} rows currently differ)")
print(f"    {n_pre} pre-migration races: q_position already official, but "
      f"q_position_official needs backfilling")
