"""Fix the false-positive damage and make the repair guard reliable.

TWO bugs, both mine:

1. ORIGINAL: positional INSERT shifted columns (fixed by un-shifting 993 rows).
2. THE GUARD ITSELF: it detected corruption via
       q_position_official IN (0,1) AND (gap IS NULL OR gap >= 50)
   But 2025 R6 VER is legitimately q_position_official=1.0 with gap=NULL
   (P1, no lap times - FastF1's Q1/Q2/Q3 are all NaT there). The guard fired
   on correct data and un-shifted that row a SECOND time, corrupting it.

Repair strategy:
  a) restore rows that now fail flag/best consistency from the backup
     (the backup was taken before the 2nd run, so it holds correct values);
  b) switch the guard to the reliable signature - a corrupted row stores a
     POSITION (1..22) in q1_s, where a lap time (60..140s) belongs.

Run:  python scripts/fix_guard_and_restore.py
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

CUR = Path("f1.db")
BAK = Path("f1_backup_before_shift_repair.db")

COLS = [
    "year", "round", "driver", "driver_number", "team",
    "q_position", "q_position_official", "q1_s", "q2_s", "q3_s",
    "best_q_s", "gap_to_pole_pct", "has_qualifying_time",
]


def main() -> int:
    if not BAK.exists():
        print(f"backup {BAK} missing - cannot restore safely")
        return 1

    # snapshot current state so this step is itself reversible
    snap = Path("f1_backup_before_guard_fix.db")
    shutil.copy2(CUR, snap)
    print(f"snapshot of current state: {snap}")

    con = sqlite3.connect(CUR)
    con.row_factory = sqlite3.Row
    bak = sqlite3.connect(BAK)
    bak.row_factory = sqlite3.Row

    # ------------------------------------------------ (a) restore damaged row
    damaged = con.execute(
        """SELECT rowid FROM qualifying
           WHERE (has_qualifying_time=1 AND best_q_s IS NULL)
              OR (has_qualifying_time=0 AND best_q_s IS NOT NULL)"""
    ).fetchall()
    print(f"\nrows failing flag/best consistency: {len(damaged)}")

    restored = 0
    for d in damaged:
        old = bak.execute(
            f"SELECT {', '.join(COLS)} FROM qualifying WHERE rowid=?",
            (d["rowid"],),
        ).fetchone()
        if old is None:
            print(f"  rowid={d['rowid']}: NOT in backup, cannot restore")
            continue
        # sanity: the backup row must itself be consistent
        if (old["has_qualifying_time"] == 1) != (old["best_q_s"] is not None):
            print(f"  rowid={d['rowid']}: backup is ALSO inconsistent, "
                  f"skipping")
            continue
        con.execute(
            f"UPDATE qualifying SET {', '.join(f'{c}=?' for c in COLS)} "
            f"WHERE rowid=?",
            tuple(old[c] for c in COLS) + (d["rowid"],),
        )
        restored += 1
        print(f"  rowid={d['rowid']}: restored from backup "
              f"({old['year']} R{old['round']} {old['driver']})")
    con.commit()

    # ------------------------------------- (b) confirm the reliable signature
    print()
    print("=" * 70)
    print("GUARD SIGNATURE CHECK")
    print("=" * 70)
    # corrupted row: q1_s holds a position (1..22) instead of 60..140s
    for name, path in (("backup (known good)", BAK), ("f1.db (now)", CUR)):
        c = sqlite3.connect(path)
        n = c.execute(
            "SELECT COUNT(*) FROM qualifying "
            "WHERE q1_s IS NOT NULL AND q1_s < 50.0"
        ).fetchone()[0]
        # and prove it does NOT fire on known-good data
        print(f"  {name:22} q1_s<50 hits = {n}")

    print()
    print("Interpretation: 0 hits on the backup means the new guard is")
    print("idempotent - it will not touch already-correct rows.")

    # ------------------------------------------------------- final validation
    print()
    print("=" * 70)
    print("FULL VALIDATION")
    print("=" * 70)
    failures = 0

    def report(label: str, bad: int, detail: str = "") -> None:
        nonlocal failures
        failures += bad
        print(f"  {label:40} "
              f"{'OK' if bad == 0 else f'FAIL ({bad})'}")
        if bad and detail:
            print(f"      {detail}")

    report("has_qualifying_time in (0,1)",
           con.execute(
               "SELECT COUNT(*) FROM qualifying "
               "WHERE has_qualifying_time NOT IN (0,1) "
               "OR has_qualifying_time IS NULL").fetchone()[0])

    report("flag consistent with best_q_s",
           con.execute(
               "SELECT COUNT(*) FROM qualifying WHERE "
               "(has_qualifying_time=1 AND best_q_s IS NULL) OR "
               "(has_qualifying_time=0 AND best_q_s IS NOT NULL)"
           ).fetchone()[0])

    for col, lo, hi in (("q_position", 1, 22),
                        ("q_position_official", 1, 22),
                        ("q1_s", 60, 140), ("q2_s", 60, 140),
                        ("q3_s", 60, 140), ("best_q_s", 60, 140),
                        ("gap_to_pole_pct", 0.0, 50.0)):
        report(f"{col} in [{lo},{hi}]",
               con.execute(
                   f"SELECT COUNT(*) FROM qualifying WHERE {col} IS NOT NULL "
                   f"AND ({col} < ? OR {col} > ?)", (lo, hi)).fetchone()[0])

    # no position stored where a lap time belongs
    report("q1_s holds a lap time (not a position)",
           con.execute(
               "SELECT COUNT(*) FROM qualifying "
               "WHERE q1_s IS NOT NULL AND q1_s < 50.0").fetchone()[0])

    report("q_position unique + starts at 1",
           len(con.execute(
               """SELECT year, round FROM qualifying
                  WHERE q_position IS NOT NULL
                  GROUP BY year, round
                  HAVING MIN(q_position) != 1
                      OR COUNT(DISTINCT q_position) != COUNT(*)
                      OR MAX(q_position) > 22"""
           ).fetchall()))

    report("gap matches (best-pole)/pole*100",
           con.execute(
               """SELECT COUNT(*) FROM qualifying q
                  JOIN (SELECT year, round, MIN(best_q_s) AS pole
                        FROM qualifying WHERE best_q_s IS NOT NULL
                        GROUP BY year, round) p
                    ON p.year=q.year AND p.round=q.round
                  WHERE q.best_q_s IS NOT NULL
                    AND ABS(q.gap_to_pole_pct
                            - (q.best_q_s-p.pole)/p.pole*100.0) > 1e-6"""
           ).fetchone()[0])

    report("pole sitter has gap == 0",
           len(con.execute(
               """SELECT q.year, q.round FROM qualifying q
                  JOIN (SELECT year, round, MIN(best_q_s) AS pole
                        FROM qualifying WHERE best_q_s IS NOT NULL
                        GROUP BY year, round) p
                    ON p.year=q.year AND p.round=q.round
                  WHERE q.best_q_s = p.pole
                    AND ABS(q.gap_to_pole_pct) > 1e-9"""
           ).fetchall()))

    total = con.execute("SELECT COUNT(*) FROM qualifying").fetchone()[0]
    with_time = con.execute(
        "SELECT COUNT(*) FROM qualifying WHERE has_qualifying_time=1"
    ).fetchone()[0]
    print(f"\n  rows={total}  with_lap_time={with_time}  "
          f"missing={total - with_time}")

    print()
    if failures:
        print(f"STILL FAILING: {failures}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
