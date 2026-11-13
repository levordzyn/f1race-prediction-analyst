"""Make q_position mean FastF1 official Position for EVERY row.

Two repairs, because q_position currently means two different things:

  * 49 post-migration races: q_position = derive_rank(best_q_s)  (WRONG)
        -> q_position := q_position_official
        also fills the 10 rows where official exists but q_position is NULL
        (drivers classified without setting a lap, e.g. 2024 R15 SAR = P20).

  * 42 pre-migration races: q_position = official already (verified three ways:
        grid agreement 77.30% vs official anchor 76.12%; 155/837 rows differ
        from derive_rank; 2023 R2 stored == FastF1 raw Position 20/20)
        -> q_position_official := q_position   (backfill the provenance column)

Rows where both are NULL stay NULL (6 drivers who started but FastF1 never
classified in qualifying, e.g. 2026 R1 SAI/STR/VER). Those keep
has_qualifying_time=0 as their missing flag.

After the repair q_position == q_position_official everywhere (or both NULL),
so the column can never drift into two meanings again.

A timestamped backup of f1.db is written first.

Run:  python scripts/repair_q_position.py
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB = Path("f1.db")
if not DB.exists():
    sys.exit("f1.db not found - run from the project root")

backup = DB.with_name(f"f1_backup_before_q_position_repair_"
                      f"{datetime.now():%Y%m%d_%H%M%S}.db")
shutil.copy2(DB, backup)
print(f"backup written: {backup.name}")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

n_pre = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position_official IS NULL"
).fetchone()[0]
n_copy = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position_official IS NOT NULL "
    "AND (q_position IS NULL OR q_position != q_position_official)"
).fetchone()[0]

print()
print("repair plan:")
print(f"  (A) q_position := q_position_official   rows to change : {n_copy}")
print(f"  (B) q_position_official := q_position   rows to fill   : {n_pre}")

# (A) post-migration: overwrite q_position with the official value
con.execute(
    "UPDATE qualifying SET q_position = q_position_official "
    "WHERE q_position_official IS NOT NULL "
    "AND (q_position IS NULL OR q_position != q_position_official)"
)

# (B) pre-migration: backfill the provenance column from q_position
con.execute(
    "UPDATE qualifying SET q_position_official = q_position "
    "WHERE q_position_official IS NULL AND q_position IS NOT NULL"
)

con.commit()

# ---------------------------------------------------------------- verification
print()
print("=" * 74)
print("VERIFICATION")
print("=" * 74)

# q_position and q_position_official must now agree on every row:
# rows differ if NULL-ness differs, or if both set but values differ
n_diff = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE "
    "(q_position IS NULL) != (q_position_official IS NULL) "
    "OR (q_position IS NOT NULL AND q_position_official IS NOT NULL "
    "    AND q_position != q_position_official)"
).fetchone()[0]
n_both_null = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position IS NULL "
    "AND q_position_official IS NULL"
).fetchone()[0]
n_rows = con.execute("SELECT COUNT(*) FROM qualifying").fetchone()[0]

print(f"  rows total                                  : {n_rows}")
print(f"  rows where q_position != q_position_official: {n_diff}   (expect 0)")
print(f"  rows where both are NULL                    : {n_both_null}  (expect 6)")

n_ties = con.execute(
    "SELECT COUNT(*) FROM (SELECT year, round, q_position, COUNT(*) c "
    "FROM qualifying WHERE q_position IS NOT NULL "
    "GROUP BY year, round, q_position HAVING COUNT(*) > 1)"
).fetchone()[0]
print(f"  tied (race, position) groups kept as-is     : {n_ties}")

n_out_of_range = con.execute(
    "SELECT COUNT(*) FROM qualifying WHERE q_position IS NOT NULL "
    "AND (q_position < 1 OR q_position > 22)"
).fetchone()[0]
print(f"  q_position outside 1..22                    : {n_out_of_range}   (expect 0)")

# range per race against the 22-car/20-car expectation
bad = con.execute(
    "SELECT year, round, MAX(q_position) mx, COUNT(DISTINCT driver) n "
    "FROM qualifying WHERE q_position IS NOT NULL "
    "GROUP BY year, round HAVING MAX(q_position) > 22"
).fetchall()
print(f"  races whose max position exceeds 22          : {len(bad)}   (expect 0)")

# sample: the rows that changed
print()
print("sample of rows that changed (was -> now):")
# we cannot see old values after the update; show a known group instead
for r in con.execute(
        "SELECT year, round, driver, q_position, q_position_official "
        "FROM qualifying WHERE year=2025 AND round=17 "
        "ORDER BY q_position IS NULL, q_position LIMIT 8"):
    print(f"    {r['year']} R{r['round']:<3} {r['driver']:>4} "
          f"q_position={r['q_position']}  official={r['q_position_official']}")

print()
print("2025 R17 (Baku) official top 4 - SAI P2, ANT P4 as classified:")
for r in con.execute(
        "SELECT driver, q_position FROM qualifying "
        "WHERE year=2025 AND round=17 AND q_position <= 4 "
        "ORDER BY q_position"):
    print(f"    P{int(r['q_position'])} {r['driver']}")

print()
if n_diff == 0 and n_out_of_range == 0 and not bad:
    print("REPAIR OK - q_position now means official Position on every row.")
else:
    print("REPAIR INCOMPLETE - inspect the counts above.")
    con.close()
    sys.exit(1)

con.close()
