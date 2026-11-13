"""VERIFY FastF1 sprint/qualifying session identifiers + result fields.

Spec 5 says identifiers such as FP1/FP2/FP3/Q/SQ/S/R are [VERIFY] - this
prints what the installed FastF1 3.9.0 actually accepts.

Run:  python scripts/verify_identifiers.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import fastf1

Path("f1_cache").mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))
pd.set_option("display.width", 240)

# FastF1's own registry of valid identifiers, if it exposes one
print("=== FastF1 supported session identifiers ===")
for attr in ("_SUPPORTED_IDENTIFIERS", "SUPPORTED_SESSIONS", "_SESSION_TYPES"):
    if hasattr(fastf1, attr):
        print(f"  {attr} = {getattr(fastf1, attr)}")
try:
    from fastf1.core import Session as _S
    for attr in ("_RACE_LIKE_SESSIONS", "_QUALI_LIKE_SESSIONS", "_PRACTICE_LIKE_SESSIONS"):
        if hasattr(_S, attr):
            print(f"  Session.{attr} = {getattr(_S, attr)}")
except Exception as exc:                       # noqa: BLE001
    print("  introspection failed:", exc)

CANDIDATES = ["FP1", "FP2", "FP3", "Q", "SQ", "SS", "S", "R",
              "Practice 1", "Practice 3", "Qualifying",
              "Sprint Qualifying", "Sprint Shootout", "Sprint", "Race"]

# 2024 R5 China = sprint_shootout format (has Sprint Shootout + Sprint)
# 2026 R2 China = sprint_qualifying format
for label, year, rnd in (("2024 R5 China (sprint_shootout)", 2024, 5),
                         ("2026 R2 China (sprint_qualifying)", 2026, 2),
                         ("2026 R1 Australia (conventional)", 2026, 1)):
    print(f"\n=== {label} ===")
    sched = fastf1.get_event_schedule(year, include_testing=False)
    row = sched[sched["RoundNumber"] == rnd].iloc[0]
    print("  format:", row["EventFormat"])
    slots = [str(row[f"Session{i}"]) for i in range(1, 6)
             if f"Session{i}" in row and pd.notna(row[f"Session{i}"])]
    print("  slots :", slots)

    for ident in CANDIDATES:
        try:
            ses = fastf1.get_session(year, rnd, ident)
        except Exception as exc:               # noqa: BLE001
            print(f"    {ident:<20} REJECTED  {type(exc).__name__}")
            continue
        resolved = getattr(ses, "name", "?")
        ok = "OK " if resolved in slots or resolved == ident else "~  "
        print(f"    {ident:<20} {ok} resolves to session.name={resolved!r}")

# result fields for a sprint + sprint qualifying
print("\n=== sprint / sprint-qualifying result fields (2026 R2) ===")
for ident in ("SQ", "Sprint Qualifying", "Sprint", "S"):
    try:
        ses = fastf1.get_session(2026, 2, ident)
        ses.load(laps=False, telemetry=False, weather=False, messages=False)
        res = ses.results
        print(f"\n  {ident!r} -> session.name={ses.name!r}, rows={len(res)}")
        print("    columns:", list(res.columns))
        cols = [c for c in ("Position", "Abbreviation", "DriverNumber",
                            "GridPosition", "Q1", "Q2", "Q3", "Time",
                            "Status", "Points") if c in res]
        print(res[cols].head(6).to_string(index=False))
        break
    except Exception as exc:                   # noqa: BLE001
        print(f"  {ident!r} failed: {type(exc).__name__}: {exc}")
