"""Verify f1pred/features.py: shape, completeness, and above all NO LEAKAGE.

The leakage check is an INDEPENDENT recomputation: driver_form, team_form and
non_finish_rate are recalculated from raw SQL, taking only races strictly
before the row's own race, and compared against what build_features produced.
If any row's form had peeked at its own race's result the two would differ.

Checks
  1. 1816 rows, one per starter per race;
  2. one row per (year, round, driver);
  3. all 12 features present;
  4. no NULLs in any feature;
  5. every feature is numeric;
  6. feature groups cover all 12 exactly once;
  7. driver_form matches an independent past-races-only recomputation;
  8. non_finish_rate matches an independent past-races-only recomputation;
  9. team_form matches an independent past-races-only recomputation
     (windowed over the previous 5 RACES, not the previous 5 driver rows);
 10. positive control: a deliberately leaky form IS caught by that same
     comparison, so checks 7-9 are not vacuously passing;
 11. pit-lane grid fill applies to exactly the 5 known rows;
 12. each of those 5 was filled with field_n + 1;
 13. on_pole agrees with q_position == 1 on every row;
 14. exactly 89 pole-sitters, one per race.

Run:  python scripts/check_features.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, features  # noqa: E402

con = db.connect()
con.row_factory = sqlite3.Row
df = features.build_features(con)

ok = True


def chk(n, cond, label, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  [{n}] {label:<56} {'PASS' if cond else 'FAIL'}{detail}")


print("=" * 78)
print("SHAPE AND COMPLETENESS")
print("=" * 78)
chk(1, len(df) == 1816, "1816 rows", f" ({len(df)})")
chk(2, not df.duplicated(["year", "round", "driver"]).any(),
    "one row per (year, round, driver)")

missing = [c for c in features.ALL_FEATURES if c not in df.columns]
chk(3, not missing, "all 12 features present", f" missing={missing}")

nulls = {c: int(df[c].isna().sum()) for c in features.ALL_FEATURES}
chk(4, all(v == 0 for v in nulls.values()),
    "no NULLs in any feature",
    " " + str({k: v for k, v in nulls.items() if v}))

nonnum = [c for c in features.ALL_FEATURES
          if not pd.api.types.is_numeric_dtype(df[c])]
chk(5, not nonnum, "every feature is numeric", f" {nonnum}")

seen = [c for g in features.FEATURE_GROUPS.values() for c in g]
chk(6, sorted(seen) == sorted(features.ALL_FEATURES)
    and len(seen) == len(set(seen)) == 12,
    "groups cover all 12 features exactly once", f" ({len(seen)})")

# ---------------------------------------------------------------- leakage --
print()
print("=" * 78)
print("LEAKAGE: independent recomputation from raw SQL")
print("=" * 78)


def race_order():
    """{(year, round): chronological index 1..89} from raw results."""
    rows = con.execute(
        "SELECT DISTINCT year, round FROM results ORDER BY year, round"
    ).fetchall()
    return {(r["year"], r["round"]): i + 1 for i, r in enumerate(rows)}


ORDER = race_order()
WINDOW = features.FORM_WINDOW


def prior(driver, cur_idx):
    """Races strictly before cur_idx for this driver -> list of finishes."""
    rows = con.execute(
        "SELECT year, round, finish FROM results WHERE driver=? ORDER BY year, round",
        (driver,)).fetchall()
    return [r["finish"] for r in rows if ORDER[(r["year"], r["round"])] < cur_idx]


def prior_nonfinish(driver, cur_idx):
    rows = con.execute(
        "SELECT rs.year, rs.round, rs.status FROM race_status rs "
        "WHERE rs.driver=? ORDER BY rs.year, rs.round", (driver,)).fetchall()
    out = []
    for r in rows:
        if ORDER[(r["year"], r["round"])] < cur_idx:
            out.append(0 if r["status"] in features.FINISHING_STATUSES else 1)
    return out


def prior_team(team, cur_idx):
    """Team-race mean finishes in races strictly before cur_idx.

    Must collapse to ONE value per race first: a team has two drivers per race,
    so the window for "recent team form" is the previous 5 RACES (5 team-race
    means), not the previous 5 driver rows (~2.5 races). Taking the last 5
    driver rows was the bug in an earlier version of this check.
    """
    rows = con.execute(
        "SELECT year, round, finish FROM results WHERE team=? "
        "ORDER BY year, round", (team,)).fetchall()
    per_race: dict[int, list[float]] = {}
    for r in rows:
        idx = ORDER[(r["year"], r["round"])]
        if idx < cur_idx:
            per_race.setdefault(idx, []).append(r["finish"])
    return [sum(v) / len(v) for _, v in sorted(per_race.items())]


# --- driver_form -----------------------------------------------------------
bad_d, checked_d, nohist_d = [], 0, 0
for row in df.itertuples():
    idx = ORDER[(row.year, row.round)]
    hist = prior(row.driver, idx)
    if not hist:
        # debut: build_features fills mid-field from THIS race's field size
        nohist_d += 1
        expect = (row.field_n + 1) / 2.0
    else:
        expect = sum(hist[-WINDOW:]) / len(hist[-WINDOW:])
    checked_d += 1
    if abs(float(row.driver_form) - expect) > 1e-9:
        bad_d.append((row.year, row.round, row.driver,
                      float(row.driver_form), expect, len(hist)))
chk(7, not bad_d,
    f"driver_form = mean of PREVIOUS {WINDOW} races (all {checked_d} rows)",
    f" ({len(bad_d)} wrong, {nohist_d} debut rows)")
for b in bad_d[:6]:
    print(f"        {b}")

# --- non_finish_rate -------------------------------------------------------
bad_n = []
for row in df.itertuples():
    idx = ORDER[(row.year, row.round)]
    hist = prior_nonfinish(row.driver, idx)
    expect = (sum(hist[-WINDOW:]) / len(hist[-WINDOW:])) if hist else 0.0
    if abs(float(row.non_finish_rate) - expect) > 1e-9:
        bad_n.append((row.year, row.round, row.driver,
                      float(row.non_finish_rate), expect, len(hist)))
chk(8, not bad_n,
    f"non_finish_rate = rate over PREVIOUS {WINDOW} races "
    f"({len(df) - len(bad_n)}/{len(df)} rows)", f" ({len(bad_n)} wrong)")
for b in bad_n[:6]:
    print(f"        {b}")

# --- team_form -------------------------------------------------------------
bad_t = []
for row in df.itertuples():
    idx = ORDER[(row.year, row.round)]
    hist = prior_team(row.team, idx)
    expect = (sum(hist[-WINDOW:]) / len(hist[-WINDOW:])) if hist else None
    if expect is None:
        expect = (row.field_n + 1) / 2.0        # new team
    if abs(float(row.team_form) - expect) > 1e-9:
        bad_t.append((row.year, row.round, row.team,
                      float(row.team_form), expect, len(hist)))
chk(9, not bad_t,
    f"team_form = mean over team's PREVIOUS {WINDOW} races "
    f"({len(df) - len(bad_t)}/{len(df)} rows)", f" ({len(bad_t)} wrong)")
for b in bad_t[:6]:
    print(f"        {b}")

# --- positive control: does the check in [7] actually have power? ---------
# Check [7] matching all 1816 rows only means something if the past-only
# expectation can be told apart from a leaking one. So build the LEAKING
# version (form computed WITH this race included) and run it through the same
# comparison. It must mismatch on most rows; otherwise [7] would be vacuous.
#
# A genuine tie occurs whenever this race's finish equals the driver's finish
# WINDOW races ago (f_n == f_{n-5}) - both windows then hold the same multiset.
# Those are counted as coincidence, not leakage.
ctl_checked = ctl_bad = ties = 0
for row in df.itertuples():
    idx = ORDER[(row.year, row.round)]
    hist = prior(row.driver, idx)
    if not hist:
        continue
    expect = sum(hist[-WINDOW:]) / len(hist[-WINDOW:])   # past-only truth
    rows = con.execute(
        "SELECT year, round, finish FROM results WHERE driver=? "
        "ORDER BY year, round", (row.driver,)).fetchall()
    upto = [r["finish"] for r in rows
            if ORDER[(r["year"], r["round"])] <= idx]      # includes THIS race
    if len(upto) < WINDOW:
        continue
    cheat = sum(upto[-WINDOW:]) / WINDOW                  # deliberately leaky
    ctl_checked += 1
    if abs(cheat - expect) < 1e-9:
        ties += 1
    else:
        ctl_bad += 1

# [7] already proved stored == expect on every row. The control only has to
# show that expect and cheat are usually distinguishable.
chk(10, ctl_checked > 0 and ctl_bad > ctl_checked * 0.5,
    "positive control: a deliberately leaky form IS caught by the same test",
    f" ({ctl_bad}/{ctl_checked} leaky rows detected, {ties} coincidental ties)")

# -------------------------------------------------------------- grid fill --
print()
print("=" * 78)
print("CLEANED EDGE CASES")
print("=" * 78)
pit = df[(df["grid"] == df["field_n"] + 1)]
known_pit = {("2023", 13, "MAG"), ("2023", 15, "STR"), ("2023", 19, "STR"),
             ("2024", 20, "OCO"), ("2026", 19, "HIR")}
got_pit = {(str(r.year), int(r.round), r.driver) for r in pit.itertuples()}
# a genuine last-place qualifier on a 20-car grid sits at 20, not 21, so only
# rows that were 0/NULL before are field_n+1 when field_n+1 > max real grid
raw0 = con.execute(
    "SELECT year, round, driver FROM results WHERE grid IS NULL OR grid <= 0"
).fetchall()
raw0_set = {(str(r["year"]), int(r["round"]), r["driver"]) for r in raw0}
chk(11, raw0_set == known_pit,
    "the 5 pit-lane rows are exactly the known 5", f" ({len(raw0_set)})")
filled_ok = all(float(df[(df.year == y) & (df["round"] == rd) &
                         (df.driver == dv)]["grid"].iloc[0]) == fn + 1
                for (y, rd, dv) in
                [(2023, 13, "MAG"), (2023, 15, "STR"), (2023, 19, "STR"),
                 (2024, 20, "OCO"), (2026, 19, "HIR")]
                for fn in [int(df[(df.year == y) & (df["round"] == rd)]["field_n"].iloc[0])])
chk(12, filled_ok, "each pit-lane row filled with field_n + 1")

poles = int((df["q_position"] == 1).sum())
chk(13, int(df["on_pole"].sum()) == poles,
    "on_pole == (q_position == 1)",
    f" ({int(df['on_pole'].sum())} vs {poles})")
chk(14, int((df["q_position"] == 1).sum()) == 89,
    "exactly 89 pole-sitters (one per race)",
    f" ({int((df['q_position'] == 1).sum())})")

print()
print("=" * 78)
print("FEATURE RANGES (sanity)")
print("=" * 78)
print(f"  {'feature':<20} {'min':>9} {'max':>9} {'mean':>9}  zeros")
for c in features.ALL_FEATURES:
    s = df[c]
    print(f"  {c:<20} {s.min():>9.3f} {s.max():>9.3f} {s.mean():>9.3f}  "
          f"{int((s == 0).sum())}")

print()
print("=" * 78)
print("SAMPLE ROWS - 2026 R7, first 6 by finish")
print("=" * 78)
cols = ["driver", "finish"] + features.ALL_FEATURES
sub = df[(df.year == 2026) & (df["round"] == 7)].head(6)
print(sub[cols].to_string(index=False,
                           float_format=lambda v: f"{v:.3f}"))

con.close()
print()
print("=" * 78)
print("FEATURES VERIFIED - NO LEAKAGE" if ok else "FEATURES FAILED")
print("=" * 78)
sys.exit(0 if ok else 1)
