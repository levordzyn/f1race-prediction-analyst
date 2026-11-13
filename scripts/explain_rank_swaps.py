"""Why do 4 races have swapped ranks despite NO gaps in the rank sequence?

Two rival explanations for 2025 R10/R11/R18/R23 (2 rows each, a clean swap):

  A. EXACT TIE. clean.derive_rank sorts by (time, key). The original call was
     keyed by driver_number (int), the repair by driver name (str). If two
     drivers have byte-identical best_practice_s the tie-break differs and the
     two swap - which would mean the repair is CHANGING correct data.

  B. HIDDEN PHANTOM. A non-starting driver took one rank while a starter with
     no practice lap took none, so the sequence still reads 1..20 with no gap.

The tie-break key decides it: if the two times are exactly equal -> A.
If they differ -> the original order cannot come from sorting by time at all
-> B.

Run:  python scripts/explain_rank_swaps.py
"""
from __future__ import annotations

import sqlite3

RACES = [(2025, 10), (2025, 11), (2025, 18), (2025, 23)]
SWAPS = {
    (2025, 10): ("SAI", "PIA"),
    (2025, 11): ("GAS", "BEA"),
    (2025, 18): ("NOR", "ANT"),
    (2025, 23): ("BOR", "BEA"),
}

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

for y, r in RACES:
    a, b = SWAPS[(y, r)]
    print("=" * 78)
    print(f"{y} R{r}   the swapped pair is {a} vs {b}")
    print("=" * 78)

    rows = con.execute(
        "SELECT driver, driver_number, practice_rank, best_practice_s, "
        "       has_practice_lap, n_sessions "
        "FROM practice WHERE year=? AND round=? "
        "ORDER BY best_practice_s, driver",
        (y, r),
    ).fetchall()

    field = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?", (y, r)
    ).fetchone()[0]
    n_null_rank = sum(1 for x in rows if x["practice_rank"] is None)
    n_no_lap = sum(1 for x in rows if x["has_practice_lap"] == 0)
    ranks = [int(x["practice_rank"]) for x in rows
             if x["practice_rank"] is not None]

    print(f"  field={field}  rows={len(rows)}  "
          f"NULL rank={n_null_rank}  has_practice_lap=0: {n_no_lap}  "
          f"rank span={min(ranks)}..{max(ranks)} "
          f"(gaps={[i for i in range(1, max(ranks)+1) if i not in ranks]})")
    print(f"  NOTE: NULL-rank drivers + phantoms would show as "
          f"has_practice_lap=0 = {n_no_lap}")
    print()

    pair = [x for x in rows if x["driver"] in (a, b)]
    print(f"  THE PAIR (full precision):")
    for x in pair:
        print(f"    {x['driver']:<5} num={x['driver_number']:<4} "
              f"rank={x['practice_rank']:<5} "
              f"best_practice_s={x['best_practice_s']!r}")
    if len(pair) == 2:
        ta, tb = pair[0]["best_practice_s"], pair[1]["best_practice_s"]
        if ta is None or tb is None:
            print("    -> one of them has no time; cannot be a time tie")
        elif ta == tb:
            print(f"    -> EXACTLY EQUAL ({ta!r} == {tb!r})  => EXPLANATION A: "
                  f"tie-break difference (driver_number vs driver name)")
            na, nb = pair[0]["driver_number"], pair[1]["driver_number"]
            print(f"       sort by driver_number: {na} vs {nb} -> "
                  f"{a if (na < nb) else b} first")
            print(f"       sort by driver name  : {a} vs {b} -> "
                  f"{a if (a < b) else b} first")
        else:
            print(f"    -> DIFFER by {abs(ta - tb):.6f}s  => NOT a tie. "
                  f"Explanation A is impossible; check B.")

    print()

print("=" * 78)
print("CROSS-CHECK: are there ANY exact ties in best_practice_s at all?")
print("=" * 78)
ties = con.execute(
    """
    SELECT year, round, best_practice_s, COUNT(*) n,
           GROUP_CONCAT(driver) drivers
    FROM practice
    WHERE best_practice_s IS NOT NULL
    GROUP BY year, round, best_practice_s
    HAVING COUNT(*) > 1
    ORDER BY year, round
    """
).fetchall()
print(f"  groups of drivers sharing an identical best_practice_s: {len(ties)}")
for t in ties:
    print(f"    {t['year']} R{t['round']}: {t['n']} drivers at "
          f"{t['best_practice_s']!r} -> {t['drivers']}")
if not ties:
    print("    NONE. So no rank difference can be caused by a time tie.")

print()
print("=" * 78)
print("CROSS-CHECK: do these 4 races have a starter with NO practice lap?")
print("=" * 78)
for y, r in RACES:
    no_lap = con.execute(
        "SELECT driver FROM practice WHERE year=? AND round=? "
        "AND has_practice_lap = 0", (y, r)
    ).fetchall()
    no_rank = con.execute(
        "SELECT driver FROM practice WHERE year=? AND round=? "
        "AND practice_rank IS NULL", (y, r)
    ).fetchall()
    print(f"  {y} R{r}: has_practice_lap=0 -> "
          f"{[x['driver'] for x in no_lap] or 'none'}   "
          f"practice_rank IS NULL -> {[x['driver'] for x in no_rank] or 'none'}")

print()
print("=" * 78)
print("DECISIVE TEST: reproduce the ORIGINAL rank using driver_number ordering")
print("=" * 78)
print("  If ranking by (time, driver_number) reproduces the STORED ranks for")
print("  all 13 races, the original key really was driver_number and the 4")
print("  'gapless' races are tie-break artifacts (explanation A).")
print("  If it does not reproduce them, something else ordered the original")
print("  (explanation B).")
print()

ok_tie = ok_other = 0
for (y, r), (a, b) in SWAPS.items():
    rows = con.execute(
        "SELECT driver, driver_number, practice_rank, best_practice_s "
        "FROM practice WHERE year=? AND round=? AND best_practice_s IS NOT NULL",
        (y, r)).fetchall()
    # original: derive_rank keyed by driver_number
    order = sorted(rows, key=lambda x: (x["best_practice_s"], x["driver_number"]))
    by_num = {x["driver"]: i + 1 for i, x in enumerate(order)}
    # repair: derive_rank keyed by driver name
    order2 = sorted(rows, key=lambda x: (x["best_practice_s"], x["driver"]))
    by_name = {x["driver"]: i + 1 for i, x in enumerate(order2)}

    stored = {x["driver"]: int(x["practice_rank"]) for x in rows
              if x["practice_rank"] is not None}
    match_num = all(by_num[d] == stored[d] for d in stored)
    match_name = all(by_name[d] == stored[d] for d in stored)
    print(f"  {y} R{r}: stored matches (time,driver_number)={match_num}  "
          f"matches (time,driver)={match_name}")
    if match_num and not match_name:
        ok_tie += 1
    elif match_name and not match_num:
        ok_other += 1
    else:
        print(f"       by_num  = {by_num}")
        print(f"       by_name = {by_name}")
        print(f"       stored  = {stored}")

print()
print(f"  reproduced by driver_number ordering : {ok_tie}/4")
print(f"  reproduced by driver-name ordering   : {ok_other}/4")

con.close()
