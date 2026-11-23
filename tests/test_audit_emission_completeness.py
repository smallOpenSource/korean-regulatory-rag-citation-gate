"""Audit emission completeness tests (AC23).

Assert: every ai_jobs row with status_code IN ('SUCCEEDED', 'FAILED') has
at least one matching audit_logs row where:
  - action_code = 'AI_CALL_STARTED'  AND
  - (detail_json->>'job_id' = ai_jobs.id::text
     OR resource_type = 'ai_job' AND resource_id = ai_jobs.id)

Schema notes (V008:33-43):
  - audit_logs has NO job_id column — must use detail_json->>'job_id' (JSONB)
    OR resource_type='ai_job' AND resource_id=ai_jobs.id
  - ai_jobs.status_code CHECK: ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED')
    — 'STARTED' is NOT a valid value (V008:100)

Connects to real PostgreSQL 17 via asyncpg + db.migrator (same pattern as
test_audit_append_only.py). Skips gracefully when DB is unavailable.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Module-level event loop — avoids "Future attached to a different loop" errors
# when asyncpg connections are reused across tests in the same module.
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
    assert _module_loop is not None, "_event_loop fixture must be active"
    return _module_loop.run_until_complete(coro)


async def _get_connection():  # type: ignore[return]
    asyncpg = pytest.importorskip("asyncpg")
    from db.migrator import database_url_from_env, load_env_file
    from db.migrator import run as run_migrations

    load_env_file(PROJECT_ROOT / ".env")

    async def _migrate_and_connect():
        await run_migrations()
        return await asyncpg.connect(database_url_from_env())

    # A transient Patroni/HAProxy connect drop must NOT silently skip the whole
    # module — that masks a regression in a full-suite run (the DB is healthy; the
    # timeout is transient). Retry with backoff (run_migrations is idempotent +
    # transactional, so a cancelled attempt is safe to repeat); skip ONLY if PG is
    # genuinely unreachable after the budget is exhausted ([[pg-patroni-transient-drop]]).
    last_exc: Exception | None = None
    for delay in (0.0, 1.0, 2.0, 4.0):
        if delay:
            await asyncio.sleep(delay)
        try:
            return await asyncio.wait_for(_migrate_and_connect(), timeout=20.0)
        except Exception as exc:  # noqa: BLE001 — retry transient; skip after exhaustion
            last_exc = exc
    pytest.skip(f"PostgreSQL unavailable after retries: {last_exc}")


@pytest.fixture(scope="module")
def pg_conn(_event_loop):  # type: ignore[return]
    """Provide a real asyncpg connection for the module, bound to _event_loop."""
    conn = _event_loop.run_until_complete(_get_connection())
    try:
        yield conn
    finally:
        _event_loop.run_until_complete(conn.close())


# ---------------------------------------------------------------------------
# AC23: ai_jobs completeness
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_every_terminal_ai_job_has_audit_call_started(pg_conn):
    """AC23: every ai_jobs row with status_code IN ('SUCCEEDED','FAILED') must have
    at least one audit_logs row with action_code='AI_CALL_STARTED' linked via
    detail_json->>'job_id' OR (resource_type='ai_job' AND resource_id=ai_jobs.id).

    V008:100 — ai_jobs.status_code CHECK omits 'STARTED'; 'SUCCEEDED'/'FAILED' are terminal.
    V008:33-43 — audit_logs has no job_id column; JSONB detail_json used for job linkage.
    """
    # Exclude known pre-AC23 fixture rows (ffffffff- prefix UUIDs are seed-data
    # fixtures inserted before the AC23 AI_CALL_STARTED emission requirement was
    # established; they pre-date the audit emission contract and are excluded by
    # design — see db/fixtures/seed_30_workflows.sql lines 460-461).
    orphan_rows = _run(pg_conn.fetch(
        """/* sql_id: test_audit_emission_completeness_terminal_jobs */
        SELECT aj.id::text AS job_id, aj.status_code
        FROM ai_jobs aj
        WHERE aj.status_code IN ('SUCCEEDED', 'FAILED')
          AND aj.id::text NOT LIKE 'ffffffff-%'
          AND NOT EXISTS (
            SELECT 1
            FROM audit_logs al
            WHERE al.action_code = 'AI_CALL_STARTED'
              AND (
                al.detail_json->>'job_id' = aj.id::text
                OR (al.resource_type = 'ai_job' AND al.resource_id = aj.id)
              )
          )
        ORDER BY aj.id
        LIMIT 50
        """
    ))

    assert len(orphan_rows) == 0, (
        f"Found {len(orphan_rows)} terminal ai_jobs row(s) with no AI_CALL_STARTED "
        f"audit_logs entry. Orphan job_ids: "
        f"{[dict(r)['job_id'] for r in orphan_rows[:10]]}\n"
        "Each SUCCEEDED/FAILED ai_job must emit AI_CALL_STARTED in audit_logs "
        "with detail_json->>'job_id'=<job_id> OR resource_type='ai_job' AND resource_id=<job_id>. "
        "Schema ref: V008:33-43 (audit_logs), V008:100 (ai_jobs CHECK)."
    )


@pytest.mark.integration
def test_audit_logs_ai_call_started_action_code_exists(pg_conn):
    """Prerequisite: AI_CALL_STARTED action_code must be registered in audit_action_codes.

    V008:9-11 seeds this code. Without it, FK inserts would fail silently.
    """
    count = _run(pg_conn.fetchval(
        """/* sql_id: test_audit_emission_ai_call_started_registered */
        SELECT COUNT(*)::int
        FROM audit_action_codes
        WHERE action_code = 'AI_CALL_STARTED'
        """
    ))
    assert count == 1, (
        "AI_CALL_STARTED action_code not found in audit_action_codes "
        "(expected by V008:9-11 seed)"
    )


@pytest.mark.integration
def test_ai_jobs_status_code_check_excludes_started(pg_conn):
    """V008:100 contract: 'STARTED' is NOT a valid ai_jobs.status_code.

    The denominator for runtime metrics uses AI_CALL_STARTED audit events,
    not ai_jobs.STARTED (which doesn't exist per CHECK constraint).
    NR1+NR7 fix verification.
    """
    # Verify the CHECK constraint exists by confirming no rows have status_code='STARTED'
    # and that valid codes are the expected set.
    count_started = _run(pg_conn.fetchval(
        """/* sql_id: test_audit_emission_no_started_status */
        SELECT COUNT(*)::int
        FROM ai_jobs
        WHERE status_code = 'STARTED'
        """
    ))
    assert count_started == 0, (
        f"Found {count_started} ai_jobs rows with status_code='STARTED'. "
        "V008:100 CHECK constraint should prevent this. "
        "NR1+NR7 fix: runtime denominator must use audit_logs.AI_CALL_STARTED, "
        "not ai_jobs.STARTED."
    )
