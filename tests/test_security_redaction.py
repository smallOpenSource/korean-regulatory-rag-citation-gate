"""Logging redaction and error sanitizer tests (REG-05 T288).

Task IDs: T288
Ref: docs/regulations/REG-05_internet_security.md §8
     apps/api/harness/core/redaction.py (SecretRedactionFilter, configure_logging_redaction)
     apps/api/harness/core/logging.py (redact_mapping, redact_secret_text)

Covers:
- SecretRedactionFilter masks 'Authorization' key value to ***REDACTED***
- SecretRedactionFilter masks '*_token' key suffix values
- SecretRedactionFilter masks Bearer token in free-form msg strings
- redact_mapping masks password= key-value pairs
- AI prompt: password=secret123 pattern masked in log records
- 500 response body from API contains no stack trace text
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from apps.api.harness.core.redaction import SecretRedactionFilter, _redact_string
from apps.api.harness.core.logging import redact_mapping, redact_secret_text
from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "tests"

_REDACTED = "***REDACTED***"


# ---------------------------------------------------------------------------
# Unit tests — SecretRedactionFilter (no server needed)
# ---------------------------------------------------------------------------

@pytest.mark.security
def test_filter_masks_authorization_header_value():
    """Authorization key value is replaced with ***REDACTED*** (REG-05 T288)."""
    filt = SecretRedactionFilter()
    # Python 3.11 LogRecord.__init__ does args[0] when len(args)==1, which breaks
    # for a plain dict.  Create with args=None then assign to bypass that check.
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="request headers: %(Authorization)s",
        args=None,
        exc_info=None,
    )
    record.args = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.abc.def"}
    filt.filter(record)
    assert record.args["Authorization"] == _REDACTED  # type: ignore[index]


@pytest.mark.security
def test_filter_masks_access_token_key():
    """Keys ending in _token are masked regardless of prefix (REG-05 T288)."""
    filt = SecretRedactionFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="tokens: %(access_token)s %(refresh_token)s %(harness_refresh_token)s",
        args={
            "access_token": "eyJhbGci.payload.sig",
            "refresh_token": "eyJhbGci.refresh.sig",
            "harness_refresh_token": "eyJhbGci.cookie.sig",
        },
        exc_info=None,
    )
    filt.filter(record)
    assert record.args["access_token"] == _REDACTED  # type: ignore[index]
    assert record.args["refresh_token"] == _REDACTED  # type: ignore[index]
    assert record.args["harness_refresh_token"] == _REDACTED  # type: ignore[index]


@pytest.mark.security
def test_filter_masks_bearer_token_in_free_form_msg():
    """Bearer token in log message string is replaced with ***REDACTED*** (REG-05 T288)."""
    filt = SecretRedactionFilter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret.payload",
        args=None,
        exc_info=None,
    )
    filt.filter(record)
    assert "eyJhbGciOiJIUzI1NiJ9" not in record.msg
    assert _REDACTED in record.msg


@pytest.mark.security
def test_filter_masks_password_key_value():
    """'password' key value is masked (REG-05 T288)."""
    filt = SecretRedactionFilter()
    # Python 3.11 LogRecord.__init__ does args[0] when len(args)==1 on a dict.
    # Create with args=None then assign to bypass that check.
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="login attempt %(password)s",
        args=None,
        exc_info=None,
    )
    record.args = {"password": "HarnessSynthetic!2026"}
    filt.filter(record)
    assert record.args["password"] == _REDACTED  # type: ignore[index]


@pytest.mark.security
def test_redact_string_masks_bearer_in_text():
    """_redact_string replaces Bearer token in free text (REG-05 T288)."""
    masked = _redact_string("Authorization: Bearer abc.def.ghi")
    assert "abc.def.ghi" not in masked
    assert _REDACTED in masked


@pytest.mark.security
def test_redact_string_masks_api_key_query_param():
    """_redact_string masks ?api_key= query parameter value (REG-05 T288)."""
    masked = _redact_string("GET /data?api_key=supersecret123&other=ok")
    assert "supersecret123" not in masked
    assert _REDACTED in masked


@pytest.mark.security
def test_redact_mapping_masks_sensitive_key_suffixes():
    """redact_mapping masks *_secret, *_api_key, *_token, *password patterns (REG-05 T288).

    SENSITIVE_KEY_RE covers: password, passwd, secret, token, api_key, auth_key,
    client_secret, authorization, service_key.  Keys like 'smtp_pass' (no match)
    are NOT masked — only the canonical patterns above are.
    """
    result = redact_mapping({
        "broker_app_secret": "very-secret",
        "azure_api_key": "azure-key-123",
        "smtp_password": "email-pass",     # 'password' matched by SENSITIVE_KEY_RE
        "safe_field": "visible-value",
        "smtp_pass": "not-masked-value",   # '_pass' is not in SENSITIVE_KEY_RE
    })
    assert result["broker_app_secret"] == "<redacted>", "keys containing 'secret' must be masked (T288)"
    assert result["azure_api_key"] == "<redacted>", "keys containing 'api_key' must be masked (T288)"
    assert result["smtp_password"] == "<redacted>", "keys containing 'password' must be masked (T288)"
    assert result["safe_field"] == "visible-value", "non-sensitive key must not be masked (T288)"
    assert result["smtp_pass"] == "not-masked-value", "'_pass' suffix is not in SENSITIVE_KEY_RE (T288)"


@pytest.mark.security
def test_ai_prompt_password_pattern_masked():
    """password=<value> pattern in AI prompt-like text is masked (REG-05 T288)."""
    prompt_text = "System context: password=HarnessSecret123 and token=eyJhb"
    masked = redact_secret_text(prompt_text)
    assert "HarnessSecret123" not in masked
    assert "eyJhb" not in masked


# ---------------------------------------------------------------------------
# Integration: 500 response body must not contain stack traces
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
    log_path = LOG_DIR / "redaction.log"
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


@pytest.mark.security
@pytest.mark.integration
def test_error_response_body_contains_no_stack_trace(api_server: str):
    """4xx/5xx response body must not contain Python stack trace text (REG-05 T288/T294)."""
    # Send malformed JSON to trigger a parse/validation error
    raw_body = b'{"question":'  # truncated JSON
    req = urllib.request.Request(
        f"{api_server}/auth/login",
        data=raw_body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode()
    else:
        pytest.skip("Expected error response from malformed request")

    stack_trace_markers = ["Traceback (most recent call last)", "File ", "line ", "raise "]
    for marker in stack_trace_markers:
        assert marker not in body_text, (
            f"Stack trace marker {marker!r} found in error response body (T288/T294)"
        )


@pytest.mark.security
@pytest.mark.integration
def test_authorization_header_not_in_response_body(api_server: str):
    """Authorization header value must never appear in any response body (REG-05 T288)."""
    sentinel_token = "eyJTENTINEL.payload.signature"
    req = urllib.request.Request(
        f"{api_server}/dashboard",
        headers={
            "Authorization": f"Bearer {sentinel_token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode()
        assert sentinel_token not in body_text, (
            "Bearer token value leaked into error response body (T288)"
        )
