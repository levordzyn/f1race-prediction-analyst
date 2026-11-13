"""Are fastf1.Cache.enable_cache() and Cache.configure() equivalent in 3.9.0?

f1_baseline.py (Appendix A) calls enable_cache(path) positionally. It is
deprecated in 3.9.0 with a FutureWarning promising removal. The rest of the
project uses configure(cache_dir=...).

Before replacing it we must know that configure() actually ENABLES the cache
for an existing directory - if it only sets config without activating, every
fetch would re-download and blow the 500 calls/hour budget.

Run:  python scripts/check_cache_api.py
"""
from __future__ import annotations

import inspect
import warnings
from pathlib import Path

import fastf1

print("=" * 78)
print("SIGNATURES")
print("=" * 78)
for name in ("enable_cache", "configure"):
    fn = getattr(fastf1.Cache, name, None)
    if fn is None:
        print(f"  {name}: NOT PRESENT")
        continue
    print(f"  {name}{inspect.signature(fn)}")

print()
print("=" * 78)
print("SOURCE OF enable_cache (is it a thin wrapper?)")
print("=" * 78)
src = inspect.getsource(fastf1.Cache.enable_cache)
print(src)

print("=" * 78)
print("DOES enable_cache JUST CALL configure?")
print("=" * 78)
print("  mentions configure():", "configure" in src)
print("  mentions warn       :", "warn" in src.lower())

print()
print("=" * 78)
print("DOES configure() ACTIVATE THE CACHE, OR ONLY SET CONFIG?")
print("=" * 78)
cfg_src = inspect.getsource(fastf1.Cache.configure)
# the activation happens by assigning the cache directory into a class attr
for line in cfg_src.splitlines():
    if "cache_dir" in line and ("self" in line or "cls" in line or "=" in line):
        print(f"  {line.strip()}")

print()
print("=" * 78)
print("LIVE TEST: does configure(cache_dir=...) make an existing dir active?")
print("=" * 78)
cache_dir = Path("f1_cache")
print(f"  f1_cache exists : {cache_dir.exists()}")
print(f"  files inside    : "
      f"{len(list(cache_dir.rglob('*'))) if cache_dir.exists() else 0}")

# reset to a known state, then enable via each API and read back the class attr
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    fastf1.Cache.configure(cache_dir=str(cache_dir))
    print(f"  after configure()   -> Cache._cache_dir = "
          f"{getattr(fastf1.Cache, '_cache_dir', getattr(fastf1.Cache, 'CACHE_DIR', '<attr?>'))}")
    for x in w:
        print(f"      warning: {x.category.__name__}: {x.message}")

with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    fastf1.Cache.enable_cache(str(cache_dir))
    print(f"  after enable_cache() -> Cache._cache_dir = "
          f"{getattr(fastf1.Cache, '_cache_dir', getattr(fastf1.Cache, 'CACHE_DIR', '<attr?>'))}")
    for x in w:
        print(f"      warning: {x.category.__name__}: {x.message}")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
print("  If both APIs land the cache on the same attribute, configure() is a")
print("  safe drop-in replacement and removes the FutureWarning.")
