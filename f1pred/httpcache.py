"""Disk-cached, rate-limit-aware HTTP client for the OpenF1 REST API.

Spec 6 requires fetching to be:
  * idempotent           -> every URL is cached on disk, re-running downloads nothing
  * rate-limit aware     -> global spacing between requests + backoff on HTTP 429
  * tolerant of missing  -> "no rows" is logged and returned as an empty result,
                            it never crashes the pipeline

OpenF1 documents roughly 3 req/s and 30 req/min [VERIFY - not published in a
header; see _raise_spacing]. We start below the per-second figure and only
tighten spacing if the server actually complains.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://api.openf1.org"
DEFAULT_CACHE_DIR = Path("cache/openf1")

MIN_INTERVAL_S = 0.4          # start at 2.5 req/s (just under the ~3 req/s claim)
SPACING_AFTER_429_S = 2.5     # ~24 req/min, safely under the ~30 req/min claim
MAX_TRIES = 5

_spacing_s = MIN_INTERVAL_S
_last_request = 0.0


class OpenF1Error(RuntimeError):
    """Raised when OpenF1 answers with something we cannot interpret."""


def reset_rate_limit(interval: float = MIN_INTERVAL_S) -> None:
    """Forget the measured spacing (used by tests and by --no-cache runs)."""
    global _spacing_s, _last_request
    _spacing_s = interval
    _last_request = 0.0


def current_spacing() -> float:
    return _spacing_s


def _throttle() -> None:
    global _last_request
    wait = _spacing_s - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.monotonic()


def _raise_spacing() -> None:
    """First 429 seen: adopt the documented per-minute limit for good."""
    global _spacing_s
    if _spacing_s < SPACING_AFTER_429_S:
        _spacing_s = SPACING_AFTER_429_S
        log.warning("HTTP 429 observed -> request spacing raised to %.1fs",
                    _spacing_s)


def _backoff_seconds(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return max(1.0, float(retry_after))
        except ValueError:
            pass
    return min(2.0 ** attempt * 2.0, 60.0)


def _cache_file(cache_dir: Path, url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return cache_dir / f"{digest}.json"


def _write_cache(path: Path, url: str, status: int, body) -> None:
    record = {
        "url": url,
        "status": status,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "body": body,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    tmp.replace(path)          # atomic, so an interrupted run never leaves junk


def get_json(path: str, *, cache_dir: Path = DEFAULT_CACHE_DIR):
    """GET ``BASE_URL + path`` and return the parsed JSON body.

    Returns ``None`` when OpenF1 legitimately has no rows for the query
    (HTTP 404 with its "No results found." payload).
    """
    url = BASE_URL + path
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_file(cache_dir, url)

    if cache_file.exists():
        record = json.loads(cache_file.read_text(encoding="utf-8"))
        log.debug("cache hit  %s", path)
        return record["body"]

    log.debug("cache miss %s", path)

    for attempt in range(1, MAX_TRIES + 1):
        _throttle()
        try:
            resp = requests.get(url, timeout=30)
        except requests.RequestException as exc:
            log.warning("network error on %s (attempt %d/%d): %s",
                        path, attempt, MAX_TRIES, exc)
            time.sleep(min(2.0 ** attempt, 30.0))
            continue

        if resp.status_code == 429:
            wait = _backoff_seconds(resp.headers.get("Retry-After"), attempt)
            log.warning("HTTP 429 on %s -> sleeping %.1fs (attempt %d/%d)",
                        path, wait, attempt, MAX_TRIES)
            _raise_spacing()
            time.sleep(wait)
            continue

        if resp.status_code >= 500:
            log.warning("HTTP %d on %s -> retrying (attempt %d/%d)",
                        resp.status_code, path, attempt, MAX_TRIES)
            time.sleep(min(2.0 ** attempt, 30.0))
            continue

        if resp.status_code == 404:
            # OpenF1 answers 404 + {"detail": "No results found."} for zero rows.
            try:
                payload = resp.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict) and "No results found" in str(payload.get("detail", "")):
                log.info("no rows from OpenF1 for %s (cached as empty)", path)
                _write_cache(cache_file, url, 404, None)
                return None
            raise OpenF1Error(f"HTTP 404 for {url}: {resp.text[:200]}")

        if resp.status_code >= 400:
            raise OpenF1Error(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")

        body = resp.json()
        _write_cache(cache_file, url, resp.status_code, body)
        return body

    raise OpenF1Error(f"giving up on {url} after {MAX_TRIES} attempts")
