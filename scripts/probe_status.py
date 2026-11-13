"""What exactly is Status for the rows my filter should have dropped?

fetch_race kept all 33 rows for 2026 R19, so `pd.isna(status)` must be
returning False for the placeholders. This prints the exact type and repr.

Run:  python scripts/probe_status.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.ERROR)

from f1pred import credentials  # noqa: E402

credentials.load()
import fastf1  # noqa: E402
import pandas as pd  # noqa: E402

fastf1.Cache.configure(cache_dir=str(Path("f1_cache")))

ses = fastf1.get_session(2026, 19, "R")
ses.load(laps=False, telemetry=False, weather=False, messages=False)
res = ses.results

print("columns:", list(res.columns))
print("Status dtype:", res["Status"].dtype)
print()

for abbr in ("FM1", "SC1", "MC1", "OCO", "HIR", "VER"):
    row = res[res["Abbreviation"] == abbr]
    if row.empty:
        print(f"{abbr}: not present")
        continue
    r = row.iloc[0]
    st = r.get("Status")
    pos = r.get("Position")
    team = r.get("TeamName")
    print(f"{abbr:4} Status={st!r:26} type={type(st).__name__:5} "
          f"pd.isna={pd.isna(st)!s:5} | Position={pos!r:8} "
          f"TeamName={team!r}")

print()
print("=" * 74)
print("Would each predicate drop it?")
print("=" * 74)
print(f"{'abbr':5} {'cur(finish&!status)':>20} {'team empty':>11} "
      f"{'num>100':>9} {'name None':>10}")
for abbr in ("FM1", "SC1", "MC1", "OCO", "HIR", "VER"):
    r = res[res["Abbreviation"] == abbr].iloc[0]
    finish = r.get("Position")
    st = r.get("Status")
    has_status = st is not None and not pd.isna(st)
    cur = (finish is None or pd.isna(finish)) and not has_status
    team = r.get("TeamName")
    team_empty = team is None or pd.isna(team) or str(team).strip() == ""
    num = r.get("DriverNumber")
    num_high = pd.notna(num) and float(num) > 100
    name = r.get("FullName")
    name_none = name is None or pd.isna(name)
    print(f"{abbr:5} {cur!s:>20} {team_empty!s:>11} {num_high!s:>9} "
          f"{name_none!s:>10}")

print()
print("=" * 74)
print("How many rows would EACH predicate drop? (target: 11 -> leaves 22)")
print("=" * 74)
finish_null = res["Position"].isna()
status_null = res["Status"].isna() if res["Status"].dtype != object else \
    res["Status"].apply(lambda v: v is None or pd.isna(v))
print(f"  Position isna                 : {int(finish_null.sum())}")
print(f"  Status isna                   : {int(status_null.sum())}")
print(f"  BOTH (current predicate)      : {int((finish_null & status_null).sum())}")
print(f"  FullName isna                 : "
      f"{int(res['FullName'].isna().sum())}")
print(f"  TeamName isna                 : "
      f"{int(res['TeamName'].isna().sum())}")
print(f"  DriverNumber > 100            : "
      f"{int((res['DriverNumber'].astype(float) > 100).sum())}")
print(f"  total rows                    : {len(res)}")

# the cleanest single predicate: FullName missing = FastF1 has no identity
dropped = res[res["FullName"].isna()]
print(f"\n  rows with FullName missing ({len(dropped)}):")
for _, r in dropped.iterrows():
    print(f"      {r['Abbreviation']:5} num={r['DriverNumber']} "
          f"Status={r['Status']!r} Position={r['Position']!r}")
kept = res[res["FullName"].notna()]
print(f"  rows kept: {len(kept)}")
print(f"  kept with a Position: {int(kept['Position'].notna().sum())}")
print(f"  kept without Position: {int(kept['Position'].isna().sum())}")
print(f"      -> "
      f"{list(kept[kept['Position'].isna()]['Abbreviation'])}")
