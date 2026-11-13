"""Which qualifying rows are corrupted by the positional-INSERT shift?

The bug: _migrate appended q_position_official at index 12, but fetch.py
INSERTs 13 values in the NEW schema order (q_position_official at index 6).
SQLite maps positionally, so every column from index 6 on is shifted one left.

Symptoms to detect:
  * has_qualifying_time holding fractional values (it should be 0 or 1)
  * q_position_official holding 0/1 (it should be a position 1..n or NULL)
  * q1_s holding a position number (it should be seconds ~70-110)

Run:  python scripts/diagnose_shift.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")

print("=" * 74)
print("VALUE RANGES PER COLUMN (corruption signature)")
print("=" * 74)
checks = [
    ("has_qualifying_time", "must be 0 or 1"),
    ("q_position_official", "must be 1..22 or NULL"),
    ("q1_s", "must be ~70-120 seconds or NULL"),
    ("q2_s", "must be ~70-120 seconds or NULL"),
    ("q3_s", "must be ~70-120 seconds or NULL"),
    ("best_q_s", "must be ~70-120 seconds or NULL"),
    ("gap_to_pole_pct", "must be 0..~5 or NULL"),
    ("q_position", "must be 1..22 or NULL"),
]
for col, expect in checks:
    row = con.execute(
        f"SELECT COUNT(*), COUNT({col}), MIN({col}), MAX({col}), "
        f"AVG({col}) FROM qualifying"
    ).fetchone()
    print(f"\n{col:22} ({expect})")
    print(f"   n={row[0]}  non-null={row[1]}  "
          f"min={row[2]}  max={row[3]}  avg={row[4]}")

print()
print("=" * 74)
print("CORRUPTION TEST PER ROW")
print("=" * 74)
# A healthy row has has_qualifying_time in (0,1). A shifted row has a gap
# float there instead.
bad = con.execute(
    """SELECT year, round, COUNT(*) FROM qualifying
       WHERE has_qualifying_time NOT IN (0,1) OR has_qualifying_time IS NULL
       GROUP BY year, round ORDER BY year, round"""
).fetchall()
print(f"rounds with bad has_qualifying_time: {len(bad)}")
for y, r, n in bad:
    print(f"   {y} R{r}: {n} rows")

# Which (year, round) are entirely bad vs entirely good?
allr = con.execute(
    "SELECT DISTINCT year, round FROM qualifying ORDER BY year, round"
).fetchall()
good_only, mixed, bad_only = [], [], []
for y, r in allr:
    n_bad = con.execute(
        "SELECT COUNT(*) FROM qualifying WHERE year=? AND round=? "
        "AND (has_qualifying_time NOT IN (0,1) OR has_qualifying_time IS NULL)",
        (y, r),
    ).fetchone()[0]
    n_tot = con.execute(
        "SELECT COUNT(*) FROM qualifying WHERE year=? AND round=?", (y, r)
    ).fetchone()[0]
    if n_bad == 0:
        good_only.append((y, r))
    elif n_bad == n_tot:
        bad_only.append((y, r))
    else:
        mixed.append((y, r, n_bad, n_tot))

print(f"\nfully GOOD rounds  : {len(good_only)}")
print(f"fully BAD rounds   : {len(bad_only)}")
print(f"MIXED rounds       : {len(mixed)}")
for y, r, nb, nt in mixed:
    print(f"   {y} R{r}: {nb}/{nt} bad")

print("\nBAD rounds:")
for y, r in bad_only:
    print(f"   {y} R{r}")

# Also: which rounds have q_position_official populated with a 0/1 flag?
flagged = con.execute(
    """SELECT year, round, COUNT(*) FROM qualifying
       WHERE q_position_official IN (0,1)
       GROUP BY year, round ORDER BY year, round"""
).fetchall()
print(f"\nrounds where q_position_official looks like a 0/1 flag "
      f"(should be a position): {len(flagged)}")
for y, r, n in flagged[:15]:
    print(f"   {y} R{r}: {n} rows")
