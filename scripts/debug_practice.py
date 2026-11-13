"""Debug: practice Position NaN, qualifying row count, laps not loaded.

Run:  python scripts/debug_practice.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import fastf1

Path("f1_cache").mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

pd.set_option("display.width", 200)


def dbg(year: int, rnd: int, ident: str) -> None:
    print(f"\n########## {year} R{rnd} '{ident}' ##########")
    s = fastf1.get_session(year, rnd, ident)
    s.load(laps=True, telemetry=False, weather=False, messages=False)
    print("loaded attrs:", [a for a in ("_laps", "_results", "_weather", "_messages") if hasattr(s, a) and getattr(s, a) is not None])
    r = s.results
    print("results rows:", len(r))
    print("Position notna:", int(r["Position"].notna().sum()) if "Position" in r else "n/a")
    show = [c for c in ["Position", "ClassifiedPosition", "Abbreviation", "TeamName", "Q1", "Q2", "Q3", "Time", "Status", "Laps"] if c in r]
    print(r[show].to_string(index=False))

    try:
        laps = s.laps
        print("LAPS rows:", len(laps))
        print("laps cols:", list(laps.columns))
        cnt = laps.groupby("Abbreviation").size().sort_values(ascending=False)
        print("laps per driver head:", cnt.head(3).to_dict(), "| n drivers:", cnt.size)
        print("LapNumber range:", laps["LapNumber"].min(), laps["LapNumber"].max())
        print("LapTime notna:", int(laps["LapTime"].notna().sum()))
        best = laps.dropna(subset=["LapTime"]).groupby("Abbreviation")["LapTime"].min().sort_values()
        print("best laps per driver (first 3):\n", best.head(3))
    except Exception as exc:
        print("LAPS FAILED:", type(exc).__name__, exc)


dbg(2026, 1, "FP3")
dbg(2026, 1, "Q")
dbg(2026, 1, "R")
