"""Why does 2026 R19 have 32 rows with no grid/finish?

Hypothesis: the Mexico City GP is scheduled for TODAY (2026-11-01) and has not
run, so FastF1 returns an entry list (22 real cars) plus placeholder codes
(FM*/MC*/SC*) with null Position/GridPosition - and we stored it as if it were
real race data.

This script asks FastF1 directly and prints the RAW rows, plus the current UTC
time, plus a known-good race (2026 R18) for comparison.

Run:  python scripts/inspect_r19_source.py
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.ERROR)

from f1pred import credentials  # noqa: E402

credentials.load()
import fastf1  # noqa: E402
import pandas as pd  # noqa: E402

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 60)

print("=" * 74)
print("NOW")
print("=" * 74)
print(f"  UTC now : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")


def show(year: int, rnd: int, ident: str) -> None:
    print()
    print("=" * 74)
    print(f"{year} R{rnd}  identifier={ident}")
    print("=" * 74)
    try:
        ses = fastf1.get_session(year, rnd, ident)
        ses.load(laps=False, telemetry=False, weather=False, messages=False)
    except Exception as exc:  # noqa: BLE001
        print(f"  load FAILED: {type(exc).__name__}: {exc}")
        return
    res = ses.results
    print(f"  rows: {len(res)}")
    if len(res) == 0:
        print("  (empty)")
        return
    cols = [c for c in ("Position", "GridPosition", "Abbreviation",
                        "DriverNumber", "FullName", "TeamName", "Status")
            if c in res.columns]
    df = res[cols].copy()
    df = df.sort_values("Position", na_position="last")
    print(df.to_string(index=False))

    pos_null = int(res["Position"].isna().sum()) if "Position" in res else -1
    print(f"\n  Position null: {pos_null}/{len(res)}")
    if "GridPosition" in res:
        print(f"  GridPosition null: {int(res['GridPosition'].isna().sum())}/{len(res)}")
    # rows whose abbreviation looks like a placeholder
    if "Abbreviation" in res:
        weird = [str(a) for a in res["Abbreviation"]
                 if isinstance(a, str) and len(a) == 3
                 and a[1:].isdigit()]
        print(f"  placeholder-looking abbreviations: {weird}")


# the suspect race, and a known-good control from the same season
show(2026, 19, "R")
show(2026, 19, "Q")
show(2026, 18, "R")

print()
print("=" * 74)
print("WHAT OUR DB STORED FOR 2026 R19 vs R18")
print("=" * 74)
import sqlite3  # noqa: E402

con = sqlite3.connect("f1.db")
for rnd in (18, 19):
    rows = con.execute(
        "SELECT COUNT(*), SUM(finish IS NULL), SUM(grid IS NULL) "
        "FROM results WHERE year=2026 AND round=?", (rnd,)
    ).fetchone()
    print(f"  R{rnd}: rows={rows[0]}  finish_null={rows[1]}  "
          f"grid_null={rows[2]}")
