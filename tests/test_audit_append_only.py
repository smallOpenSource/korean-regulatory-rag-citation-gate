"""Audit log append-only integrity tests (REG-05 T293, V008 prior-art, V019).

Task IDs: T293
Ref: docs/regulations/REG-05_internet_security.md §7
     db/migrations/V008__audit_email_ai.sql:52-75  (V008 prior-art triggers)
     db/migrations/V019__audit_append_only_trigger.sql  (V019 TRUNCATE trigger + REVOKE)
     docs/security/SEC-02_data_privacy.md (5-year append-only retention)

Covers:
- V008 trigger trg_audit_logs_no_update exists in pg_trigger
- V008 trigger trg_audit_logs_no_delete exists in pg_trigger
- V019 trigger trg_audit_logs_no_truncate exists in pg_trigger
- UPDATE on audit_logs raises exception containing 'append-only'
- DELETE on audit_logs raises exception containing 'append-only'
- TRUNCATE on audit_logs raises exception containing 'TRUNCATE denied'
- PUBLIC cannot UPDATE/DELETE/TRUNCATE audit_logs (privilege check)

All tests connect to real PostgreSQL 17 (no mocks).

Note: a module-level event loop (_module_loop) is kept alive for the entire
module to avoid the "Future attached to a different loop" asyncpg error that
occurs when asyncio.run() is called repeatedly on the same connection object.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# V008 migration lines cited per task #18 spec
V008_CITATION = "db/migrations/V008__audit_email_ai.sql:52-75"

# Module-level event loop kept alive for the duration of this test module.
# asyncpg connections are bound to the loop that created them; calling
# asyncio.run() in each test would create a new loop, causing
# "Future attached to a different loop" errors.
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


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


async def _get_connection():  # type: ignore[return]
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
    conn = _event_loop.run_until_complete(_get_connection())
    try:
        yield conn
    finally:
        _event_loop.run_until_complete(conn.close())


# ---------------------------------------------------------------------------
# Trigger existence tests (V008 prior-art + V019)
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_v008_trg_audit_logs_no_update_exists(pg_conn):
    """V008 prior-art: trg_audit_logs_no_update trigger must exist on audit_logs.

    Citation: db/migrations/V008__audit_email_ai.sql:52-75
    """
    result = _run(pg_conn.fetchval(
        """/* sql_id: test_v008_no_update_trigger_exists */
        SELECT COUNT(*)::int
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE c.relname = 'audit_logs'
          AND t.tgname = 'trg_audit_logs_no_update'
          AND NOT t.tgisinternal
        """
    ))
    assert result == 1, (
        f"V008 trigger 'trg_audit_logs_no_update' not found on audit_logs "
        f"(prior-art citation: {V008_CITATION})"
    )


@pytest.mark.security
@pytest.mark.integration
def test_v008_trg_audit_logs_no_delete_exists(pg_conn):
    """V008 prior-art: trg_audit_logs_no_delete trigger must exist on audit_logs.

    Citation: db/migrations/V008__audit_email_ai.sql:52-75
    """
    result = _run(pg_conn.fetchval(
        """/* sql_id: test_v008_no_delete_trigger_exists */
        SELECT COUNT(*)::int
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE c.relname = 'audit_logs'
          AND t.tgname = 'trg_audit_logs_no_delete'
          AND NOT t.tgisinternal
        """
    ))
    assert result == 1, (
        f"V008 trigger 'trg_audit_logs_no_delete' not found on audit_logs "
        f"(prior-art citation: {V008_CITATION})"
    )


@pytest.mark.security
@pytest.mark.integration
def test_v019_trg_audit_logs_no_truncate_exists(pg_conn):
    """V019: trg_audit_logs_no_truncate trigger must exist on audit_logs."""
    result = _run(pg_conn.fetchval(
        """/* sql_id: test_v019_no_truncate_trigger_exists */
        SELECT COUNT(*)::int
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        WHERE c.relname = 'audit_logs'
          AND t.tgname = 'trg_audit_logs_no_truncate'
          AND NOT t.tgisinternal
        """
    ))
    assert result == 1, (
        "V019 trigger 'trg_audit_logs_no_truncate' not found on audit_logs"
    )


# ---------------------------------------------------------------------------
# Mutation denial tests
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_update_on_audit_logs_is_denied(pg_conn):
    """UPDATE on any audit_log row must raise 'audit_logs are append-only' (V008 T293)."""
    asyncpg = pytest.importorskip("asyncpg")

    async def _run_test() -> None:
        row_id = await pg_conn.fetchval(
            """/* sql_id: test_insert_throwaway_audit */
            INSERT INTO audit_logs (actor_id, action_code, resource_type, detail_json)
            VALUES (NULL, 'AI_CALL_STARTED', 'test', '{"test": true}'::jsonb)
            RETURNING id
            """
        )
        with pytest.raises(asyncpg.PostgresError, match="(?i)append-only"):
            await pg_conn.execute(
                "UPDATE audit_logs SET action_code = 'AI_CALL_FAILED' WHERE id = $1",
                row_id,
            )

    _run(_run_test())


@pytest.mark.security
@pytest.mark.integration
def test_delete_on_audit_logs_is_denied(pg_conn):
    """DELETE on any audit_log row must raise 'audit_logs are append-only' (V008 T293)."""
    asyncpg = pytest.importorskip("asyncpg")

    async def _run_test() -> None:
        row_id = await pg_conn.fetchval(
            """/* sql_id: test_insert_throwaway_audit_delete */
            INSERT INTO audit_logs (actor_id, action_code, resource_type, detail_json)
            VALUES (NULL, 'AI_CALL_STARTED', 'test', '{"test": true}'::jsonb)
            RETURNING id
            """
        )
        with pytest.raises(asyncpg.PostgresError, match="(?i)append-only"):
            await pg_conn.execute(
                "DELETE FROM audit_logs WHERE id = $1",
                row_id,
            )

    _run(_run_test())


@pytest.mark.security
@pytest.mark.integration
def test_truncate_on_audit_logs_is_denied(pg_conn):
    """TRUNCATE on audit_logs must raise 'TRUNCATE denied' (V019 T293)."""
    asyncpg = pytest.importorskip("asyncpg")

    async def _run_test() -> None:
        with pytest.raises(asyncpg.PostgresError, match="(?i)TRUNCATE denied"):
            await pg_conn.execute("TRUNCATE audit_logs")

    _run(_run_test())


# ---------------------------------------------------------------------------
# Privilege checks (V019 REVOKE PUBLIC)
# ---------------------------------------------------------------------------

@pytest.mark.security
@pytest.mark.integration
def test_public_revoke_update_on_audit_logs(pg_conn):
    """PUBLIC role must not have UPDATE privilege on audit_logs (V019 REVOKE)."""
    result = _run(pg_conn.fetchval(
        """/* sql_id: test_public_no_update_priv */
        SELECT COUNT(*)::int
        FROM information_schema.role_table_grants
        WHERE table_name = 'audit_logs'
          AND grantee = 'PUBLIC'
          AND privilege_type = 'UPDATE'
        """
    ))
    assert result == 0, "PUBLIC must not have UPDATE privilege on audit_logs (V019 REVOKE)"


@pytest.mark.security
@pytest.mark.integration
def test_public_revoke_delete_on_audit_logs(pg_conn):
    """PUBLIC role must not have DELETE privilege on audit_logs (V019 REVOKE)."""
    result = _run(pg_conn.fetchval(
        """/* sql_id: test_public_no_delete_priv */
        SELECT COUNT(*)::int
        FROM information_schema.role_table_grants
        WHERE table_name = 'audit_logs'
          AND grantee = 'PUBLIC'
          AND privilege_type = 'DELETE'
        """
    ))
    assert result == 0, "PUBLIC must not have DELETE privilege on audit_logs (V019 REVOKE)"
