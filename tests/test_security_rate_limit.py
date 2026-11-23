"""Rate limiting tests (REG-05 T280, T292).

Task IDs: T280, T292
Ref: docs/regulations/REG-05_internet_security.md §3 §10
     apps/api/harness/core/rate_limit.py (check_login_rate_limit, check_refresh_rate_limit,
                                           check_global_rate_limit)
     apps/api/harness/api/routers/auth.py (login, refresh — T280 integration)

Covers:
- Unit: check_login_rate_limit returns False (rate-limited) on the 11th call (T280)
- Unit: check_refresh_rate_limit returns False on the 31st call (T280)
- Unit: check_global_rate_limit returns (True, 0) for /health — exempt path (T292)
- Unit: check_global_rate_limit returns (True, 0) for /metrics — exempt path (T292)
- Unit: check_global_rate_limit returns (False, >0) for /docs after 10 calls (T292 docs limit)
- Integration: 11th POST /auth/login from same (IP, username) → 429 (T280)
- Integration: 31st POST /auth/refresh from same IP → 429 (T280)
- Integration: /health remains 200 after repeated requests — exempt from global limit (T292)

Each test uses a unique synthetic IP address to prevent cross-test counter pollution.
Rate limit windows are fixed 60-second buckets; tests complete well within one window.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "tests"


# ---------------------------------------------------------------------------
# Server helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _prepare_database() -> None:
    asyncpg = pytest.importorskip("asyncpg")
    from db.migrator import database_url_from_env, load_env_file
    from db.migrator import run as run_migrations
    from db.seed import apply_profile

    load_env_file(PROJECT_ROOT / ".env")
    try:
        await run_migrations()
        connection = await connect_with_retry(asyncpg, database_url_from_env())
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    try:
        await apply_profile(connection, "full-mvp")
    finally:
        await connection.close()


@pytest.fixture(scope="module")
def api_server() -> str:  # type: ignore[return]
    """Running API server for rate-limit integration tests."""
    asyncio.run(_prepare_database())
    port = _free_port()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "rate-limit.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}:{env.get('PYTHONPATH', '')}"
    env["HARNESS_EMAIL_SEND_ENABLED"] = "false"
    # Use locally available Redis instead of .env's remote host (redis.internal.example:6379)
    env["REDIS_URL"] = "redis://localhost:6379/15"
    env["REDIS_SENTINEL_HOSTS"] = ""
    env["REDIS_HOST"] = ""
    command = [
        str(Path(os.environ.get("PYTHON_PATH", "/opt/conda/envs/wm_env/bin/python"))),
        "-m", "uvicorn", "apps.api.harness.main:app",
        "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
    ]
    with log_path.open("w") as log_file:
        process = subprocess.Popen(command, cwd=PROJECT_ROOT, env=env,
                                   stdout=log_file, stderr=log_file)
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 25
        while time.time() < deadline:
            if process.poll() is not None:
                pytest.skip(f"API server exited; see {log_path}")
            try:
                with urllib.request.urlopen(f"{base_url}/health", timeout=2) as r:
                    if json.load(r).get("status") == "ok":
                        break
            except Exception:  # noqa: BLE001
                pass
            time.sleep(0.25)
        else:
            pytest.skip(f"API server not healthy; see {log_path}")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------

def _post_login(base_url: str, email: str, password: str, *,
                forwarded_ip: str) -> int:
    """POST /auth/login with synthetic X-Forwarded-For; return HTTP status code."""
    body = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{base_url}/auth/login", data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Forwarded-For": forwarded_ip,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _post_refresh(base_url: str, token: str, *, forwarded_ip: str) -> int:
    """POST /auth/refresh with dummy Bearer + synthetic IP; return HTTP status code."""
    req = urllib.request.Request(
        f"{base_url}/auth/refresh",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Forwarded-For": forwarded_ip,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _get(base_url: str, path: str, *, forwarded_ip: str) -> int:
    """GET a path with synthetic X-Forwarded-For; return HTTP status code."""
    req = urllib.request.Request(
        f"{base_url}{path}",
        headers={"Accept": "application/json", "X-Forwarded-For": forwarded_ip},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


# ---------------------------------------------------------------------------
# Redis helper for unit tests
# ---------------------------------------------------------------------------

async def _open_redis():  # type: ignore[return]
    """Return an async Redis client pointed at localhost:6379/15, or skip if unreachable.

    Uses the locally available Redis (db 15 for test isolation) rather than the
    .env remote host (redis.internal.example:6379) which may be unreachable in CI/dev.
    """
    try:
        import redis.asyncio as aioredis  # type: ignore[import]
        client = aioredis.from_url("redis://localhost:6379/15")
        await client.ping()  # Fail fast — skip rather than fail if Redis absent
        return client
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"Local Redis unavailable: {exc}")


# ---------------------------------------------------------------------------
# Unit tests — rate limit functions (real Redis, no HTTP server)
# ---------------------------------------------------------------------------

@pytest.mark.security
def test_login_rate_limit_returns_false_on_11th_call():
    """check_login_rate_limit returns False on the 11th call for the same (IP, username) (T280)."""
    from apps.api.harness.core.rate_limit import check_login_rate_limit

    unique_ip = f"10.200.{uuid.uuid4().hex[:3]}.1"
    unique_user = f"rl-unit-{uuid.uuid4().hex}@test.invalid"

    async def _run() -> None:
        redis = await _open_redis()
        try:
            for i in range(10):
                allowed = await check_login_rate_limit(redis, ip=unique_ip, username=unique_user)
                assert allowed is True, (
                    f"Call {i + 1} of 10 must be allowed; check_login_rate_limit returned False (T280)"
                )
            eleventh = await check_login_rate_limit(redis, ip=unique_ip, username=unique_user)
            assert eleventh is False, (
                "11th check_login_rate_limit call must return False (rate-limited) (T280)"
            )
        finally:
            await redis.aclose()

    asyncio.run(_run())


@pytest.mark.security
def test_refresh_rate_limit_returns_false_on_31st_call():
    """check_refresh_rate_limit returns False on the 31st call for the same IP (T280)."""
    from apps.api.harness.core.rate_limit import check_refresh_rate_limit

    unique_ip = f"10.201.{uuid.uuid4().hex[:3]}.1"

    async def _run() -> None:
        redis = await _open_redis()
        try:
            for i in range(30):
                allowed = await check_refresh_rate_limit(redis, ip=unique_ip)
                assert allowed is True, (
                    f"Call {i + 1} of 30 must be allowed; check_refresh_rate_limit returned False (T280)"
                )
            thirty_first = await check_refresh_rate_limit(redis, ip=unique_ip)
            assert thirty_first is False, (
                "31st check_refresh_rate_limit call must return False (rate-limited) (T280)"
            )
        finally:
            await redis.aclose()

    asyncio.run(_run())


@pytest.mark.security
def test_global_rate_limit_health_path_always_exempt():
    """check_global_rate_limit returns (True, 0) for /health regardless of call count (T292)."""
    from apps.api.harness.core.rate_limit import check_global_rate_limit

    unique_ip = f"10.202.{uuid.uuid4().hex[:3]}.1"

    async def _run() -> None:
        redis = await _open_redis()
        try:
            for _ in range(5):
                allowed, retry_after = await check_global_rate_limit(
                    redis, ip=unique_ip, path="/health"
                )
                assert allowed is True, "/health must always be exempt from rate limiting (T292)"
                assert retry_after == 0, "/health retry_after must be 0 (T292)"
        finally:
            await redis.aclose()

    asyncio.run(_run())


@pytest.mark.security
def test_global_rate_limit_metrics_path_always_exempt():
    """check_global_rate_limit returns (True, 0) for /metrics regardless of call count (T292)."""
    from apps.api.harness.core.rate_limit import check_global_rate_limit

    unique_ip = f"10.203.{uuid.uuid4().hex[:3]}.1"

    async def _run() -> None:
        redis = await _open_redis()
        try:
            allowed, retry_after = await check_global_rate_limit(
                redis, ip=unique_ip, path="/metrics"
            )
            assert allowed is True, "/metrics must be exempt from rate limiting (T292)"
            assert retry_after == 0
        finally:
            await redis.aclose()

    asyncio.run(_run())


@pytest.mark.security
def test_global_rate_limit_docs_path_uses_reduced_10_per_min_limit():
    """check_global_rate_limit returns (False, >0) for /docs after 10 calls — docs limit (T292)."""
    from apps.api.harness.core.rate_limit import check_global_rate_limit

    unique_ip = f"10.204.{uuid.uuid4().hex[:3]}.1"

    async def _run() -> None:
        redis = await _open_redis()
        try:
            for i in range(10):
                allowed, _ = await check_global_rate_limit(
                    redis, ip=unique_ip, path="/docs"
                )
                assert allowed is True, (
                    f"Call {i + 1} of 10 to /docs must be allowed (docs limit=10/min, T292)"
                )
            allowed_11, retry_after = await check_global_rate_limit(
                redis, ip=unique_ip, path="/docs"
            )
            assert allowed_11 is False, (
                "11th call to /docs must be rate-limited by reduced docs limit (T292)"
            )
            assert retry_after > 0, (
                f"retry_after must be > 0 when rate-limited; got {retry_after} (T292)"
            )
        finally:
            await redis.aclose()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Integration tests — HTTP via running server
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_11th_login_attempt_from_same_ip_and_username_returns_429(api_server: str):
    """11 POST /auth/login from same (IP, username) within one window → 11th is 429 (REG-05 T280)."""
    # Unique IP per test ensures no counter bleed from other tests.
    # Use int() to convert hex bytes → valid decimal IPv4 octets (PostgreSQL inet column).
    unique_ip = f"10.10.{int(uuid.uuid4().hex[:2], 16)}.{int(uuid.uuid4().hex[:2], 16)}"
    email = f"rl-intg-{uuid.uuid4().hex}@ratelimittest.invalid"

    # Requests 1–10: rate limit not exceeded; wrong credentials → 401 (not 429)
    for attempt in range(10):
        status = _post_login(api_server, email, "wrong-pass", forwarded_ip=unique_ip)
        assert status != 429, (
            f"Login attempt {attempt + 1} of 10 must not be rate-limited; got 429 (T280)"
        )

    # Request 11: rate limit exceeded → 429
    status_11 = _post_login(api_server, email, "wrong-pass", forwarded_ip=unique_ip)
    assert status_11 == 429, (
        f"11th login attempt from same (IP, username) must return 429; got {status_11} (T280)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_31st_refresh_attempt_from_same_ip_returns_429(api_server: str):
    """31 POST /auth/refresh from same IP within one window → 31st is 429 (REG-05 T280)."""
    unique_ip = f"10.11.{int(uuid.uuid4().hex[:2], 16)}.{int(uuid.uuid4().hex[:2], 16)}"
    dummy_token = "dummy.token.value"

    # Requests 1–30: rate limit not exceeded; bad token → 401 (not 429)
    for attempt in range(30):
        status = _post_refresh(api_server, dummy_token, forwarded_ip=unique_ip)
        assert status != 429, (
            f"Refresh attempt {attempt + 1} of 30 must not be rate-limited; got 429 (T280)"
        )

    # Request 31: rate limit exceeded → 429 (checked before token decode)
    status_31 = _post_refresh(api_server, dummy_token, forwarded_ip=unique_ip)
    assert status_31 == 429, (
        f"31st refresh attempt from same IP must return 429; got {status_31} (T280)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_health_endpoint_always_200_under_repeated_requests(api_server: str):
    """/health is exempt from global per-IP rate limit and returns 200 repeatedly (REG-05 T292)."""
    unique_ip = f"10.12.{int(uuid.uuid4().hex[:2], 16)}.{int(uuid.uuid4().hex[:2], 16)}"
    for i in range(20):
        status = _get(api_server, "/health", forwarded_ip=unique_ip)
        assert status == 200, (
            f"/health request {i + 1} returned {status}; "
            "/health must be exempt from rate limiting (T292)"
        )
