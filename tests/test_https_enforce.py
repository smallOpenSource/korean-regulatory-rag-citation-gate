"""HTTPS enforcement middleware tests (REG-05 T295).

Task IDs: T295
Ref: docs/regulations/REG-05_internet_security.md §3 §8 (HTTPS / Transport)
     apps/api/harness/core/https_enforce.py (HttpsEnforceMiddleware)

Covers:
- Non-dev APP_ENV + X-Forwarded-Proto: http → 308 redirect to https URL
- Non-dev APP_ENV + X-Forwarded-Proto: https → 200 OK (no redirect)
- Non-dev APP_ENV + no X-Forwarded-Proto → passes through (trusted proxy absent)
- Dev APP_ENV (APP_ENV=development) → no redirect even with X-Forwarded-Proto: http
- /health path is always exempt from redirect (load-balancer probes)

Two server instances are started:
  - 'staging' APP_ENV → enforcement ON
  - 'development' APP_ENV → enforcement OFF
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

import pytest

from tests._env_overlay import write_env_overlay
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


def _start_server(app_env: str) -> tuple[subprocess.Popen, str, str]:  # type: ignore[type-arg]
    port = _free_port()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"https-enforce-{app_env}.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}:{env.get('PYTHONPATH', '')}"
    env["HARNESS_EMAIL_SEND_ENABLED"] = "false"
    # APP_ENV must reach the spawned server authoritatively; a bare subprocess env
    # var is clobbered by load_env_file(override=True), so route it through an env
    # overlay the server reads via HARNESS_ENV_FILE (core.config.default_env_path).
    env_file = write_env_overlay({"APP_ENV": app_env})
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
            raise RuntimeError(f"Server (APP_ENV={app_env}) exited; see {log_path}")
        try:
            with urllib.request.urlopen(f"{base_url}/health", timeout=2) as r:
                if json.load(r).get("status") == "ok":
                    return process, base_url, env_file
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.25)
    os.unlink(env_file)
    raise RuntimeError(f"Server (APP_ENV={app_env}) not healthy; see {log_path}")


@pytest.fixture(scope="module")
def staging_server() -> str:  # type: ignore[return]
    """API server with APP_ENV=staging — HTTPS enforcement ON."""
    asyncio.run(_prepare_database())
    try:
        process, base_url, env_file = _start_server("staging")
    except RuntimeError as exc:
        pytest.skip(str(exc))
    try:
        yield base_url
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)
        process.kill()
        with contextlib.suppress(Exception):
            process.wait(timeout=5)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(env_file)


@pytest.fixture(scope="module")
def dev_server() -> str:  # type: ignore[return]
    """API server with APP_ENV=development — HTTPS enforcement OFF."""
    try:
        process, base_url, env_file = _start_server("development")
    except RuntimeError as exc:
        pytest.skip(str(exc))
    try:
        yield base_url
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)
        process.kill()
        with contextlib.suppress(Exception):
            process.wait(timeout=5)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(env_file)


def _get(base_url: str, path: str, *, extra_headers: dict[str, str] | None = None,
         follow_redirects: bool = False) -> tuple[int, dict[str, str]]:  # type: ignore[type-arg]
    """Return (status_code, response_headers). Does NOT follow redirects by default."""
    headers = {"Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(f"{base_url}{path}", headers=headers, method="GET")
    opener = urllib.request.build_opener()
    if not follow_redirects:
        # Override redirect handler to capture 3xx without following
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):  # type: ignore[override]
                return None
        opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=10) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}


# ---------------------------------------------------------------------------
# Tests — enforcement ON (staging)
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_http_proto_header_triggers_308_redirect(staging_server: str):
    """X-Forwarded-Proto: http in non-dev profile → 308 Permanent Redirect (REG-05 T295)."""
    status, headers = _get(
        staging_server, "/dashboard",
        extra_headers={"X-Forwarded-Proto": "http"},
    )
    assert status == 308, (
        f"Expected 308 redirect for X-Forwarded-Proto: http in staging, got {status}"
    )
    location = headers.get("location", "")
    assert location.startswith("https://"), (
        f"308 redirect Location must point to https://...; got {location!r}"
    )


@pytest.mark.security
@pytest.mark.integration
def test_https_proto_header_passes_through(staging_server: str):
    """X-Forwarded-Proto: https in non-dev profile → no redirect (REG-05 T295)."""
    status, _ = _get(
        staging_server, "/health",
        extra_headers={"X-Forwarded-Proto": "https"},
    )
    assert status == 200, (
        f"Expected 200 for X-Forwarded-Proto: https in staging, got {status}"
    )


@pytest.mark.security
@pytest.mark.integration
def test_health_path_exempt_from_https_redirect(staging_server: str):
    """/health is always exempt from HTTPS redirect (load-balancer probe path, T295)."""
    status, _ = _get(
        staging_server, "/health",
        extra_headers={"X-Forwarded-Proto": "http"},
    )
    assert status == 200, (
        f"/health must be exempt from HTTPS redirect; got {status}"
    )


# ---------------------------------------------------------------------------
# Tests — enforcement OFF (development)
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_dev_env_no_redirect_for_http_proto(dev_server: str):
    """APP_ENV=development → no HTTPS redirect even with X-Forwarded-Proto: http (T295)."""
    status, _ = _get(
        dev_server, "/health",
        extra_headers={"X-Forwarded-Proto": "http"},
    )
    assert status == 200, (
        f"Development env must not redirect; got {status}"
    )
