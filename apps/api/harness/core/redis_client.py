"""Redis/Sentinel client factory and lock helpers."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

from .config import RedisConfig
from .logging import redact_secret_text


class RedisUnavailableError(RuntimeError):
    """Raised when Redis is not configured or reachable."""


@dataclass(frozen=True)
class RedisLock:
    key: str
    owner: str
    ttl_seconds: int


def parse_sentinel_hosts(value: str | None) -> list[tuple[str, int]]:
    """Parse `host:port,host:port` Sentinel configuration."""

    hosts: list[tuple[str, int]] = []
    if not value:
        return hosts
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        host, _, port = item.partition(":")
        hosts.append((host, int(port or "26379")))
    return hosts


def create_redis_client(config: RedisConfig):
    """Create a real Redis client from URL, Sentinel, or host/port config."""

    try:
        import redis
        from redis.sentinel import Sentinel
    except ImportError as exc:  # pragma: no cover - missing dependency boundary
        raise RedisUnavailableError("redis package is required") from exc

    password = config.password
    sentinel_hosts = parse_sentinel_hosts(config.sentinel_hosts)
    if sentinel_hosts and config.sentinel_service_name:
        sentinel = Sentinel(
            sentinel_hosts,
            socket_timeout=config.socket_timeout,
            socket_connect_timeout=config.socket_connect_timeout,
            sentinel_kwargs={"password": password} if password else None,
        )
        return sentinel.master_for(
            config.sentinel_service_name,
            password=password,
            db=config.db,
            decode_responses=True,
            socket_timeout=config.socket_timeout,
            socket_connect_timeout=config.socket_connect_timeout,
            max_connections=config.max_connections,
        )

    if config.redis_url:
        try:
            return redis.Redis.from_url(
                config.redis_url,
                decode_responses=True,
                socket_timeout=config.socket_timeout,
                socket_connect_timeout=config.socket_connect_timeout,
                max_connections=config.max_connections,
            )
        except Exception as exc:  # noqa: BLE001
            raise RedisUnavailableError(redact_secret_text(str(exc))) from exc

    if not config.host or not config.port:
        raise RedisUnavailableError("Redis host/port or REDIS_URL is required")
    return redis.Redis(
        host=config.host,
        port=config.port,
        password=password,
        db=config.db,
        decode_responses=True,
        socket_timeout=config.socket_timeout,
        socket_connect_timeout=config.socket_connect_timeout,
        max_connections=config.max_connections,
    )


def create_async_redis_client(config: RedisConfig):
    """Create an async Redis client (redis.asyncio) from Sentinel, URL, or host/port config.

    Sentinel topology (env REDIS_SENTINEL_HOSTS + REDIS_SENTINEL_SERVICE_NAME) is preferred
    when configured — the async client connects via `redis.asyncio.sentinel.Sentinel.master_for`
    so the application always reaches the current master and follows failover.
    Falls back to REDIS_URL or REDIS_HOST/REDIS_PORT only when no sentinel config is provided.

    Returns a redis.asyncio.Redis instance; callers must await aclose() on shutdown.
    """
    try:
        from redis import asyncio as aioredis
        from redis.asyncio.sentinel import Sentinel as AsyncSentinel
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise RedisUnavailableError("redis[asyncio] package is required") from exc

    password = config.password
    sentinel_hosts = parse_sentinel_hosts(config.sentinel_hosts)
    if sentinel_hosts and config.sentinel_service_name:
        sentinel = AsyncSentinel(
            sentinel_hosts,
            socket_timeout=config.socket_timeout,
            socket_connect_timeout=config.socket_connect_timeout,
            sentinel_kwargs={"password": password} if password else None,
        )
        return sentinel.master_for(
            config.sentinel_service_name,
            password=password,
            db=config.db,
            decode_responses=True,
            socket_timeout=config.socket_timeout,
            socket_connect_timeout=config.socket_connect_timeout,
            max_connections=config.max_connections,
        )

    if config.redis_url:
        try:
            return aioredis.Redis.from_url(
                config.redis_url,
                decode_responses=True,
                socket_timeout=config.socket_timeout,
                socket_connect_timeout=config.socket_connect_timeout,
                max_connections=config.max_connections,
            )
        except Exception as exc:  # noqa: BLE001
            raise RedisUnavailableError(redact_secret_text(str(exc))) from exc

    if not config.host or not config.port:
        raise RedisUnavailableError("Redis host/port or REDIS_URL is required for async client")
    return aioredis.Redis(
        host=config.host,
        port=config.port,
        password=password,
        db=config.db,
        decode_responses=True,
        socket_timeout=config.socket_timeout,
        socket_connect_timeout=config.socket_connect_timeout,
        max_connections=config.max_connections,
    )


def acquire_lock(
    client: Any, *, key: str, ttl_seconds: int, owner: str | None = None
) -> RedisLock | None:
    """Acquire a Redis SETNX lock with owner-value release semantics."""

    lock_owner = owner or f"{uuid.uuid4().hex}:{int(time.time())}"
    acquired = client.set(key, lock_owner, nx=True, ex=ttl_seconds)
    if acquired:
        return RedisLock(key=key, owner=lock_owner, ttl_seconds=ttl_seconds)
    return None


def release_lock(client: Any, lock: RedisLock) -> bool:
    """Release a lock only when the stored owner value still matches."""

    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """
    return bool(client.eval(script, 1, lock.key, lock.owner))
