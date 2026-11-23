"""asyncpg raw-SQL connection pool helpers."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from .config import DatabaseConfig
from .logging import redact_secret_text
from .sql import ensure_sql_id

T = TypeVar("T")


class DatabaseUnavailableError(RuntimeError):
    """Raised when the configured PostgreSQL service cannot be reached safely."""


async def create_pool(config: DatabaseConfig, *, min_size: int = 1, max_size: int = 10):
    """Create an asyncpg pool for raw-SQL repositories.

    Pool creation retries transient Patroni/HAProxy connect drops with backoff
    ([[pg-patroni-transient-drop]]): a single transient timeout must not fail
    startup (or flake an integration test whose fixture builds a pool). Only
    raise ``DatabaseUnavailableError`` once the retry budget is exhausted
    (genuine outage / misconfiguration). Called at startup / per test-fixture
    (NOT per request — pooling happens once), so the bounded backoff is safe.
    """

    try:
        import asyncpg
    except ImportError as exc:  # pragma: no cover - exercised by startup smoke in missing envs
        raise DatabaseUnavailableError("asyncpg package is required") from exc
    last_exc: Exception | None = None
    for delay in (0.0, 1.0, 2.0, 4.0):
        if delay:
            await asyncio.sleep(delay)
        try:
            return await asyncpg.create_pool(
                config.database_url, min_size=min_size, max_size=max_size
            )
        except Exception as exc:  # noqa: BLE001 - retry transient; raise after exhaustion
            last_exc = exc
    message = redact_secret_text(str(last_exc))
    raise DatabaseUnavailableError(
        f"PostgreSQL connection failed after retries: {message}"
    ) from last_exc


async def fetch_one(connection: Any, sql_text: str, *args: Any):
    """Validate and execute a single-row raw SQL query."""

    ensure_sql_id(sql_text, context="fetch_one")
    return await connection.fetchrow(sql_text, *args)


async def fetch_all(connection: Any, sql_text: str, *args: Any):
    """Validate and execute a multi-row raw SQL query."""

    ensure_sql_id(sql_text, context="fetch_all")
    return await connection.fetch(sql_text, *args)


async def execute(connection: Any, sql_text: str, *args: Any) -> str:
    """Validate and execute a raw SQL command."""

    ensure_sql_id(sql_text, context="execute")
    return await connection.execute(sql_text, *args)


async def in_transaction(pool: Any, work: Callable[[Any], Awaitable[T]]) -> T:
    """Run ``work`` inside a single asyncpg transaction."""

    async with pool.acquire() as connection, connection.transaction():
        return await work(connection)


# svc-viability-v3 C8 — Patroni transient leader rotation produces
# "server closed the connection unexpectedly" mid-request even when the
# cluster is healthy. ``with_retry`` wraps idempotent read paths (or
# mutations fronted by the idempotency-key middleware, see ADR-011) with
# exponential backoff + jitter so a transient drop does not surface as a
# 500 to callers.
#
# Idempotency boundary: callers MUST ensure the wrapped operation is
# naturally idempotent or is fronted by the idempotency-key middleware.
# Otherwise a transient drop after a partial commit can re-execute
# mutations. Memory rule: [[pg-patroni-transient-drop]].

def with_retry(
    *,
    max_attempts: int = 5,
    base: float = 1.0,
    max_delay: float = 8.0,
    jitter: float = 0.5,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Retry decorator for transient asyncpg disconnections.

    Exponential backoff: 1.0, 2.0, 4.0, 8.0s (capped at ``max_delay``) plus
    uniform jitter in ``[0, jitter)``.
    """
    try:
        from asyncpg.exceptions import (  # type: ignore[import-not-found]
            ConnectionDoesNotExistError,
            InterfaceError,
            PostgresConnectionError,
        )
        transient_errors: tuple[type[BaseException], ...] = (
            ConnectionDoesNotExistError,
            InterfaceError,
            PostgresConnectionError,
            ConnectionError,
            OSError,
        )
    except ImportError:
        transient_errors = (ConnectionError, OSError)

    def decorator(
        fn: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: BaseException | None = None
            for attempt in range(max_attempts):
                try:
                    return await fn(*args, **kwargs)
                except transient_errors as exc:
                    last_exc = exc
                    if attempt == max_attempts - 1:
                        break
                    delay = min(base * (2 ** attempt), max_delay) + random.uniform(0, jitter)
                    await asyncio.sleep(delay)
            assert last_exc is not None
            raise last_exc
        return wrapper

    return decorator
