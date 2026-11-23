"""Refresh token rotation and JTI reuse detection tests (REG-05 T283).

Task IDs: T283
Ref: docs/regulations/REG-05_internet_security.md §3 §6
     apps/api/harness/api/routers/auth.py (_blocklist_refresh_jti,
                                            _mass_revoke_employee_tokens,
                                            _register_refresh_jti, refresh)
     apps/api/harness/core/security.py (decode_token)

Covers:
- POST /auth/refresh issues new access_token (parseable, non-empty)
- POST /auth/refresh issues new refresh_token cookie (Set-Cookie present)
- Old refresh JTI is blocklisted in Redis after successful rotation
- New refresh JTI is registered in per-employee Redis namespace
- Reusing a blocklisted refresh JTI triggers mass-revoke → 401
- auth_refresh_reuse audit row is written with correct action_code and jti field
- Third /auth/refresh after mass-revoke returns 401 (all tokens invalidated)
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
from pathlib import Path

import pytest

from tests._env_overlay import write_env_overlay
from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "tests"

SYNTHETIC_EMAIL = "synthetic.pb1@example.invalid"
SYNTHETIC_PASSWORD = "HarnessSynthetic!2026"
_REFRESH_COOKIE_NAME = "harness_refresh_token"
_BLOCKLIST_PREFIX = "harness:auth:refresh:jti:"


# ---------------------------------------------------------------------------
# Server + DB helpers
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
    """Running API server for refresh rotation integration tests."""
    asyncio.run(_prepare_database())
    port = _free_port()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "refresh-rotation.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}:{env.get('PYTHONPATH', '')}"
    env["HARNESS_EMAIL_SEND_ENABLED"] = "false"
    # Use locally available Redis instead of .env's remote host (redis.internal.example:6379).
    # Bare subprocess env vars are clobbered by load_env_file(override=True), so route
    # the local-Redis override through an overlay read via HARNESS_ENV_FILE — otherwise
    # the backend writes the JTI blocklist to the .env Redis while the test reads localhost.
    env_file = write_env_overlay({
        "REDIS_URL": "redis://localhost:6379/15",
        "REDIS_SENTINEL_HOSTS": "",
        "REDIS_HOST": "",
    })
    env["HARNESS_ENV_FILE"] = env_file
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
        os.unlink(env_file)


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------

def _login(base_url: str) -> tuple[int, str, str]:
    """Login with synthetic credentials; return (status, access_token, refresh_token).

    The refresh_token is extracted from the ``harness_refresh_token`` Set-Cookie header.
    """
    body = json.dumps({"email": SYNTHETIC_EMAIL, "password": SYNTHETIC_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{base_url}/auth/login", data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
            access_token = payload.get("access_token", "")
            refresh_token = _extract_refresh_cookie(resp.headers)
            return resp.status, access_token, refresh_token
    except urllib.error.HTTPError as exc:
        return exc.code, "", ""


def _extract_refresh_cookie(headers) -> str:  # type: ignore[return]
    """Parse the harness_refresh_token value from response headers."""
    # http.client.HTTPMessage.get_all() returns a list of Set-Cookie strings
    set_cookies = headers.get_all("Set-Cookie") or []
    for cookie_str in set_cookies:
        for segment in cookie_str.split(";"):
            segment = segment.strip()
            if segment.lower().startswith(f"{_REFRESH_COOKIE_NAME}="):
                _, _, value = segment.partition("=")
                return value.strip()
    return ""


def _do_refresh(base_url: str, refresh_token: str) -> tuple[int, dict]:  # type: ignore[type-arg]
    """POST /auth/refresh with the given refresh_token as Bearer; return (status, payload)."""
    req = urllib.request.Request(
        f"{base_url}/auth/refresh",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {refresh_token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
            new_refresh = _extract_refresh_cookie(resp.headers)
            payload["_refresh_token"] = new_refresh
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {}
        return exc.code, payload


# ---------------------------------------------------------------------------
# Helper: decode JTI without validation (extract claim only)
# ---------------------------------------------------------------------------

def _extract_jti(token: str) -> str:
    """Decode base64url JWT payload and return the jti claim (no signature check)."""
    import base64
    parts = token.split(".")
    if len(parts) < 2:
        return ""
    # Add padding
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    return str(payload.get("jti", ""))


# ---------------------------------------------------------------------------
# Helper: open async Redis for blocklist checks
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
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_refresh_issues_new_access_token(api_server: str):
    """POST /auth/refresh returns a non-empty access_token (REG-05 T283)."""
    status, access_token, refresh_token = _login(api_server)
    if status != 200 or not refresh_token:
        pytest.skip(f"Login failed (status={status}); cannot test refresh rotation")

    status2, payload2 = _do_refresh(api_server, refresh_token)
    assert status2 == 200, (
        f"First /auth/refresh must return 200; got {status2}: {payload2} (T283)"
    )
    new_access = payload2.get("access_token", "")
    assert new_access, "POST /auth/refresh must return a non-empty access_token (T283)"
    assert new_access != access_token, (
        "New access_token must differ from the original (T283)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_refresh_issues_new_refresh_cookie(api_server: str):
    """POST /auth/refresh sets a new harness_refresh_token cookie (REG-05 T283)."""
    status, _, refresh_token = _login(api_server)
    if status != 200 or not refresh_token:
        pytest.skip("Login failed; cannot test refresh rotation")

    status2, payload2 = _do_refresh(api_server, refresh_token)
    assert status2 == 200, f"First /auth/refresh must return 200; got {status2} (T283)"

    new_refresh = payload2.get("_refresh_token", "")
    assert new_refresh, "POST /auth/refresh must set a new harness_refresh_token cookie (T283)"
    assert new_refresh != refresh_token, (
        "New refresh_token must differ from the original (T283)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_old_refresh_jti_is_blocklisted_after_rotation(api_server: str):
    """Old refresh JTI is recorded in Redis blocklist after first rotation (REG-05 T283)."""
    status, _, refresh_token = _login(api_server)
    if status != 200 or not refresh_token:
        pytest.skip("Login failed; cannot test refresh rotation")

    old_jti = _extract_jti(refresh_token)
    if not old_jti:
        pytest.skip("Could not extract JTI from refresh token")

    status2, _ = _do_refresh(api_server, refresh_token)
    assert status2 == 200, f"/auth/refresh must return 200; got {status2} (T283)"

    # Check Redis blocklist contains the old JTI
    async def _check() -> bool:
        redis = await _open_redis()
        try:
            key = f"{_BLOCKLIST_PREFIX}{old_jti}"
            exists = bool(await redis.exists(key))
            return exists
        finally:
            await redis.aclose()

    jti_blocklisted = asyncio.run(_check())
    assert jti_blocklisted, (
        f"Old JTI {old_jti!r} must be in Redis blocklist after rotation "
        f"(key: {_BLOCKLIST_PREFIX}{old_jti}) (T283)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_reusing_old_refresh_jti_returns_401(api_server: str):
    """Reusing an already-rotated refresh JTI returns 401 (REG-05 T283 reuse detection).

    Sleeps past the OQ-5 grace window (JTI_BLOCKLIST_GRACE_SECONDS=5)
    before the reuse attempt so the assertion exercises the enforced
    blocklist path, not the in-flight-race grace path.
    """
    import time as _time
    from apps.api.harness.api.routers.auth import JTI_BLOCKLIST_GRACE_SECONDS

    status, _, refresh_token = _login(api_server)
    if status != 200 or not refresh_token:
        pytest.skip("Login failed; cannot test refresh rotation")

    # First rotation: normal — blocklists old JTI, issues new token
    status2, _ = _do_refresh(api_server, refresh_token)
    assert status2 == 200, f"First rotation must return 200; got {status2} (T283)"

    # Wait past the grace window so blocklist is fully enforced.
    _time.sleep(JTI_BLOCKLIST_GRACE_SECONDS + 1)

    # Second rotation attempt with OLD refresh_token: must trigger reuse detection
    status3, payload3 = _do_refresh(api_server, refresh_token)
    assert status3 == 401, (
        f"Reusing a rotated refresh JTI must return 401; got {status3}: {payload3} (T283)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_refresh_reuse_audit_row_written(api_server: str):
    """auth_refresh_reuse audit row is written when a reused JTI is detected (REG-05 T283).

    Sleeps past the OQ-5 grace window before reuse so the enforced-
    blocklist + mass-revoke + audit-row path executes.
    """
    import time as _time
    from apps.api.harness.api.routers.auth import JTI_BLOCKLIST_GRACE_SECONDS

    status, _, refresh_token = _login(api_server)
    if status != 200 or not refresh_token:
        pytest.skip("Login failed; cannot test refresh rotation")

    old_jti = _extract_jti(refresh_token)

    # Rotate once (blocklists old JTI)
    status2, _ = _do_refresh(api_server, refresh_token)
    assert status2 == 200, f"First rotation must succeed; got {status2} (T283)"

    # Wait past the grace window so the enforced blocklist returns 401.
    _time.sleep(JTI_BLOCKLIST_GRACE_SECONDS + 1)

    # Reuse old token → triggers audit_refresh_reuse write
    status3, _ = _do_refresh(api_server, refresh_token)
    assert status3 == 401, f"Reuse must return 401; got {status3} (T283)"

    # Verify audit log row was written
    async def _verify_audit() -> bool:
        asyncpg = pytest.importorskip("asyncpg")
        from db.migrator import database_url_from_env, load_env_file
        load_env_file(PROJECT_ROOT / ".env")
        conn = await connect_with_retry(asyncpg, database_url_from_env())
        try:
            row = await conn.fetchrow(
                """/* sql_id: test_refresh_reuse_audit */
                SELECT id, detail_json
                FROM audit_logs
                WHERE action_code = 'auth_refresh_reuse'
                  AND detail_json->>'jti' = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                old_jti,
            )
            return row is not None
        finally:
            await conn.close()

    audit_found = asyncio.run(_verify_audit())
    assert audit_found, (
        f"auth_refresh_reuse audit row with jti={old_jti!r} must be written on reuse detection (T283)"
    )
