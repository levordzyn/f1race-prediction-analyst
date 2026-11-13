"""Purge the bad 2026 R19 rows so the race can be fetched again.

WHAT WENT WRONG
---------------
`fetch_race` stored the session FastF1 returned at 2026-11-01T05:55 UTC -
before the Mexico City GP had run. That response was a pre-race entry list:
32 rows, every `finish` and `grid` NULL, including 10 placeholder codes
(FM1-FM5, SC1-SC3, MC1-MC2, driver numbers 236-247, no name/team/status).
The step was logged as done, so it would never have been retried.
Field-size validation DID fire ("32 rows exceeds the 22-car grid") but only
in pass 2 - after pass 1 had already committed and logged the step.

`fetch_race` now refuses to store a session with zero classified finishers
and ignores entrants that took no part. This script only clears the damage.

A backup is taken first. Idempotent: safe to re-run.

Run:  python scripts/purge_bad_2026_r19.py
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

DB = Path("f1.db")
BACKUP = Path("f1_backup_before_r19_purge.db")

# which rows are bad: the placeholders and the all-null phantom entrant
PLACEHOLDER_NUMBERS = (236, 237, 238, 239, 240, 241, 242, 243, 246, 247)


def main() -> int:
    if not DB.exists():
        print(f"no {DB} found")
        return 1

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    # ---- report what is there BEFORE touching anything
    print("=" * 74)
    print("BEFORE")
    print("=" * 74)
    for t in ("results", "driver_numbers", "qualifying", "practice",
              "sprint", "sprint_qualifying"):
        n = con.execute(
            f"SELECT COUNT(*) FROM {t} WHERE year=2026 AND round=19"
        ).fetchone()[0]
        print(f"  {t:20} {n}")
    s = con.execute(
        "SELECT n_starters, expected_size FROM sessions "
        "WHERE year=2026 AND round=19"
    ).fetchone()
    print(f"  sessions.n_starters   {s['n_starters']} "
          f"(expected_size={s['expected_size']})")
    for l in con.execute(
        "SELECT step, nrows, run_at FROM fetch_log "
        "WHERE year=2026 AND round=19 ORDER BY step"
    ):
        print(f"  fetch_log {l['step']:20} nrows={l['nrows']} {l['run_at']}")

    # sanity: confirm the diagnosis before deleting. Two bad states exist:
    #   state 1 (fetched pre-race): every finish/grid NULL, 32 rows
    #   state 2 (fetched post-race with the broken filter): 33 rows mixing
    #          real finishes with 10 placeholder entrants + OCO
    # Both are identified by the placeholder driver numbers, which are
    # invalid in every state - that is the reliable signal.
    total = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=2026 AND round=19"
    ).fetchone()[0]
    ph = con.execute(
        "SELECT COUNT(*) FROM driver_numbers WHERE year=2026 AND round=19 "
        "AND driver_number IN ({})".format(",".join("?" * len(PLACEHOLDER_NUMBERS))),
        PLACEHOLDER_NUMBERS,
    ).fetchone()[0]
    n_finish = con.execute(
        "SELECT COUNT(*) FROM results WHERE year=2026 AND round=19 "
        "AND finish IS NOT NULL"
    ).fetchone()[0]
    print(f"\n  results rows                 : {total}")
    print(f"  rows with a finish           : {n_finish}")
    print(f"  placeholder driver numbers   : {ph}")

    if total == 0:
        print("\nnothing to purge (already clean)")
        return 0
    if ph != len(PLACEHOLDER_NUMBERS):
        print(f"\nABORT: expected {len(PLACEHOLDER_NUMBERS)} placeholder "
              f"driver numbers, found {ph}. This does not look like the "
              f"known-bad state - inspect before deleting.")
        return 1

    # ---- backup, then delete
    shutil.copy2(DB, BACKUP)
    print(f"\nbackup written: {BACKUP}")

    # Delete the race/qualifying/practice rows AND their fetch_log entries so
    # the next run re-fetches them. sessions row is kept (its meeting_key and
    # event metadata are valid) but n_starters/expected_size are reset to NULL
    # so assign_field_sizes recomputes them from the corrected data.
    steps = [r["step"] for r in con.execute(
        "SELECT DISTINCT step FROM fetch_log WHERE year=2026 AND round=19"
    )]
    for t in ("results", "driver_numbers", "qualifying", "practice",
              "sprint", "sprint_qualifying"):
        cur = con.execute(
            f"DELETE FROM {t} WHERE year=2026 AND round=19"
        )
        if cur.rowcount:
            print(f"  deleted {cur.rowcount:3} rows from {t}")
    for step in steps:
        con.execute(
            "DELETE FROM fetch_log WHERE year=2026 AND round=19 AND step=?",
            (step,),
        )
        print(f"  cleared fetch_log step: {step}")
    con.execute(
        "UPDATE sessions SET n_starters=NULL, expected_size=NULL "
        "WHERE year=2026 AND round=19"
    )
    print("  reset sessions.n_starters / expected_size to NULL")
    con.commit()

    # ---- verify
    print()
    print("=" * 74)
    print("AFTER")
    print("=" * 74)
    ok = True
    for t in ("results", "driver_numbers", "qualifying", "practice",
              "sprint", "sprint_qualifying"):
        n = con.execute(
            f"SELECT COUNT(*) FROM {t} WHERE year=2026 AND round=19"
        ).fetchone()[0]
        print(f"  {t:20} {n}{'   <-- still present!' if n else ''}")
        ok = ok and n == 0
    n_log = con.execute(
        "SELECT COUNT(*) FROM fetch_log WHERE year=2026 AND round=19"
    ).fetchone()[0]
    print(f"  fetch_log entries    {n_log}{'   <-- still present!' if n_log else ''}")
    ok = ok and n_log == 0
    s = con.execute(
        "SELECT n_starters, expected_size FROM sessions "
        "WHERE year=2026 AND round=19"
    ).fetchone()
    print(f"  sessions.n_starters  {s['n_starters']} "
          f"expected_size={s['expected_size']}")

    # ---- confirm the rest of the DB is untouched
    print()
    print("=" * 74)
    print("REST OF DATABASE UNTOUCHED")
    print("=" * 74)
    for t in ("results", "qualifying", "practice", "sessions", "fetch_log"):
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:14} {n} rows")
    per_year = con.execute(
        "SELECT year, COUNT(*) FROM results GROUP BY year ORDER BY year"
    ).fetchall()
    print("  results by year:", dict(per_year))

    print()
    if ok:
        print("PURGE OK - re-run the fetch to pick up the real result:")
        print("    python -m f1pred.fetch --years 2026")
        return 0
    print("PURGE INCOMPLETE")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
