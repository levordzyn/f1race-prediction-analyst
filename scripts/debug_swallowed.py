"""Show the SWALLOWED exception behind 'Failed to load timing data!'.

Run:  python scripts/debug_swallowed.py
"""
from __future__ import annotations

import logging
from pathlib import Path

import fastf1

Path("f1_cache").mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

logging.basicConfig(level=logging.DEBUG)
# keep it readable: demote the noisy http libs
for noisy in ("urllib3", "charset_normalizer", "matplotlib"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

s = fastf1.get_session(2026, 1, "FP3")
try:
    s.load(laps=True, telemetry=False, weather=False, messages=False)
except Exception as exc:
    print("load raised:", type(exc).__name__, exc)

print("\n--- lap-timing related log records above ---")
print("has _laps:", hasattr(s, "_laps"))
