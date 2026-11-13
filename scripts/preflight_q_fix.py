"""Pre-flight checks before making q_position mean official Position everywhere.

Answers three questions the repair must not guess at:

  1. In post-migration races, is q_position_official populated for EVERY row?
     The repair is "q_position := q_position_official", so any row with a NULL
     official cannot be copied and needs a separate decision.

  2. Which rows would actually change? (both set but different)

  3. Do the 42 pre-migration races - where q_position_official is NULL and
     q_position must stay as-is - look like official Position? Official can
     contain ties (2023 R10: PER and BOT both 15) and gaps (2025 R9: no 14).
     derive_rank NEVER produces either. If pre-migration races show a tie or
     gap, that is direct proof they already hold official values.

Run:  python scripts/preflight_q_fix.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

races = [tuple(x) for x in con.execute(
    "SELECT DISTINCT year, round FROM qualifying ORDER BY year, round")]

print("=" * 74)
print("(1) POST-MIGRATION: is q_position_official populated for EVERY row?")
print("=" * 74)
partial = []
for y, rd in races:
    tot = con.execute(
        "SELECT COUNT(*) FROM qualifying WHERE year=? AND round=?",
        (y, rd)).fetchone()[0]
    off = con.execute(
        "SELECT COUNT(*) FROM qualifying WHERE year=? AND round=? "
        "AND q_position_official IS NOT NULL", (y, rd)).fetchone()[0]
    if 0 < off < tot:
        partial.append((y, rd, off, tot))
print(f"  races where official is PARTIALLY populated: {len(partial)}")
for y, rd, off, tot in partial:
    print(f"    {y} R{rd}: {off}/{tot} rows have official")

n_null_off = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position_official IS NULL").fetchone()[0]
n_null_qp = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position IS NULL").fetchone()[0]
print(f"\n  rows with official NULL : {n_null_off}")
print(f"  rows with q_position NULL: {n_null_qp}")

print()
print("  rows: official NULL but q_position SET (cannot copy -> keep as is):")
n = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position_official IS NULL "
    "AND q_position IS NOT NULL").fetchone()[0]
print(f"    {n}  (these are the pre-migration rows; q_position already IS official)")

print()
print("  rows: official SET but q_position NULL (would be filled by repair):")
n = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position_official IS NOT NULL "
    "AND q_position IS NULL").fetchone()[0]
print(f"    {n}")
for r in con.execute(
        "SELECT year, round, driver, q_position, q_position_official, "
        "       has_qualifying_time, best_q_s "
        "FROM qualifying WHERE q_position_official IS NOT NULL "
        "AND q_position IS NULL ORDER BY year, round LIMIT 20"):
    print(f"      {r['year']} R{r['round']:<3} {r['driver']:>4} "
          f"official={r['q_position_official']} has_time={r['has_qualifying_time']} "
          f"best={r['best_q_s']}")

print()
print("=" * 74)
print("(2) ROWS THAT WOULD ACTUALLY CHANGE (both set but different)")
print("=" * 74)
n = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position_official IS NOT NULL "
    "AND q_position IS NOT NULL AND q_position != q_position_official"
).fetchone()[0]
n_race = con.execute(
    "SELECT COUNT(DISTINCT year || '-' || round) FROM qualifying "
    "WHERE q_position_official IS NOT NULL AND q_position IS NOT NULL "
    "AND q_position != q_position_official").fetchone()[0]
print(f"  rows to update   : {n}")
print(f"  across races     : {n_race}")
print("\n  sample:")
for r in con.execute(
        "SELECT year, round, driver, q_position, q_position_official "
        "FROM qualifying WHERE q_position_official IS NOT NULL "
        "AND q_position IS NOT NULL AND q_position != q_position_official "
        "ORDER BY year, round, q_position_official LIMIT 12"):
    d = r["q_position"] - r["q_position_official"]
    print(f"    {r['year']} R{r['round']:<3} {r['driver']:>4} "
          f"q_position {r['q_position']:>5} -> {r['q_position_official']:>5} "
          f"({d:+.0f})")

print()
print("=" * 74)
print("(3) PRE-MIGRATION races: do they contain ties or gaps?")
print("=" * 74)
print("  derive_rank NEVER yields a duplicate or a gap.")
print("  official Position CAN (2023 R10 tie, 2025 R9 gap).")
print("  So a single tie or gap proves those rows already hold official.")
print()
dup_races = gap_races = clean_races = 0
for y, rd in races:
    off = con.execute(
        "SELECT COUNT(*) FROM qualifying WHERE year=? AND round=? "
        "AND q_position_official IS NOT NULL", (y, rd)).fetchone()[0]
    if off:
        continue                      # post-migration, skip
    vals = [int(x[0]) for x in con.execute(
        "SELECT q_position FROM qualifying WHERE year=? AND round=? "
        "AND q_position IS NOT NULL", (y, rd))]
    if not vals:
        continue
    if len(vals) != len(set(vals)):
        dup_races += 1
        print(f"  DUPLICATE  {y} R{rd}: {sorted(vals)}")
    elif sorted(set(vals)) != list(range(min(vals), max(vals) + 1)):
        gap_races += 1
        print(f"  GAP        {y} R{rd}: {sorted(vals)}")
    else:
        clean_races += 1
print()
print(f"  pre-migration races: clean 1..n = {clean_races}, "
      f"with a duplicate = {dup_races}, with a gap = {gap_races}")
if dup_races or gap_races:
    print("  -> at least one pre-migration race has an official-only pattern,")
    print("     confirming q_position there is already the official value.")
else:
    print("  -> none found; rely on the grid-agreement test instead")
    print("     (pre-migration 77.30% vs official anchor 76.12%).")

print()
print("=" * 74)
print("(4) WHAT THE TIES LOOK LIKE AFTER THE FIX")
print("=" * 74)
rows = con.execute(
    "SELECT year, round, q_position_official, COUNT(*) c, "
    "GROUP_CONCAT(driver) drivers "
    "FROM qualifying WHERE q_position_official IS NOT NULL "
    "GROUP BY year, round, q_position_official HAVING COUNT(*) > 1").fetchall()
print(f"  tied (race, official) groups that become tied q_position: {len(rows)}")
for r in rows:
    print(f"    {r['year']} R{r['round']:<3} position {r['q_position_official']}: "
          f"{r['drivers']}")

print()
print("=" * 74)
print("(5) NULL q_position AFTER THE FIX")
print("=" * 74)
# after fix: q_position = official wherever official exists, else unchanged
n_after = con.execute(
    "SELECT COUNT(*) FROM qualifying "
    "WHERE (q_position_official IS NOT NULL AND q_position_official IS NULL) "
    "   OR (q_position_official IS NULL AND q_position IS NULL)").fetchone()[0]
n_after = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE "
    "CASE WHEN q_position_official IS NOT NULL THEN q_position_official "
    "     ELSE q_position END IS NULL").fetchone()[0]
print(f"  rows that would have NULL q_position after the fix: {n_after}")
for r in con.execute(
        "SELECT year, round, driver, q_position, q_position_official, "
        "       has_qualifying_time, best_q_s "
        "FROM qualifying WHERE "
        "CASE WHEN q_position_official IS NOT NULL THEN q_position_official "
        "     ELSE q_position END IS NULL "
        "ORDER BY year, round"):
    print(f"    {r['year']} R{r['round']:<3} {r['driver']:>4} "
          f"official={r['q_position_official']} "
          f"has_time={r['has_qualifying_time']} best={r['best_q_s']}")
print()
print("  These are drivers who started but set no qualifying lap.")
print("  NULL is the honest value - the model already has")
print("  has_qualifying_time=0 as the missing flag for them.")
