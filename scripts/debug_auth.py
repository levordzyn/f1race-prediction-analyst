"""Inspect FastF1's F1-account auth: what credentials it wants and where from.

Run:  python scripts/debug_auth.py
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import fastf1

import fastf1.internals.f1account.transport as tr
import fastf1.internals.f1account as fa

print("f1account file:", fa.__file__)
print("transport file:", tr.__file__)

src = Path(tr.__file__).read_text(encoding="utf-8", errors="replace")
print("\n--- ENV vars referenced ---")
for line in src.splitlines():
    if "environ" in line or "getenv" in line:
        print("  ", line.strip())

pkg = Path(fa.__file__).parent
print("\n--- f1account package files ---")
for f in sorted(pkg.rglob("*.py")):
    print("  ", f.relative_to(pkg))

print("\n--- search whole fastf1 pkg for env credential names ---")
root = Path(fastf1.__file__).parent
for f in sorted(root.rglob("*.py")):
    txt = f.read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(txt.splitlines(), 1):
        if ("FASTF1_" in line or "F1_ACCOUNT" in line) and (
            "environ" in line or "getenv" in line or "FASTF1_" in line
        ):
            print(f"  {f.relative_to(root)}:{i}: {line.strip()}")
