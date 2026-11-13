"""Definitive test: do our credentials reach FastF1's login, and what does
the F1 identity provider say?

Reports ONLY success/failure and the server's error message. Never prints the
username or password.

Run:  python scripts/test_f1_login.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from f1pred import credentials  # noqa: E402

ok = credentials.load()
print(f"credentials.load() -> {ok}")
print(f"F1_USERNAME set: {bool(__import__('os').environ.get('F1_USERNAME'))}")
print(f"F1_PASSWORD set: {bool(__import__('os').environ.get('F1_PASSWORD'))}")
print()

# Call FastF1's own login entry point directly, so there is no ambiguity
# about whether the env vars were picked up.
from fastf1.internals.f1account.login import (  # noqa: E402
    _credentials_from_env_or_prompt,
    login,
)

user, pw = _credentials_from_env_or_prompt()
print(f"credentials FastF1 will use -> username len={len(user)}, "
      f"password len={len(pw)}")
print(f"username contains '@': {'@' in user}")
print()

try:
    token = login(user, pw)
except Exception as exc:  # noqa: BLE001
    print("LOGIN FAILED")
    print("  exception type:", type(exc).__name__)
    print("  message       :", str(exc))
    print()
    print("Interpretation:")
    msg = str(exc).lower()
    if "password or email" in msg:
        print("  -> F1 rejected the credentials themselves (typo / wrong")
        print("     account / password changed). Parsing is NOT the issue.")
    elif "subscription" in msg:
        print("  -> credentials accepted, but no active F1TV subscription.")
    elif "config scrape" in msg or "no config object" in msg:
        print("  -> FastF1 could not read F1's login config (site changed).")
    else:
        print("  -> see message above.")
else:
    print("LOGIN SUCCEEDED - token type:", type(token).__name__)
    # do NOT print the token
    print("authenticated FastF1 lap data should now be available")
