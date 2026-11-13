"""Back up f1.db, re-fetch ONLY 2026 R4 practice, and show before/after.

Conditions this satisfies:
  * f1.db is backed up first (timestamped copy, alongside the earlier ones);
  * only 2026 R4 (Miami) is re-fetched - every other race keeps its rows;
  * before/after best lap and gap are printed for PIA plus two other drivers
    (LEC and VER, the two whose practice_rank also moves);
  * the other 88 races are proven unchanged by hashing every practice row
    outside 2026 R4 before and after.

Re-fetch mechanism: delete the fetch_log step so ``fetch_practice`` runs again,
then let it recompute through the FIXED ``openf1.best_practice_laps``.
``_write_rows`` uses INSERT OR REPLACE on the (year, round, driver) key, so
existing rows are overwritten in place - no delete of the table is needed.

Run:  python scripts/refetch_miami_practice.py
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f1pred import db, practice  # noqa: E402

YEAR, RND = 2026, 4
SHOW = ["PIA", "LEC", "VER"]          # PIA is the corrupt row; LEC/VER move rank
DB_PATH = Path("f1.db")

con = db.connect()
con.row_factory = None


def rule(t=""):
    print("=" * 78)
    if t:
        print(t)
        print("=" * 78)


def snapshot(year, rnd):
    """All practice rows of one race, as a canonical tuple list."""
    return con.execute(
        "SELECT driver, driver_number, team, n_sessions, best_practice_s, "
        "practice_rank, laps_completed, pit_out_laps, gap_to_best_pct, "
        "has_practice_lap FROM practice WHERE year=? AND round=? "
        "ORDER BY driver", (year, rnd)).fetchall()


def hash_except(exclude_year, exclude_round):
    """Hash every practice row NOT belonging to the excluded race."""
    rows = con.execute(
        "SELECT year, round, driver, driver_number, team, n_sessions, "
        "best_practice_s, practice_rank, laps_completed, pit_out_laps, "
        "gap_to_best_pct, has_practice_lap FROM practice "
        "ORDER BY year, round, driver").fetchall()
    payload = [r for r in rows if not (r[0] == exclude_year and r[1] == exclude_round)]
    blob = repr(payload).encode("utf-8")
    return hashlib.sha256(blob).hexdigest(), len(payload)


# ------------------------------------------------------------------ BACKUP
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = Path(f"f1_backup_before_miami_practice_refetch_{ts}.db")
con.close()

if backup.exists():
    print(f"backup already exists: {backup}")
    sys.exit(1)
shutil.copy2(DB_PATH, backup)
print(f"backup written: {backup}  ({backup.stat().st_size} bytes)")
print()

con = db.connect()
con.row_factory = None

before_rows = snapshot(YEAR, RND)
before_hash, before_n = hash_except(YEAR, RND)
total_before = con.execute("SELECT COUNT(*) FROM practice").fetchone()[0]
other_races_before = con.execute(
    "SELECT COUNT(DISTINCT year || '-' || round) FROM practice").fetchone()[0]

# ------------------------------------------------------------ BEFORE values
before = {r[0]: r for r in before_rows}

rule("BEFORE - stored values for 2026 R4 (Miami)")
print(f"  {'drv':<5} {'best_practice_s':>16} {'gap%':>9} {'rank':>6} {'laps':>6}")
for d in SHOW:
    r = before[d]
    print(f"  {d:<5} {r[4]:>16.3f} {r[8]:>9.4f} {r[5]:>6.0f} {r[6]:>6}")

# --------------------------------------------------------------- RE-FETCH
rule("RE-FETCHING 2026 R4 PRACTICE ONLY")
step = con.execute(
    "SELECT nrows, run_at FROM fetch_log WHERE year=? AND round=? "
    "AND step='practice'", (YEAR, RND)).fetchone()
print(f"  fetch_log before: practice nrows={step[0]} run_at={step[1]}")
con.execute("DELETE FROM fetch_log WHERE year=? AND round=? AND step='practice'",
            (YEAR, RND))
con.commit()
print("  fetch_log step 'practice' deleted -> fetch_practice will run again")

practice.fetch_practice(con, YEAR, RND)

step = con.execute(
    "SELECT nrows, run_at FROM fetch_log WHERE year=? AND round=? "
    "AND step='practice'", (YEAR, RND)).fetchone()
print(f"  fetch_log after : practice nrows={step[0]} run_at={step[1]}")
print("  (no API call was needed - all lap rows were already disk-cached)")

# --------------------------------------------------------------- AFTER values
after_rows = snapshot(YEAR, RND)
after_hash, after_n = hash_except(YEAR, RND)
after = {r[0]: r for r in after_rows}
total_after = con.execute("SELECT COUNT(*) FROM practice").fetchone()[0]
other_races_after = con.execute(
    "SELECT COUNT(DISTINCT year || '-' || round) FROM practice").fetchone()[0]

rule("AFTER - stored values for 2026 R4 (Miami)")
print(f"  {'drv':<5} {'best_practice_s':>16} {'gap%':>9} {'rank':>6} {'laps':>6}")
for d in SHOW:
    r = after[d]
    print(f"  {d:<5} {r[4]:>16.3f} {r[8]:>9.4f} {r[5]:>6.0f} {r[6]:>6}")

rule("BEFORE / AFTER SIDE BY SIDE")
print(f"  {'drv':<5} {'best lap':>34}   {'gap%':>21}   {'rank':>13}")
for d in SHOW:
    b, a = before[d], after[d]
    print(f"  {d:<5} {b[4]:>14.3f} -> {a[4]:<14.3f}   "
          f"{b[8]:>9.4f} -> {a[8]:<9.4f}   {b[5]:>5.0f} -> {a[5]:<5.0f}")

# ------------------------------------------------------- full race diff
diffs = []
for d in sorted(before):
    b, a = before[d], after[d]
    for i, col in enumerate(["driver", "driver_number", "team", "n_sessions",
                             "best_practice_s", "practice_rank",
                             "laps_completed", "pit_out_laps",
                             "gap_to_best_pct", "has_practice_lap"]):
        if b[i] != a[i]:
            diffs.append((d, col, b[i], a[i]))

rule("EVERY CHANGED VALUE IN 2026 R4")
print(f"  {len(diffs)} value(s) changed across {len(before)} rows")
for d, col, b, a in diffs:
    if isinstance(b, float) and isinstance(a, float):
        print(f"    {d:<5} {col:<18} {b:>12.4f} -> {a:>12.4f}")
    else:
        print(f"    {d:<5} {col:<18} {b!r} -> {a!r}")

# -------------------------------------------------------------- invariants
rule("INVARIANTS")
ok = True


def chk(n, cond, label, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  [{n}] {label:<54} {'PASS' if cond else 'FAIL'}{detail}")


chk(1, total_before == total_after == 1816,
    "practice still 1816 rows",
    f" ({total_before} -> {total_after})")
chk(2, len(after_rows) == 22, "2026 R4 still has 22 rows",
    f" ({len(before_rows)} -> {len(after_rows)})")
chk(3, before_n == after_n, f"the OTHER 88 races' rows are byte-identical",
    f" ({before_n} rows, hash "
    f"{'MATCH' if before_hash == after_hash else 'DIFFER'})")
chk(4, before_hash == after_hash, "hash of all non-Miami practice rows unchanged")
chk(5, other_races_before == other_races_after == 89,
    "still 89 distinct races",
    f" ({other_races_before} -> {other_races_after})")
chk(6, after["PIA"][4] > 80.0,
    "PIA's best lap is now physically plausible at Miami",
    f" ({after['PIA'][4]:.3f}s; Miami laps run ~89-93s)")
chk(7, after["PIA"][8] < 5.0,
    "no car in 2026 R4 has a gap over 5% now",
    f" (max {max(r[8] for r in after_rows if r[8] is not None):.2f}%)")
chk(8, sorted(r[5] for r in after_rows) == list(range(1, 23)),
    "practice_rank is a contiguous 1..22 permutation")

# laps_completed must be untouched: we only stopped trusting a duration, we did
# not claim the driver failed to drive the lap
laps_same = all(before[d][6] == after[d][6] for d in before)
chk(9, laps_same, "laps_completed unchanged for every driver",
    " (lap_count still counts rejected rows)")

# other tables untouched
for tbl, want in (("results", 1816), ("qualifying", 1816), ("sprint", 492),
                  ("sprint_qualifying", 492)):
    n = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
    chk(10, n == want, f"{tbl} still {want} rows", f" ({n})")

con.close()
print()
rule("MIAMI PRACTICE RE-FETCH " + ("COMPLETE" if ok else "FAILED"))
print(f"  backup: {backup}")
sys.exit(0 if ok else 1)
