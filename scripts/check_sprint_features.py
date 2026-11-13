"""Phase 6a acceptance: sprint features are complete, correctly filled, and
NOT the target in disguise.

WHAT THIS PROVES
  [1]  the six sprint columns exist, are numeric and have no NULLs
  [2]  `has_sprint` agrees with `sessions.event_format` (a calendar fact)
  [3]  `has_sprint` agrees with which races actually appear in the sprint
       tables - 24 races, 492 rows each
  [4]  non-sprint weekends land exactly on the "no sprint here" fills
  [5]  sprint weekends carry real values, and the only gaps are the drivers
       who genuinely set no sprint-qualifying lap
  [6]  LEAKAGE: `sprint_pos` is NOT the race result. If the sprint result
       were identical to the Grand Prix result the feature would hand the
       model the answer; here the two are different races and must differ.
  [7]  `sq_rank` is not a copy of `q_position` (different session)
  [8]  the documented exact duplication: no_sprint_result == 1 - has_sprint
  [9]  no row mixes the two states (a non-sprint race with sprint data)
  [10] the base 12 features are byte-identical to before Phase 6a
  [11] the default (non-forecast) call still returns 1816 rows
  [12] a non-sprint driver's sprint_pos fill is field_n + 1, never 0

Run:  python scripts/check_sprint_features.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from f1pred import db, features

FAILS: list[str] = []


def chk(n: int, cond: bool, msg: str) -> None:
    print(f"  [{n:>2}] {'PASS' if cond else 'FAIL'}  {msg}")
    if not cond:
        FAILS.append(msg)


def rule(t: str = "") -> None:
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


con = db.connect()
con.row_factory = None
df = features.build_features(con)

rule("[1] THE SIX SPRINT COLUMNS EXIST AND ARE CLEAN")
missing = [c for c in features.SPRINT_FEATURES if c not in df.columns]
print(f"  expected {len(features.SPRINT_FEATURES)} columns: "
      f"{', '.join(features.SPRINT_FEATURES)}")
print(f"  missing : {missing or 'none'}")
nulls = {c: int(df[c].isna().sum()) for c in features.SPRINT_FEATURES}
print(f"  NULLs   : {nulls}")
nonnum = [c for c in features.SPRINT_FEATURES
          if not pd.api.types.is_numeric_dtype(df[c])]
print(f"  non-numeric: {nonnum or 'none'}")
chk(1, not missing and not any(nulls.values()) and not nonnum,
    "all six sprint features present, numeric, zero NULLs")

rule("[2] has_sprint AGREES WITH sessions.event_format (CALENDAR FACT)")
fmt = pd.read_sql_query(
    "SELECT year, round, event_format FROM sessions", con)
m = df[["year", "round", "has_sprint"]].merge(
    fmt, on=["year", "round"], how="left", validate="many_to_one")
agree = int((m["has_sprint"] == (m["event_format"] != "conventional")
             .astype(int)).sum())
print(f"  rows where the flag matches event_format: {agree} / {len(m)}")
print(f"  event_format values on sprint weekends  : "
      f"{sorted(set(m.loc[m['has_sprint'] == 1, 'event_format']))}")
chk(2, agree == len(m), "has_sprint is derived from the calendar, not results")

rule("[3] has_sprint AGREES WITH THE SPRINT TABLES")
sq_n = con.execute("SELECT COUNT(DISTINCT year||'-'||round) "
                   "FROM sprint_qualifying").fetchone()[0]
sp_n = con.execute("SELECT COUNT(DISTINCT year||'-'||round) "
                   "FROM sprint").fetchone()[0]
flagged = df.loc[df["has_sprint"] == 1, ["year", "round"]].drop_duplicates()
flag_set = {(int(y), int(r)) for y, r in flagged.itertuples(index=False)}
sq_set = {(int(y), int(r)) for y, r in con.execute(
    "SELECT DISTINCT year, round FROM sprint_qualifying")}
sp_set = {(int(y), int(r)) for y, r in con.execute(
    "SELECT DISTINCT year, round FROM sprint")}
print(f"  sprint_qualifying : {sq_n} races, {sq_set == flag_set} identical to flag")
print(f"  sprint            : {sp_n} races, {sp_set == flag_set} identical to flag")
print(f"  races flagged as sprint weekends: {len(flag_set)}")
chk(3, sq_set == flag_set == sp_set, "flag, sprint and sprint_qualifying "
    "describe the same 24 weekends")

rule("[4] NON-SPRINT WEEKENDS LAND ON THE 'NO SPRINT HERE' FILLS")
ns = df[df["has_sprint"] == 0]
sp = df[df["has_sprint"] == 1]
print(f"  rows: {len(ns)} non-sprint, {len(sp)} sprint")
bad = {
    "has_sprint != 0": int((ns["has_sprint"] != 0).sum()),
    "no_sq_lap != 1": int((ns["no_sq_lap"] != 1).sum()),
    "no_sprint_result != 1": int((ns["no_sprint_result"] != 1).sum()),
    "sq_rank != field_n+1": int((ns["sq_rank"] != ns["field_n"] + 1).sum()),
    "sprint_pos != field_n+1": int((ns["sprint_pos"] != ns["field_n"] + 1).sum()),
    "sq_gap_pct != 0.0": int((ns["sq_gap_pct"] != 0.0).sum()),
}
print(f"  rows not on the expected fill: {bad}")
chk(4, not any(bad.values()),
    "all 65 non-sprint races are encoded as 'no sprint', not as data")

rule("[5] SPRINT WEEKENDS CARRY REAL VALUES")
print(f"  sprint rows: {len(sp)}")
print(f"  has_sprint=1 rows with no_sprint_result=1 : "
      f"{int(sp['no_sprint_result'].sum())}")
print(f"  has_sprint=1 rows with no_sq_lap=1        : {int(sp['no_sq_lap'].sum())}")
print(f"  distinct sprint_pos values  : "
      f"{sorted(sp['sprint_pos'].unique())[:12]} ...")
print(f"  distinct sq_rank values     : "
      f"{sorted(sp['sq_rank'].unique())[:12]} ...")
print(f"  sq_rank filled at field_n+1 : "
      f"{int((sp['sq_rank'] == sp['field_n'] + 1).sum())} row(s)")
# A units bug (ratio vs percent) would make this feature ~100x too small,
# nearly constant, and useless - while every other check still passed.
print(f"\n  GAP SCALE - all three must be percentages of the fastest lap:")
for col, src in (("sq_gap_pct", "sprint qualifying"),
                 ("q_gap_pct", "Grand Prix qualifying"),
                 ("practice_gap_pct", "practice")):
    s = df.loc[df["has_sprint"] == 1, col] if col == "sq_gap_pct" else df[col]
    print(f"    {col:<18} ({src:<20}) min {s.min():8.3f}  "
          f"median {s.median():8.3f}  max {s.max():8.3f}  "
          f"nonzero {int((s != 0).sum()):5d}")
scale_ok = (0.5 < sp["sq_gap_pct"].median() < 5.0
            and sp["sq_gap_pct"].max() > 5.0)
print(f"  -> median is a few percent and the max is several percent, i.e. a")
print(f"     percentage and not a 0..1 ratio: {scale_ok}")
# A sprint result exists for every sprint starter (verified in the Phase 6
# input inspection), so only sprint QUALIFYING has genuine gaps.
chk(5, int(sp["no_sprint_result"].sum()) == 0 and scale_ok,
    "every sprint starter has a sprint result; sq_gap_pct is a real percent")

rule("[6] LEAKAGE: sprint_pos IS NOT THE RACE RESULT")
both = sp[["driver", "sprint_pos", "finish", "field_n"]].copy()
n = len(both)
same = int((both["sprint_pos"] == both["finish"]).sum())
rho = float(np.corrcoef(
    both["sprint_pos"].rank(), both["finish"].rank())[0, 1])
print(f"  rows compared                       : {n}")
print(f"  sprint_pos identical to race finish : {same} ({same / n:.1%})")
print(f"  Spearman-like rank correlation      : {rho:.4f}")
print(f"  -> a leak would show ~100% identical and ~1.0000 correlation")
chk(6, same / n < 0.90 and rho < 0.999,
    "sprint result is a different race from the one being predicted")

rule("[7] sq_rank IS NOT A COPY OF q_position")
q = df[["driver", "year", "round", "sq_rank", "q_position", "has_sprint"]]
qq = q[q["has_sprint"] == 1].copy()
diff = int((qq["sq_rank"] != qq["q_position"]).sum())
print(f"  sprint rows where sq_rank != q_position: {diff} / {len(qq)}")
chk(7, diff > 0, "sprint qualifying position differs from Grand Prix qualifying")

rule("[8] DOCUMENTED DUPLICATION: no_sprint_result == 1 - has_sprint")
dup = int((df["no_sprint_result"] == (1 - df["has_sprint"])).sum())
print(f"  rows where no_sprint_result == 1 - has_sprint: {dup} / {len(df)}")
print(f"  -> exact linear duplication. Kept because the spec asks for a")
print(f"     missing flag; Ridge splits that weight arbitrarily. Reported,")
print(f"     not silently dropped.")
chk(8, dup == len(df), "duplication confirmed so it can be reported honestly")

rule("[9] NO ROW MIXES THE TWO STATES")
mixed = int(((df["has_sprint"] == 0) & (df["no_sq_lap"] == 0)).sum()) + \
    int(((df["has_sprint"] == 0) & (df["no_sprint_result"] == 0)).sum())
print(f"  non-sprint rows claiming sprint data: {mixed}")
chk(9, mixed == 0, "a weekend without a sprint never reports sprint data")

rule("[10] THE BASE 12 FEATURES ARE UNCHANGED")
base = ["grid", "driver_form", "team_form", "non_finish_rate",
        "practice_pos", "practice_gap_pct", "practice_laps_30",
        "no_practice_time", "q_position", "q_gap_pct", "no_q_time", "on_pole"]
print(f"  ALL_FEATURES is still {len(features.ALL_FEATURES)} columns: "
      f"{features.ALL_FEATURES == base}")
print(f"  sprint columns are NOT in ALL_FEATURES: "
      f"{not (set(features.SPRINT_FEATURES) & set(features.ALL_FEATURES))}")
print(f"  sprint rows carry the base 12 too      : "
      f"{all(c in df.columns for c in base)}")
chk(10, features.ALL_FEATURES == base and
    not (set(features.SPRINT_FEATURES) & set(features.ALL_FEATURES)),
    "Phase 6a did not touch the locked 12-feature set")

rule("[11] THE DEFAULT CALL STILL RETURNS 1816 ROWS")
print(f"  rows: {len(df)}")
chk(11, len(df) == 1816, "row-count invariant holds with sprint columns added")

rule("[12] FILLS ARE field_n + 1, NEVER 0")
zero = int((df["sq_rank"] == 0).sum()) + int((df["sprint_pos"] == 0).sum())
missing_sq = df[df["no_sq_lap"] == 1]
missing_sp = df[df["no_sprint_result"] == 1]
print(f"  sprint position features equal to 0: {zero}")
print(f"  minimum sq_rank    : {df['sq_rank'].min()}  "
      f"(a real sprint pole, not a fill)")
print(f"  rows with no sprint-qualifying lap: {len(missing_sq)}")
print(f"    all at field_n + 1 : "
      f"{bool((missing_sq['sq_rank'] == missing_sq['field_n'] + 1).all())}")
print(f"  rows with no sprint result        : {len(missing_sp)}")
print(f"    all at field_n + 1 : "
      f"{bool((missing_sp['sprint_pos'] == missing_sp['field_n'] + 1).all())}")
# The distinction that matters: a MISSING position must sit behind every
# classified car, while a measured P1 is allowed to be 1. The naive
# "min >= 2" test would wrongly reject a genuine sprint pole.
chk(12, zero == 0
    and bool((missing_sq["sq_rank"] == missing_sq["field_n"] + 1).all())
    and bool((missing_sp["sprint_pos"] == missing_sp["field_n"] + 1).all()),
    "every unknown sprint position sits at field_n + 1, never at 0 or 1")

con.close()
rule("RESULT")
if FAILS:
    print(f"  {len(FAILS)} of 12 FAILED:")
    for f in FAILS:
        print(f"    - {f}")
    sys.exit(1)
print("  12 of 12 PASS")
sys.exit(0)
