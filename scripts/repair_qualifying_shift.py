"""Repair the qualifying column shift caused by a positional INSERT.

THE BUG
-------
`db._migrate()` appended `q_position_official` at physical index 12, but
`fetch.py` built its tuple in logical schema order (index 6) and used a
positional `VALUES (?,?,...)`. SQLite maps positionally, so from index 6 on
every value landed one column to the left:

    tuple index  content              landed in column
    ----------  -------------------  ----------------
    6           q_position_official   q1_s
    7           q1_s                  q2_s
    8           q2_s                  q3_s
    9           q3_s                  best_q_s
    10          best_q_s              gap_to_pole_pct
    11          gap_to_pole_pct       has_qualifying_time
    12          has_qualifying_time   q_position_official

Rows inserted BEFORE the migration got `q_position_official = NULL` (the
column did not exist yet) and are correct, so
`q_position_official IS NOT NULL` identifies exactly the corrupted rows.

This un-shifts them in place and verifies every column against its documented
valid range. A backup is written first. The fix itself is in
`f1pred/fetch.py`, which now uses explicit column names.

Run:  python scripts/repair_qualifying_shift.py
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

DB = Path("f1.db")
BACKUP = Path("f1_backup_before_shift_repair.db")

COLS = [
    "year", "round", "driver", "driver_number", "team",
    "q_position", "q_position_official", "q1_s", "q2_s", "q3_s",
    "best_q_s", "gap_to_pole_pct", "has_qualifying_time",
]

# destination column <- source column currently holding its value
UNSHIFT = [
    ("q_position_official", "q1_s"),
    ("q1_s", "q2_s"),
    ("q2_s", "q3_s"),
    ("q3_s", "best_q_s"),
    ("best_q_s", "gap_to_pole_pct"),
    ("gap_to_pole_pct", "has_qualifying_time"),
    ("has_qualifying_time", "q_position_official"),
]

# column -> (min, max) inclusive; NULL always allowed.
# NOTE: gaps above 6% are REAL (verified against FastF1 raw: SAR 2023 R2 is
# 45.596% off pole and FastF1 reports the same Q1). So this is a loose
# sanity bound only - it must exclude lap times (which are 60-140s) that would
# indicate the shift is still present.
RANGES = {
    "q_position": (1, 22),
    "q_position_official": (1, 22),
    "q1_s": (60, 140),
    "q2_s": (60, 140),
    "q3_s": (60, 140),
    "best_q_s": (60, 140),
    "gap_to_pole_pct": (0.0, 50.0),
}


def find_corrupted(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """Rows still carrying the positional-INSERT shift.

    MUST be idempotent. An earlier version of this guard used
    ``q_position_official IN (0,1) AND gap IS NULL``, which fired on correct
    data - 2025 R6 VER is legitimately P1 (q_position_official=1) with no lap
    times (gap NULL), so the guard un-shifted a good row a second time and
    corrupted it. Detecting on q_position_official can never work, because
    "position 1" is indistinguishable from the old 0/1 flag.

    The reliable signature is where the values LANDED: a shifted row stores a
    POSITION (1..22) in ``q1_s``, where a lap time (60..140 s) belongs. A
    repaired or untouched row never has q1_s < 50, so this cannot re-fire.
    """
    return con.execute(
        "SELECT rowid, * FROM qualifying "
        "WHERE q1_s IS NOT NULL AND q1_s < 50.0"
    ).fetchall()


def main() -> int:
    if not DB.exists():
        print(f"no {DB} found")
        return 1

    shutil.copy2(DB, BACKUP)
    print(f"backup written: {BACKUP}")

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    rows = find_corrupted(con)
    n_good = con.execute(
        "SELECT COUNT(*) FROM qualifying"
    ).fetchone()[0] - len(rows)
    print(f"corrupted rows (positional shift detected): {len(rows)}")
    print(f"already-correct rows                      : {n_good}")
    if not rows:
        print("nothing to repair (idempotent: already repaired)")
    else:
        # Read every source value BEFORE writing any destination: building the
        # whole new tuple from the original row avoids in-place aliasing bugs.
        # Bindings must be flat: 13 column values followed by the rowid.
        payload = []
        for r in rows:
            orig = {k: r[k] for k in r.keys() if k != "rowid"}
            new = dict(orig)
            for dest, src in UNSHIFT:
                new[dest] = orig[src]
            payload.append(tuple(new[c] for c in COLS) + (r["rowid"],))

        set_sql = ", ".join(f"{c}=?" for c in COLS)
        con.executemany(
            f"UPDATE qualifying SET {set_sql} WHERE rowid=?", payload
        )
        con.commit()
        print(f"un-shifted {len(payload)} rows")

    # ---------------------------------------------------------------- verify
    print()
    print("=" * 70)
    print("VERIFICATION")
    print("=" * 70)
    failures = 0

    def report(label: str, bad: int) -> None:
        nonlocal failures
        failures += bad
        print(f"  {label:34} "
              f"{'OK' if bad == 0 else f'FAIL ({bad} rows)'}")

    report("has_qualifying_time in (0,1)",
           con.execute(
               "SELECT COUNT(*) FROM qualifying "
               "WHERE has_qualifying_time NOT IN (0,1) "
               "OR has_qualifying_time IS NULL").fetchone()[0])

    for col, (lo, hi) in RANGES.items():
        report(f"{col} in [{lo},{hi}]",
               con.execute(
                   f"SELECT COUNT(*) FROM qualifying WHERE {col} IS NOT NULL "
                   f"AND ({col} < ? OR {col} > ?)", (lo, hi)).fetchone()[0])

    # Positions must start at 1, contain no duplicates, and stay within the
    # grid. GAPS are legal: 2025 R9 has no rank 14 because STR qualified but
    # did not start the race - absent drivers must NOT be renumbered around,
    # or we would misreport where everyone actually qualified.
    bad_races = con.execute(
        """SELECT year, round, COUNT(*) AS n, MIN(q_position) AS lo,
                  MAX(q_position) AS hi, COUNT(DISTINCT q_position) AS uniq
           FROM qualifying WHERE q_position IS NOT NULL
           GROUP BY year, round
           HAVING lo != 1 OR uniq != n OR hi > 22"""
    ).fetchall()
    report("q_position starts 1, unique, <=22", len(bad_races))
    for r in bad_races:
        print(f"      {r['year']} R{r['round']}: n={r['n']} lo={r['lo']} "
              f"hi={r['hi']} distinct={r['uniq']}")

    # and confirm any gap is explained by a driver absent from results
    gapped = con.execute(
        """SELECT year, round, COUNT(*) AS n, MAX(q_position) AS hi
           FROM qualifying WHERE q_position IS NOT NULL
           GROUP BY year, round HAVING hi != n"""
    ).fetchall()
    unexplained = 0
    for r in gapped:
        # does results have fewer drivers than the top rank used?
        n_res = con.execute(
            "SELECT COUNT(*) FROM results WHERE year=? AND round=?",
            (r["year"], r["round"]),
        ).fetchone()[0]
        if n_res < r["hi"]:
            continue          # absent driver explains the gap
        unexplained += 1
        print(f"      UNEXPLAINED gap: {r['year']} R{r['round']} "
              f"n={r['n']} hi={r['hi']} results={n_res}")
    report("q_position gaps explained by absent drivers", unexplained)

    # gap must equal (best - pole)/pole*100 within rounding tolerance
    report("gap_to_pole_pct matches best_q_s",
           con.execute(
               """SELECT COUNT(*) FROM qualifying q
                  JOIN (SELECT year, round, MIN(best_q_s) AS pole
                        FROM qualifying WHERE best_q_s IS NOT NULL
                        GROUP BY year, round) p
                    ON p.year=q.year AND p.round=q.round
                  WHERE q.best_q_s IS NOT NULL
                    AND ABS(q.gap_to_pole_pct
                            - (q.best_q_s - p.pole) / p.pole * 100.0) > 1e-6"""
           ).fetchone()[0])

    report("flag consistent with best_q_s",
           con.execute(
               "SELECT COUNT(*) FROM qualifying WHERE "
               "(has_qualifying_time=1 AND best_q_s IS NULL) OR "
               "(has_qualifying_time=0 AND best_q_s IS NOT NULL)"
           ).fetchone()[0])

    # official position, where present, must not contain the old 0/1 flag
    report("q_position_official not a 0/1 flag",
           con.execute(
               "SELECT COUNT(*) FROM qualifying "
               "WHERE q_position_official IS NOT NULL "
               "AND q_position_official NOT BETWEEN 1 AND 22"
           ).fetchone()[0])

    print()
    if failures:
        print(f"REPAIR INCOMPLETE - {failures} problems.")
        print(f"Restore from {BACKUP} and re-fetch instead.")
        return 1
    print(f"REPAIR OK - all checks passed.")
    print(f"Backup kept at: {BACKUP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
