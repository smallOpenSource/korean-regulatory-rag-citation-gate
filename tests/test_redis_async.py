"""Async Redis sentinel integration check (US-W6-1, R22/R23).

Mirrors tests/test_redis.py for the async client path. Verifies that
`create_async_redis_client` connects via Sentinel.master_for and the resulting
client can ping, round-trip a string, and reports a SentinelManagedConnection
connection class (positive assert against silent REDIS_URL fallback).

These tests use real Redis/Sentinel credentials from .env. They do not mock or
hardcode service details. Test data keys are namespaced and deleted after use.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest

from apps.api.harness.core.config import load_config
from apps.api.harness.core.redis_client import create_async_redis_client

pytest.importorskip("redis")
pytest.importorskip("redis.asyncio.sentinel")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@pytest.fixture()
def redis_config():
    _load_env()
    config = load_config(PROJECT_ROOT / ".env")
    if not config.redis.sentinel_hosts or not config.redis.sentinel_service_name:
        pytest.skip("REDIS_SENTINEL_HOSTS/REDIS_SENTINEL_SERVICE_NAME not configured")
    return config.redis


def test_async_redis_sentinel_ping(redis_config):
    """Async client routed via Sentinel must reach a live master and ping."""

    async def _exercise():
        client = create_async_redis_client(redis_config)
        try:
            return await client.ping()
        finally:
            await client.aclose()

    assert asyncio.run(_exercise()) is True


def test_async_redis_sentinel_string_roundtrip(redis_config):
    """Async client must SET/GET on the Sentinel-elected master."""

    key = f"harness:test:async:{uuid.uuid4().hex}"

    async def _exercise():
        client = create_async_redis_client(redis_config)
        try:
            await client.set(key, "ok", ex=60)
            value = await client.get(key)
            await client.delete(key)
            return value
        finally:
            await client.aclose()

    assert asyncio.run(_exercise()) == "ok"


def test_async_redis_client_uses_sentinel_managed_connection(redis_config):
    """Connection pool must use SentinelManagedConnection — positive assert against
    silent REDIS_URL fallback that would otherwise yield a working but topology-wrong client.
    """

    from redis.asyncio.sentinel import SentinelManagedConnection

    async def _exercise():
        client = create_async_redis_client(redis_config)
        try:
            pool = client.connection_pool
            return pool.connection_class
        finally:
            await client.aclose()

    connection_class = asyncio.run(_exercise())
    assert issubclass(connection_class, SentinelManagedConnection), (
        f"Expected SentinelManagedConnection, got {connection_class.__name__}. "
        "Sentinel path likely fell back to REDIS_URL — check REDIS_SENTINEL_* env vars."
    )
