"""WebSocket short-lived ticket tests (REG-05 T287, T297).

Task IDs: T287, T297
Ref: docs/regulations/REG-05_internet_security.md §3 §11
     apps/api/harness/api/routers/websocket.py (issue_ws_ticket, websocket_endpoint)
     _WS_TICKET_PREFIX = "harness:ws:ticket:"
     TICKET_TTL_SECONDS = 30
     WS_SUBPROTOCOL = "harness.v1"
     WS_CLOSE_UNAUTHORIZED = 4001
     WS_CLOSE_EXPIRED = 4002

Covers:
- POST /ws/ticket without Authorization header → 401 (requires auth)
- POST /ws/ticket with valid Bearer token → {ticket: UUID str, ttl_seconds: 30}
- Returned ticket is a valid UUID v4 string
- Redis key harness:ws:ticket:<ticket> exists with TTL ≤ 30 s after issuance
- WS /ws without Sec-WebSocket-Protocol: harness.v1 → server rejects connection (4001)
- WS /ws with valid subprotocol but non-existent ticket → close code 4002
- ws_ticket_issued audit row written on successful ticket issuance
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

SYNTHETIC_EMAIL = "synthetic.pb1@example.invalid"
SYNTHETIC_PASSWORD = "HarnessSynthetic!2026"
_WS_TICKET_PREFIX = "harness:ws:ticket:"
_WS_SUBPROTOCOL = "harness.v1"


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
    """Running API server for WebSocket ticket integration tests."""
    asyncio.run(_prepare_database())
    port = _free_port()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "ws-ticket.log"
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

def _get_access_token(base_url: str) -> str:
    """Login with synthetic credentials and return the access token."""
    body = json.dumps({"email": SYNTHETIC_EMAIL, "password": SYNTHETIC_PASSWORD}).encode()
    req = urllib.request.Request(
        f"{base_url}/auth/login", data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()).get("access_token", "")
    except urllib.error.HTTPError:
        return ""


def _post_ws_ticket(base_url: str, token: str | None = None) -> tuple[int, dict]:  # type: ignore[type-arg]
    """POST /ws/ticket with optional Bearer token; return (status, payload)."""
    headers: dict[str, str] = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{base_url}/ws/ticket", headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {}
        return exc.code, payload


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
# Tests — ticket issuance (HTTP, no WebSocket library required)
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_ws_ticket_endpoint_requires_authorization(api_server: str):
    """POST /ws/ticket without a Bearer token returns 401 (REG-05 T287)."""
    status, _ = _post_ws_ticket(api_server, token=None)
    assert status == 401, (
        f"POST /ws/ticket without auth must return 401; got {status} (T287)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_ws_ticket_returns_uuid_and_30s_ttl(api_server: str):
    """POST /ws/ticket with valid Bearer token returns {ticket: UUID, ttl_seconds: 30} (REG-05 T287)."""
    token = _get_access_token(api_server)
    if not token:
        pytest.skip("Could not obtain access token for ws ticket test")

    status, payload = _post_ws_ticket(api_server, token=token)
    assert status == 200, (
        f"POST /ws/ticket with valid auth must return 200; got {status}: {payload} (T287)"
    )
    assert "ticket" in payload, f"Response must contain 'ticket' field; got {payload} (T287)"
    assert "ttl_seconds" in payload, f"Response must contain 'ttl_seconds'; got {payload} (T287)"
    assert payload["ttl_seconds"] == 30, (
        f"ttl_seconds must be 30; got {payload['ttl_seconds']} (T287)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_ws_ticket_value_is_valid_uuid(api_server: str):
    """The ticket value returned by POST /ws/ticket is a valid UUID string (REG-05 T287)."""
    token = _get_access_token(api_server)
    if not token:
        pytest.skip("Could not obtain access token for ws ticket test")

    _, payload = _post_ws_ticket(api_server, token=token)
    ticket_str = payload.get("ticket", "")
    try:
        parsed = uuid.UUID(ticket_str)
    except (ValueError, AttributeError):
        pytest.fail(f"ticket {ticket_str!r} is not a valid UUID (T287)")

    # Confirm string form round-trips (no reformatting)
    assert str(parsed) == ticket_str.lower() or ticket_str.replace("-", "") == parsed.hex, (
        f"ticket {ticket_str!r} must be a canonical UUID string (T287)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_ws_ticket_stored_in_redis_with_correct_key_and_ttl(api_server: str):
    """Issued ticket exists in Redis under harness:ws:ticket:<uuid> with TTL ≤ 30 s (REG-05 T287)."""
    token = _get_access_token(api_server)
    if not token:
        pytest.skip("Could not obtain access token for ws ticket test")

    status, payload = _post_ws_ticket(api_server, token=token)
    assert status == 200, f"Ticket issuance failed: {payload}"
    ticket = payload.get("ticket", "")

    async def _check_redis() -> int:
        redis = await _open_redis()
        try:
            key = f"{_WS_TICKET_PREFIX}{ticket}"
            ttl: int = await redis.ttl(key)
            return ttl
        finally:
            await redis.aclose()

    ttl = asyncio.run(_check_redis())
    assert ttl > 0, (
        f"Redis key harness:ws:ticket:{ticket} must exist after issuance (T287)"
    )
    assert ttl <= 30, (
        f"Redis key TTL must be ≤ 30 s; got {ttl} s (T287)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_ws_ticket_issued_audit_row_written(api_server: str):
    """ws_ticket_issued audit row is written when a ticket is issued (REG-05 T287)."""
    token = _get_access_token(api_server)
    if not token:
        pytest.skip("Could not obtain access token for ws ticket audit test")

    status, payload = _post_ws_ticket(api_server, token=token)
    assert status == 200, f"Ticket issuance failed: {payload}"
    ticket = payload.get("ticket", "")

    async def _check_audit() -> bool:
        asyncpg = pytest.importorskip("asyncpg")
        from db.migrator import database_url_from_env, load_env_file
        load_env_file(PROJECT_ROOT / ".env")
        conn = await connect_with_retry(asyncpg, database_url_from_env())
        try:
            row = await conn.fetchrow(
                """/* sql_id: test_ws_ticket_issued_audit */
                SELECT id FROM audit_logs
                WHERE action_code = 'ws_ticket_issued'
                  AND resource_id = $1
                ORDER BY created_at DESC LIMIT 1
                """,
                ticket,
            )
            return row is not None
        finally:
            await conn.close()

    found = asyncio.run(_check_audit())
    assert found, (
        f"ws_ticket_issued audit row must exist for ticket {ticket!r} (T287)"
    )


# ---------------------------------------------------------------------------
# Tests — WebSocket connection close codes (requires websockets library)
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_ws_connection_without_subprotocol_is_rejected(api_server: str):
    """WS /ws without Sec-WebSocket-Protocol: harness.v1 is rejected by the server (REG-05 T287)."""
    websockets = pytest.importorskip("websockets")

    ws_url = api_server.replace("http://", "ws://") + "/ws"

    async def _run() -> None:
        # Connecting without the required subprotocol; server closes before accept
        try:
            async with websockets.connect(ws_url, open_timeout=10) as ws_conn:
                # If we connect successfully, server should close shortly
                try:
                    await asyncio.wait_for(ws_conn.recv(), timeout=5.0)
                except Exception:
                    pass
                # Connection must not be open normally — close code 4001 expected
                close_code = getattr(ws_conn, "close_code", None)
                assert close_code == 4001 or not ws_conn.open, (
                    f"WS without harness.v1 subprotocol must be rejected (close 4001); "
                    f"got close_code={close_code} (T287)"
                )
        except Exception as exc:
            # The server may reject the upgrade entirely (non-101 response → InvalidHandshake/
            # InvalidStatusCode) or close with 4001. Both are acceptable rejections.
            exc_name = type(exc).__name__
            acceptable = (
                "InvalidHandshake" in exc_name
                or "InvalidStatusCode" in exc_name
                or "ConnectionClosed" in exc_name
                or "WebSocketException" in exc_name
                or "OSError" in exc_name
            )
            assert acceptable, (
                f"Unexpected exception type {exc_name!r} when connecting without "
                f"harness.v1 subprotocol: {exc} (T287)"
            )

    asyncio.run(_run())


@pytest.mark.security
@pytest.mark.integration
def test_ws_connection_with_expired_ticket_closes_4002(api_server: str):
    """WS /ws with valid subprotocol but non-existent ticket → close code 4002 (REG-05 T297)."""
    websockets = pytest.importorskip("websockets")

    ws_url = api_server.replace("http://", "ws://") + "/ws"
    nonexistent_ticket = str(uuid.uuid4())

    async def _run() -> None:
        try:
            async with websockets.connect(
                ws_url,
                subprotocols=[_WS_SUBPROTOCOL],
                open_timeout=10,
            ) as ws_conn:
                # Send ticket that does not exist in Redis
                await ws_conn.send(json.dumps({"ticket": nonexistent_ticket}))
                # Server should close with 4002
                try:
                    await asyncio.wait_for(ws_conn.recv(), timeout=5.0)
                except Exception:
                    pass
                close_code = getattr(ws_conn, "close_code", None)
                assert close_code == 4002, (
                    f"WS with non-existent ticket must close with 4002; "
                    f"got close_code={close_code} (T297)"
                )
        except Exception as exc:
            # ConnectionClosed with code 4002 is the expected path
            close_code = getattr(getattr(exc, "rcvd", None), "code", None)
            if close_code is not None:
                assert close_code == 4002, (
                    f"Expected close code 4002 for expired ticket; got {close_code} (T297)"
                )
            else:
                # If we cannot extract the code, re-raise so CI sees the failure
                raise

    asyncio.run(_run())
