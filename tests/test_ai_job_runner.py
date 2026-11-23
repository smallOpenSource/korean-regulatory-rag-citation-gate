"""Tests for scripts/run_ai_job_runner.py (Wave 6 US-W6-3, R3+R39).

Verifies the worker entry script's three observable behaviors against a real
PostgreSQL database:

1. ``--dry-run`` reports the pending count without claiming or mutating rows.
2. ``claim_one`` selects the oldest PENDING job via ``FOR UPDATE SKIP LOCKED``
   and atomically transitions it to RUNNING.
3. ``mark_failed`` records ``error_code`` + ``error_message`` on the RUNNING
   row, which is how unknown dispatchers fail-close.

Every test wraps its work in an asyncpg transaction that is rolled back
before the connection is released, so the live ai_jobs table is never
mutated. The test job uses a deterministic UUID and a backdated
``created_at`` so that the FOR-UPDATE-SKIP-LOCKED claim picks the test row
first regardless of how many real PENDING rows exist (see verdict L82 — 61
PENDING in the live DB).

The defensive skip pattern (see feedback-integration-test-defensive-skip)
is honored: tests skip when DATABASE_URL is unset or no seeded employee row
is available for the FK.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("asyncpg")

_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_ai_job_runner.py"
_spec = importlib.util.spec_from_file_location("_ai_job_runner_module", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
ai_job_runner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ai_job_runner)

TEST_JOB_ID = uuid.UUID("00000000-0000-4000-8000-000000000301")
TEST_JOB_TYPE = "wave6-us-w6-3-test"


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@pytest.fixture()
def db_config():
    _load_env()
    from apps.api.harness.core.config import load_config

    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        pytest.skip(".env not present")
    config = load_config(env_path)
    if not config.database.database_url:
        pytest.skip("DATABASE_URL missing")
    return config


def test_dry_run_reports_pending_without_claiming(db_config):
    """`--dry-run` must observe pending count and return claimed=False."""

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                pending_before = await conn.fetchval(ai_job_runner.COUNT_PENDING_SQL)
            claimed = await ai_job_runner.process_one(pool, dry_run=True)
            async with pool.acquire() as conn:
                pending_after = await conn.fetchval(ai_job_runner.COUNT_PENDING_SQL)
            return claimed, pending_before, pending_after
        finally:
            await pool.close()

    claimed, pending_before, pending_after = asyncio.run(_exercise())
    assert claimed is False
    assert pending_before == pending_after, (
        "dry-run must not change pending count"
    )


def test_claim_then_mark_failed_transitions_status(db_config):
    """`claim_one` + `mark_failed` together must move PENDING → RUNNING → FAILED."""

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    employee_row = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if employee_row is None:
                        pytest.skip("no employees seeded")

                    # Backdated created_at so FIFO claim picks this row first.
                    await conn.execute(
                        """
                        INSERT INTO ai_jobs(id, job_type_code, status_code,
                                            requested_by_id, created_at)
                        VALUES ($1::uuid, $2, 'PENDING', $3::uuid,
                                TIMESTAMPTZ '1970-01-01 00:00:00Z')
                        """,
                        str(TEST_JOB_ID), TEST_JOB_TYPE, str(employee_row["id"]),
                    )

                    claimed = await ai_job_runner.claim_one(conn)
                    assert claimed is not None
                    assert claimed["id"] == TEST_JOB_ID
                    assert claimed["job_type_code"] == TEST_JOB_TYPE

                    status_after_claim = await conn.fetchval(
                        "SELECT status_code FROM ai_jobs WHERE id = $1::uuid",
                        str(TEST_JOB_ID),
                    )
                    assert status_after_claim == "RUNNING"

                    await ai_job_runner.mark_failed(
                        conn, str(TEST_JOB_ID), "no_dispatcher", "test message"
                    )

                    final_row = await conn.fetchrow(
                        """
                        SELECT status_code, error_code, error_message, finished_at
                        FROM ai_jobs WHERE id = $1::uuid
                        """,
                        str(TEST_JOB_ID),
                    )
                    return dict(final_row)
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    final_row = asyncio.run(_exercise())
    assert final_row["status_code"] == "FAILED"
    assert final_row["error_code"] == "no_dispatcher"
    assert final_row["error_message"] == "test message"
    assert final_row["finished_at"] is not None


def test_handle_unknown_raises_not_implemented():
    """`handle_unknown` must raise NotImplementedError naming the job_type_code."""

    job = {"job_type_code": "totally-unknown-type", "id": TEST_JOB_ID}

    async def _call():
        await ai_job_runner.handle_unknown(None, job)

    with pytest.raises(NotImplementedError) as excinfo:
        asyncio.run(_call())
    assert "totally-unknown-type" in str(excinfo.value)


def test_dispatchers_dict_wires_worker_scope_only():
    """Wave 6.5 final: worker DISPATCHERS holds the four async-eligible agents.

    * email_draft, consultation_briefing — ADR-005 §Status dual-LLM scope
      (Wave 6.3 US-W63-2).
    * nba_script, portfolio_analysis — ADR-005 §Status T265 single-LLM +
      spotlighting + sanitize scope, worker-dispatched (Wave 6.5 US-W65-1/2).

    compliance_check is intentionally OUT of the worker registry because
    the consultation completion attempt depends on its result; it is
    invoked synchronously from routers/consultations.py and persists via
    the same ai_repo.create_ai_output path. house_view_generation is
    invoked from the house_view router activation path; both attach T265
    in their own modules.

    Positive assert against accidental future wiring of compliance_check
    or house_view into the worker (which would silently change the
    consultation-completion flow into an async race).
    """

    from apps.api.harness.services.consultation_briefing import run_consultation_briefing
    from apps.api.harness.services.email_draft import run_email_draft
    from apps.api.harness.services.nba_script import run_nba_script
    from apps.api.harness.services.portfolio_analysis import run_portfolio_analysis

    expected = {
        "email_draft": run_email_draft,
        "consultation_briefing": run_consultation_briefing,
        "nba_script": run_nba_script,
        "portfolio_analysis": run_portfolio_analysis,
    }
    assert set(ai_job_runner.DISPATCHERS.keys()) == set(expected.keys())
    for key, fn in expected.items():
        assert ai_job_runner.DISPATCHERS[key] is fn
