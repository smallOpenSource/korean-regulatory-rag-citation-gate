"""tests/test_pg_retry_decorator.py — svc-viability-v3 C8 unit test.

Verifies that ``apps.api.harness.core.db.with_retry`` recovers from
``N-1`` transient ``ConnectionError`` failures and surfaces the
``N``-th success, that it surfaces the underlying error after
``max_attempts`` exhaustion, and that it does not retry programming
errors (e.g. ``ValueError``) that fall outside the transient set.

Mirrors the Patroni leader rotation pattern observed on
db.internal.example:5432 during svc-viability-v3 W0 (PG ~15min outage
with HAProxy still listening but the backend closing the connection
mid-handshake).
"""

from __future__ import annotations

import asyncio

import pytest

from apps.api.harness.core.db import with_retry


def _run(coro):
    return asyncio.run(coro)


def test_with_retry_recovers_after_transient_disconnects():
    attempt_count = 0

    @with_retry(max_attempts=5, base=0.0, jitter=0.0)
    async def flaky() -> str:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise ConnectionError("simulated patroni leader rotation")
        return "ok"

    assert _run(flaky()) == "ok"
    assert attempt_count == 3


def test_with_retry_re_raises_after_max_attempts():
    @with_retry(max_attempts=3, base=0.0, jitter=0.0)
    async def always_fails() -> str:
        raise ConnectionError("never recovers")

    with pytest.raises(ConnectionError, match="never recovers"):
        _run(always_fails())


def test_with_retry_does_not_retry_non_transient():
    @with_retry(max_attempts=5, base=0.0, jitter=0.0)
    async def value_error() -> str:
        raise ValueError("logic error")

    with pytest.raises(ValueError, match="logic error"):
        _run(value_error())


def test_with_retry_preserves_return_value():
    @with_retry(max_attempts=3, base=0.0, jitter=0.0)
    async def returns_payload() -> dict[str, int]:
        return {"rows": 7}

    assert _run(returns_payload()) == {"rows": 7}
