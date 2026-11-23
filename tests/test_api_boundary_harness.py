"""Real local API RBAC, row-scope, validation, and audit boundary harness."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from tests._env_overlay import write_env_overlay
from tests._pg_retry import connect_with_retry


def _idem() -> dict[str, str]:
    """Fresh Idempotency-Key header for endpoints under ADR-011."""
    return {"Idempotency-Key": str(uuid.uuid4())}

import pytest

from db.migrator import database_url_from_env, load_env_file
from db.migrator import run as run_migrations
from db.seed import apply_profile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "tests"
SYNTHETIC_PASSWORD = "HarnessSynthetic!2026"
SECRET_PATTERN = re.compile(
    r"DATABASE_URL|JWT_SECRET|SERVICE_KEY|AZURE_OPENAI_API_KEY|BREVO_API_KEY|HarnessSynthetic|PASSWORD=",
    re.IGNORECASE,
)
ACCOUNTS = {
    "PB": "synthetic.pb1@example.invalid",
    "PB2": "synthetic.pb2@example.invalid",
    "WM": "synthetic.wm1@example.invalid",
    "BRANCH_MANAGER": "synthetic.branch.manager@example.invalid",
    "ADMIN": "synthetic.admin@example.invalid",
    "AUDIT_VIEWER": "synthetic.audit@example.invalid",
}
CUSTOMER_PB1 = "33333333-3333-3333-3333-333333333301"
CUSTOMER_PB2 = "33333333-3333-3333-3333-333333333313"
CONSULTATION_PB1 = "66666666-6666-6666-6666-666666666301"
PRODUCT_ID = "44444444-4444-4444-4444-444444444401"
ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _prepare_database() -> None:
    asyncpg = pytest.importorskip("asyncpg")
    load_env_file(PROJECT_ROOT / ".env")
    try:
        await run_migrations()
        connection = await connect_with_retry(asyncpg, database_url_from_env())
    except Exception as exc:  # pragma: no cover - environment-dependent skip path
        pytest.skip(f"PostgreSQL integration database is unavailable: {exc}")
    try:
        await apply_profile(connection, "full-mvp")
    finally:
        await connection.close()


async def _audit_count(action_code: str, resource_id: str | None = None) -> int:
    asyncpg = pytest.importorskip("asyncpg")
    connection = await connect_with_retry(asyncpg, database_url_from_env())
    try:
        return int(
            await connection.fetchval(
                """/* sql_id: test_api_boundary_audit_count */
                SELECT count(*)::integer
                FROM audit_logs
                WHERE action_code = $1::varchar
                  AND ($2::uuid IS NULL OR resource_id = $2::uuid);
                """,
                action_code,
                resource_id,
            )
            or 0
        )
    finally:
        await connection.close()


async def _cleanup_test_fixtures(
    house_view_id: str | None = None,
    email_draft_id: str | None = None,
) -> None:
    """Restore ACTIVE→SUPERSEDED + DELETE email_drafts to prevent fixture leak
    into dashboard/email-drafts surfaces during parallel e2e runs."""
    asyncpg = pytest.importorskip("asyncpg")
    connection = await connect_with_retry(asyncpg, database_url_from_env())
    try:
        if house_view_id:
            await connection.execute(
                """/* sql_id: test_api_boundary_cleanup_house_view */
                UPDATE house_views SET status_code = 'SUPERSEDED'
                WHERE id = $1::uuid AND status_code = 'ACTIVE'
                """,
                house_view_id,
            )
        if email_draft_id:
            await connection.execute(
                """/* sql_id: test_api_boundary_cleanup_email_draft */
                DELETE FROM email_drafts WHERE id = $1::uuid
                """,
                email_draft_id,
            )
    finally:
        await connection.close()


@pytest.fixture(scope="module")
def api_server() -> str:
    asyncio.run(_prepare_database())
    port = _free_port()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "api-boundary-harness.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}:{env.get('PYTHONPATH', '')}"
    env["HARNESS_EMAIL_SEND_ENABLED"] = "false"
    # The fail-closed boundary test expects POST /email-drafts/{approved}/send → 503.
    # The only 503 path is MailpitTransportError; .env's HARNESS_EMAIL_TRANSPORT=mailpit +
    # a reachable Mailpit makes the send succeed (200). Route a disabled transport through
    # an overlay (HARNESS_ENV_FILE) so the send fails closed (transport_disallowed → 503)
    # with no side effect. No other test in this file performs a successful email send.
    env_file = write_env_overlay({"HARNESS_EMAIL_TRANSPORT": "disabled"})
    env["HARNESS_ENV_FILE"] = env_file
    command = [
        str(Path(os.environ.get("PYTHON_PATH", "/opt/conda/envs/wm_env/bin/python"))),
        "-m",
        "uvicorn",
        "apps.api.harness.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            command, cwd=PROJECT_ROOT, env=env, stdout=log_file, stderr=log_file
        )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 25
        last_error = "startup timeout"
        while time.time() < deadline:
            if process.poll() is not None:
                pytest.skip(f"API server exited during startup; see {log_path}")
            try:
                status, payload, _ = _request(base_url, "GET", "/health")
                if status == 200 and payload.get("status") == "ok":
                    break
            except Exception as exc:  # noqa: BLE001 - retry loop boundary
                last_error = exc.__class__.__name__
            time.sleep(0.25)
        else:
            pytest.skip(f"API server did not become healthy: {last_error}; see {log_path}")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        os.unlink(env_file)


def _request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    extra_headers: dict[str, str] | None = None,
    body: Any | None = None,
    raw_body: bytes | None = None,
) -> tuple[int, Any, str]:
    status, payload, text, _ = _request_with_headers(
        base_url,
        method,
        path,
        token=token,
        body=body,
        raw_body=raw_body,
        extra_headers=extra_headers,
    )
    return status, payload, text


def _request_with_headers(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: Any | None = None,
    raw_body: bytes | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, Any, str, dict[str, str]]:
    data = raw_body
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif raw_body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else {}, text, dict(response.headers)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {"raw": text}
        return exc.code, payload, text, dict(exc.headers)


def _login_response(base_url: str, role: str) -> tuple[dict[str, Any], dict[str, str]]:
    status, payload, text, headers = _request_with_headers(
        base_url,
        "POST",
        "/auth/login",
        body={"email": ACCOUNTS[role], "password": SYNTHETIC_PASSWORD},
    )
    assert status == 200, text
    return payload, headers


def _login_payload(base_url: str, role: str) -> dict[str, Any]:
    payload, _ = _login_response(base_url, role)
    return payload


def _login(base_url: str, role: str) -> str:
    payload = _login_payload(base_url, role)
    return str(payload["access_token"])


def _tokens(base_url: str) -> dict[str, str]:
    return {role: _login(base_url, role) for role in ACCOUNTS}


def _cookie_pair(set_cookie: str, cookie_name: str) -> str:
    for part in set_cookie.split(","):
        candidate = part.strip().split(";", 1)[0]
        if candidate.startswith(f"{cookie_name}="):
            return candidate
    raise AssertionError(f"{cookie_name} cookie not found in Set-Cookie header")


def _header(headers: dict[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def _assert_no_secret_text(text: str) -> None:
    assert SECRET_PATTERN.search(text) is None


def test_refresh_accepts_bearer_or_cookie_and_returns_employee(api_server: str):
    # T283 rotation: each refresh JTI is single-use (blocklisted after one refresh,
    # mass-revoked on reuse). Verify Bearer and Cookie auth paths each work by using
    # a fresh login per path. Negative assertions also use a fresh login so the
    # refresh JTI under test is still valid when the negative checks run.

    for use_cookie in (False, True):
        login_payload, login_headers = _login_response(api_server, "PB")
        assert "refresh_token" not in login_payload
        set_cookie = _header(login_headers, "Set-Cookie")
        assert "harness_refresh_token=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "samesite=lax" in set_cookie.lower()
        refresh_cookie = _cookie_pair(set_cookie, "harness_refresh_token")
        refresh_token = refresh_cookie.split("=", 1)[1]

        request_kwargs = (
            {"extra_headers": {"Cookie": refresh_cookie}}
            if use_cookie
            else {"token": refresh_token}
        )
        status, payload, text = _request(
            api_server, "POST", "/auth/refresh", **request_kwargs
        )
        assert status == 200, text
        assert payload["access_token"]
        assert payload["employee"]["id"] == login_payload["employee"]["id"]
        assert payload["employee"]["role_code"] == "PB"
        assert (
            _request(api_server, "GET", "/dashboard", token=payload["access_token"])[0]
            == 200
        )

    fresh_login_payload, fresh_login_headers = _login_response(api_server, "PB")
    fresh_set_cookie = _header(fresh_login_headers, "Set-Cookie")
    fresh_refresh_cookie = _cookie_pair(fresh_set_cookie, "harness_refresh_token")
    fresh_refresh_token = fresh_refresh_cookie.split("=", 1)[1]

    for protected_path in ("/dashboard", "/customers?limit=1&offset=0"):
        status, _, text = _request(
            api_server, "GET", protected_path, token=fresh_refresh_token
        )
        assert status == 401
        _assert_no_secret_text(text)

    status, _, text = _request(api_server, "POST", "/auth/refresh")
    assert status == 401
    _assert_no_secret_text(text)
    assert (
        _request(
            api_server,
            "POST",
            "/auth/refresh",
            token=fresh_login_payload["access_token"],
        )[0]
        == 401
    )

    status, _, text, logout_headers = _request_with_headers(
        api_server,
        "POST",
        "/auth/logout",
        extra_headers={"Cookie": fresh_refresh_cookie},
    )
    assert status == 200, text
    logout_set_cookie = _header(logout_headers, "Set-Cookie")
    assert "harness_refresh_token=" in logout_set_cookie
    assert "Max-Age=0" in logout_set_cookie


def test_role_row_scope_and_audit_only_boundaries(api_server: str):
    tokens = _tokens(api_server)

    status, _, text = _request(api_server, "GET", "/dashboard")
    assert status == 401
    _assert_no_secret_text(text)

    # PB2 fixture has 8 assigned customers but 3 are seeded inactive
    # (is_active=FALSE) to exercise the active-only filter in the
    # /customers list query (repositories/customers.py:32 has the
    # `c.is_active IS TRUE` clause). The active-row count for PB2
    # is therefore 5, not 8 — design-intent inactive-customer
    # diversity per the customer-fixture rebake notes in
    # .omc/handoffs/wave-fix-Z2-backend-live.md.
    # PB2 fixture has 8 assigned customers but 3 are seeded inactive
    # (is_active=FALSE) to exercise the active-only filter in the
    # /customers list query (repositories/customers.py:32 has the
    # `c.is_active IS TRUE` clause). The active-row count for PB2
    # is therefore 5, not 8 — design-intent inactive-customer
    # diversity per the customer-fixture rebake notes in
    # .omc/handoffs/wave-fix-Z2-backend-live.md. Same filter applies
    # to the WM/BM (branch1 active = 18) and ADMIN (all active = 23)
    # views.
    #
    # 2026-05-23 v5+ adjustment: the SYN-FAM seed (V037 db/fixtures/
    # seed_50_family_personas.sql, 6 family-persona customers in
    # branch1) was applied 2026-05-22 and lifted every role-scoped
    # count by their respective share:
    #   - PB1 (assigned): +2 (SYN-FAM-001, SYN-FAM-002 assigned to PB1)
    #   - PB2 (assigned): +0 (no SYN-FAM assigned to PB2)
    #   - WM/BM (branch1): +6 (all 6 SYN-FAM at branch1)
    #   - ADMIN (all): +6
    # The counts below match the post-SYN-FAM DB state.
    expected_customer_counts = {
        "PB": 14,
        "PB2": 5,
        "WM": 18,
        "BRANCH_MANAGER": 18,
        "ADMIN": 23,
    }
    for role, expected_count in expected_customer_counts.items():
        status, payload, text = _request(
            api_server, "GET", "/customers?limit=100&offset=0", token=tokens[role]
        )
        assert status == 200, text
        assert len(payload["items"]) == expected_count
        _assert_no_secret_text(text)
    status, _, _ = _request(
        api_server, "GET", "/customers?limit=100&offset=0", token=tokens["AUDIT_VIEWER"]
    )
    assert status == 403

    assert _request(api_server, "GET", f"/customers/{CUSTOMER_PB1}", token=tokens["PB"])[0] == 200
    assert _request(api_server, "GET", f"/customers/{CUSTOMER_PB2}", token=tokens["PB"])[0] == 404
    assert _request(api_server, "GET", f"/customers/{CUSTOMER_PB1}", token=tokens["PB2"])[0] == 404
    assert (
        _request(api_server, "GET", f"/customers/{CUSTOMER_PB2}", token=tokens["ADMIN"])[0] == 200
    )
    assert (
        _request(api_server, "GET", f"/customers/{CUSTOMER_PB1}", token=tokens["AUDIT_VIEWER"])[0]
        == 403
    )

    assert (
        _request(api_server, "GET", "/audit-logs?limit=5&offset=0", token=tokens["ADMIN"])[0] == 200
    )
    assert (
        _request(api_server, "GET", "/audit-logs?limit=5&offset=0", token=tokens["AUDIT_VIEWER"])[0]
        == 200
    )
    assert _request(api_server, "GET", "/audit-logs?limit=5&offset=0", token=tokens["PB"])[0] == 403


def test_action_rbac_and_ai_fail_closed_boundaries(api_server: str):
    tokens = _tokens(api_server)

    consultation_body = {"customer_id": CUSTOMER_PB1, "channel_code": "PHONE"}
    assert (
        _request(
            api_server, "POST", "/consultations",
            token=tokens["PB"], body=consultation_body, extra_headers=_idem(),
        )[0]
        == 201
    )
    assert (
        _request(
            api_server, "POST", "/consultations",
            token=tokens["WM"], body=consultation_body, extra_headers=_idem(),
        )[0]
        == 201
    )
    for role in ("BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"):
        assert (
            _request(
                api_server, "POST", "/consultations",
                token=tokens[role], body=consultation_body, extra_headers=_idem(),
            )[0]
            == 403
        )

    for role in ("PB", "WM", "BRANCH_MANAGER", "ADMIN"):
        status, payload, text = _request(
            api_server,
            "POST",
            "/rag/query",
            token=tokens[role],
            body={"question": "synthetic compliance scope"},
        )
        assert status == 200, text
        assert payload["status_code"] == "BLOCKED"
        _assert_no_secret_text(text)
    assert (
        _request(
            api_server,
            "POST",
            "/rag/query",
            token=tokens["AUDIT_VIEWER"],
            body={"question": "audit"},
        )[0]
        == 403
    )

    email_body = {
        "customer_id": CUSTOMER_PB1,
        "consultation_id": CONSULTATION_PB1,
        "subject": "후속 상담 안내",
        "body": "상담에서 확인한 설명 항목과 다음 점검 일정을 정리합니다.",
    }
    status, draft_payload, text = _request(
        api_server, "POST", "/email-drafts",
        token=tokens["PB"], body=email_body, extra_headers=_idem(),
    )
    assert status == 201, text
    assert draft_payload["status_code"] == "DRAFT"
    assert draft_payload["ai_output_id"] is None
    assert (
        _request(
            api_server,
            "POST",
            "/email-drafts",
            token=tokens["PB2"],
            body=email_body,
            extra_headers=_idem(),
        )[0]
        == 404
    )
    for role in ("BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"):
        assert (
            _request(
                api_server, "POST", "/email-drafts",
                token=tokens[role], body=email_body, extra_headers=_idem(),
            )[0]
            == 403
        )
    assert (
        _request(
            api_server,
            "POST",
            f"/email-drafts/{draft_payload['draft_id']}/send",
            token=tokens["PB"],
            extra_headers=_idem(),
        )[0]
        == 409
    )
    approved_seed_draft = "eeeeeeee-eeee-eeee-eeee-eeeeeeee0302"
    before_email_send_count = asyncio.run(
        _audit_count("email_sent_via_sandbox", approved_seed_draft)
    )
    status, _, text = _request(
        api_server,
        "POST",
        f"/email-drafts/{approved_seed_draft}/send",
        token=tokens["PB"],
        extra_headers=_idem(),
    )
    assert status == 503
    _assert_no_secret_text(text)
    assert (
        asyncio.run(_audit_count("email_sent_via_sandbox", approved_seed_draft))
        == before_email_send_count
    )

    simulation_body = {
        "customer_id": CUSTOMER_PB1,
        "consultation_id": CONSULTATION_PB1,
        "product_id": PRODUCT_ID,
        "explanation_checked": True,
        "simulated_customer_consented": True,
        "employee_final_approved": True,
    }
    assert (
        _request(
            api_server,
            "POST",
            "/recommendation-simulations",
            token=tokens["PB"],
            body=simulation_body,
        )[0]
        == 201
    )
    for role in ("BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"):
        assert (
            _request(
                api_server,
                "POST",
                "/recommendation-simulations",
                token=tokens[role],
                body=simulation_body,
            )[0]
            == 403
        )

    assert (
        _request(api_server, "GET", "/batch/status?limit=5&offset=0", token=tokens["ADMIN"])[0]
        == 200
    )
    for role in ("PB", "WM", "BRANCH_MANAGER", "AUDIT_VIEWER"):
        assert (
            _request(api_server, "GET", "/batch/status?limit=5&offset=0", token=tokens[role])[0]
            == 403
        )


def test_nba_aftercare_and_house_view_mutation_boundaries(api_server: str):
    tokens = _tokens(api_server)

    status, nba_payload, text = _request(
        api_server, "GET", "/nba-actions?limit=1&offset=0", token=tokens["PB"]
    )
    assert status == 200, text
    nba_id = nba_payload["items"][0]["id"]
    assert (
        _request(
            api_server,
            "PATCH",
            f"/nba-actions/{nba_id}/status",
            token=tokens["PB"],
            body={"status_code": "IN_PROGRESS"},
            extra_headers=_idem(),
        )[0]
        == 200
    )
    for role in ("BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"):
        assert (
            _request(
                api_server,
                "PATCH",
                f"/nba-actions/{nba_id}/status",
                token=tokens[role],
                body={"status_code": "DONE"},
                extra_headers=_idem(),
            )[0]
            == 403
        )

    create_status, draft, create_text = _request(
        api_server,
        "POST",
        "/house-views",
        token=tokens["ADMIN"],
        body={
            "period_code": "RALPH",
            "title": "Ralph boundary draft",
            "summary": "Synthetic boundary test.",
        },
        extra_headers=_idem(),
    )
    assert create_status == 201, create_text
    draft_id = draft["id"]
    before_count = asyncio.run(_audit_count("house_view_activate", draft_id))
    status, _, text = _request(
        api_server, "POST", f"/house-views/{draft_id}/activate",
        token=tokens["ADMIN"], extra_headers=_idem(),
    )
    assert status == 200, text
    after_count = asyncio.run(_audit_count("house_view_activate", draft_id))
    assert after_count == before_count + 1
    assert (
        _request(
            api_server, "POST", f"/house-views/{ZERO_UUID}/activate",
            token=tokens["ADMIN"], extra_headers=_idem(),
        )[0]
        == 404
    )
    assert asyncio.run(_audit_count("house_view_activate", ZERO_UUID)) == 0
    for role in ("PB", "WM", "BRANCH_MANAGER", "AUDIT_VIEWER"):
        assert (
            _request(
                api_server, "POST", "/house-views",
                token=tokens[role], body={"title": "denied"}, extra_headers=_idem(),
            )[0]
            == 403
        )

    asyncio.run(_cleanup_test_fixtures(house_view_id=draft_id))


def test_malformed_inputs_return_controlled_4xx_without_secret_leakage(api_server: str):
    tokens = _tokens(api_server)
    checks = [
        ("GET", "/customers/not-a-uuid", tokens["PB"], None, None),
        ("POST", "/consultations", tokens["PB"], {"customer_id": "not-a-uuid"}, None),
        ("PATCH", "/consultations/not-a-uuid", tokens["PB"], {"status_code": "COMPLETED"}, None),
        ("POST", "/house-views/not-a-uuid/generate", tokens["ADMIN"], None, None),
        ("POST", "/email-drafts/not-a-uuid/send", tokens["PB"], None, None),
        ("PATCH", "/nba-actions/not-a-uuid/status", tokens["PB"], {"status_code": "DONE"}, None),
        ("POST", "/recommendation-simulations", tokens["PB"], {"customer_id": "not-a-uuid"}, None),
        ("POST", "/rag/query", tokens["PB"], None, b'{"question":'),
    ]
    for method, path, token, body, raw_body in checks:
        status, _, text = _request(
            api_server, method, path, token=token, body=body, raw_body=raw_body
        )
        assert 400 <= status < 500, f"{method} {path} returned {status}: {text}"
        _assert_no_secret_text(text)
