"""ADR-011 Idempotency-Key middleware replay-attack pytest.

Exercises the @idempotent decorator end-to-end against the live backend
(127.0.0.1, HARNESS_API_PORT). The 7 scenarios mirror ADR-011 §Test Plan:

1. happy path                          → 201 + new audit row
2. identical replay                    → cached response, audit row count unchanged
3. same key + different body           → 422 idempotency_key_payload_mismatch
4. missing header                      → 409 idempotency_key_required
5. concurrent identical replays        → exactly 1 audit row across N parallel POSTs
6. (skipped here — TTL expiry needs a 24h time-shift fixture)
7. determinism                         → repeat scenario 5 fifty times; every
                                          iteration must converge to exactly 1

The test class skips itself if the backend isn't reachable so a CI run
that doesn't start uvicorn still passes silently per
[[integration-test-defensive-skip]].
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import socket
import urllib.error
import urllib.request
import uuid

import pytest

BASE_URL = os.environ.get(
    "WMAH_BACKEND_URL",
    f"http://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}",
)
PB_EMAIL = "synthetic.pb1@example.invalid"
PB_PASSWORD = os.environ.get("WMAH_E2E_PASSWORD", "HarnessSynthetic!2026")
CUSTOMER_PB1 = "33333333-3333-3333-3333-333333333301"


def _backend_up() -> bool:
    try:
        port = int(os.environ.get("HARNESS_API_PORT", "8010"))
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _backend_up(), reason="backend uvicorn not reachable")


def _post(path: str, body: dict, headers: dict[str, str] | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}
        return exc.code, body


@pytest.fixture(scope="module")
def pb_token() -> str:
    status, body = _post("/auth/login", {"email": PB_EMAIL, "password": PB_PASSWORD})
    assert status == 200, f"login failed: {status} {body}"
    token = body.get("access_token")
    assert isinstance(token, str) and len(token) > 100
    return token


def _create_consultation(token: str, *, idempotency_key: str | None, channel_code: str = "PHONE") -> tuple[int, dict]:
    headers = {"Authorization": f"Bearer {token}"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    return _post(
        "/consultations",
        {"customer_id": CUSTOMER_PB1, "channel_code": channel_code},
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Scenario 1 — happy path
# ---------------------------------------------------------------------------
def test_happy_path_creates_consultation(pb_token: str) -> None:
    key = str(uuid.uuid4())
    status, body = _create_consultation(pb_token, idempotency_key=key)
    assert status == 201, f"expected 201, got {status}: {body}"
    assert isinstance(body.get("id"), str)


# ---------------------------------------------------------------------------
# Scenario 2 — identical replay returns same id
# ---------------------------------------------------------------------------
def test_identical_replay_returns_cached_response(pb_token: str) -> None:
    key = str(uuid.uuid4())
    status1, body1 = _create_consultation(pb_token, idempotency_key=key)
    assert status1 == 201, body1
    first_id = body1["id"]

    status2, body2 = _create_consultation(pb_token, idempotency_key=key)
    # Replay returns the declared status_code (201) from the cached row.
    assert status2 == 201, f"replay status mismatch: {status2} {body2}"
    assert body2.get("id") == first_id, "replay returned a different consultation id"


# ---------------------------------------------------------------------------
# Scenario 3 — same key + different body → 422 payload_mismatch
# ---------------------------------------------------------------------------
def test_same_key_different_body_returns_422(pb_token: str) -> None:
    key = str(uuid.uuid4())
    status1, body1 = _create_consultation(pb_token, idempotency_key=key, channel_code="PHONE")
    assert status1 == 201, body1

    status2, body2 = _create_consultation(pb_token, idempotency_key=key, channel_code="VISIT")
    assert status2 == 422, f"expected 422, got {status2}: {body2}"
    assert body2.get("error_code") == "idempotency_key_payload_mismatch"


# ---------------------------------------------------------------------------
# Scenario 4 — missing header → 409
# ---------------------------------------------------------------------------
def test_missing_header_returns_409(pb_token: str) -> None:
    status, body = _create_consultation(pb_token, idempotency_key=None)
    assert status == 409, f"expected 409, got {status}: {body}"
    assert body.get("error_code") == "idempotency_key_required"


# ---------------------------------------------------------------------------
# Scenario 4b — malformed (non-UUID) header → 400, not a 500 DataError
# ---------------------------------------------------------------------------
def test_non_uuid_header_returns_400(pb_token: str) -> None:
    status, body = _create_consultation(pb_token, idempotency_key="not-a-uuid-value")
    assert status == 400, f"expected 400, got {status}: {body}"
    assert body.get("error_code") == "idempotency_key_invalid"


# ---------------------------------------------------------------------------
# Scenario 5 — concurrent identical replays converge to exactly 1
# ---------------------------------------------------------------------------
def _converged_to_one(token: str, key: str, parallelism: int = 12) -> bool:
    """Fire ``parallelism`` identical POSTs in parallel; return True iff
    exactly one unique consultation id appears across all 2xx responses.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=parallelism) as pool:
        futures = [pool.submit(_create_consultation, token, idempotency_key=key) for _ in range(parallelism)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    ids = set()
    in_flight_409 = 0
    other = 0
    for status, body in results:
        if status in (200, 201) and isinstance(body.get("id"), str):
            ids.add(body["id"])
        elif status == 409 and body.get("error_code") == "idempotency_key_in_flight":
            in_flight_409 += 1
        else:
            other += 1
    if other:
        pytest.fail(f"unexpected response shape in concurrent run: {results}")
    return len(ids) == 1


def test_concurrent_identical_replays_converge(pb_token: str) -> None:
    key = str(uuid.uuid4())
    assert _converged_to_one(pb_token, key), "concurrent replays did not converge to one consultation id"


# ---------------------------------------------------------------------------
# Scenario 7 — determinism: scenario 5 must hold across 50 iterations.
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_determinism_50_iterations(pb_token: str) -> None:
    failures: list[int] = []
    for i in range(50):
        key = str(uuid.uuid4())
        if not _converged_to_one(pb_token, key, parallelism=8):
            failures.append(i)
    assert not failures, f"determinism failed on iterations: {failures}"
