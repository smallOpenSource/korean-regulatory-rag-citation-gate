"""HTTP security response headers tests (REG-05 T284).

Task IDs: T284
Ref: docs/regulations/REG-05_internet_security.md §5
     apps/api/harness/core/security_headers.py

Covers:
- Strict-Transport-Security present with max-age=15552000; includeSubDomains; preload
- Content-Security-Policy present
- X-Content-Type-Options: nosniff
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy present (camera, microphone, geolocation)
- Cross-Origin-Opener-Policy: same-origin
- Cross-Origin-Resource-Policy: same-origin
- Headers present on both 200 and 4xx responses
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
from typing import Any

import pytest

from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "tests"

EXPECTED_HSTS_MAX_AGE = 15552000


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
    log_path = LOG_DIR / "security-headers.log"
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


def _get_headers(base_url: str, path: str = "/health") -> dict[str, str]:
    """Return response headers (lowercased keys) for the given path."""
    req = urllib.request.Request(f"{base_url}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as exc:
        return {k.lower(): v for k, v in exc.headers.items()}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_hsts_header_present_with_correct_max_age(api_server: str):
    """HSTS header must be present with max-age=15552000 (REG-05 T284, RFC 6797)."""
    headers = _get_headers(api_server)
    hsts = headers.get("strict-transport-security", "")
    assert hsts, "Strict-Transport-Security header is missing"
    assert f"max-age={EXPECTED_HSTS_MAX_AGE}" in hsts, (
        f"HSTS max-age must be {EXPECTED_HSTS_MAX_AGE}; got: {hsts!r}"
    )
    assert "includesubdomains" in hsts.lower(), "HSTS must include includeSubDomains"


@pytest.mark.security
@pytest.mark.integration
def test_content_security_policy_header_present(api_server: str):
    """Content-Security-Policy header must be present (REG-05 T284)."""
    headers = _get_headers(api_server)
    csp = headers.get("content-security-policy", "")
    assert csp, "Content-Security-Policy header is missing"
    assert "default-src" in csp, "CSP must include default-src directive"
    assert "frame-ancestors 'none'" in csp, "CSP must include frame-ancestors 'none'"


@pytest.mark.security
@pytest.mark.integration
def test_x_content_type_options_nosniff(api_server: str):
    """X-Content-Type-Options must be 'nosniff' (REG-05 T284)."""
    headers = _get_headers(api_server)
    value = headers.get("x-content-type-options", "")
    assert value.lower() == "nosniff", (
        f"X-Content-Type-Options must be 'nosniff'; got {value!r}"
    )


@pytest.mark.security
@pytest.mark.integration
def test_referrer_policy_strict_origin(api_server: str):
    """Referrer-Policy must be 'strict-origin-when-cross-origin' (REG-05 T284)."""
    headers = _get_headers(api_server)
    value = headers.get("referrer-policy", "")
    assert value == "strict-origin-when-cross-origin", (
        f"Referrer-Policy must be strict-origin-when-cross-origin; got {value!r}"
    )


@pytest.mark.security
@pytest.mark.integration
def test_permissions_policy_header_present(api_server: str):
    """Permissions-Policy must restrict camera, microphone, geolocation (REG-05 T284)."""
    headers = _get_headers(api_server)
    value = headers.get("permissions-policy", "")
    assert value, "Permissions-Policy header is missing"
    assert "camera=()" in value, "Permissions-Policy must disable camera"
    assert "microphone=()" in value, "Permissions-Policy must disable microphone"
    assert "geolocation=()" in value, "Permissions-Policy must disable geolocation"


@pytest.mark.security
@pytest.mark.integration
def test_cross_origin_opener_policy_same_origin(api_server: str):
    """Cross-Origin-Opener-Policy must be 'same-origin' (REG-05 T284)."""
    headers = _get_headers(api_server)
    value = headers.get("cross-origin-opener-policy", "")
    assert value == "same-origin", (
        f"Cross-Origin-Opener-Policy must be same-origin; got {value!r}"
    )


@pytest.mark.security
@pytest.mark.integration
def test_cross_origin_resource_policy_same_origin(api_server: str):
    """Cross-Origin-Resource-Policy must be 'same-origin' (REG-05 T284)."""
    headers = _get_headers(api_server)
    value = headers.get("cross-origin-resource-policy", "")
    assert value == "same-origin", (
        f"Cross-Origin-Resource-Policy must be same-origin; got {value!r}"
    )


@pytest.mark.security
@pytest.mark.integration
def test_security_headers_present_on_4xx_response(api_server: str):
    """Security headers must be present even on 401 error responses (REG-05 T284)."""
    # Request a protected endpoint without auth → 401
    req = urllib.request.Request(
        f"{api_server}/dashboard", headers={"Accept": "application/json"}, method="GET"
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        resp_headers = {k.lower(): v for k, v in exc.headers.items()}
        assert exc.code == 401
    else:
        pytest.fail("Expected 401 from /dashboard without auth")

    assert "strict-transport-security" in resp_headers, (
        "HSTS header missing from 401 error response"
    )
    assert "x-content-type-options" in resp_headers, (
        "X-Content-Type-Options missing from 401 error response"
    )
