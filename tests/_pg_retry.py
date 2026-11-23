"""Shared transient-retry for integration-test PostgreSQL connects.

A single transient Patroni/HAProxy connect drop ([[pg-patroni-transient-drop]]) must
not flake an integration test nor — via a skip-on-error fixture — silently mask it in
a full-suite run. ``connect_with_retry`` retries ``asyncpg.connect`` with backoff and a
per-attempt timeout, surfacing the last error only after the budget is exhausted (a
genuine outage / misconfig still fails — visibly, never silently skipped).

Pooled fixtures get the same resilience from ``core.db.create_pool``'s own retry; this
helper is for the raw ``asyncpg.connect`` integration tests.

Usage (the connect is the only line that changes):

    from tests._pg_retry import connect_with_retry
    connection = await connect_with_retry(asyncpg, database_url)
"""

from __future__ import annotations

import asyncio
from typing import Any

# Backoff schedule (seconds); the first attempt is immediate.
_RETRY_DELAYS: tuple[float, ...] = (0.0, 1.0, 2.0, 4.0)


async def connect_with_retry(
    asyncpg: Any, database_url: str, *, timeout: float = 15.0
) -> Any:
    """Return a live asyncpg connection, retrying transient connect drops.

    ``asyncpg`` is passed in (tests resolve it via ``pytest.importorskip``). A
    per-attempt ``asyncio.wait_for`` bounds a hung connect so the budget cannot
    stall; the last error is raised only after all attempts fail.
    """
    last_exc: Exception | None = None
    for delay in _RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            return await asyncio.wait_for(asyncpg.connect(database_url), timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - retry transient; raise after exhaustion
            last_exc = exc
    raise last_exc or RuntimeError("PostgreSQL unreachable after connect retries")
