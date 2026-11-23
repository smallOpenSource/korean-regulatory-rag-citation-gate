"""Redis-backed fixed-window rate limiting for auth and global API endpoints.

Key namespaces (REG-05 T280/T292):
    harness:auth:rl:{ip}:{username}:1m:{window}   — login 10 req/min per ip+username
    harness:auth:rl:{ip}:{username}:15m:{window}  — login 60 req/15min per ip+username
    harness:auth:rl:refresh:{ip}:1m:{window}      — refresh 30 req/min per ip
    harness:global:rl:{ip}:1m:{window}            — global 600 req/min per ip
    harness:global:rl:{ip}:docs:1m:{window}       — /docs paths 10 req/min per ip
"""

from __future__ import annotations

import logging
import time
from typing import Any

_logger = logging.getLogger(__name__)

_RL_PREFIX = "harness:auth:rl"

_LOGIN_LIMIT_PER_MIN = 10
_LOGIN_LIMIT_PER_15MIN = 60
_REFRESH_LIMIT_PER_MIN = 30


async def _fixed_window_incr(
    redis: Any,
    key_prefix: str,
    window_seconds: int,
) -> int:
    """Atomically increment a fixed-window counter and return the new value.

    The window key is ``{key_prefix}:{epoch // window_seconds}`` so it rotates
    every ``window_seconds`` seconds. TTL is set to ``window_seconds + 2`` to
    prevent premature expiry at window boundaries.
    """
    window = int(time.time()) // window_seconds
    full_key = f"{key_prefix}:{window}"
    async with redis.pipeline(transaction=False) as pipe:
        pipe.incr(full_key)
        pipe.expire(full_key, window_seconds + 2)
        results = await pipe.execute()
    return int(results[0])


async def check_login_rate_limit(redis: Any, *, ip: str, username: str) -> bool:
    """Return True if the login attempt is within limits, False if rate-limited.

    Limits enforced (REG-05 T280):
    - 10 attempts per minute  per IP+username
    - 60 attempts per 15 min per IP+username

    Both counters are incremented on every call so attempts are always counted,
    even when the first window is already exceeded.
    """
    base = f"{_RL_PREFIX}:{ip}:{username}"
    now = int(time.time())
    w1m = now // 60
    w15m = now // 900
    key_1m = f"{base}:1m:{w1m}"
    key_15m = f"{base}:15m:{w15m}"

    try:
        async with redis.pipeline(transaction=False) as pipe:
            pipe.incr(key_1m)
            pipe.expire(key_1m, 62)
            pipe.incr(key_15m)
            pipe.expire(key_15m, 902)
            results = await pipe.execute()
    except Exception as exc:  # noqa: BLE001 — Redis outage must not 500 the login
        _logger.warning("check_login_rate_limit fail-open: %s: %s", type(exc).__name__, exc)
        return True

    count_1m = int(results[0])
    count_15m = int(results[2])
    return count_1m <= _LOGIN_LIMIT_PER_MIN and count_15m <= _LOGIN_LIMIT_PER_15MIN


async def check_refresh_rate_limit(redis: Any, *, ip: str) -> bool:
    """Return True if the refresh attempt is within limits, False if rate-limited.

    Limit enforced (REG-05 T280): 30 attempts per minute per IP.
    """
    key_prefix = f"{_RL_PREFIX}:refresh:{ip}:1m"
    try:
        count = await _fixed_window_incr(redis, key_prefix, 60)
    except Exception as exc:  # noqa: BLE001 — Redis outage must not 500 the refresh
        _logger.warning("check_refresh_rate_limit fail-open: %s: %s", type(exc).__name__, exc)
        return True
    return count <= _REFRESH_LIMIT_PER_MIN


# ---------------------------------------------------------------------------
# Global per-IP rate limit (REG-05 T292)
# ---------------------------------------------------------------------------

_GLOBAL_RL_PREFIX = "harness:global:rl"
_GLOBAL_LIMIT_PER_MIN = 600
_DOCS_LIMIT_PER_MIN = 10

# Paths completely exempt from rate limiting (load-balancer probes, monitoring)
_EXEMPT_PATH_PREFIXES: tuple[str, ...] = ("/health", "/metrics")
# Paths subject to the reduced docs limit
_DOCS_PATH_PREFIXES: tuple[str, ...] = ("/docs", "/redoc", "/openapi.json")


async def check_global_rate_limit(
    redis: Any, *, ip: str, path: str
) -> tuple[bool, int]:
    """Check per-IP global rate limit. Returns ``(allowed, retry_after_seconds)``.

    Limits (REG-05 T292):
    - /health, /metrics: exempt — always allowed, 0 retry_after
    - /docs, /redoc, /openapi.json: 10 req/min
    - All other routes: 600 req/min

    ``retry_after_seconds`` is the number of seconds until the current
    fixed window resets (meaningful only when ``allowed`` is False).
    """
    # Exempt paths — no rate limiting applied
    for prefix in _EXEMPT_PATH_PREFIXES:
        if path == prefix or path.startswith(f"{prefix}/"):
            return True, 0

    is_docs = any(path.startswith(p) for p in _DOCS_PATH_PREFIXES)
    limit = _DOCS_LIMIT_PER_MIN if is_docs else _GLOBAL_LIMIT_PER_MIN
    key_suffix = "docs" if is_docs else "api"

    now = int(time.time())
    window = now // 60
    key = f"{_GLOBAL_RL_PREFIX}:{ip}:{key_suffix}:1m:{window}"

    async with redis.pipeline(transaction=False) as pipe:
        pipe.incr(key)
        pipe.expire(key, 62)
        results = await pipe.execute()

    count = int(results[0])
    if count > limit:
        retry_after = 60 - (now % 60)
        return False, retry_after
    return True, 0
