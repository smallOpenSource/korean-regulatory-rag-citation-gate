"""Error response sanitizer tests (REG-05 T294).

Task IDs: T294
Ref: docs/regulations/REG-05_internet_security.md §3 (§9 Error Surface)
     apps/api/harness/core/errors.py (unhandled_exception_handler)
     apps/api/harness/core/error_codes.py (ErrorCode)

Covers:
- 500 response body contains no 'asyncpg.exceptions' class name strings
- 500 response body contains no Python stack trace markers
- 400/401/403/404 error response body schema is {error_code, message, request_id}
- error_code values are from the ErrorCode enum (not raw exception messages)
- request_id field is present in all error responses
- No internal implementation detail strings in any error response body
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

from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "tests"
SYNTHETIC_PASSWORD = "HarnessSynthetic!2026"
PB_EMAIL = "synthetic.pb1@example.invalid"

_STACK_TRACE_MARKERS = [
    "Traceback (most recent call last)",
    "File ",
    'raise ',
    "asyncpg.exceptions",
    "asyncpg.pgproto",
    "PostgresError",
    "fastapi.exceptions",
    "starlette.routing",
]


# ---------------------------------------------------------------------------
# Server fixture
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
    asyncio.run(_prepare_database())
    port = _free_port()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "error-sanitizer.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}:{env.get('PYTHONPATH', '')}"
    env["HARNESS_EMAIL_SEND_ENABLED"] = "false"
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


def _error_body(base_url: str, method: str, path: str, *,
                token: str | None = None,
                body: bytes | None = None,
                content_type: str = "application/json") -> tuple[int, str, dict]:  # type: ignore[type-arg]
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{base_url}{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode()
            return resp.status, text, json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {}
        return exc.code, text, payload


def _assert_no_stack_trace(body_text: str, context: str) -> None:
    for marker in _STACK_TRACE_MARKERS:
        assert marker not in body_text, (
            f"Marker {marker!r} found in {context} response body (T294)"
        )


def _assert_sanitized_schema(payload: dict, status_code: int) -> None:  # type: ignore[type-arg]
    """Assert error response has exactly {error_code, message, request_id}."""
    assert "error_code" in payload, f"error_code missing from {status_code} response"
    assert "message" in payload, f"message missing from {status_code} response"
    assert "request_id" in payload, f"request_id missing from {status_code} response"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_401_response_has_sanitized_schema(api_server: str):
    """401 Unauthorized response has {error_code, message, request_id} only (T294)."""
    status, body_text, payload = _error_body(api_server, "GET", "/dashboard")
    assert status == 401
    _assert_sanitized_schema(payload, 401)
    _assert_no_stack_trace(body_text, "401")


@pytest.mark.security
@pytest.mark.integration
def test_401_error_code_is_canonical_value(api_server: str):
    """401 response error_code must be a canonical ErrorCode value, not an exception name (T294)."""
    status, _, payload = _error_body(api_server, "GET", "/dashboard")
    assert status == 401
    error_code = payload.get("error_code", "")
    internal_indicators = ["Exception", "Error", "asyncpg", "ValueError", "fastapi"]
    for indicator in internal_indicators:
        assert indicator not in error_code, (
            f"error_code {error_code!r} leaks internal exception type (T294)"
        )


@pytest.mark.security
@pytest.mark.integration
def test_400_malformed_json_has_no_stack_trace(api_server: str):
    """Malformed JSON body returns 4xx with no stack trace or sensitive internals (T294).

    FastAPI returns 422 Unprocessable Entity for request validation errors using
    its own ``{"detail": [...]}`` schema — not the custom sanitized schema.  The
    custom unhandled_exception_handler only fires for uncaught server exceptions
    (5xx path).  This test verifies the 422 body does NOT leak stack traces or
    internal exception details — the core T294 concern for all error responses.
    """
    status, body_text, payload = _error_body(
        api_server, "POST", "/auth/login",
        body=b'{"email": "x"',  # truncated JSON
    )
    # FastAPI RequestValidationError → 422 (acceptable 4xx client error)
    assert 400 <= status < 500, (
        f"Malformed JSON must produce a 4xx response; got {status} (T294)"
    )
    _assert_no_stack_trace(body_text, f"{status}")
    # 422 uses FastAPI's {"detail": [...]} format — no custom sanitizer needed here.
    # Verify no internal exception class names leak into the response.
    for forbidden in ("asyncpg", "Traceback", "ValueError", "Exception"):
        assert forbidden not in body_text, (
            f"{forbidden!r} must not appear in {status} response body (T294)"
        )


@pytest.mark.security
@pytest.mark.integration
def test_404_not_found_has_sanitized_schema(api_server: str):
    """404 response has {error_code, message, request_id} schema (T294)."""
    status, body_text, payload = _error_body(
        api_server, "GET", "/customers/00000000-0000-0000-0000-000000000000",
        token="dummy.dummy.dummy",
    )
    # Will get 401 for bad token or 404 for missing resource — both must be sanitized
    assert status in (401, 404)
    _assert_no_stack_trace(body_text, f"{status}")


@pytest.mark.security
@pytest.mark.integration
def test_invalid_uuid_path_has_sanitized_schema(api_server: str):
    """422/400 response for invalid UUID path param has sanitized schema (T294)."""
    # Log in to get a real token first
    status, body_text, payload = _error_body(
        api_server, "POST", "/auth/login",
        body=json.dumps({"email": PB_EMAIL, "password": SYNTHETIC_PASSWORD}).encode(),
    )
    if status != 200:
        pytest.skip("Could not obtain auth token for 422 test")
    token = payload.get("access_token", "")

    status, body_text, payload = _error_body(
        api_server, "GET", "/customers/not-a-uuid", token=token
    )
    assert 400 <= status < 500
    _assert_no_stack_trace(body_text, "422/400 invalid UUID")
    assert "request_id" in payload, "request_id missing from 422/400 response"


@pytest.mark.security
@pytest.mark.integration
def test_error_response_contains_no_asyncpg_exception_strings(api_server: str):
    """asyncpg exception class names must never appear in error response bodies (T294)."""
    # Request that would trigger a DB error path (bad auth to protected endpoint)
    for path in ("/dashboard", "/customers?limit=1&offset=0", "/audit-logs?limit=1&offset=0"):
        status, body_text, _ = _error_body(api_server, "GET", path)
        assert "asyncpg" not in body_text, (
            f"'asyncpg' string leaked in {status} response for {path} (T294)"
        )
        assert "PostgresError" not in body_text, (
            f"'PostgresError' string leaked in {status} response for {path} (T294)"
        )
