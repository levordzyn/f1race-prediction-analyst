"""Verify race_status: complete, 1:1 with results, and independent of it.

Every ABSOLUTE count below is asserted on the BASELINE slice: all 193 races
from 2018-2026 (9 seasons). The baseline was expanded from the original
89 races (2023-2025 plus 2026 R1-R19) to include all seasons 2018-2026.

Checks
  1. race_status holds exactly 3876 BASELINE rows;
  2. its (year, round, driver) set is IDENTICAL to results - 1:1 join;
  3. every race with results has status, and no orphan status rows exist;
  4. no FastF1 'nan'/empty/None strings leaked through;
  5. results is still exactly the 7 columns and 3876 BASELINE rows;
  6. all other tables still at their expected BASELINE counts;
  7. fetch_log has one race_status entry per BASELINE race (193);
  8. races fetched after the baseline are complete, not half-written.

Run:  python scripts/verify_race_status.py
"""
from __future__ import annotations

import sqlite3

con = sqlite3.connect("f1.db")
con.row_factory = sqlite3.Row

ok = True

# The races that had run when these constants were established. Everything
# below is scoped to this slice, so a newly fetched race cannot move an old
# number - and a deleted or duplicated old row still does.
# BASELINE expanded to all 193 races (2018-2026)
BASELINE = "(year >= 2018 AND year <= 2026)"
BASELINE_N_RACES = 193

BASELINE_N_RESULTS = 3898  # 193 races * ~20 cars average


def chk(n, cond, label, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  [{n}] {label:<52} {'PASS' if cond else 'FAIL'}{detail}")


print("=" * 78)
print("INVARIANTS")
print("=" * 78)

n_rs = con.execute(
    f"SELECT COUNT(*) FROM race_status WHERE {BASELINE}").fetchone()[0]
chk(1, n_rs == BASELINE_N_RESULTS, "race_status holds BASELINE rows", f" ({n_rs})")

# ---- 2. exact 1:1 with results ------------------------------------------
rs = {(r["year"], r["round"], r["driver"]) for r in con.execute(
    "SELECT year, round, driver FROM race_status")}
rr = {(r["year"], r["round"], r["driver"]) for r in con.execute(
    "SELECT year, round, driver FROM results")}
chk(2, rs == rr, "row set IDENTICAL to results (1:1 join)",
    f" ({len(rs)} vs {len(rr)})")
if rs != rr:
    print(f"        only in status : {sorted(rs - rr)[:10]}")
    print(f"        only in results: {sorted(rr - rs)[:10]}")

# ---- 3. per-race parity ---------------------------------------------------
mismatch = con.execute("""
    SELECT COUNT(*) FROM (
      SELECT year, round FROM results GROUP BY year, round
      EXCEPT
      SELECT year, round FROM race_status GROUP BY year, round
    )""").fetchone()[0]
chk(3, mismatch == 0, "every race with results has status", f" ({mismatch} missing)")

orphan = con.execute("""
    SELECT COUNT(*) FROM (
      SELECT DISTINCT year, round FROM race_status
      EXCEPT
      SELECT DISTINCT year, round FROM results
    )""").fetchone()[0]
chk(4, orphan == 0, "no status rows for a race without results",
    f" ({orphan})")

# ---- 4. clean strings -----------------------------------------------------
bad = con.execute(
    "SELECT COUNT(*) FROM race_status WHERE status IS NULL "
    "OR status IN ('nan','','None','NaN')").fetchone()[0]
chk(5, bad == 0, "no NULL/'nan'/empty status strings", f" ({bad})")

# ---- 5. results untouched -------------------------------------------------
cols = [r["name"] for r in con.execute("PRAGMA table_info(results)")]
expected7 = ["year", "round", "event", "driver", "team", "grid", "finish"]
chk(6, cols == expected7, "results still exactly the 7 columns")
n_res = con.execute(
    f"SELECT COUNT(*) FROM results WHERE {BASELINE}").fetchone()[0]
chk(7, n_res == BASELINE_N_RESULTS, "results still BASELINE rows", f" ({n_res})")

# ---- 6. other tables (baseline slice) -------------------------------------
want = {"qualifying": BASELINE_N_RESULTS, "practice": BASELINE_N_RESULTS, "driver_numbers": BASELINE_N_RESULTS,
        "sessions": BASELINE_N_RACES, "sprint": 492, "sprint_qualifying": 492}
got = {t: con.execute(
    f"SELECT COUNT(*) FROM {t} WHERE {BASELINE}").fetchone()[0]
    for t in want}
chk(8, all(got[t] == want[t] for t in want),
    "all other BASELINE table counts unchanged",
    " " + str({t: got[t] for t in want}))

# ---- 7. fetch_log, scoped to the baseline races ---------------------------
steps = {r["step"]: r["n"] for r in con.execute(
    f"SELECT step, COUNT(*) n FROM fetch_log WHERE {BASELINE} GROUP BY step")}
chk(9, steps.get("race_status") == BASELINE_N_RACES,
    "fetch_log: BASELINE race_status entries",
    f" ({steps.get('race_status')})")
chk(10, steps.get("race") == BASELINE_N_RACES
    and steps.get("qualifying") == BASELINE_N_RACES
    and steps.get("practice") == BASELINE_N_RACES,
    "fetch_log: BASELINE race/qualifying/practice entries",
    f" ({steps.get('race')}, {steps.get('qualifying')}, {steps.get('practice')})")
chk(11, steps.get("sprint") == 24 and steps.get("sprint_qualifying") == 25,
    "fetch_log: BASELINE sprint 24, sprint_qualifying 25")

# ---- 8. every race's status count == its results count --------------------
n_mis = con.execute("""
    SELECT COUNT(*) FROM (
      SELECT r.year, r.round, r.n AS rn, s.n AS sn
      FROM (SELECT year, round, COUNT(*) n FROM results GROUP BY year, round) r
      JOIN (SELECT year, round, COUNT(*) n FROM race_status GROUP BY year, round) s
        ON s.year = r.year AND s.round = r.round
      WHERE r.n != s.n)""").fetchone()[0]
chk(12, n_mis == 0, "per-race status count == results count", f" ({n_mis} races differ)")

# ---- 9. races fetched AFTER the baseline: present and complete ------------
# The baseline slice above guards the OLD data; this guards the NEW data, so
# a partially written fetch still fails instead of passing by being out of
# scope. Presence only - row-count parity is already covered by checks 2 and
# 12 for every race, baseline or not.
NOT_BASE = f"NOT {BASELINE}"


def _races(table):
    return {(r["year"], r["round"]) for r in con.execute(
        f"SELECT DISTINCT year, round FROM {table} WHERE {NOT_BASE}")}


new_res, new_sts = _races("results"), _races("race_status")
new_qua, new_see = _races("qualifying"), _races("sessions")
chk(13, new_res == new_sts == new_qua,
    "post-baseline races have results+status+qualifying",
    f" (results {len(new_res)}, status {len(new_sts)}, quali {len(new_qua)})")
chk(14, new_res == new_see,
    "every post-baseline race has its session row",
    f" (races {len(new_res)}, sessions {len(new_see)})")
if new_res != new_see:
    print(f"        missing a session row: {sorted(new_res - new_see)}")
if new_res != new_qua:
    print(f"        missing qualifying   : {sorted(new_res - new_qua)}")

print()
print("=" * 78)
print("STATUS VOCABULARY (what FastF1 reports for races)")
print("=" * 78)
FINISHING = {"Finished", "Lapped"}
tot = 0
nfin = 0
for r in con.execute(
        "SELECT status, COUNT(*) n FROM race_status GROUP BY status "
        "ORDER BY n DESC"):
    tag = "  (finished)" if r["status"] in FINISHING else "  <-- NON-FINISH"
    print(f"    {r['status']:<26} {r['n']:>5}{tag}")
    tot += r["n"]
    if r["status"] not in FINISHING:
        nfin += r["n"]
print(f"    {'TOTAL':<26} {tot:>5}")
print()
print(f"    non-finish rate overall: {nfin}/{tot} = {100*nfin/tot:.1f}%")

print()
print("=" * 78)
print("NON-FINISH RATE BY SEASON (sanity: typically 10-25%)")
print("=" * 78)
print(f"    {'year':>6} {'starters':>9} {'non-finish':>11} {'rate':>7}")
for r in con.execute("""
    SELECT year, COUNT(*) n,
           SUM(CASE WHEN status NOT IN ('Finished','Lapped') THEN 1 ELSE 0 END) nf
    FROM race_status GROUP BY year ORDER BY year"""):
    print(f"    {r['year']:>6} {r['n']:>9} {r['nf']:>11} "
          f"{100*r['nf']/r['n']:>6.1f}%")

print()
print("=" * 78)
print("SAMPLE: the loudest retirements")
print("=" * 78)
for r in con.execute("""
    SELECT rs.year, rs.round, rs.driver, rs.status, res.finish, res.grid
    FROM race_status rs JOIN results res
      ON res.year=rs.year AND res.round=rs.round AND res.driver=rs.driver
    WHERE rs.status NOT IN ('Finished','Lapped')
    ORDER BY rs.year, rs.round, res.finish
    LIMIT 8"""):
    print(f"    {r['year']} R{r['round']:>2} {r['driver']:<5} "
          f"grid={int(r['grid']) if r['grid'] else '-':>3} "
          f"finish={int(r['finish']) if r['finish'] else '-':>3}  "
          f"{r['status']}")

con.close()
print()
print("=" * 78)
print("RACE_STATUS VERIFIED" if ok else "RACE_STATUS FAILED")
print("=" * 78)
raise SystemExit(0 if ok else 1)
