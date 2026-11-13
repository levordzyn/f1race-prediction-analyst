"""Structural check of credentials.env - reports ONLY safe facts.

Never prints the username or password value. Used to rule out a parsing bug
(quotes, whitespace, CRLF, BOM) before blaming the credentials themselves.

Run:  python scripts/check_creds_structure.py
"""
from __future__ import annotations

import os
from pathlib import Path

p = Path("credentials.env")
raw = p.read_bytes()

print("FILE STRUCTURE")
print("  BOM present        :", raw[:3] == b"\xef\xbb\xbf")
print("  line endings       :", "CRLF" if b"\r\n" in raw else "LF")
print("  trailing newline   :", raw.endswith(b"\n"))
print()

print("PER-LINE STRUCTURE (values never shown)")
QUOTE_CHARS = (b'"', b"'")
for i, line in enumerate(raw.split(b"\n"), 1):
    line = line.rstrip(b"\r")
    if not line.strip() or line.strip().startswith(b"#"):
        continue
    if b"=" not in line:
        print(f"  line {i}: NO '=' SIGN - will be ignored")
        continue
    key_b, val_b = line.split(b"=", 1)
    key = key_b.strip().decode("utf-8", "replace")
    facts: list[str] = []
    if val_b != val_b.strip():
        facts.append("leading/trailing whitespace")
    stripped = val_b.strip()
    if len(stripped) >= 2 and stripped[:1] in QUOTE_CHARS and stripped[-1:] in QUOTE_CHARS:
        facts.append("VALUE IS QUOTED (quotes would be sent literally!)")
    if b"\t" in val_b:
        facts.append("contains tab")
    if b" " in stripped:
        facts.append("contains internal space")
    try:
        stripped.decode("ascii")
    except UnicodeDecodeError:
        facts.append("NON-ASCII bytes")
    if not stripped:
        facts.append("EMPTY VALUE")
    print(f"  line {i}: {key:14} raw_len={len(val_b):3} "
          f"stripped_len={len(stripped):3}  "
          f"{'; '.join(facts) if facts else '[clean]'}")

print()
u = os.environ.get("F1_USERNAME", "")
pw = os.environ.get("F1_PASSWORD", "")
print("AFTER LOADING INTO ENVIRONMENT")
print("  F1_USERNAME set    :", bool(u), "| length:", len(u),
      "| contains @:", "@" in u)
print("  F1_PASSWORD set    :", bool(pw), "| length:", len(pw))
print()
print("NOTE: 'contains @' tells us whether it looks like an email address,")
print("which is what the F1 login error refers to. The value stays hidden.")
