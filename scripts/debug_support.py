"""Probe why laps / practice Position are missing.

Run:  python scripts/debug_support.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import fastf1

Path("f1_cache").mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))
pd.set_option("display.width", 200)

sched = fastf1.get_event_schedule(2026, include_testing=False)
print("F1ApiSupport by round:")
print(sched[["RoundNumber", "EventName", "EventFormat", "F1ApiSupport"]].to_string(index=False))

for ident in ("FP1", "FP3", "Q", "R"):
    s = fastf1.get_session(2026, 1, ident)
    s.load(laps=True, telemetry=False, weather=False, messages=False)
    print(f"\n--- 2026 R1 {ident} ---")
    print("  f1_api_support:", s.f1_api_support)
    print("  hasattr _laps:", hasattr(s, "_laps"),
          "| _laps is None:", getattr(s, "_laps", "MISSING") is None)
    print("  results Position notna:", int(s.results["Position"].notna().sum()), "/", len(s.results))
    try:
        print("  s.laps ->", len(s.laps), "rows")
    except Exception as exc:
        print("  s.laps FAILED:", type(exc).__name__, str(exc)[:120])
    # practice-like results are computed here:
    try:
        plr = s._calculate_practice_like_session_results()
        print("  practice-like returns:", type(plr).__name__ if plr is not None else None)
        print("  results Position notna after:", int(s.results["Position"].notna().sum()))
    except Exception as exc:
        print("  practice-like FAILED:", type(exc).__name__, str(exc)[:160])
