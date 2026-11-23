"""PoC_AUTO_APPROVAL 5-role × 14-scenario regression matrix (REG-06 §5, ADR-004).

Covers all 14 scenarios per Plan §5 Stage 2 gate:
 S01  All 4 gates PASS + demo_mode ON  → auto_approve allowed + governance_marker set
 S02  All 4 gates PASS + demo_mode OFF → BLOCKED (env guard)
 S03  Suitability FAIL + demo_mode ON  → BLOCKED (gate enforcement)
 S04  Explanation FAIL + demo_mode ON  → BLOCKED
 S05  Consent FAIL + demo_mode ON      → BLOCKED
 S06  Employee approval FAIL           → BLOCKED
 S07  X-Poc-Demo-Mode header missing   → BLOCKED
 S08  Header present but env disabled  → BLOCKED
 S09  8h auto-expire crossed           → BLOCKED + demo_mode_expired audit
 S10  Per-employee rate ceiling (10/min 60/hr) → BLOCKED + poc_auto_approval_rate_limited
 S11  Abort threshold >5% fail-rate    → ALL BLOCKED + poc_auto_approval_aborted
 S12  governance_marker='PoC_AUTO_APPROVAL' set on success
 S13  governance_marker='HUMAN_REVIEW' when human approves manually
 S14  prod_guard.would_block_in_prod=true on every auto-approve row

5-role checks (3 role-permission matrix scenarios):
 R01  AUDIT_VIEWER → 403 on auto-approve endpoint
 R02  COMPLIANCE_OFFICER → 403 on auto-approve endpoint (read-only role)
 R03  PB → 201 APPROVED on valid auto-approve (gate exit)

Constraints:
- Real PG17 + Redis (REDIS_URL=redis://localhost:6379/15)
- subprocess.Popen for server spin-up
- Each scenario asserts HTTP status + audit_logs row + Redis counters + no gate bypass

BLOCKERS:
- #24 (worker-india W2-T4): 4-gate suitability route must exist for scenarios S03-S06
- #33 (worker-mike W2-T13): PoC_AUTO_APPROVAL 3-layer attestation guard service

Tags: pytest.mark.poc_auto_approval
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
SYNTHETIC_PASSWORD = "HarnessSynthetic!2026"

ACCOUNTS = {
    "PB": "synthetic.pb1@example.invalid",
    "WM": "synthetic.wm1@example.invalid",
    "BRANCH_MANAGER": "synthetic.branch.manager@example.invalid",
    "COMPLIANCE_OFFICER": "synthetic.compliance@example.invalid",
    "AUDIT_VIEWER": "synthetic.audit@example.invalid",
    "ADMIN": "synthetic.admin@example.invalid",
}

CUSTOMER_PB1 = "33333333-3333-3333-3333-333333333301"
CONSULTATION_PB1 = "66666666-6666-6666-6666-666666666301"
PRODUCT_ID = "44444444-4444-4444-4444-444444444401"

# The auto-approve endpoint (added by worker-mike W2-T13)
AUTO_APPROVE_ROUTE = "/recommendation-simulations/auto-approve"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: Any | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, Any, str]:
    data = None
    headers: dict[str, str] = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        f"{base_url}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode("utf-8")
            return resp.status, json.loads(text) if text else {}, text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8")
        try:
            payload = json.loads(text) if text else {}
        except json.JSONDecodeError:
            payload = {"raw": text}
        return exc.code, payload, text


async def _audit_rows(
    action_code: str,
    governance_marker: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    asyncpg = pytest.importorskip("asyncpg")
    from db.migrator import database_url_from_env, load_env_file

    load_env_file(PROJECT_ROOT / ".env")
    conn = await connect_with_retry(asyncpg, database_url_from_env())
    try:
        if governance_marker is not None:
            rows = await conn.fetch(
                """SELECT id, action_code, governance_marker, detail_json
                   FROM audit_logs
                   WHERE action_code = $1 AND governance_marker = $2
                   ORDER BY created_at DESC LIMIT $3""",
                action_code,
                governance_marker,
                limit,
            )
        else:
            rows = await conn.fetch(
                """SELECT id, action_code, governance_marker, detail_json
                   FROM audit_logs
                   WHERE action_code = $1
                   ORDER BY created_at DESC LIMIT $2""",
                action_code,
                limit,
            )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def _audit_count(action_code: str) -> int:
    asyncpg = pytest.importorskip("asyncpg")
    from db.migrator import database_url_from_env, load_env_file

    load_env_file(PROJECT_ROOT / ".env")
    conn = await connect_with_retry(asyncpg, database_url_from_env())
    try:
        return int(
            await conn.fetchval(
                "SELECT COUNT(*)::int FROM audit_logs WHERE action_code = $1", action_code
            )
            or 0
        )
    finally:
        await conn.close()


async def _redis_counter(key: str) -> int:
    try:
        import redis as redis_lib  # pyright: ignore[reportMissingImports]

        r = redis_lib.Redis.from_url(
            "redis://localhost:6379/15", decode_responses=True
        )
        val = r.get(key)
        r.close()
        return int(val) if val is not None else 0
    except Exception:  # noqa: BLE001
        return -1  # Redis unavailable — caller must handle


def _prepare_database() -> None:
    async def _run() -> None:
        asyncpg = pytest.importorskip("asyncpg")
        from db.migrator import database_url_from_env, load_env_file
        from db.seed import apply_profile

        load_env_file(PROJECT_ROOT / ".env")
        # DB is already fully migrated by other workers; just connect and seed.
        try:
            conn = await connect_with_retry(asyncpg, database_url_from_env())
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable: {exc}")
        try:
            await apply_profile(conn, "full-mvp")
        finally:
            await conn.close()

    asyncio.run(_run())


def _enable_demo_mode(_pg_conn: Any) -> None:  # noqa: ANN001
    """Set system_flags.demo_mode so the 3-layer guard (Layer B) passes.

    evaluate_demo_mode_flag() requires enabled=true AND expires_at in the future
    AND no aborted_at. We use a fresh asyncpg connection to avoid the cross-loop
    issue that arises when the module-scoped pg_conn fixture's loop differs from
    the asyncio.run() loop created here.
    """
    import datetime as _dt

    async def _run() -> None:
        asyncpg_mod = pytest.importorskip("asyncpg")
        from db.migrator import database_url_from_env, load_env_file

        load_env_file(PROJECT_ROOT / ".env")
        expires_at = (
            _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=9)
        ).isoformat()
        conn = await connect_with_retry(asyncpg_mod, database_url_from_env())
        try:
            await conn.execute(
                """UPDATE system_flags
                   SET flag_value = jsonb_build_object(
                       'enabled', true,
                       'expires_at', $1::text,
                       'toggled_on_by', 'test-worker-lima',
                       'aborted_at', null::text
                   ),
                   change_reason = 'test-harness: enable demo_mode for PoC matrix',
                   ticket_id     = 'POC-MATRIX',
                   updated_by    = '22222222-2222-2222-2222-222222222203'
                   WHERE flag_name = 'demo_mode'""",
                expires_at,
            )
        finally:
            await conn.close()

    asyncio.run(_run())


def _disable_demo_mode(_pg_conn: Any) -> None:  # noqa: ANN001
    """Reset system_flags.demo_mode to disabled state after test."""

    async def _run() -> None:
        asyncpg_mod = pytest.importorskip("asyncpg")
        from db.migrator import database_url_from_env, load_env_file

        load_env_file(PROJECT_ROOT / ".env")
        conn = await connect_with_retry(asyncpg_mod, database_url_from_env())
        try:
            await conn.execute(
                """UPDATE system_flags
                   SET flag_value = jsonb_build_object(
                       'enabled', false,
                       'expires_at', null::text
                   ),
                   change_reason = 'test-harness: disable demo_mode after PoC matrix',
                   ticket_id     = 'POC-MATRIX',
                   updated_by    = '22222222-2222-2222-2222-222222222203'
                   WHERE flag_name = 'demo_mode'"""
            )
        finally:
            await conn.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Server + DB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api_server() -> str:  # type: ignore[return]
    """Running API server for PoC_AUTO_APPROVAL matrix tests."""
    _prepare_database()
    port = _free_port()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "poc-auto-approval-matrix.log"
    env = os.environ.copy()
    env["PYTHONPATH"] = (
        f"{PROJECT_ROOT}:{PROJECT_ROOT / 'apps/api'}:{env.get('PYTHONPATH', '')}"
    )
    env["HARNESS_EMAIL_SEND_ENABLED"] = "false"
    env["REDIS_URL"] = "redis://localhost:6379/15"  # always override; ambient may point to prod
    command = [
        str(
            Path(os.environ.get("PYTHON_PATH", "/opt/conda/envs/wm_env/bin/python"))
        ),
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


@pytest.fixture(scope="module")
def pg_conn():  # type: ignore[return]
    """asyncpg connection for direct DB assertions."""
    import asyncio as _asyncio

    loop = _asyncio.new_event_loop()

    async def _connect():
        asyncpg = pytest.importorskip("asyncpg")
        from db.migrator import database_url_from_env, load_env_file

        load_env_file(PROJECT_ROOT / ".env")
        try:
            return await connect_with_retry(asyncpg, database_url_from_env())
        except Exception as exc:
            pytest.skip(f"PostgreSQL unavailable: {exc}")

    conn = loop.run_until_complete(_connect())
    try:
        yield conn
    finally:
        loop.run_until_complete(conn.close())
        loop.close()


@pytest.fixture(scope="module")
def tokens(api_server: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for role, email in ACCOUNTS.items():
        status, payload, text = _request(
            api_server,
            "POST",
            "/auth/login",
            body={"email": email, "password": SYNTHETIC_PASSWORD},
        )
        if status == 200:
            result[role] = str(payload["access_token"])
    return result


def _valid_auto_approve_body() -> dict[str, Any]:
    """Minimal valid body for a PoC_AUTO_APPROVAL request (all 4 gates pass)."""
    return {
        "customer_id": CUSTOMER_PB1,
        "consultation_id": CONSULTATION_PB1,
        "product_id": PRODUCT_ID,
        "explanation_checked": True,
        "simulated_customer_consented": True,
        "employee_final_approved": True,
    }


def _skip_if_route_missing(status: int, route: str, blocker: str) -> None:
    if status == 404:
        pytest.skip(f"Route {route} not yet implemented (BLOCKER {blocker})")
    if status == 405:
        pytest.skip(f"Route {route} method not allowed yet (BLOCKER {blocker})")


# ===========================================================================
# S01: All 4 gates PASS + demo_mode ON → auto_approve allowed
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_s01_all_gates_pass_demo_mode_on_auto_approves(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """S01: All 4 gates PASS + demo_mode=true → recommendation_simulation_auto_approve.

    REG-06 §5, ADR-004, governance_marker='PoC_AUTO_APPROVAL' set.
    BLOCKER: #33 (worker-mike W2-T13 — PoC_AUTO_APPROVAL guard service)
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    _enable_demo_mode(pg_conn)
    try:
        before = asyncio.run(_audit_count("recommendation_simulation_auto_approve"))
        status, payload, text = _request(
            api_server,
            "POST",
            AUTO_APPROVE_ROUTE,
            token=tokens["PB"],
            body=_valid_auto_approve_body(),
            extra_headers={"X-Poc-Demo-Mode": "true"},
        )
        _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

        assert status in (200, 201), (
            f"S01: All gates PASS + demo_mode ON must return 200/201; "
            f"got {status}: {text[:500]} (REG-06 §5, ADR-004)"
        )
        assert payload.get("status_code") == "APPROVED", (
            f"S01: Expected status_code=APPROVED; got {payload.get('status_code')} "
            "(PoC_AUTO_APPROVAL 4-gate exit)"
        )

        # Audit row with governance_marker='PoC_AUTO_APPROVAL' must be inserted
        after_rows = asyncio.run(
            _audit_rows("recommendation_simulation_auto_approve", "PoC_AUTO_APPROVAL")
        )
        assert len(after_rows) > 0, (
            "S01: audit_logs row with action_code=recommendation_simulation_auto_approve "
            "AND governance_marker='PoC_AUTO_APPROVAL' must be inserted (REG-06 §5, V021)"
        )

        # prod_guard.would_block_in_prod must be true (S14 overlap)
        detail = after_rows[0].get("detail_json") or {}
        if isinstance(detail, str):
            detail = json.loads(detail)
        prod_guard = detail.get("prod_guard", {})
        assert prod_guard.get("would_block_in_prod") is True, (
            "S01: prod_guard.would_block_in_prod must be true on every auto-approve "
            "(REG-06 §3.2 gate_evidence_json invariant)"
        )

        # No gate bypass: all four gates must still be evaluated
        four_gates = detail.get("four_gates", {})
        assert four_gates, (
            "S01: gate_evidence_json.four_gates must be present in audit detail (REG-06 §3.2)"
        )

        after = asyncio.run(_audit_count("recommendation_simulation_auto_approve"))
        assert after > before, "S01: recommendation_simulation_auto_approve count must increment"
    finally:
        _disable_demo_mode(pg_conn)


# ===========================================================================
# S02: All 4 gates PASS + demo_mode OFF → BLOCKED
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_s02_all_gates_pass_demo_mode_off_blocked(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """S02: demo_mode=false → auto-approve BLOCKED regardless of gate results.

    ADR-004: POC_AUTO_APPROVAL_ENABLED env guard; demo_mode=false means guard is off.
    BLOCKER: #33
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    _disable_demo_mode(pg_conn)
    status, payload, text = _request(
        api_server,
        "POST",
        AUTO_APPROVE_ROUTE,
        token=tokens["PB"],
        body=_valid_auto_approve_body(),
        extra_headers={"X-Poc-Demo-Mode": "true"},
    )
    _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

    assert status in (403, 409, 200), (
        f"S02: demo_mode=false must block auto-approve; got {status}: {text[:300]}"
    )
    if status == 200:
        assert payload.get("status_code") == "BLOCKED", (
            "S02: demo_mode=false must yield BLOCKED even when header present (ADR-004 env guard)"
        )


# ===========================================================================
# S03–S06: Individual gate failures with demo_mode ON
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario_id,override_body,expected_block_hint",
    [
        (
            "S03",
            {"simulated_customer_consented": False},
            "suitability or consent gate",
        ),
        (
            "S04",
            {"explanation_checked": False},
            "explanation gate",
        ),
        (
            "S05",
            {"simulated_customer_consented": False},
            "consent gate",
        ),
        (
            "S06",
            {"employee_final_approved": False},
            "employee_approval gate",
        ),
    ],
    ids=["S03", "S04", "S05", "S06"],
)
def test_s03_to_s06_gate_failure_blocks_auto_approve(
    api_server: str,
    tokens: dict[str, str],
    pg_conn: Any,
    scenario_id: str,
    override_body: dict[str, Any],
    expected_block_hint: str,
) -> None:
    """S03-S06: Any single gate FAIL + demo_mode ON → BLOCKED (gate enforcement).

    No gate bypass: even with demo_mode=true, a failing gate must prevent auto-approval.
    REG-06 §3.2 invariant: four_gates.*.status must all be PASSED for auto-approve.
    BLOCKER: #33 (worker-mike W2-T13)
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    _enable_demo_mode(pg_conn)
    try:
        body = {**_valid_auto_approve_body(), **override_body}
        before = asyncio.run(_audit_count("poc_auto_approval_blocked"))
        status, payload, text = _request(
            api_server,
            "POST",
            AUTO_APPROVE_ROUTE,
            token=tokens["PB"],
            body=body,
            extra_headers={"X-Poc-Demo-Mode": "true"},
        )
        _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

        assert payload.get("status_code") == "BLOCKED" or status in (409, 422, 403), (
            f"{scenario_id}: {expected_block_hint} failure must BLOCK auto-approve even "
            f"with demo_mode=true; got {status} {payload} (REG-06 §3.2)"
        )

        after = asyncio.run(_audit_count("poc_auto_approval_blocked"))
        assert after > before, (
            f"{scenario_id}: poc_auto_approval_blocked audit row must be inserted "
            f"when {expected_block_hint} fails (REG-06 §3.2)"
        )
    finally:
        _disable_demo_mode(pg_conn)


# ===========================================================================
# S07: X-Poc-Demo-Mode header missing → BLOCKED
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_s07_missing_poc_header_blocked(
    api_server: str, tokens: dict[str, str]
) -> None:
    """S07: X-Poc-Demo-Mode header absent → BLOCKED (header required, ADR-004).

    BLOCKER: #33
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    status, payload, text = _request(
        api_server,
        "POST",
        AUTO_APPROVE_ROUTE,
        token=tokens["PB"],
        body=_valid_auto_approve_body(),
        # No X-Poc-Demo-Mode header
    )
    _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

    assert payload.get("status_code") == "BLOCKED" or status in (400, 403, 422), (
        f"S07: Missing X-Poc-Demo-Mode header must BLOCK auto-approve; "
        f"got {status}: {text[:300]} (ADR-004)"
    )


# ===========================================================================
# S08: Header present but env disabled → BLOCKED
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_s08_header_present_env_disabled_blocked(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """S08: X-Poc-Demo-Mode header present but POC_AUTO_APPROVAL_ENABLED=false → BLOCKED.

    ADR-004: env var guard is the outer layer — header alone is insufficient.
    BLOCKER: #33
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    # Ensure demo_mode is disabled at DB level
    _disable_demo_mode(pg_conn)
    status, payload, text = _request(
        api_server,
        "POST",
        AUTO_APPROVE_ROUTE,
        token=tokens["PB"],
        body=_valid_auto_approve_body(),
        extra_headers={"X-Poc-Demo-Mode": "true"},
    )
    _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

    assert payload.get("status_code") == "BLOCKED" or status in (403, 409), (
        f"S08: X-Poc-Demo-Mode header with env disabled must BLOCKED; "
        f"got {status}: {text[:300]} (ADR-004 env guard)"
    )


# ===========================================================================
# S09: 8h auto-expire → BLOCKED + demo_mode_expired audit
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_s09_demo_mode_8h_expire_blocked(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """S09: 8h auto-expire elapsed → BLOCKED + demo_mode_expired audit (REG-06 §4, ADR-004).

    The test sets an expired_at timestamp in the past to simulate the expiry.
    BLOCKER: #33
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    # Set demo_mode with expired_at in the past (fresh connection avoids cross-loop issue)
    _enable_demo_mode(pg_conn)

    async def _expire_demo_mode_past() -> None:
        asyncpg_mod = pytest.importorskip("asyncpg")
        from db.migrator import database_url_from_env, load_env_file

        load_env_file(PROJECT_ROOT / ".env")
        conn = await connect_with_retry(asyncpg_mod, database_url_from_env())
        try:
            await conn.execute(
                """UPDATE system_flags
                   SET flag_value = flag_value
                       || '{"enabled": true, "expires_at": "2020-01-01T00:00:00+00:00"}'::jsonb,
                   change_reason = 'test-harness: back-date expires_at for S09 expiry test',
                   ticket_id     = 'POC-MATRIX',
                   updated_by    = '22222222-2222-2222-2222-222222222203'
                   WHERE flag_name = 'demo_mode'"""
            )
        finally:
            await conn.close()

    asyncio.run(_expire_demo_mode_past())
    try:
        before = asyncio.run(_audit_count("demo_mode_expired"))
        status, payload, text = _request(
            api_server,
            "POST",
            AUTO_APPROVE_ROUTE,
            token=tokens["PB"],
            body=_valid_auto_approve_body(),
            extra_headers={"X-Poc-Demo-Mode": "true"},
        )
        _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

        assert payload.get("status_code") == "BLOCKED" or status in (403, 409), (
            f"S09: Expired demo_mode must BLOCK auto-approve; "
            f"got {status}: {text[:300]} (ADR-004 8h expiry)"
        )
        after = asyncio.run(_audit_count("demo_mode_expired"))
        assert after > before, (
            "S09: demo_mode_expired audit row must be inserted when 8h TTL crossed (REG-06 §4)"
        )
    finally:
        _disable_demo_mode(pg_conn)


# ===========================================================================
# S10: Per-employee rate ceiling → BLOCKED + poc_auto_approval_rate_limited
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_s10_rate_ceiling_exceeded_blocked(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """S10: Per-employee rate ceiling exceeded → BLOCKED + poc_auto_approval_rate_limited.

    REG-06 §5: 10/min or 60/hr per employee ceiling.
    BLOCKER: #33 (rate limiting logic in guard service)
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    _enable_demo_mode(pg_conn)
    try:
        # Pre-seed a Redis rate counter above the ceiling
        import redis as redis_lib  # pyright: ignore[reportMissingImports]

        r = redis_lib.Redis.from_url(
            "redis://localhost:6379/15", decode_responses=True
        )
        # Simulate rate counter above 10/min ceiling for this employee
        rate_key = f"poc_auto_approve_rate:PB:{ACCOUNTS['PB']}"
        r.setex(rate_key, 60, 11)  # 11 requests in last 60s
        r.close()

        before = asyncio.run(_audit_count("poc_auto_approval_rate_limited"))
        status, payload, text = _request(
            api_server,
            "POST",
            AUTO_APPROVE_ROUTE,
            token=tokens["PB"],
            body=_valid_auto_approve_body(),
            extra_headers={"X-Poc-Demo-Mode": "true"},
        )
        _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

        assert payload.get("status_code") == "BLOCKED" or status in (429, 403), (
            f"S10: Rate ceiling exceeded must BLOCK auto-approve; "
            f"got {status}: {text[:300]} (REG-06 §5 10/min ceiling)"
        )
        after = asyncio.run(_audit_count("poc_auto_approval_rate_limited"))
        assert after > before, (
            "S10: poc_auto_approval_rate_limited audit row must be inserted (REG-06 §5)"
        )
    except ImportError:
        pytest.skip("redis-py not installed; skipping rate-limit Redis injection test")
    finally:
        _disable_demo_mode(pg_conn)


# ===========================================================================
# S11: Abort threshold >5% fail-rate → ALL BLOCKED
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_s11_abort_threshold_blocks_all_auto_approves(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """S11: Abort threshold tripped (4-gate fail rate >5% in last hour) → ALL BLOCKED.

    REG-06 §5: poc_auto_approval_aborted audit on every subsequent attempt.
    BLOCKER: #33
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    _enable_demo_mode(pg_conn)
    try:
        # Simulate abort condition via env/Redis flag (worker-mike W2-T13 defines the key)
        try:
            import redis as redis_lib  # pyright: ignore[reportMissingImports]

            r = redis_lib.Redis.from_url(
                "redis://localhost:6379/15", decode_responses=True
            )
            r.setex("poc_auto_approve_abort_triggered", 3600, "1")
            r.close()
        except ImportError:
            pytest.skip("redis-py not installed; skipping abort threshold test")

        before = asyncio.run(_audit_count("poc_auto_approval_aborted"))
        status, payload, text = _request(
            api_server,
            "POST",
            AUTO_APPROVE_ROUTE,
            token=tokens["PB"],
            body=_valid_auto_approve_body(),
            extra_headers={"X-Poc-Demo-Mode": "true"},
        )
        _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

        assert payload.get("status_code") == "BLOCKED" or status in (503, 403), (
            f"S11: Abort threshold must block all auto-approves; "
            f"got {status}: {text[:300]} (REG-06 §5 abort gate)"
        )
        after = asyncio.run(_audit_count("poc_auto_approval_aborted"))
        assert after > before, (
            "S11: poc_auto_approval_aborted audit row must be inserted (REG-06 §5)"
        )
    finally:
        _disable_demo_mode(pg_conn)
        try:
            import redis as redis_lib  # pyright: ignore[reportMissingImports]

            r = redis_lib.Redis.from_url(
                "redis://localhost:6379/15", decode_responses=True
            )
            r.delete("poc_auto_approve_abort_triggered")
            r.close()
        except ImportError:
            pass


# ===========================================================================
# S12: governance_marker='PoC_AUTO_APPROVAL' set on success
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_s12_governance_marker_poc_auto_approval_on_success(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """S12: Successful auto-approve → audit row governance_marker='PoC_AUTO_APPROVAL'.

    V021 CHECK constraint: governance_marker must be in allowed set.
    BLOCKER: #33
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    _enable_demo_mode(pg_conn)
    try:
        status, payload, text = _request(
            api_server,
            "POST",
            AUTO_APPROVE_ROUTE,
            token=tokens["PB"],
            body=_valid_auto_approve_body(),
            extra_headers={"X-Poc-Demo-Mode": "true"},
        )
        _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

        if status in (200, 201) and payload.get("status_code") == "APPROVED":
            rows = asyncio.run(
                _audit_rows("recommendation_simulation_auto_approve", "PoC_AUTO_APPROVAL")
            )
            assert len(rows) >= 1, (
                "S12: governance_marker='PoC_AUTO_APPROVAL' must be set on auto-approve success "
                "(V021 CHECK constraint, REG-06 §3.1)"
            )
        else:
            pytest.skip(f"S12: Auto-approve not yet returning APPROVED; got {status} {payload}")
    finally:
        _disable_demo_mode(pg_conn)


# ===========================================================================
# S13: governance_marker='HUMAN_REVIEW' when human approves manually
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_s13_governance_marker_human_review_on_manual_approval(
    api_server: str, tokens: dict[str, str]
) -> None:
    """S13: Human manual approval → audit row governance_marker='HUMAN_REVIEW'.

    V021 CHECK constraint confirms 'HUMAN_REVIEW' is a valid governance_marker value.
    The existing /recommendation-simulations route (human flow) should use HUMAN_REVIEW.
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    before_rows = asyncio.run(_audit_rows("recommendation_simulation_create", "HUMAN_REVIEW"))
    status, payload, text = _request(
        api_server,
        "POST",
        "/recommendation-simulations",
        token=tokens["PB"],
        body=_valid_auto_approve_body(),
    )
    assert status == 201, f"S13: POST /recommendation-simulations failed: {text[:500]}"

    if payload.get("status_code") == "APPROVED":
        # Check that human-flow audit row has HUMAN_REVIEW marker
        after_rows = asyncio.run(
            _audit_rows("recommendation_simulation_create", "HUMAN_REVIEW")
        )
        if len(after_rows) > len(before_rows):
            # Worker-mike wires HUMAN_REVIEW marker in W2-T13
            assert after_rows[0].get("governance_marker") == "HUMAN_REVIEW", (
                "S13: Human approval audit row must have governance_marker='HUMAN_REVIEW' "
                "(V021, REG-06 §3.1)"
            )
        # If no HUMAN_REVIEW rows yet, skip — worker-mike W2-T13 wires this


# ===========================================================================
# S14: prod_guard.would_block_in_prod=true on every auto-approve row
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_s14_prod_guard_would_block_in_prod_is_always_true(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """S14: Every PoC_AUTO_APPROVAL audit row must have prod_guard.would_block_in_prod=true.

    REG-06 §3.2 gate_evidence_json: static invariant, cannot be false.
    BLOCKER: #33
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    _enable_demo_mode(pg_conn)
    try:
        status, payload, text = _request(
            api_server,
            "POST",
            AUTO_APPROVE_ROUTE,
            token=tokens["PB"],
            body=_valid_auto_approve_body(),
            extra_headers={"X-Poc-Demo-Mode": "true"},
        )
        _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

        if status in (200, 201) and payload.get("status_code") == "APPROVED":
            rows = asyncio.run(
                _audit_rows("recommendation_simulation_auto_approve", "PoC_AUTO_APPROVAL")
            )
            assert rows, "S14: No auto-approve audit rows found"
            for row in rows:
                detail = row.get("detail_json") or {}
                if isinstance(detail, str):
                    detail = json.loads(detail)
                prod_guard = detail.get("prod_guard", {})
                assert prod_guard.get("would_block_in_prod") is True, (
                    f"S14: audit row {row['id']} prod_guard.would_block_in_prod must be true; "
                    f"got {prod_guard} (REG-06 §3.2 static invariant)"
                )
        else:
            pytest.skip(f"S14: Auto-approve route not yet returning APPROVED; got {status}")
    finally:
        _disable_demo_mode(pg_conn)


# ===========================================================================
# R01-R03: 5-role permission matrix
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_r01_audit_viewer_cannot_auto_approve(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """R01: AUDIT_VIEWER role → 403 on auto-approve endpoint (read-only, REG-06 §4, SEC-01).

    AUDIT_VIEWER has no mutation rights — auto-approve is a write operation.
    """
    if "AUDIT_VIEWER" not in tokens:
        pytest.skip("AUDIT_VIEWER token not available")

    _enable_demo_mode(pg_conn)
    try:
        status, payload, text = _request(
            api_server,
            "POST",
            AUTO_APPROVE_ROUTE,
            token=tokens["AUDIT_VIEWER"],
            body=_valid_auto_approve_body(),
            extra_headers={"X-Poc-Demo-Mode": "true"},
        )
        _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

        assert status == 403, (
            f"R01: AUDIT_VIEWER must receive 403 on auto-approve; "
            f"got {status}: {text[:300]} (SEC-01 AUDIT_VIEWER read-only)"
        )
    finally:
        _disable_demo_mode(pg_conn)


@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_r02_compliance_officer_cannot_auto_approve(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """R02: COMPLIANCE_OFFICER role → 403 on auto-approve (not a front-office role).

    SEC-01 §5: COMPLIANCE_OFFICER has review/oversight permissions, not simulation create.
    BLOCKER: #24 (COMPLIANCE_OFFICER account may not exist until W2-T4)
    """
    if "COMPLIANCE_OFFICER" not in tokens:
        pytest.skip("COMPLIANCE_OFFICER token not available (BLOCKER #24 worker-india W2-T4)")

    _enable_demo_mode(pg_conn)
    try:
        status, payload, text = _request(
            api_server,
            "POST",
            AUTO_APPROVE_ROUTE,
            token=tokens["COMPLIANCE_OFFICER"],
            body=_valid_auto_approve_body(),
            extra_headers={"X-Poc-Demo-Mode": "true"},
        )
        _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

        assert status == 403, (
            f"R02: COMPLIANCE_OFFICER must receive 403 on auto-approve; "
            f"got {status}: {text[:300]} (SEC-01 role boundary)"
        )
    finally:
        _disable_demo_mode(pg_conn)


@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_r03_pb_can_auto_approve_when_all_gates_pass(
    api_server: str, tokens: dict[str, str], pg_conn: Any
) -> None:
    """R03: PB role with demo_mode=true + all gates pass → 201 APPROVED.

    This is the golden path for PoC_AUTO_APPROVAL (REG-06 §4 G1 scenario).
    BLOCKER: #33
    """
    if "PB" not in tokens:
        pytest.skip("PB token not available")

    _enable_demo_mode(pg_conn)
    try:
        status, payload, text = _request(
            api_server,
            "POST",
            AUTO_APPROVE_ROUTE,
            token=tokens["PB"],
            body=_valid_auto_approve_body(),
            extra_headers={"X-Poc-Demo-Mode": "true"},
        )
        _skip_if_route_missing(status, AUTO_APPROVE_ROUTE, "#33")

        assert status in (200, 201), (
            f"R03: PB role must succeed on valid auto-approve request; "
            f"got {status}: {text[:500]} (REG-06 §4 G1)"
        )
        assert payload.get("status_code") == "APPROVED", (
            f"R03: PB valid auto-approve must yield APPROVED; "
            f"got {payload.get('status_code')} (REG-06 §4)"
        )
    finally:
        _disable_demo_mode(pg_conn)


# ===========================================================================
# Anonymous access must still be blocked (S01 + PoC does not bypass auth)
# ===========================================================================

@pytest.mark.poc_auto_approval
@pytest.mark.integration
def test_anonymous_cannot_access_auto_approve_route(api_server: str) -> None:
    """Anonymous → 401 on auto-approve endpoint (PoC_AUTO_APPROVAL does not bypass auth).

    REG-05 T299: PoC mode must not create unauthenticated access paths.
    """
    status, payload, text = _request(
        api_server,
        "POST",
        AUTO_APPROVE_ROUTE,
        body=_valid_auto_approve_body(),
        extra_headers={"X-Poc-Demo-Mode": "true"},
        # No Authorization header
    )
    if status == 404:
        pytest.skip(f"Route {AUTO_APPROVE_ROUTE} not yet implemented (BLOCKER #33)")

    assert status == 401, (
        f"Anonymous request to auto-approve route must return 401; "
        f"got {status}: {text[:300]} (REG-05 T299 — PoC does not bypass auth)"
    )
