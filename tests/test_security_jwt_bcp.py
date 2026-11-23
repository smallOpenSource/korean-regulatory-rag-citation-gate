"""JWT Best Current Practice tests (REG-05 T282, RFC 8725).

Task IDs: T282
Ref: docs/regulations/REG-05_internet_security.md §4
     apps/api/harness/core/security.py (JWT_ALG_ALLOWLIST, CLOCK_SKEW_SECONDS)

Covers:
- alg=none explicitly rejected by decode_token allowlist
- alg=HS512 (valid HMAC but not in allowlist) rejected
- Token within CLOCK_SKEW_SECONDS grace period accepted
- Token beyond CLOCK_SKEW_SECONDS grace period rejected
- API-level: token with wrong iss → 401
- API-level: token with wrong aud → 401
- API-level: token missing jti → 401

Unit tests (no server): alg allowlist, clock_skew.
Integration tests (real server): iss/aud/jti enforcement at auth boundary.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
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

from apps.api.harness.core.security import (
    CLOCK_SKEW_SECONDS,
    JWT_AUDIENCE,
    JWT_ISSUER,
    create_access_token,
    decode_token,
)
from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "tests"
SYNTHETIC_PASSWORD = "HarnessSynthetic!2026"
PB_EMAIL = "synthetic.pb1@example.invalid"


# ---------------------------------------------------------------------------
# Low-level JWT forge helpers (for crafting non-standard tokens)
# ---------------------------------------------------------------------------

def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _forge_jwt(*, alg: str, payload: dict[str, Any], secret: str = "") -> str:
    """Craft a raw JWT with any alg header — used to test allowlist enforcement."""
    header = {"alg": alg, "typ": "JWT"}
    h_enc = _b64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode())
    p_enc = _b64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signing_input = f"{h_enc}.{p_enc}".encode("ascii")
    if alg == "none":
        return f"{h_enc}.{p_enc}."
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h_enc}.{p_enc}.{_b64url_encode(sig)}"


def _load_jwt_secret() -> str:
    env_path = PROJECT_ROOT / ".env"
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if line.startswith("JWT_SECRET="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("JWT_SECRET not found in .env")


# ---------------------------------------------------------------------------
# Unit tests — decode_token alg allowlist enforcement (no server needed)
# ---------------------------------------------------------------------------

@pytest.mark.security
def test_decode_token_rejects_alg_none():
    """alg=none token is explicitly rejected by the JWT alg allowlist (RFC 8725 §3.1)."""
    secret = "test-secret-for-unit"
    payload = {
        "sub": "test-subject",
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "exp": int(time.time()) + 300,
        "jti": "unit-test-jti",
    }
    alg_none_token = _forge_jwt(alg="none", payload=payload, secret="")
    with pytest.raises(ValueError, match="(?i)algorithm"):
        decode_token(alg_none_token, secret=secret)


@pytest.mark.security
def test_decode_token_rejects_alg_hs512():
    """alg=HS512 token (valid HMAC family, not in allowlist) is rejected (RFC 8725)."""
    secret = "test-secret-for-unit"
    payload = {
        "sub": "test-subject",
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "exp": int(time.time()) + 300,
        "jti": "unit-test-jti",
    }
    # Craft HS512-header token but sign with SHA256 — rejected at header parsing
    token = _forge_jwt(alg="HS512", payload=payload, secret=secret)
    with pytest.raises(ValueError, match="(?i)algorithm"):
        decode_token(token, secret=secret)


@pytest.mark.security
def test_decode_token_accepts_token_within_clock_skew():
    """Token expired exactly CLOCK_SKEW_SECONDS ago is still accepted (grace window)."""
    secret = "test-secret-for-unit"
    # Expire at exactly CLOCK_SKEW_SECONDS ago → should be at boundary of acceptance
    token = create_access_token(
        subject="test-subject",
        secret=secret,
        expires_in_seconds=-(CLOCK_SKEW_SECONDS - 1),  # expired (skew-1) seconds ago
    )
    # Should not raise — within clock skew
    payload = decode_token(token, secret=secret)
    assert payload["sub"] == "test-subject"


@pytest.mark.security
def test_decode_token_rejects_token_beyond_clock_skew():
    """Token expired more than CLOCK_SKEW_SECONDS ago is rejected (RFC 7519 §4.1.4)."""
    secret = "test-secret-for-unit"
    token = create_access_token(
        subject="test-subject",
        secret=secret,
        expires_in_seconds=-(CLOCK_SKEW_SECONDS + 5),  # expired (skew+5) seconds ago
    )
    with pytest.raises(ValueError, match="(?i)expired"):
        decode_token(token, secret=secret)


@pytest.mark.security
def test_decode_token_includes_standard_bcp_claims():
    """create_access_token always emits iss, aud, nbf, jti claims (RFC 8725)."""
    secret = "test-secret-for-unit"
    token = create_access_token(subject="test-subject", secret=secret, expires_in_seconds=60)
    payload = decode_token(token, secret=secret)
    assert payload["iss"] == JWT_ISSUER, "iss claim must match JWT_ISSUER"
    assert payload["aud"] == JWT_AUDIENCE, "aud claim must match JWT_AUDIENCE"
    assert "jti" in payload, "jti claim must be present"
    assert "nbf" in payload, "nbf claim must be present"


# ---------------------------------------------------------------------------
# Server fixtures (integration tests for iss/aud/jti enforcement at API boundary)
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
    log_path = LOG_DIR / "jwt-bcp.log"
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


def _http(base_url: str, method: str, path: str, *,
          token: str | None = None, body: Any | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    headers: dict[str, str] = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()
        return exc.code, json.loads(text) if text else {}


def _login(base_url: str) -> tuple[str, str]:
    """Return (access_token, employee_id) for the synthetic PB account."""
    status, payload = _http(base_url, "POST", "/auth/login",
                            body={"email": PB_EMAIL, "password": SYNTHETIC_PASSWORD})
    assert status == 200, f"Login failed: {payload}"
    return str(payload["access_token"]), str(payload["employee"]["id"])


# ---------------------------------------------------------------------------
# Integration tests — iss / aud / jti enforcement at API auth boundary
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_api_rejects_token_with_wrong_iss(api_server: str):
    """Token signed with real secret but wrong iss must be rejected at the auth boundary (T282)."""
    secret = _load_jwt_secret()
    _, employee_id = _login(api_server)
    token = create_access_token(
        subject=employee_id,
        secret=secret,
        expires_in_seconds=60,
        extra_claims={"role_code": "PB", "token_type": "access", "iss": "evil-issuer"},
    )
    status, payload = _http(api_server, "GET", "/dashboard", token=token)
    assert status == 401, (
        f"Expected 401 for token with wrong iss, got {status}. "
        "decode_token must validate iss=harness-poc (RFC 8725 T282)."
    )


@pytest.mark.security
@pytest.mark.integration
def test_api_rejects_token_with_wrong_aud(api_server: str):
    """Token signed with real secret but wrong aud must be rejected at the auth boundary (T282)."""
    secret = _load_jwt_secret()
    _, employee_id = _login(api_server)
    token = create_access_token(
        subject=employee_id,
        secret=secret,
        expires_in_seconds=60,
        extra_claims={"role_code": "PB", "token_type": "access", "aud": "evil-audience"},
    )
    status, payload = _http(api_server, "GET", "/dashboard", token=token)
    assert status == 401, (
        f"Expected 401 for token with wrong aud, got {status}. "
        "decode_token must validate aud=harness-web (RFC 8725 T282)."
    )


@pytest.mark.security
@pytest.mark.integration
def test_api_rejects_token_without_jti(api_server: str):
    """Token missing jti claim must be rejected at the auth boundary (T282 jti required)."""
    secret = _load_jwt_secret()
    _, employee_id = _login(api_server)
    # Forge a properly signed token without jti
    payload_dict = {
        "sub": employee_id,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "exp": int(time.time()) + 60,
        "nbf": int(time.time()) - CLOCK_SKEW_SECONDS,
        "role_code": "PB",
        "token_type": "access",
        # jti intentionally omitted
    }
    token = _forge_jwt(alg="HS256", payload=payload_dict, secret=secret)
    status, _ = _http(api_server, "GET", "/dashboard", token=token)
    assert status == 401, (
        f"Expected 401 for token without jti, got {status}. "
        "Auth boundary must require jti presence (T282)."
    )
