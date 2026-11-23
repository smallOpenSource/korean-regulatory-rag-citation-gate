"""Regression: dispute same-actor resolve is PREVENTIVE (403), not audit-only.

A responder must not resolve their own dispute (REG-01 §36 four-eye). Fixed
2026-05-30: ``routers/disputes.py`` now emits ``same_actor_mutation_blocked`` and
returns 403 WITHOUT mutating (it previously ran the UPDATE first and only added a
forensic audit row, so a responder could resolve their own dispute at HTTP 200).

Integration test: skips if the backend is not reachable, per
[[integration-test-defensive-skip]].
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
import uuid
from typing import Any

import pytest

BASE_URL = os.environ.get(
    "WMAH_BACKEND_URL",
    f"http://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}",
)
PB_EMAIL = "synthetic.pb1@example.invalid"
WM_EMAIL = "synthetic.wm1@example.invalid"
PASSWORD = os.environ.get("WMAH_E2E_PASSWORD", "HarnessSynthetic!2026")
CUSTOMER = "33333333-3333-3333-3333-333333333306"


def _backend_up() -> bool:
    port = int(os.environ.get("HARNESS_API_PORT", "8010"))
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _backend_up(), reason="backend uvicorn not reachable")


def _req(
    method: str,
    path: str,
    token: str | None,
    body: dict[str, Any] | None = None,
    *,
    idempotent: bool = False,
) -> tuple[int, dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if idempotent:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        return exc.code, payload


def _login(email: str) -> str:
    status, body = _req("POST", "/auth/login", None, {"email": email, "password": PASSWORD})
    assert status == 200, f"login failed: {status} {body}"
    token = body.get("access_token")
    assert isinstance(token, str) and len(token) > 100
    return token


@pytest.fixture(scope="module")
def pb_token() -> str:
    return _login(PB_EMAIL)


@pytest.fixture(scope="module")
def wm_token() -> str:
    return _login(WM_EMAIL)


def test_responder_cannot_resolve_own_dispute(pb_token: str, wm_token: str) -> None:
    # A consultation_id is required to open a dispute.
    status, consult = _req(
        "POST", "/consultations", pb_token,
        {"customer_id": CUSTOMER, "channel_code": "FACE_TO_FACE"}, idempotent=True,
    )
    assert status == 201, f"consultation create failed: {status} {consult}"
    consultation_id = consult["id"]

    status, dispute = _req(
        "POST", "/disputes", pb_token,
        {"customer_id": CUSTOMER, "consultation_id": consultation_id, "dispute_type": "부당권유"},
    )
    assert status == 201, f"dispute open failed: {status} {dispute}"
    dispute_id = dispute["dispute_id"]

    # PB records the response.
    status, _ = _req(
        "PATCH", f"/disputes/{dispute_id}", pb_token, {"resolution_status": "RESPONDED"}
    )
    assert status == 200

    # PB (the responder) tries to resolve their own dispute → 403, no mutation.
    status, blocked = _req(
        "PATCH", f"/disputes/{dispute_id}", pb_token, {"resolution_status": "RESOLVED"}
    )
    assert status == 403, f"responder self-resolve should be 403, got {status}: {blocked}"
    assert blocked.get("error_code") == "forbidden"

    # A different staff member (WM) can resolve it.
    status, resolved = _req(
        "PATCH", f"/disputes/{dispute_id}", wm_token, {"resolution_status": "RESOLVED"}
    )
    assert status == 200, f"different-actor resolve should be 200, got {status}: {resolved}"
    assert resolved.get("status") == "RESOLVED"
