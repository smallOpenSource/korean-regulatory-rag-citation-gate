"""Regression: GET /audit-logs date filter must not 500 (smoke 2026-05-30).

``from_date`` / ``to_date`` were bound to asyncpg as raw strings against a
``$::date`` parameter, so asyncpg's date encoder called ``.toordinal()`` on a
str and raised ``'str' object has no attribute 'toordinal'`` -> 500. The router
now parses ``YYYY-MM-DD`` to ``datetime.date`` and returns 400 on a malformed
value.

Integration test: skips if the backend is not reachable, per
[[integration-test-defensive-skip]].
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from typing import Any

import pytest

BASE_URL = os.environ.get(
    "WMAH_BACKEND_URL",
    f"http://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}",
)
ADMIN_EMAIL = "synthetic.admin@example.invalid"
ADMIN_PASSWORD = os.environ.get("WMAH_E2E_PASSWORD", "HarnessSynthetic!2026")


def _backend_up() -> bool:
    try:
        port = int(os.environ.get("HARNESS_API_PORT", "8010"))
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _backend_up(), reason="backend uvicorn not reachable")


def _request(
    method: str,
    path: str,
    body: dict[str, Any] | None,
    headers: dict[str, str] | None,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        return exc.code, payload


@pytest.fixture(scope="module")
def admin_token() -> str:
    status, body = _request(
        "POST", "/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, None
    )
    assert status == 200, f"admin login failed: {status} {body}"
    token = body.get("access_token")
    assert isinstance(token, str) and len(token) > 100
    return token


def test_valid_date_range_returns_200(admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    status, body = _request(
        "GET", "/audit-logs?from_date=2026-01-01&to_date=2026-12-31&limit=5", None, headers
    )
    assert status == 200, f"expected 200, got {status}: {body}"
    assert "items" in body


def test_malformed_date_returns_400(admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}
    status, body = _request("GET", "/audit-logs?from_date=not-a-date", None, headers)
    assert status == 400, f"expected 400, got {status}: {body}"
