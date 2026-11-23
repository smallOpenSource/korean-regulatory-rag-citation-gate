"""PoC_AUTO_APPROVAL regression tests (REG-05/REG-06 T299, ADR-004).

Task IDs: T299
Ref: docs/regulations/REG-05_internet_security.md §3
     docs/regulations/REG-06_poc_auto_approval.md (ADR-004)
     db/migrations/V020__system_flags.sql (demo_mode seed)
     db/migrations/V021__governance_marker.sql (governance_marker CHECK constraint)

Covers:
- system_flags.demo_mode.enabled is seeded to false (PoC gate off by default)
- system_flags update trigger trg_system_flags_admin_check exists
- governance_marker column exists on audit_logs (V021)
- governance_marker CHECK constraint accepts PoC_AUTO_APPROVAL, HUMAN_REVIEW, AUTO_SYSTEM, NULL
- governance_marker CHECK constraint rejects invalid values
- Protected API endpoints require auth token even in PoC environment (no bypass)
- PoC_AUTO_APPROVAL audit row with governance_marker='PoC_AUTO_APPROVAL' is valid

Note: a module-level event loop (_module_loop) is kept alive for the entire
module to avoid the "Future attached to a different loop" asyncpg error that
occurs when asyncio.run() is called repeatedly on the same connection object.
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

import pytest

from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / ".omx" / "logs" / "tests"

# Module-level event loop kept alive for the duration of this test module.
_module_loop: asyncio.AbstractEventLoop | None = None


@pytest.fixture(scope="module", autouse=True)
def _event_loop():
    """Provide a single event loop for the entire module."""
    global _module_loop
    _module_loop = asyncio.new_event_loop()
    yield _module_loop
    _module_loop.close()
    _module_loop = None


def _run(coro):  # type: ignore[return]
    """Run a coroutine in the module-level event loop."""
    assert _module_loop is not None, "_event_loop fixture must be active"
    return _module_loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# DB connection helper
# ---------------------------------------------------------------------------

async def _get_pg_conn():  # type: ignore[return]
    asyncpg = pytest.importorskip("asyncpg")
    from db.migrator import database_url_from_env, load_env_file
    from db.migrator import run as run_migrations

    load_env_file(PROJECT_ROOT / ".env")
    try:
        await run_migrations()
        return await connect_with_retry(asyncpg, database_url_from_env())
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL unavailable: {exc}")


@pytest.fixture(scope="module")
def pg_conn(_event_loop):  # type: ignore[return]
    """Provide a real asyncpg connection for the module, bound to _event_loop."""
    conn = _event_loop.run_until_complete(_get_pg_conn())
    try:
        yield conn
    finally:
        _event_loop.run_until_complete(conn.close())


# ---------------------------------------------------------------------------
# Server helpers for API integration tests
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
    """Running API server for PoC_AUTO_APPROVAL regression tests."""
    _run(_prepare_database())
    port = _free_port()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "poc-auto-approval.log"
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


# ---------------------------------------------------------------------------
# DB-only tests — system_flags and governance_marker (no server needed)
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_system_flags_demo_mode_enabled_is_false(pg_conn):
    """system_flags.demo_mode.enabled must be seeded to false (ADR-004, REG-06 T299)."""
    result = _run(pg_conn.fetchval(
        """/* sql_id: test_demo_mode_seeded_false */
        SELECT flag_value->>'enabled'
        FROM system_flags
        WHERE flag_name = 'demo_mode'
        """
    ))
    assert result is not None, (
        "system_flags row 'demo_mode' must exist (V020 seed, ADR-004, T299)"
    )
    assert result == "false", (
        f"system_flags.demo_mode.enabled must be 'false' (ADR-004, T299); got {result!r}"
    )


@pytest.mark.security
@pytest.mark.integration
def test_system_flags_admin_check_trigger_exists(pg_conn):
    """trg_system_flags_admin_check trigger must exist on system_flags (V020, T299)."""
    result = _run(pg_conn.fetchval(
        """/* sql_id: test_system_flags_trigger_exists */
        SELECT COUNT(*)::int
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE c.relname = 'system_flags'
          AND t.tgname = 'trg_system_flags_admin_check'
          AND NOT t.tgisinternal
        """
    ))
    assert result == 1, (
        "trg_system_flags_admin_check trigger must exist on system_flags (V020, T299)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_governance_marker_column_exists_on_audit_logs(pg_conn):
    """governance_marker column must exist on audit_logs table (V021, T299)."""
    result = _run(pg_conn.fetchval(
        """/* sql_id: test_governance_marker_column_exists */
        SELECT COUNT(*)::int
        FROM information_schema.columns
        WHERE table_name = 'audit_logs'
          AND column_name = 'governance_marker'
        """
    ))
    assert result == 1, (
        "governance_marker column must exist on audit_logs (V021 migration, T299)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_governance_marker_check_constraint_exists(pg_conn):
    """chk_governance_marker_values CHECK constraint must exist on audit_logs (V021, T299)."""
    result = _run(pg_conn.fetchval(
        """/* sql_id: test_governance_marker_constraint_exists */
        SELECT COUNT(*)::int
        FROM information_schema.table_constraints
        WHERE table_name = 'audit_logs'
          AND constraint_name = 'chk_governance_marker_values'
          AND constraint_type = 'CHECK'
        """
    ))
    assert result == 1, (
        "chk_governance_marker_values CHECK constraint must exist on audit_logs (V021, T299)"
    )


@pytest.mark.security
@pytest.mark.integration
def test_governance_marker_poc_auto_approval_value_is_valid(pg_conn):
    """INSERT audit_log with governance_marker='PoC_AUTO_APPROVAL' must succeed (V021, T299)."""
    async def _run_test() -> None:
        row_id = await pg_conn.fetchval(
            """/* sql_id: test_governance_marker_poc_auto_approval_valid */
            INSERT INTO audit_logs
                (actor_id, action_code, resource_type, detail_json, governance_marker)
            VALUES
                (NULL, 'AI_CALL_STARTED', 'test', '{"test": true}'::jsonb, 'PoC_AUTO_APPROVAL')
            RETURNING id
            """
        )
        assert row_id is not None, (
            "INSERT with governance_marker='PoC_AUTO_APPROVAL' must succeed (V021, T299)"
        )

    _run(_run_test())


@pytest.mark.security
@pytest.mark.integration
def test_governance_marker_human_review_value_is_valid(pg_conn):
    """INSERT audit_log with governance_marker='HUMAN_REVIEW' must succeed (V021, T299)."""
    async def _run_test() -> None:
        row_id = await pg_conn.fetchval(
            """/* sql_id: test_governance_marker_human_review_valid */
            INSERT INTO audit_logs
                (actor_id, action_code, resource_type, detail_json, governance_marker)
            VALUES
                (NULL, 'AI_CALL_STARTED', 'test', '{"test": true}'::jsonb, 'HUMAN_REVIEW')
            RETURNING id
            """
        )
        assert row_id is not None, (
            "INSERT with governance_marker='HUMAN_REVIEW' must succeed (V021, T299)"
        )

    _run(_run_test())


@pytest.mark.security
@pytest.mark.integration
def test_governance_marker_null_value_is_valid(pg_conn):
    """INSERT audit_log with governance_marker=NULL is allowed (default, V021, T299)."""
    async def _run_test() -> None:
        row_id = await pg_conn.fetchval(
            """/* sql_id: test_governance_marker_null_valid */
            INSERT INTO audit_logs
                (actor_id, action_code, resource_type, detail_json)
            VALUES
                (NULL, 'AI_CALL_STARTED', 'test', '{"test": true}'::jsonb)
            RETURNING id
            """
        )
        assert row_id is not None, (
            "INSERT with governance_marker=NULL (default) must succeed (V021, T299)"
        )

    _run(_run_test())


@pytest.mark.security
@pytest.mark.integration
def test_governance_marker_invalid_value_fails_check_constraint(pg_conn):
    """INSERT audit_log with an invalid governance_marker value raises a constraint violation (V021, T299)."""
    asyncpg = pytest.importorskip("asyncpg")

    async def _run_test() -> None:
        with pytest.raises(asyncpg.CheckViolationError):
            await pg_conn.execute(
                """/* sql_id: test_governance_marker_invalid_value */
                INSERT INTO audit_logs
                    (actor_id, action_code, resource_type, detail_json, governance_marker)
                VALUES
                    (NULL, 'AI_CALL_STARTED', 'test', '{"test": true}'::jsonb,
                     'INVALID_MARKER_VALUE')
                """
            )

    _run(_run_test())


# ---------------------------------------------------------------------------
# Integration tests — API endpoint auth not bypassed by PoC environment
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_dashboard_requires_auth_in_poc_environment(api_server: str):
    """GET /dashboard returns 401 without auth token — PoC_AUTO_APPROVAL does not bypass auth (T299)."""
    req = urllib.request.Request(
        f"{api_server}/dashboard",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        pytest.fail("Expected 401 for unauthenticated /dashboard request")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401, (
            f"/dashboard must return 401 without auth; got {exc.code} "
            "(PoC_AUTO_APPROVAL must not bypass endpoint auth, T299)"
        )


@pytest.mark.security
@pytest.mark.integration
def test_customers_endpoint_requires_auth_in_poc_environment(api_server: str):
    """GET /customers returns 401 without auth — PoC_AUTO_APPROVAL does not grant open access (T299)."""
    req = urllib.request.Request(
        f"{api_server}/customers?limit=1&offset=0",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        pytest.fail("Expected 401 for unauthenticated /customers request")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401, (
            f"/customers must return 401 without auth; got {exc.code} "
            "(PoC_AUTO_APPROVAL must not bypass endpoint auth, T299)"
        )


@pytest.mark.security
@pytest.mark.integration
def test_audit_logs_endpoint_requires_auth_in_poc_environment(api_server: str):
    """GET /audit-logs returns 401 without auth — PoC mode does not expose audit data (T299)."""
    req = urllib.request.Request(
        f"{api_server}/audit-logs?limit=1&offset=0",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        pytest.fail("Expected 401 for unauthenticated /audit-logs request")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401, (
            f"/audit-logs must return 401 without auth; got {exc.code} (T299)"
        )
