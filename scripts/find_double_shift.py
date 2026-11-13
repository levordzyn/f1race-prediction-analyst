"""Why did the repair script un-shift a SECOND time? Find the false positive.

Theory: the idempotency guard was
    q_position_official IN (0,1) AND (gap IS NULL OR gap >= 50)
A REPAIRED pole sitter with no lap time (2025 R6 Miami, where every driver
has best/gap NULL) has q_position_official = 1 and gap = NULL, so it matches
the "corrupted" pattern and gets un-shifted again.

Run:  python scripts/find_double_shift.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

CUR = Path("f1.db")
BAK = Path("f1_backup_before_shift_repair.db")

print("=" * 74)
print("CURRENT f1.db")
print("=" * 74)
con = sqlite3.connect(CUR)
con.row_factory = sqlite3.Row

# the row that fails the flag/best consistency check
bad = con.execute(
    """SELECT rowid, year, round, driver, q_position, q_position_official,
              q1_s, q2_s, q3_s, best_q_s, gap_to_pole_pct, has_qualifying_time
       FROM qualifying
       WHERE (has_qualifying_time=1 AND best_q_s IS NULL)
          OR (has_qualifying_time=0 AND best_q_s IS NOT NULL)"""
).fetchall()
print(f"rows failing flag/best consistency: {len(bad)}")
for r in bad:
    print(f"  rowid={r['rowid']} {r['year']} R{r['round']} {r['driver']}")
    print(f"     q_position        = {r['q_position']}")
    print(f"     q_position_official = {r['q_position_official']}")
    print(f"     q1_s={r['q1_s']}  q2_s={r['q2_s']}  q3_s={r['q3_s']}")
    print(f"     best_q_s          = {r['best_q_s']}")
    print(f"     gap_to_pole_pct   = {r['gap_to_pole_pct']}")
    print(f"     has_qualifying_time = {r['has_qualifying_time']}")

print()
print("=" * 74)
print("THE SAME ROW IN THE BACKUP (taken before the 2nd run)")
print("=" * 74)
if BAK.exists():
    b = sqlite3.connect(BAK)
    b.row_factory = sqlite3.Row
    for r in bad:
        old = b.execute(
            """SELECT rowid, year, round, driver, q_position,
                      q_position_official, q1_s, q2_s, q3_s, best_q_s,
                      gap_to_pole_pct, has_qualifying_time
               FROM qualifying WHERE rowid=?""",
            (r["rowid"],),
        ).fetchone()
        if old is None:
            print(f"  rowid={r['rowid']} not in backup")
            continue
        print(f"  rowid={old['rowid']} {old['year']} R{old['round']} "
              f"{old['driver']}")
        for k in ("q_position", "q_position_official", "q1_s", "q2_s",
                  "q3_s", "best_q_s", "gap_to_pole_pct",
                  "has_qualifying_time"):
            mark = "" if old[k] == r[k] else "   <-- CHANGED"
            print(f"     {k:22} backup={old[k]!s:>8}  now={r[k]!s:>8}{mark}")
else:
    print("  no backup found")

print()
print("=" * 74)
print("WOULD THE CURRENT GUARD RE-FIRE ON THE BACKUP (idempotency test)?")
print("=" * 74)
if BAK.exists():
    b = sqlite3.connect(BAK)
    hits = b.execute(
        """SELECT year, round, driver, q_position_official, gap_to_pole_pct
           FROM qualifying
           WHERE q_position_official IN (0,1)
             AND (gap_to_pole_pct IS NULL OR gap_to_pole_pct >= 50.0)"""
    ).fetchall()
    print(f"rows the OLD guard flags in an already-repaired DB: {len(hits)}")
    for h in hits:
        print(f"   {h[0]} R{h[1]} {h[2]}  official={h[3]}  gap={h[4]}")
    print("  => any hit here is a FALSE POSITIVE (it is correct data).")

print()
print("=" * 74)
print("PROPOSED GUARD: corrupted rows hold a POSITION in q1_s (1..22),")
print("not a lap time (60..140)")
print("=" * 74)
for name, path in (("current f1.db", CUR), ("backup", BAK)):
    if not path.exists():
        continue
    c = sqlite3.connect(path)
    n = c.execute(
        """SELECT COUNT(*) FROM qualifying
           WHERE q_position_official IN (0,1)
             AND q1_s IS NOT NULL AND q1_s < 50.0"""
    ).fetchone()[0]
    n2 = c.execute(
        """SELECT COUNT(*) FROM qualifying
           WHERE q1_s IS NOT NULL AND q1_s < 50.0"""
    ).fetchone()[0]
    print(f"  {name:16} proposed-guard hits={n}   "
          f"q1_s<50 anywhere={n2}")
