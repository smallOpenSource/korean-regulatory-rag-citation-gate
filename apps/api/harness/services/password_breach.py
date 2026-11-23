"""HIBP k-anonymity password breach check (REG-05 T281).

Uses the Have I Been Pwned range API: only the first 5 hex chars of the SHA-1
hash are sent, preserving full k-anonymity — the plaintext password never leaves
the process boundary.

Production note: for an air-gapped environment, replace with an offline prefix
lookup against the HIBP downloaded hash list (sorted by SHA-1, binary search).
"""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

_HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"
_HIBP_TIMEOUT_SECONDS = 3.0


async def is_password_breached(password: str) -> bool:
    """Return True if the password appears in HIBP breach corpus.

    Uses k-anonymity: sends the first 5 hex chars of the SHA-1 hash and checks
    the returned suffix list. Returns False on any network error so the caller
    is not blocked by connectivity issues (best-effort, non-blocking check).
    """
    sha1_hex = hashlib.sha1(password.encode("utf-8"), usedforsecurity=False).hexdigest().upper()
    prefix = sha1_hex[:5]
    suffix = sha1_hex[5:]

    try:
        import httpx

        async with httpx.AsyncClient(timeout=_HIBP_TIMEOUT_SECONDS) as client:
            response = await client.get(
                _HIBP_RANGE_URL.format(prefix=prefix),
                headers={
                    "Add-Padding": "true",
                    "User-Agent": "harness-poc/1.0 security-check",
                },
            )
        _ = response.raise_for_status()
        for line in response.text.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            hash_suffix, _count = line.split(":", 1)
            if hash_suffix.upper() == suffix:
                return True
    except Exception:  # noqa: BLE001 — breach check is best-effort; never block login
        logger.warning("HIBP breach check unavailable; skipping for this request")

    return False
