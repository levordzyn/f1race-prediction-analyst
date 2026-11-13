"""Load the local F1 account credentials into the environment.

SECURITY
--------
* The credentials live in ``credentials.env`` in the project root, which is
  listed in ``.gitignore``. This project is PRIVATE and local to this machine:
  never commit, publish, or paste the contents of that file anywhere.
* Nothing in this module ever logs, prints, raises, or returns the password.
  Only the *presence* of each variable is reported, never its value.
* If the file is missing, we degrade gracefully: FastF1 then runs without
  authentication, which is enough for results/qualifying but NOT for lap data
  (those endpoints need an F1 account).

Usage::

    from f1pred import credentials
    credentials.load()          # sets os.environ["F1_USERNAME"/"F1_PASSWORD"]

Run:  python -m f1pred.credentials        # reports status only, no values
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# project root = parent of the f1pred package directory
ROOT = Path(__file__).resolve().parents[1]
CREDS_FILE = ROOT / "credentials.env"

# variable names we expect; values are never written to any log
EXPECTED = ("F1_USERNAME", "F1_PASSWORD")


def _read_pairs(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Returns {} if the file is absent/unreadable."""
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("could not read %s (%s) - continuing unauthenticated",
                    path.name, type(exc).__name__)
        return {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        out[key.strip()] = val.strip()
    return out


def load(path: Path = CREDS_FILE, *, override: bool = False) -> bool:
    """Set F1_USERNAME/F1_PASSWORD in ``os.environ`` from ``path``.

    Returns True if both variables are now set (either from the file or
    already present in the environment). Never logs any value.
    """
    pairs = _read_pairs(path)
    if not pairs:
        have = [k for k in EXPECTED if os.environ.get(k)]
        if len(have) == len(EXPECTED):
            log.info("F1 credentials found in environment (%s set)",
                     "/".join(EXPECTED))
            return True
        log.warning("no credentials file at %s and %s not in environment - "
                    "FastF1 will run unauthenticated (lap data unavailable)",
                    path.name, "/".join(EXPECTED))
        return False

    loaded = 0
    for key in EXPECTED:
        val = pairs.get(key)
        if not val:
            continue
        if override or not os.environ.get(key):
            os.environ[key] = val
        loaded += 1

    # report ONLY whether each key was found - never the value
    status = ", ".join(
        f"{k}={'set' if os.environ.get(k) else 'missing'}" for k in EXPECTED
    )
    if loaded == len(EXPECTED):
        log.info("loaded F1 credentials from %s (%s)", path.name, status)
        return True
    log.warning("credentials file %s is incomplete (%s)", path.name, status)
    return False


if __name__ == "__main__":  # pragma: no cover - manual status check
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ok = load()
    print()
    print("credentials file :", CREDS_FILE.name, "| present:", CREDS_FILE.exists())
    for k in EXPECTED:
        # presence only - the value must never appear on screen
        print(f"  {k:14}: {'set' if os.environ.get(k) else 'NOT set'}")
    print("ready for authenticated FastF1:", ok)
