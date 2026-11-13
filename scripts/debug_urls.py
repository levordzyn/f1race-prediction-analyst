"""Find the primary + fallback timing URLs FastF1 uses, and test each one.

Run:  python scripts/debug_urls.py
"""
from __future__ import annotations

import re
from pathlib import Path

import fastf1._api as a

src = Path(a.__file__).read_text(encoding="utf-8", errors="replace")
urls = sorted(set(re.findall(r"https?://[^'\"\s)\]]+", src)))
print("URLs in fastf1._api:")
for u in urls:
    print("  ", u)

# How api_path is built
m = re.search(r"def api_path.*?(?=\n    def |\nclass )", Path(
    fastf1_core := Path(a.__file__).parent / "core.py").read_text(encoding="utf-8", errors="replace"), re.S)
print("\napi_path property source:\n", m.group(0)[:1200] if m else "not found in core.py")
