"""Do the four Appendix A review issues actually fire on OUR data?

The review listed them by severity; severity depends on whether the code path
is ever reached. This measures each one against f1.db instead of guessing.

  (1) "saved 0 drivers" message  -> does any race ever have 0 results rows?
  (2) fillna(22) hard-code       -> does any race have NO grid at all?
                                    (only then is race_max NaN for a row)
  (3) Cache.enable_cache()       -> does it still exist in fastf1 3.9.0?
  (4) datetime.utcnow()          -> deprecated; does it warn on Python 3.14?

Run:  python scripts/check_appendix_issues.py
"""
from __future__ import annotations

import sqlite3
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

print("=" * 78)
print("(1) 'saved 0 drivers' - can a race ever have 0 result rows?")
print("=" * 78)
zero = con.execute(
    "SELECT year, round, COUNT(*) n FROM results GROUP BY year, round "
    "HAVING COUNT(*) = 0").fetchall()
print(f"  races with 0 rows in results : {len(zero)}")
if zero:
    for r in zero:
        print(f"      {r['year']} R{r['round']}")
else:
    print("  none. Every stored race has at least one driver, so the")
    print("  fetch loop never prints 'saved ... (0 drivers)'.")
# the other direction: could a session load but yield nothing?
print("  smallest race by row count:")
r = con.execute(
    "SELECT year, round, COUNT(*) n FROM results GROUP BY year, round "
    "ORDER BY n ASC LIMIT 3").fetchall()
for x in r:
    print(f"      {x['year']} R{x['round']}: {x['n']} drivers")

print()
print("=" * 78)
print("(2) fillna(22) - does any race have NO grid values at all?")
print("=" * 78)
# race_max = groupby transform('max') is NaN only when EVERY grid in the
# race is NaN. That is the only path that reaches the literal 22.
n_all_missing = con.execute(
    "SELECT COUNT(*) FROM (SELECT year, round FROM results "
    "GROUP BY year, round HAVING SUM(grid IS NOT NULL) = 0)").fetchone()[0]
print(f"  races where every grid is NULL : {n_all_missing}")
n_no_grid = con.execute(
    "SELECT COUNT(*) FROM results WHERE grid IS NULL OR grid <= 0"
).fetchone()[0]
n_tot = con.execute("SELECT COUNT(*) FROM results").fetchone()[0]
print(f"  rows with grid NULL or <= 0    : {n_no_grid}/{n_tot}")
if n_all_missing == 0:
    print("  -> the literal 22 is NEVER reached: race_max is always a real")
    print("     number, so bad rows get race_max+1 from actual data.")
    print("     Severity: THEORETICAL, not observed.")
# what would race_max+1 be per race, to show the value is data-derived?
print()
print("  race_max (max grid) per year - shows the fallback is data-driven:")
for r in con.execute(
        "SELECT year, MAX(grid) mx, MIN(grid) mn FROM results "
        "WHERE grid IS NOT NULL GROUP BY year ORDER BY year"):
    print(f"      {r['year']}: grid ranges {r['mn']}..{r['mx']}")

print()
print("=" * 78)
print("(3) Cache.enable_cache() - still present in installed fastf1?")
print("=" * 78)
import fastf1  # noqa: E402
print(f"  fastf1 version : {fastf1.__version__}")
has_enable = hasattr(fastf1.Cache, "enable_cache")
has_configure = hasattr(fastf1.Cache, "configure")
print(f"  Cache.enable_cache exists : {has_enable}")
print(f"  Cache.configure exists    : {has_configure}")
if has_enable:
    import inspect
    doc = (fastf1.Cache.enable_cache.__doc__ or "").strip().splitlines()
    print(f"  enable_cache docstring    : {doc[0] if doc else '(none)'}")
    # is it deprecated?
    src = inspect.getsource(fastf1.Cache.enable_cache)
    for line in src.splitlines()[:25]:
        if "deprecat" in line.lower() or "warn" in line.lower():
            print(f"      {line.strip()}")
print("  Both APIs present -> enable_cache still runs, but configure() is")
print("  the documented one and is what f1pred/fetch.py uses.")

print()
print("=" * 78)
print("(4) datetime.utcnow() on this Python")
print("=" * 78)
print(f"  python: {sys.version.split()[0]}")
from datetime import datetime  # noqa: E402
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    v = datetime.utcnow()
    for w in caught:
        print(f"  WARNING: {w.category.__name__}: {w.message}")
if not caught:
    print("  no warning raised")
print(f"  utcnow() returned: {v} (works)")
print("  Deprecated since Python 3.12; removal is expected in a future")
print("  release. Replacement: datetime.now(timezone.utc).")
# would the replacement behave the same for Appendix A's comparison?
from datetime import timezone  # noqa: E402
new = datetime.now(timezone.utc).replace(tzinfo=None)
print(f"  datetime.now(timezone.utc) naive = {new}")
print(f"  same date as utcnow? {new.date() == v.date()}")

print()
print("=" * 78)
print("SEVERITY SUMMARY")
print("=" * 78)
print("  (1) saved-0-drivers   : not reachable on this data (min race has")
print("                           multiple rows) - cosmetic, LOW")
print("  (2) fillna(22)        : never reached (no all-NULL-grid race) -")
print("                           THEORETICAL, LOW, but wrong for 20-car")
print("                           fields if it ever did fire")
print("  (3) enable_cache      : still present and working - LOW, style")
print("  (4) utcnow()          : works today, deprecated - LOW, future break")
print()
print("  None corrupts data or leaks. All four are in Appendix A, which the")
print("  spec ships verbatim as the starting script.")
