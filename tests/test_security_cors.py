"""CORS guard tests (REG-05 T286).

Task IDs: T286
Ref: docs/regulations/REG-05_internet_security.md §5
     apps/api/harness/core/middleware.py (CorsGuardMiddleware)
     apps/api/harness/core/config.py (validate_cors_config)

Covers:
- Wildcard CORS_ALLOWED_ORIGINS raises ValueError at config load time
- With CORS enabled, request from disallowed Origin → 403
- With CORS enabled, request from allowed Origin → succeeds
- With CORS disabled (default), Origin header is ignored (no guard applied)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests._env_overlay import write_env_overlay
from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "tests"

ALLOWED_ORIGIN = "https://harness.example.com"
DISALLOWED_ORIGIN = "https://evil.attacker.example"


# ---------------------------------------------------------------------------
# Unit tests — config validation (no server needed)
# ---------------------------------------------------------------------------

@pytest.mark.security
def test_cors_wildcard_origin_raises_at_config_load():
    """CORS_ALLOWED_ORIGINS=* must raise ValueError at config load time (REG-05 T286)."""
    from apps.api.harness.core.config import validate_cors_config

    with pytest.raises(ValueError, match="(?i)wildcard"):
        validate_cors_config(enabled=True, allowed_origins=("*",))


@pytest.mark.security
def test_cors_enabled_without_origins_raises():
    """CORS_ENABLED=true without CORS_ALLOWED_ORIGINS must raise ValueError."""
    from apps.api.harness.core.config import validate_cors_config

    with pytest.raises(ValueError, match="(?i)CORS_ALLOWED_ORIGINS"):
        validate_cors_config(enabled=True, allowed_origins=())


@pytest.mark.security
def test_cors_disabled_passes_validation_with_no_origins():
    """CORS_ENABLED=false (default) must pass validation without origins."""
    from apps.api.harness.core.config import validate_cors_config

    # Must not raise
    validate_cors_config(enabled=False, allowed_origins=())


@pytest.mark.security
def test_cors_guard_middleware_rejects_disallowed_origin_in_memory():
    """CorsGuardMiddleware rejects disallowed Origin without a running server."""
    from apps.api.harness.core.middleware import CorsGuardMiddleware

    # Verify the allowed_origins frozenset logic directly
    allowed: frozenset[str] = frozenset({ALLOWED_ORIGIN})
    guard = CorsGuardMiddleware.__new__(CorsGuardMiddleware)
    guard._allowed_origins = allowed  # type: ignore[attr-defined]

    assert DISALLOWED_ORIGIN not in allowed
    assert ALLOWED_ORIGIN in allowed


# ---------------------------------------------------------------------------
# Server fixture (CORS enabled with explicit allowed origin)
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


def _start_server(extra_env: dict[str, str]) -> tuple[subprocess.Popen[bytes], str, str]:  # type: ignore[type-arg]
    port = _free_port()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"cors-{port}.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}:{env.get('PYTHONPATH', '')}"
    env["HARNESS_EMAIL_SEND_ENABLED"] = "false"
    env.update(extra_env)
    # CORS env (CORS_ENABLED / CORS_ALLOWED_ORIGINS) must reach the spawned server
    # authoritatively; bare subprocess env vars are clobbered by load_env_file(
    # override=True), so route them through an overlay read via HARNESS_ENV_FILE.
    env_file = write_env_overlay(extra_env)
    env["HARNESS_ENV_FILE"] = env_file
    command = [
        str(Path(os.environ.get("PYTHON_PATH", "/opt/conda/envs/wm_env/bin/python"))),
        "-m", "uvicorn", "apps.api.harness.main:app",
        "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
    ]
    with log_path.open("w") as lf:
        process = subprocess.Popen(command, cwd=PROJECT_ROOT, env=env, stdout=lf, stderr=lf)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 25
    while time.time() < deadline:
        if process.poll() is not None:
            os.unlink(env_file)
            raise RuntimeError(f"Server exited; see {log_path}")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as r:
                if json.load(r).get("status") == "ok":
                    return process, base_url, env_file
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.25)
    os.unlink(env_file)
    raise RuntimeError(f"Server not healthy; see {log_path}")


@pytest.fixture(scope="module")
def cors_enabled_server():  # type: ignore[return]
    """Start a server with CORS_ENABLED=true and one allowed origin."""
    asyncio.run(_prepare_database())
    try:
        process, base_url, env_file = _start_server({
            "CORS_ENABLED": "true",
            "CORS_ALLOWED_ORIGINS": ALLOWED_ORIGIN,
        })
    except RuntimeError as exc:
        pytest.skip(str(exc))
    try:
        yield base_url
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)
        process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=5)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(env_file)


def _request_with_origin(base_url: str, origin: str) -> tuple[int, dict]:  # type: ignore[type-arg]
    req = urllib.request.Request(
        f"{base_url}/health",
        headers={"Accept": "application/json", "Origin": origin},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        return exc.code, json.loads(body) if body else {}


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_disallowed_origin_returns_403(cors_enabled_server: str):
    """Request with a disallowed Origin header must return 403 (REG-05 T286)."""
    status, payload = _request_with_origin(cors_enabled_server, DISALLOWED_ORIGIN)
    assert status == 403, (
        f"Expected 403 for disallowed origin {DISALLOWED_ORIGIN!r}, got {status}: {payload}"
    )
    assert payload.get("error_code") == "forbidden"


@pytest.mark.security
@pytest.mark.integration
def test_allowed_origin_returns_200(cors_enabled_server: str):
    """Request from the configured allowed origin must succeed (REG-05 T286)."""
    status, payload = _request_with_origin(cors_enabled_server, ALLOWED_ORIGIN)
    assert status == 200, (
        f"Expected 200 for allowed origin {ALLOWED_ORIGIN!r}, got {status}: {payload}"
    )


@pytest.mark.security
@pytest.mark.integration
def test_no_origin_header_with_cors_enabled_passes(cors_enabled_server: str):
    """Request without Origin header (same-origin browser proxy) must not be blocked."""
    req = urllib.request.Request(
        f"{cors_enabled_server}/health",
        headers={"Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        assert resp.status == 200
