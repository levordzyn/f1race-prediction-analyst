"""Print one real sample of every library API Phase 3 relies on.

Rule: never guess an API. This prints the exact versions and calls used by
f1pred/features.py and f1pred/model.py so they can be checked against reality.

  1. sklearn version + Ridge / StandardScaler signatures actually available;
  2. fit a Ridge on a 6-row toy matrix and print standardised coefficients;
  3. scipy Spearman on a known example;
  4. pandas rolling(shift) behaviour used for the leakage-free form features.

Run:  python scripts/probe_phase3_libs.py
"""
from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

print("=" * 78)
print("1. VERSIONS")
print("=" * 78)
print(f"  python/pandas/numpy/sklearn : "
      f"{pd.__version__} / {np.__version__} / {sklearn.__version__}")
try:
    import scipy
    from scipy.stats import spearmanr
    print(f"  scipy                       : {scipy.__version__}")
except Exception as exc:                          # noqa: BLE001
    print(f"  scipy MISSING: {type(exc).__name__}: {exc}")
    spearmanr = None

print()
print("=" * 78)
print("2. EXACT SIGNATURES I WILL CALL")
print("=" * 78)
for name, obj in (("Ridge", Ridge), ("StandardScaler", StandardScaler)):
    print(f"  {name}{inspect.signature(obj)}")

print()
print("=" * 78)
print("3. FIT A RIDGE ON A TOY MATRIX - prints real coefficients")
print("=" * 78)
# 6 rows, 3 standardised-ish features; target = finish position.
X = np.array([
    [1.0, 5.0, 0.0],
    [2.0, 6.0, 0.0],
    [3.0, 9.0, 0.0],
    [4.0, 12.0, 1.0],
    [5.0, 15.0, 1.0],
    [6.0, 18.0, 1.0],
], dtype=float)
y = np.array([1.0, 3.0, 2.0, 8.0, 10.0, 9.0], dtype=float)

# Fit the scaler on TRAINING data only - the pattern walk-forward must follow.
sc = StandardScaler().fit(X)
Xs = sc.transform(X)
print(f"  scaler mean_      : {np.round(sc.mean_, 4)}")
print(f"  scaler scale_     : {np.round(sc.scale_, 4)}")
print(f"  X standardised    :\n{np.round(Xs, 4)}")

m = Ridge(alpha=1.0).fit(Xs, y)
print(f"  Ridge alpha       : {m.alpha}")
print(f"  coef_ (standardised, positions per 1 SD): "
      f"{np.round(m.coef_, 4)}")
print(f"  intercept_        : {m.intercept_:.4f}")
print(f"  train MAE         : {np.abs(m.predict(Xs) - y).mean():.4f}")

print()
print("=" * 78)
print("4. SPEARMAN - known example (perfect monotone => rho = 1.0)")
print("=" * 78)
if spearmanr is not None:
    rho, p = spearmanr([1, 2, 3, 4], [10, 20, 30, 40])
    print(f"  spearmanr([1,2,3,4],[10,20,30,40]) -> rho={rho:.4f} p={p:.6f}")
    rho2, p2 = spearmanr([1, 2, 3, 4], [40, 30, 20, 10])
    print(f"  reversed              -> rho={rho2:.4f} p={p2:.6f}")
    ok = abs(rho - 1.0) < 1e-9 and abs(rho2 + 1.0) < 1e-9
    print(f"  matches expectation   : {'YES' if ok else 'NO'}")

print()
print("=" * 78)
print("5. THE LEAKAGE-FREE PATTERN: shift(1) then rolling")
print("=" * 78)
# A driver's form must use ONLY races strictly before the current one.
df = pd.DataFrame({
    "race_idx": [1, 2, 3, 4, 5],
    "finish":   [10.0, 4.0, 8.0, 2.0, 6.0],
})
df["form"] = df["finish"].shift(1).rolling(3, min_periods=1).mean()
print(df.to_string(index=False))
print()
print("  race 1 form is NaN (no history); race 5 form = mean of finishes")
print("  in races 2,3,4 = (4+8+2)/3 = 4.6667 - it NEVER sees race 5's own")
print("  finish, which is the target. That is what keeps it leakage-free.")

con = None
try:
    import sqlite3
    con = sqlite3.connect("f1.db")
    con.row_factory = sqlite3.Row
    print()
    print("=" * 78)
    print("6. DB TABLES PHASE 3 READS (row counts)")
    print("=" * 78)
    for t in ("results", "qualifying", "practice", "race_status", "sessions"):
        print(f"  {t:<16} "
              f"{con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
finally:
    if con is not None:
        con.close()

print()
print("=" * 78)
print("PHASE 3 LIBRARY PROBE DONE")
print("=" * 78)
