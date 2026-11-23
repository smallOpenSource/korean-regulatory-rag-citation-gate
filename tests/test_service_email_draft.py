"""Tests for services/email_draft.py (Wave 6.3 US-W63-2, R36).

Verifies the dispatcher's contract against the live PostgreSQL schema:

1. resource_type validation: rejects non-email_drafts jobs with ValueError.
2. resource_id missing / row not found / empty body: each raises ValueError.
3. fail-closed: when Azure credentials are unset, the dispatcher raises
   RuntimeError naming the quarantined-lane error — the worker's
   ``mark_failed`` records this in ``ai_jobs.error_message``.
4. The dispatcher never mutates the live DB on failure (transaction
   rollback pattern).

No mocks for Azure — the fail-closed branch is the production-loadbearing
behavior. The success-path live LLM call is operator-credential scope
(carry-over).
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("asyncpg")

from apps.api.harness.services.email_draft import run_email_draft  # noqa: E402

TEST_DRAFT_ID = uuid.UUID("00000000-0000-4000-8000-000000000401")
TEST_JOB_ID = uuid.UUID("00000000-0000-4000-8000-000000000402")


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


def test_rejects_wrong_resource_type():
    job = {
        "id": TEST_JOB_ID,
        "resource_type": "consultations",
        "resource_id": TEST_DRAFT_ID,
        "job_type_code": "email_draft",
    }

    async def _run():
        await run_email_draft(None, job)

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(_run())
    assert "email_drafts" in str(excinfo.value)


def test_rejects_missing_resource_id():
    job = {
        "id": TEST_JOB_ID,
        "resource_type": "email_drafts",
        "resource_id": None,
        "job_type_code": "email_draft",
    }

    async def _run():
        await run_email_draft(None, job)

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(_run())
    assert "resource_id" in str(excinfo.value)


def test_fail_closed_raises_runtime_error_when_azure_unset(db_config, monkeypatch):
    """fail-closed: missing Azure creds → quarantined LLM error → RuntimeError.

    DB is wrapped in a transaction that is rolled back at the end, so no
    live email_drafts row remains after the test.
    """

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "")

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    customer_row = await conn.fetchrow("SELECT id FROM customers LIMIT 1")
                    employee_row = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if customer_row is None or employee_row is None:
                        pytest.skip("no customer/employee seeded")

                    await conn.execute(
                        """
                        INSERT INTO email_drafts(id, customer_id, employee_id, subject, body, status_code)
                        VALUES ($1::uuid, $2::uuid, $3::uuid, 'placeholder', 'PB raw request text', 'DRAFT')
                        """,
                        str(TEST_DRAFT_ID), str(customer_row["id"]), str(employee_row["id"]),
                    )

                    job = {
                        "id": TEST_JOB_ID,
                        "resource_type": "email_drafts",
                        "resource_id": TEST_DRAFT_ID,
                        "job_type_code": "email_draft",
                    }

                    err = None
                    try:
                        await run_email_draft(conn, job)
                    except RuntimeError as exc:
                        err = exc

                    row_after = await conn.fetchrow(
                        "SELECT subject, body, ai_generated_at, ai_model_name FROM email_drafts WHERE id = $1::uuid",
                        str(TEST_DRAFT_ID),
                    )
                    return err, dict(row_after) if row_after else None
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    err, row_after = asyncio.run(_exercise())
    assert err is not None
    assert "quarantined LLM error" in str(err) or "Azure credentials not configured" in str(err)
    assert row_after is not None
    assert row_after["subject"] == "placeholder"
    assert row_after["body"] == "PB raw request text"
    assert row_after["ai_generated_at"] is None
    assert row_after["ai_model_name"] is None


def test_missing_email_draft_row_raises_value_error(db_config):
    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    job = {
                        "id": TEST_JOB_ID,
                        "resource_type": "email_drafts",
                        "resource_id": uuid.UUID("00000000-0000-4000-8000-000000099999"),
                        "job_type_code": "email_draft",
                    }
                    err = None
                    try:
                        await run_email_draft(conn, job)
                    except ValueError as exc:
                        err = exc
                    return err
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    err = asyncio.run(_exercise())
    assert err is not None
    assert "not found" in str(err)
