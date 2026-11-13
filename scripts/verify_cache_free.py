"""Does a cache HIT consume FastF1 rate-limit budget?

FastF1 patches lim.limit() into requests.Session.send(). requests_cache's
CachedSession also overrides send(). Which wins decides whether re-running
the fetch over cached data is cheap or burns the same 500/hour budget.

Run:  python scripts/verify_cache_free.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fastf1

Path("f1_cache").mkdir(exist_ok=True)
fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

sess = fastf1.Cache._requests_session_cached
print("session class      :", type(sess).__name__)
print("MRO                :", " -> ".join(c.__name__ for c in type(sess).__mro__[:6]))

# instrument: count real network sends vs limit() calls
real_send = type(sess).send
counts = {"send": 0}


def counting_send(self, request, **kwargs):
    counts["send"] += 1
    return real_send(self, request, **kwargs)


# count limit() invocations separately
from fastf1.req import _SessionWithRateLimiting

lim_calls = {"n": 0}
orig_limit = None


def instrument_limits():
    global orig_limit
    # find the limiters live on the session and wrap them
    for pattern, limiters in getattr(type(sess), "_RATE_LIMITS", {}).items():
        for lim in limiters:
            if orig_limit is None:
                orig_limit = lim.limit

            def make(l):
                def wrapped():
                    lim_calls["n"] += 1
                    return orig_limit()
                return wrapped

            lim.limit = make(lim)


instrument_limits()
type(sess).send = counting_send

YEAR, RND = 2023, 1  # Bahrain 2023, fully cached from earlier runs


def load():
    ses = fastf1.get_session(YEAR, RND, "Q")
    ses.load(laps=False, telemetry=False, weather=False, messages=False)
    return len(ses.results)


counts["send"] = 0
lim_calls["n"] = 0
n = load()
print(f"\nload #1 -> {n} results | send() called {counts['send']}x, limit() {lim_calls['n']}x")

counts["send"] = 0
lim_calls["n"] = 0
n2 = load()
print(f"load #2 (should be cached) -> {n2} results | send() {counts['send']}x, limit() {lim_calls['n']}x")

print("\nVERDICT:")
if counts["send"] == 0 and lim_calls["n"] == 0:
    print("  cache hits consume NO rate budget -> re-running is cheap")
elif lim_calls["n"] > 0 and counts["send"] == 0:
    print("  cache hits DO consume rate budget (limit() called, no network)")
else:
    print(f"  cache hits hit the network ({counts['send']} sends) - cache not effective")
