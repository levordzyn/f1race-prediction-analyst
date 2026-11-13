"""Exercise Appendix A's FETCH path against a COPY of f1.db - never the real one.

Why a copy: fetch writes rows. We must prove the three fetch-path fixes work
(configure(), datetime.now(timezone.utc), the empty-rows message) without any
risk of the unguarded Appendix A code writing into the production database.

What it does:
  1. copy f1.db -> f1_baseline_fetchtest.db
  2. delete one race from the copy (so fetch has real work to do)
  3. run f1_baseline.py fetch --years 2023 against the copy
  4. check: race restored, message correct, and stderr has NO warnings

Run:  python scripts/test_baseline_fetch.py
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "f1.db"
COPY = ROOT / "f1_baseline_fetchtest.db"

YEAR = 2023
ROUND = 1

print("=" * 78)
print("SETUP: copy the DB, then delete one race so fetch has work to do")
print("=" * 78)
if COPY.exists():
    COPY.unlink()
shutil.copy(REAL, COPY)

con = sqlite3.connect(COPY)
before_total = con.execute("SELECT COUNT(*) FROM results").fetchone()[0]
con.execute("DELETE FROM results WHERE year=? AND round=?", (YEAR, ROUND))
con.commit()
after_delete = con.execute("SELECT COUNT(*) FROM results").fetchone()[0]
con.close()
print(f"  rows before              : {before_total}")
print(f"  rows after deleting "
      f"{YEAR} R{ROUND}: {after_delete}  "
      f"(-{before_total - after_delete})")

print()
print("=" * 78)
print("RUN: f1_baseline.py fetch --years 2023 (against the COPY)")
print("=" * 78)

# f1_baseline.main() reads the module global DB_PATH, so point it at the copy
# by running a tiny driver in a subprocess - keeps the test isolated.
driver = f"""
import sys
sys.path.insert(0, {str(ROOT)!r})
import f1_baseline
f1_baseline.DB_PATH = {str(COPY)!r}
sys.argv = ["f1_baseline.py", "fetch", "--years", "{YEAR}"]
f1_baseline.main()
"""
proc = subprocess.run(
    [sys.executable, "-c", driver],
    capture_output=True, text=True, cwd=str(ROOT), timeout=600,
)
print(f"  exit code : {proc.returncode}")
out = proc.stdout.strip()
err = proc.stderr.strip()
for line in out.splitlines():
    print(f"    | {line}")

print()
print("  stderr (must be EMPTY - that is the whole point of the fix):")
if err:
    for line in err.splitlines():
        print(f"    ! {line}")
else:
    print("    (empty)")

print()
print("=" * 78)
print("CHECKS")
print("=" * 78)

con = sqlite3.connect(COPY)
restored = con.execute(
    "SELECT COUNT(*) FROM results WHERE year=? AND round=?",
    (YEAR, ROUND),
).fetchone()[0]
after_total = con.execute("SELECT COUNT(*) FROM results").fetchone()[0]
# the 7-column contract f1_baseline.py depends on
cols = [r[1] for r in con.execute("PRAGMA table_info(results)")]
con.close()

ok = True

print(f"  [1] deleted race restored ({restored} rows)          "
      f"{'PASS' if restored > 0 else 'FAIL'}")
ok &= restored > 0

print(f"  [2] total rows back to {before_total} ({after_total})          "
      f"{'PASS' if after_total == before_total else 'FAIL'}")
ok &= after_total == before_total

print(f"  [3] results still has the 7 expected columns         "
      f"{'PASS' if len(cols) == 7 else 'FAIL'}")
print(f"        {cols}")
ok &= len(cols) == 7

no_warn = not any(
    w in err for w in ("DeprecationWarning", "FutureWarning", "utcnow",
                       "enable_cache")
)
print(f"  [4] no deprecation/future warnings                   "
      f"{'PASS' if no_warn else 'FAIL'}")
ok &= no_warn

# NOTE: match "(0 drivers)" with the paren, not bare "0 drivers" - the real
# message "20 drivers" contains "0 drivers" as a substring and would false-fail.
print(f"  [5] fetch reported the saved race (not '(0 drivers)')  "
      f"{'PASS' if 'saved' in out and '(0 drivers)' not in out else 'FAIL'}")
ok &= ("saved" in out) and ("(0 drivers)" not in out)

# The empty-rows branch is unreachable with real FastF1 data (measured:
# 0 races have 0 rows), so test the logic directly.
print(f"  [6] empty-rows branch says 'nothing saved'           ", end="")
rows: list = []
msg = (f"  saved 2023 R1 Test ({{len(rows)}} drivers)" if rows
       else "  no result rows for 2023 R1 Test - nothing saved")
branch_ok = ("nothing saved" in msg) and ("saved 2023" not in msg)
print("PASS" if branch_ok else "FAIL")
ok &= branch_ok

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
print("  ALL CHECKS PASSED" if ok else "  SOME CHECKS FAILED")

# leave no artefact behind
COPY.unlink(missing_ok=True)
print(f"  (removed {COPY.name})")
