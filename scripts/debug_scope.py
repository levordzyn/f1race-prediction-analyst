"""Is missing lap timing 2026-specific or global? Also check F1 account auth path.

Run:  python scripts/debug_scope.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import fastf1

Path("f1_cache").mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))
logging.basicConfig(level=logging.WARNING)


def try_laps(year, rnd, ident):
    try:
        s = fastf1.get_session(year, rnd, ident)
        s.load(laps=True, telemetry=False, weather=False, messages=False)
    except Exception as exc:
        return f"load raised {type(exc).__name__}: {exc}"
    has = hasattr(s, "_laps")
    n = "n/a"
    if has:
        try:
            n = len(s.laps)
        except Exception as exc:
            n = f"err {type(exc).__name__}"
    return f"_laps set={has} rows={n} | results Pos notna={int(s.results['Position'].notna().sum())}/{len(s.results)}"


for year, rnd, ident in [
    (2025, 1, "R"),
    (2025, 1, "Q"),
    (2025, 1, "FP3"),
    (2024, 1, "R"),
    (2024, 1, "FP3"),
    (2026, 1, "R"),
    (2026, 1, "FP3"),
]:
    print(f"{year} R{rnd} {ident:<4} -> {try_laps(year, rnd, ident)}")

# Does FastF1 look for credentials anywhere?
import fastf1.tokens as tokens  # type: ignore
print("\ntokens module file:", tokens.__file__)
src = Path(tokens.__file__).read_text(encoding="utf-8", errors="replace")
for line in src.splitlines():
    if "environ" in line or "getenv" in line:
        print("  ENV:", line.strip())
