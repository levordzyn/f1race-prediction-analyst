"""Diagnose (a) FastF1's Ergast rate limit and (b) duplicate qualifying positions.

Run:  python scripts/diagnose_q.py
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

# ---- (a) where does "500 calls/h" live in FastF1?
print("=" * 78)
print("(a) FastF1 rate-limit implementation")
print("=" * 78)
root = Path(fastf1.__file__).parent
hits = []
for f in root.rglob("*.py"):
    try:
        txt = f.read_text(encoding="utf-8", errors="replace")
    except OSError:
        continue
    for i, line in enumerate(txt.splitlines(), 1):
        if "calls/h" in line or "RateLimitExceeded" in line:
            hits.append(f"{f.relative_to(root)}:{i}: {line.strip()}")
for h in sorted(set(hits))[:25]:
    print("  ", h)

# cache state
cache_files = list(Path("f1_cache").rglob("*"))
print(f"\n  f1_cache entries: {len([p for p in cache_files if p.is_file()])}")

# ---- (b) duplicate qualifying positions
print("\n" + "=" * 78)
print("(b) qualifying rows for races that failed validation")
print("=" * 78)

for year, rnd in ((2023, 10), (2024, 8), (2024, 15), (2024, 17)):
    print(f"\n--- {year} R{rnd} ---")
    try:
        ses = fastf1.get_session(year, rnd, "Q")
        ses.load(laps=False, telemetry=False, weather=False, messages=False)
        res = ses.results
    except Exception as exc:                       # noqa: BLE001
        print(f"   LOAD FAILED: {type(exc).__name__}: {exc}")
        continue

    print(f"   rows={len(res)}")
    cols = [c for c in ("Position", "Abbreviation", "DriverNumber", "Q1", "Q2", "Q3")
            if c in res]
    show = res[cols].copy()
    # flag duplicates in Position
    pos = pd.to_numeric(show["Position"], errors="coerce")
    dup = pos.duplicated(keep=False) & pos.notna()
    show["_DUP"] = dup
    show = show.sort_values("Position", na_position="last")
    print(show.to_string(index=False))
    d = sorted(set(pos[dup].dropna().astype(int)))
    if d:
        print(f"   >>> duplicate positions: {d}")
        for p in d:
            who = res.loc[pos == p, "Abbreviation"].tolist()
            print(f"       position {p} held by {who}")
    # are Q1/Q2/Q3 all NaT for the offenders?
    if d:
        for p in d:
            sub = res[pos == p]
            for _, r in sub.iterrows():
                print(f"       {r['Abbreviation']}: Q1={r.get('Q1')} "
                      f"Q2={r.get('Q2')} Q3={r.get('Q3')} "
                      f"ClassifiedPosition={r.get('ClassifiedPosition')!r}")
