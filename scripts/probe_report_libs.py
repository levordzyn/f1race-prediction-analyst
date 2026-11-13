"""Probe the exact matplotlib API that f1pred/report.py will rely on.

Prints one real sample of every call, then writes an actual PNG and confirms
it exists. Nothing here is guessed: if a call below fails, the report module
must not use it.

Run:  python scripts/probe_report_libs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

OUT = Path("cache") / "probe"
OUT.mkdir(parents=True, exist_ok=True)

fails: list[str] = []


def step(name, fn):
    try:
        v = fn()
        print(f"  OK   {name:<34} -> {v!r}")
        return v
    except Exception as exc:                      # noqa: BLE001
        fails.append(name)
        print(f"  FAIL {name:<34} -> {type(exc).__name__}: {exc}")
        return None


print("=" * 78)
print("MATPLOTLIB API PROBE - every function report.py will use")
print("=" * 78)

import matplotlib                                  # noqa: E402

print(f"  matplotlib version: {matplotlib.__version__}")
step("matplotlib.use('Agg')", lambda: matplotlib.use("Agg") or "Agg")

import matplotlib.pyplot as plt                    # noqa: E402

print()

# --- figure creation
fig, ax = step("plt.subplots(1, 1, figsize=(6,4))",
               lambda: plt.subplots(1, 1, figsize=(6, 4)))
if fig is None:
    print("cannot continue without a figure")
    sys.exit(1)
print(f"       type(fig)={type(fig).__name__} type(ax)={type(ax).__name__}")

# --- horizontal bar chart (coefficient chart)
labels = ["q_position", "driver_form", "grid", "team_form"]
values = [1.9042, 1.3475, 0.6847, 0.6356]
step("ax.barh(labels, values)", lambda: ax.barh(labels, values))
step("ax.set_title(str)", lambda: ax.set_title(
    "ridge feature coefficients (positive = worse finish)"))
step("ax.set_xlabel(str)", lambda: ax.set_xlabel(
    "predicted finish change per feature standard deviation (positions)"))
step("ax.set_ylabel(str)", lambda: ax.set_ylabel("feature"))
step("ax.invert_yaxis()", lambda: ax.invert_yaxis() or "inverted")
step("ax.tick_params(axis='y')", lambda: ax.tick_params(axis="y") or "set")
step("ax.grid(axis='x', alpha=..)", lambda: ax.grid(axis="x", alpha=0.3) or "on")
step("ax.axvline(0)", lambda: ax.axvline(0, color="black", lw=0.8) or "drawn")

# --- scatter (gap vs prediction)
xs = [0.0, 0.5, 1.1, 2.0]
ys = [1, 2, 3, 4]
ax2 = step("fig.add_subplot(122)", lambda: fig.add_subplot(1, 2, 2))
step("ax2.scatter(xs, ys)", lambda: ax2.scatter(xs, ys, s=40))
step("ax2.invert_yaxis()", lambda: ax2.invert_yaxis() or "inverted")
step("ax2.set_ylim(bottom=22)", lambda: ax2.set_ylim(22.5, 0.5))
step("ax2.annotate(code, xy=..)", lambda: ax2.annotate(
    "PIA", xy=(0.0, 1), xytext=(4, 4), textcoords="offset points", fontsize=8))
step("ax2.set_xlabel(str)", lambda: ax2.set_xlabel("qualifying gap to fastest (%)"))
step("ax2.set_ylabel(str)", lambda: ax2.set_ylabel("predicted finishing position"))

# --- text / table-ish output
step("ax2.set_title(str)", lambda: ax2.set_title("gap vs prediction"))

# --- finish
step("fig.tight_layout()", lambda: fig.tight_layout() or "tight")
png = OUT / "probe.png"
step("fig.savefig(path, dpi=150)", lambda: fig.savefig(png, dpi=150) or "saved")
step("plt.close(fig)", lambda: plt.close(fig) or "closed")

print()
print("=" * 78)
print("RESULT FILE")
print("=" * 78)
exists = png.exists()
size = png.stat().st_size if exists else 0
print(f"  path   : {png}")
print(f"  exists : {exists}")
print(f"  bytes  : {size}")
PNG_MAGIC = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
print(f"  readable as PNG: {exists and size > 1000 and png.read_bytes()[:8] == PNG_MAGIC}")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
if fails:
    print(f"  {len(fails)} call(s) FAILED: {fails}")
    sys.exit(1)
if not exists or size < 1000:
    print("  PNG was not written correctly")
    sys.exit(1)
print("  every API call succeeded and a real PNG was written")
sys.exit(0)
