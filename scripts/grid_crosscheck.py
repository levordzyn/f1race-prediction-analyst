"""NON-CIRCULAR test: grid (from the RACE session) vs the two q_position
candidates (from the QUALIFYING session).

WHY THE EARLIER TEST WAS CIRCULAR
----------------------------------
grid is *defined* as official qualifying position + penalties, so counting
"grid agrees with official" mostly re-measures that definition. It cannot
prove official reflects true qualifying performance.

BUT grid is read from a DIFFERENT FastF1 field (race session GridPosition)
than official Position (qualifying session). So for races where official and
lap-rank DISAGREE, asking which one the race session's grid agrees with is a
genuine cross-check between two independent FastF1 fields.

The decisive case is 2025 R17, where official positions 2..10 are a
PERMUTATION of lap ranks 2..10 (SAI official 2 but 8th-fastest lap; NOR
official 7 but 2nd-fastest). A permutation smells like misalignment in one of
the two fields. Whichever the race-session grid matches is the trustworthy one.

WHAT IT PRINTS
--------------
For every race where official != lap-rank, count grid matches, and show the
races with the biggest disagreements in full.

Run:  python scripts/grid_crosscheck.py
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

off_w = lap_w = neither = both = 0
per_race = []

for rr in races:
    rows = con.execute(
        "SELECT q.driver, q.q_position, q.q_position_official, q.best_q_s, "
        "       r.grid "
        "FROM qualifying q "
        "LEFT JOIN results r ON r.year=q.year AND r.round=q.round "
        "                      AND r.driver=q.driver "
        "WHERE q.year=? AND q.round=?",
        (rr["year"], rr["round"]),
    ).fetchall()

    bests = {r["driver"]: r["best_q_s"] for r in rows}
    ranks = (
        clean.derive_rank(bests)
        if any(v is not None for v in bests.values())
        else {d: None for d in bests}
    )

    ro = rl = rn = rb = 0
    detail = []
    for r in rows:
        d = r["driver"]
        official = r["q_position_official"]
        if official is None:
            official = r["q_position"]      # pre-migration rows hold official
        g = r["grid"]
        lr = ranks.get(d)
        if official is None or g is None or lr is None:
            continue
        official, lr, g = float(official), float(lr), float(g)
        if official == lr:
            rb += 1
            continue
        if g == official and g == lr:
            both += 1
            rb += 1
        elif g == official:
            off_w += 1
            ro += 1
            detail.append((d, official, lr, g, "official"))
        elif g == lr:
            lap_w += 1
            rl += 1
            detail.append((d, official, lr, g, "laprank"))
        else:
            neither += 1
            rn += 1
            detail.append((d, official, lr, g, "penalty?"))
    if ro or rl:
        per_race.append((rr["year"], rr["round"], ro, rl, rn, detail))

print("=" * 78)
print("WHERE OFFICIAL AND LAP-RANK DISAGREE, WHICH DOES RACE-GRID AGREE WITH?")
print("=" * 78)
print(f"  rows where they agree              : {rb}")
print(f"  grid agrees with OFFICIAL only     : {off_w}")
print(f"  grid agrees with LAP-RANK only     : {lap_w}")
print(f"  grid agrees with NEITHER (penalty) : {neither}")
print()
if off_w > lap_w:
    print(f"  -> race-session grid sides with OFFICIAL {off_w} : {lap_w}.")
    print("     GridPosition (race field) is built from the official qualifying")
    print("     classification, so this says official reflects where drivers")
    print("     really lined up and lap-rank does not.")
elif lap_w > off_w:
    print(f"  -> race-session grid sides with LAP-RANK {lap_w} : {off_w}.")
    print("     lap-rank is the better definition of qualifying position.")
else:
    print("  -> tie; no separation.")

print()
print("=" * 78)
print("RACES WITH THE MOST DISAGREEMENT (sorted by how often grid picks official)")
print("=" * 78)
per_race.sort(key=lambda x: (-(x[2] - x[3]), x[0], x[1]))
for year, rnd, ro, rl, rn, detail in per_race[:8]:
    print(f"\n  {year} R{rnd}:  official right {ro}, lap-rank right {rl}, "
          f"neither {rn}")
    for d, o, l, g, w in detail:
        print(f"      {d:>4} official={o:>4.0f} laprank={l:>4.0f} "
              f"grid={g:>4.0f}  -> {w}")

print()
print("=" * 78)
print("FULL TABLE: 2025 R17 (the permutation case)")
print("=" * 78)
rows = con.execute(
    "SELECT q.driver, q.q_position, q.q_position_official, q.best_q_s, "
    "       r.grid, r.finish "
    "FROM qualifying q "
    "LEFT JOIN results r ON r.year=q.year AND r.round=q.round "
    "                      AND r.driver=q.driver "
    "WHERE q.year=2025 AND q.round=17 "
    "ORDER BY q.q_position_official"
).fetchall()
bests = {r["driver"]: r["best_q_s"] for r in rows}
ranks = clean.derive_rank(bests)
print(f"{'drv':>4} {'official':>9} {'laprank':>8} {'grid':>6} {'best':>9} "
      f"{'finish':>7}  grid agrees with")
go = gl = 0
for r in rows:
    o = r["q_position_official"]
    l = ranks.get(r["driver"])
    g = r["grid"]
    if o is None or g is None or l is None:
        w = "-"
    elif float(g) == float(o) and float(g) == float(l):
        w = "both"
    elif float(g) == float(o):
        w = "OFFICIAL"
        go += 1
    elif float(g) == float(l):
        w = "laprank"
        gl += 1
    else:
        w = "neither (penalty)"
    print(f"{r['driver']:>4} {str(o):>9} {str(l):>8} {str(g):>6} "
          f"{str(r['best_q_s']):>9} {str(r['finish']):>7}  {w}")
print(f"\n  2025 R17 tally: official {go}, laprank {gl}")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
if off_w > lap_w * 3:
    print("  Strong evidence: OFFICIAL is the correct q_position.")
    print("  derive_rank() must not overwrite it.")
elif lap_w > off_w * 3:
    print("  Strong evidence: LAP-RANK is the correct q_position.")
else:
    print("  Evidence is mixed - inspect the race tables above before deciding.")
print()
print("  NOTE whichever wins: q_position currently MIXES the two definitions")
print("  (42 races official, 49 races lap-derived). That inconsistency has to")
print("  be repaired either way.")
