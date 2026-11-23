"""Redis integration checks using the project .env contract.

These tests use real Redis/Sentinel credentials from .env. They do not mock or
hardcode service details. Test data keys are namespaced and deleted after use.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import pytest

from apps.api.harness.core.config import load_config
from apps.api.harness.core.redis_client import acquire_lock, create_redis_client, release_lock

redis = pytest.importorskip("redis")

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


@pytest.fixture(scope="module")
def redis_client():
    _load_env()
    config = load_config(PROJECT_ROOT / ".env")
    client = create_redis_client(config.redis)

    try:
        yield client
    finally:
        try:
            client.close()
        except AttributeError:
            client.connection_pool.disconnect()


def test_redis_ping(redis_client):
    assert redis_client.ping() is True


def test_redis_string_roundtrip(redis_client):
    key = f"harness:test:redis:{uuid.uuid4().hex}"
    try:
        assert redis_client.set(key, "ok", ex=60) is True
        assert redis_client.get(key) == "ok"
    finally:
        redis_client.delete(key)


def test_redis_pubsub_loopback(redis_client):
    channel = f"harness:test:pubsub:{uuid.uuid4().hex}"
    message = f"msg-{uuid.uuid4().hex}"
    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    try:
        pubsub.subscribe(channel)
        time.sleep(0.2)
        redis_client.publish(channel, message)

        deadline = time.time() + 5
        received = None
        while time.time() < deadline:
            item = pubsub.get_message(timeout=0.5)
            if item and item.get("type") == "message":
                received = item.get("data")
                break
        assert received == message
    finally:
        pubsub.close()


def test_redis_setnx_lock_owner_release(redis_client):
    key = f"harness:test:lock:{uuid.uuid4().hex}"
    try:
        first = acquire_lock(redis_client, key=key, ttl_seconds=60, owner="owner-a")
        assert first is not None
        assert acquire_lock(redis_client, key=key, ttl_seconds=60, owner="owner-b") is None
        assert redis_client.get(key) == "owner-a"
        assert release_lock(redis_client, first) is True
        assert redis_client.get(key) is None
    finally:
        redis_client.delete(key)
