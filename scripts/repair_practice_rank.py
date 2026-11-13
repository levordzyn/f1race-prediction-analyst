"""Repair practice_rank: re-derive it among STARTERS only.

Bug: clean.derive_rank() was called on every driver OpenF1 reported for the
practice session, including reserve/test drivers who never started the race.
_write_rows() then stored only starters, so phantom ranks consumed numbers
and real starters were left with inflated ranks - up to P27 in a 22-car field.

  affected: 9 of 89 races, 17 rows (0.94%)
  example : STR 2026 R7 stored practice_rank 27; he was 22nd of 22

best_practice_s was always correct, so the right rank is recoverable from the
stored times without touching OpenF1. Mirrors clean.derive_rank exactly:
rank = position among drivers WITH a lap time, ordered by (time, driver);
drivers with no time keep NULL.

Idempotent: running twice changes nothing the second time.

Run:  python scripts/repair_practice_rank.py
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import clean  # noqa: E402

DB = Path("f1.db")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row


def correct_ranks() -> dict[tuple[int, int, str], int | None]:
    """{(year, round, driver): correct practice_rank} computed per race.

    Keyed by driver_number, NOT driver name. clean.derive_rank sorts by
    (time, dict_key), and practice.py calls it with driver_number keys. Using
    the driver name instead silently flips exact ties: 2025 R10 PIA/SAI both
    set 72.519s, and name-ordering would have swapped them even though the
    stored rank was correct. Verified by scripts/explain_rank_swaps.py.
    """
    out: dict[tuple[int, int, str], int | None] = {}
    races = con.execute(
        "SELECT DISTINCT year, round FROM practice ORDER BY year, round"
    ).fetchall()
    for r in races:
        rows = con.execute(
            "SELECT driver, driver_number, best_practice_s FROM practice "
            "WHERE year=? AND round=? ORDER BY driver",
            (r["year"], r["round"]),
        ).fetchall()
        # driver_number is never NULL and never repeats within a race
        # (checked on all 1816 rows), so it is a safe dict key.
        bests = {x["driver_number"]: x["best_practice_s"] for x in rows}
        by_num = {x["driver_number"]: x["driver"] for x in rows}
        ranks = clean.derive_rank(bests)
        for num, rk in ranks.items():
            out[(r["year"], r["round"], by_num[num])] = rk
    return out


before = {  # current stored values
    (r["year"], r["round"], r["driver"]): r["practice_rank"]
    for r in con.execute(
        "SELECT year, round, driver, practice_rank FROM practice"
    )
}
want = correct_ranks()

changed = [(k, before[k], want[k]) for k in before if before[k] != want[k]]

print("=" * 78)
print("BEFORE REPAIR")
print("=" * 78)
print(f"  rows                      : {len(before)}")
print(f"  rows with wrong rank      : {len(changed)}")
over = [k for k, b, w in changed
        if b is not None and b > (
            con.execute("SELECT COUNT(*) FROM results WHERE year=? AND round=?",
                        (k[0], k[1])).fetchone()[0])]
print(f"  of those, rank > field    : {len(over)}")
print(f"  distinct races affected   : "
      f"{len({(k[0], k[1]) for k, _, _ in changed})}")

# Group by race so the FULL extent is visible. The earlier "rank > field" test
# only catches the loudest symptom: in a race where some starters have no
# practice lap, phantom ranks fit inside that slack and never exceed the field
# size, so those races were missed (13 affected, not 9).
by_race: dict[tuple[int, int], list] = {}
for k, b, w in changed:
    by_race.setdefault((k[0], k[1]), []).append((k[2], b, w))

print()
print(f"  {'race':<12} {'field':>5} {'max_rank':>8} {'gaps in 1..max':<20} {'rows':>5}")
for (y, r), items in sorted(by_race.items()):
    field = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=? AND round=?", (y, r)
    ).fetchone()[0]
    ranks = sorted(
        int(x["practice_rank"]) for x in con.execute(
            "SELECT practice_rank FROM practice WHERE year=? AND round=? "
            "AND practice_rank IS NOT NULL", (y, r))
    )
    if ranks:
        gaps = [i for i in range(ranks[0], ranks[-1] + 1) if i not in ranks]
        span = f"1..{ranks[-1]}" if ranks[0] == 1 else f"{ranks[0]}..{ranks[-1]}"
        gtxt = f"{span} missing {gaps}"
    else:
        gtxt = "(no ranks)"
    print(f"  {y} R{r:<7} {field:>5} {(ranks[-1] if ranks else 0):>8} "
          f"{gtxt:<20} {len(items):>5}")

print()
print(f"  {'race':<12} {'drv':<5} {'before':>7} {'after':>6}  change")
for (y, r), items in sorted(by_race.items()):
    for drv, b, w in sorted(items, key=lambda t: (t[1] is None, t[1] or 0)):
        delta = "" if (b is None or w is None) else f"{int(w) - int(b):+d}"
        print(f"  {y} R{r:<7} {drv:<5} {str(b):>7} {str(w):>6}  {delta}")

if not changed:
    print("\n  nothing to do - already correct")
    con.close()
    sys.exit(0)

# Dry-run unless --apply is given: this script only ever writes on request.
if "--apply" not in sys.argv:
    print("\n" + "=" * 78)
    print("DRY RUN - no rows were changed")
    print("=" * 78)
    print("  Re-run with --apply to write the repair.")
    con.close()
    sys.exit(0)

# ---- backup -------------------------------------------------------------
stamp = time.strftime("%Y%m%d_%H%M%S")
backup = Path(f"f1_backup_before_practice_rank_repair_{stamp}.db")
con.commit()
shutil.copy(DB, backup)
print(f"\n  backup written: {backup.name} ({backup.stat().st_size:,} bytes)")

# ---- apply --------------------------------------------------------------
con.executemany(
    "UPDATE practice SET practice_rank = ? WHERE year = ? AND round = ? "
    "AND driver = ?",
    [(w, k[0], k[1], k[2]) for k, _b, w in changed],
)
con.commit()
print(f"  updated {len(changed)} rows")

# ---- verify -------------------------------------------------------------
print()
print("=" * 78)
print("AFTER REPAIR")
print("=" * 78)
ok = True

# 1. stored ranks now equal the derivation
after = {
    (r["year"], r["round"], r["driver"]): r["practice_rank"]
    for r in con.execute(
        "SELECT year, round, driver, practice_rank FROM practice")
}
still = [k for k in after if after[k] != want[k]]
c1 = not still
print(f"  [1] every rank matches a fresh derivation      "
      f"{'PASS' if c1 else 'FAIL ' + str(len(still))}")
ok &= c1

# 2. no rank exceeds its own field size
bad = con.execute(
    """
    SELECT COUNT(*) FROM practice p
    WHERE p.practice_rank > (SELECT COUNT(*) FROM results r
                              WHERE r.year=p.year AND r.round=p.round)
    """
).fetchone()[0]
c2 = bad == 0
print(f"  [2] no rank exceeds its field size ({bad})            "
      f"{'PASS' if c2 else 'FAIL'}")
ok &= c2

# 3. min=1 and unique within every race
bad_min = con.execute(
    """
    SELECT COUNT(*) FROM (SELECT year, round FROM practice
      GROUP BY year, round HAVING MIN(practice_rank) != 1)
    """
).fetchone()[0]
dup = con.execute(
    """
    SELECT COUNT(*) FROM (SELECT year, round, practice_rank FROM practice
      WHERE practice_rank IS NOT NULL
      GROUP BY year, round, practice_rank HAVING COUNT(*) > 1)
    """
).fetchone()[0]
c3 = bad_min == 0 and dup == 0
print(f"  [3] MIN=1 everywhere, no duplicate ranks       "
      f"{'PASS' if c3 else f'FAIL min={bad_min} dup={dup}'}")
ok &= c3

# 4. total rows unchanged, and best_practice_s untouched
n_rows = con.execute("SELECT COUNT(*) FROM practice").fetchone()[0]
n_null_best = con.execute(
    "SELECT COUNT(*) FROM practice WHERE best_practice_s IS NULL").fetchone()[0]
c4 = n_rows == 1816
print(f"  [4] still 1816 rows ({n_rows})                    "
      f"{'PASS' if c4 else 'FAIL'}")
ok &= c4

# 5. sprint_qualifying untouched (it was never affected)
sq = con.execute("SELECT COUNT(*) FROM sprint_qualifying WHERE sq_rank > "
                 "(SELECT COUNT(*) FROM results r WHERE r.year=sprint_qualifying.year "
                 " AND r.round=sprint_qualifying.round)").fetchone()[0]
c5 = sq == 0
print(f"  [5] sprint_qualifying still clean ({sq})              "
      f"{'PASS' if c5 else 'FAIL'}")
ok &= c5

# 6. drivers with no lap keep NULL rank
n_no_lap = con.execute(
    "SELECT COUNT(*) FROM practice WHERE has_practice_lap = 0").fetchone()[0]
n_ranked_no_lap = con.execute(
    "SELECT COUNT(*) FROM practice WHERE has_practice_lap = 0 "
    "AND practice_rank IS NOT NULL").fetchone()[0]
c6 = n_ranked_no_lap == 0
print(f"  [6] no-lap drivers keep NULL rank "
      f"({n_ranked_no_lap}/{n_no_lap})      {'PASS' if c6 else 'FAIL'}")
ok &= c6

# 7. idempotency: re-deriving changes nothing now
again = correct_ranks()
c7 = all(after[k] == again[k] for k in after)
print(f"  [7] idempotent (re-run changes nothing)        "
      f"{'PASS' if c7 else 'FAIL'}")
ok &= c7

print()
print("=" * 78)
print("PRACTICE_RANK REPAIR PASSED" if ok else "PRACTICE_RANK REPAIR FAILED")
print("=" * 78)
con.close()
sys.exit(0 if ok else 1)
