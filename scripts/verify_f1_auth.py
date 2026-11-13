"""Does FastF1 now authenticate, and does lap data become available?

This is the test that matters: previously `Failed to load timing data!` meant
`session.laps` raised DataNotLoadedError, which is why 2025 R6 (Miami) had no
qualifying lap times.

Run:  python scripts/verify_f1_auth.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from f1pred import credentials  # noqa: E402

ok = credentials.load()
print(f"\ncredentials loaded: {ok} (values not shown)\n")

import fastf1  # noqa: E402

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

# Capture auth warnings without letting them hide the result
auth_warnings: list[str] = []


class _Capture(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "authenticate" in msg.lower() or "credentials" in msg.lower():
            auth_warnings.append(msg)


logging.getLogger("transport").addHandler(_Capture())
logging.getLogger("tokens").addHandler(_Capture())

YEAR, RND = 2025, 6  # Miami - the race where Q1/Q2/Q3 were all NaT

print("=" * 74)
print(f"{YEAR} R{RND} Miami - qualifying lap times")
print("=" * 74)

ses = fastf1.get_session(YEAR, RND, "Q")
ses.load(laps=True, telemetry=False, weather=False, messages=False)

print("auth warnings seen:", len(auth_warnings))
for w in auth_warnings[:3]:
    print("   ", w)

res = ses.results
print(f"\nresults rows: {len(res)}")
print(f"Q1 not-null: {int(res['Q1'].notna().sum())}  "
      f"Q2: {int(res['Q2'].notna().sum())}  "
      f"Q3: {int(res['Q3'].notna().sum())}")

try:
    laps = ses.laps
    n_laps = len(laps)
    print(f"\nlaps: {n_laps} rows")
    if n_laps:
        lt = laps["LapTime"]
        print(f"LapTime not-null: {int(lt.notna().sum())}")
        if lt.notna().any():
            work = laps[lt.notna()].copy()
            if "PitOutLap" in work.columns:
                n0 = len(work)
                work = work[~work["PitOutLap"].fillna(False).astype(bool)]
                print(f"dropped {n0 - len(work)} pit-out laps")
            work["s"] = work["LapTime"].dt.total_seconds()
            best = work.groupby("Driver")["s"].min().sort_values()
            print(f"\ndrivers with a best lap: {len(best)}")
            off = dict(zip(res["Abbreviation"], res["Position"]))
            print("\n pace driver  best_s  official  agree")
            print("-" * 46)
            bad = 0
            for rank, (d, t) in enumerate(best.items(), start=1):
                p = off.get(d)
                good = p is not None and int(p) == rank
                bad += 0 if good else 1
                print(f"  {rank:2}  {d:4}  {t:7.3f}  {p!s:>6}    "
                      f"{'OK' if good else 'DIFF'}")
            print(f"\nmismatches: {bad} of {len(best)}")
except Exception as exc:  # noqa: BLE001
    print("laps unavailable:", type(exc).__name__, exc)

print("\n" + "=" * 74)
print("VERDICT")
print("=" * 74)
no_auth = any("without authentication" in w.lower() for w in auth_warnings)
if no_auth:
    print("STILL UNAUTHENTICATED - check credentials.env")
else:
    print("authenticated - no 'continuing without authentication' warning")
