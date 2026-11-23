"""svc-viability-v4 I8 — audit action code two-source registration drift gate.

The wmah audit emit pipeline relies on two independent registrations of the
canonical action code set:

1. ``audit_action_codes`` table — populated via ``db/migrations/V*.sql``
   ``INSERT INTO audit_action_codes (action_code, description)`` statements.
   Every emit path goes through ``audit_logs.action_code`` whose FK references
   this table, so an unregistered code raises a PG error at INSERT time.

2. ``apps.api.harness.core.audit.CANONICAL_AUDIT_ACTION_CODES`` tuple —
   consulted by ``require_audit_action()`` before any DB roundtrip. A code
   missing from the tuple is rejected with ``ValueError`` even if it exists
   on the DB side.

Drift between the two surfaces produces either a Python ``ValueError`` (DB has
a code the tuple does not) or a PG FK violation (tuple has a code the DB has
not seen). This test asserts the symmetric difference is empty.

The test is marked ``integration`` because it requires a live PG connection
seeded with the wmah migration history. CI lanes that do not provide a
``DATABASE_URL`` skip with a structured WARNING log so the gap is visible.
"""

from __future__ import annotations

import asyncio
import logging
import os

import pytest

from apps.api.harness.core.audit import CANONICAL_AUDIT_ACTION_CODES

logger = logging.getLogger(__name__)


def _resolve_database_url() -> str | None:
    """Return the DATABASE_URL env var if present, else None.

    Stripped + normalized to swallow the ``postgresql+asyncpg://`` prefix that
    the migrator accepts so asyncpg's own URL parser can consume it directly.
    """

    raw = os.getenv("DATABASE_URL", "").strip()
    if not raw:
        return None
    if raw.startswith("postgresql+asyncpg://"):
        return "postgresql://" + raw[len("postgresql+asyncpg://"):]
    return raw


async def _fetch_db_action_codes(database_url: str) -> set[str]:
    asyncpg = pytest.importorskip("asyncpg")
    # Retry transient Patroni/HAProxy connect drops with backoff so a single timeout
    # neither flakes this gate nor a full-suite run (the DB is healthy; the drop is
    # transient). Surface the last error only after the budget is exhausted — a genuine
    # outage still fails (visible), never silently skipped ([[pg-patroni-transient-drop]]).
    last_exc: Exception | None = None
    connection = None
    for delay in (0.0, 1.0, 2.0, 4.0):
        if delay:
            await asyncio.sleep(delay)
        try:
            connection = await asyncio.wait_for(asyncpg.connect(database_url), timeout=15.0)
            break
        except Exception as exc:  # noqa: BLE001 — retry transient; raise after exhaustion
            last_exc = exc
    if connection is None:
        raise last_exc or RuntimeError("PostgreSQL unreachable after retries")
    try:
        rows = await connection.fetch(
            "/* sql_id: test_audit_action_code_drift_fetch */ "
            "SELECT action_code FROM audit_action_codes"
        )
    finally:
        await connection.close()
    return {row["action_code"] for row in rows}


@pytest.mark.integration
def test_audit_action_code_drift() -> None:
    """DB ↔ Python CANONICAL tuple symmetric diff must be empty.

    Skips with a WARNING log when ``DATABASE_URL`` is unset — the skip is the
    structured ops signal that the integration lane lacks PG. CI default lanes
    must inject ``DATABASE_URL`` to make this assertion run (§13 F-V5-2).
    """

    database_url = _resolve_database_url()
    if database_url is None:
        logger.warning(
            "audit_action_code_drift test skipped: DATABASE_URL unset "
            "(CI default lane must inject DATABASE_URL per F-V5-2)"
        )
        pytest.skip("DATABASE_URL unset — CI default lane must include DATABASE_URL")

    db_set: set[str] = asyncio.run(_fetch_db_action_codes(database_url))
    python_set: set[str] = set(CANONICAL_AUDIT_ACTION_CODES)

    only_in_db = db_set - python_set
    only_in_python = python_set - db_set

    assert not only_in_db, (
        f"DB has audit action codes missing from "
        f"core.audit.CANONICAL_AUDIT_ACTION_CODES: {sorted(only_in_db)}"
    )
    assert not only_in_python, (
        f"CANONICAL_AUDIT_ACTION_CODES has codes missing from DB "
        f"audit_action_codes: {sorted(only_in_python)}"
    )
