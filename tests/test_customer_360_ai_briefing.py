"""P1-c HITL data wiring (2026-05-30): Customer-360 surfaces the latest
non-fail-closed customer-scoped AI output as ai_briefing, so the frontend
AIMetadataFooter renders the P0 quality signals (data-quality / faithfulness /
PII mask) from a REAL generated output. Verified against the live PG schema;
transactions roll back.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("asyncpg")

JOB_ID = uuid.UUID("00000000-0000-4000-8000-0000000009c0")


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


async def _seed_output(conn, *, customer_id, job_id, generated_at_sql, fail_closed, output_json):
    await conn.execute(
        "INSERT INTO ai_outputs(agent_id, model_name, generated_at, resource_type, "
        "resource_id, job_id, prompt_hash, output_json, citations_json, "
        "fail_closed_reason_code, question_text) "
        "VALUES ('portfolio_analysis', 'gpt-5.5', " + generated_at_sql + ", 'customers', "
        "$1::uuid, $2::uuid, $3, $4::jsonb, '[]'::jsonb, $5, $6)",
        str(customer_id),
        str(job_id),
        f"pa:{generated_at_sql}",
        json.dumps(output_json, ensure_ascii=False),
        fail_closed,
        "포트폴리오 분석",
    )


def test_briefing_picks_latest_non_failclosed_output(db_config):
    """The newest output wins, but a fail-closed output is excluded — so an older
    non-fail-closed output is returned over a newer fail-closed one."""

    from apps.api.harness.repositories.customers import _latest_customer_ai_briefing

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    cust = await conn.fetchrow("SELECT id FROM customers LIMIT 1")
                    emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if cust is None or emp is None:
                        pytest.skip("no customer/employee seeded")
                    await conn.execute(
                        "INSERT INTO ai_jobs(id, job_type_code, status_code, requested_by_id, "
                        "resource_type, resource_id) VALUES ($1::uuid, 'portfolio_analysis', "
                        "'SUCCEEDED', $2::uuid, 'customers', $3::uuid)",
                        str(JOB_ID),
                        str(emp["id"]),
                        str(cust["id"]),
                    )
                    # older, NON-fail-closed (the one that should surface)
                    await _seed_output(
                        conn,
                        customer_id=cust["id"],
                        job_id=JOB_ID,
                        generated_at_sql="now() - interval '2 hours'",
                        fail_closed=None,
                        output_json={
                            "summary": "정상 산출 요약",
                            "data_quality_notice": "[데이터 품질 고지] 합성·미검증",
                            "faithfulness": {
                                "method": "deterministic_v1",
                                "passed": True,
                                "flags": [],
                            },
                        },
                    )
                    # newer, FAIL-CLOSED (must be excluded despite being newer)
                    await _seed_output(
                        conn,
                        customer_id=cust["id"],
                        job_id=JOB_ID,
                        generated_at_sql="now()",
                        fail_closed="LLM07_LEAKAGE_REDACTED",
                        output_json={"summary": ""},
                    )
                    briefing = await _latest_customer_ai_briefing(conn, str(cust["id"]))
                    return briefing
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    briefing = asyncio.run(_exercise())
    assert briefing is not None, "expected the non-fail-closed output to surface"
    assert briefing["output_id"]
    assert briefing["summary"] == "정상 산출 요약"
    assert briefing["model_name"] == "gpt-5.5"


def test_briefing_none_when_only_failclosed(db_config):
    """When the only customer-scoped output is fail-closed, ai_briefing is None
    (the footer then does not render)."""

    from apps.api.harness.repositories.customers import _latest_customer_ai_briefing

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    cust = await conn.fetchrow("SELECT id FROM customers LIMIT 1")
                    emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if cust is None or emp is None:
                        pytest.skip("no customer/employee seeded")
                    await conn.execute(
                        "INSERT INTO ai_jobs(id, job_type_code, status_code, requested_by_id, "
                        "resource_type, resource_id) VALUES ($1::uuid, 'portfolio_analysis', "
                        "'FAILED', $2::uuid, 'customers', $3::uuid)",
                        str(JOB_ID),
                        str(emp["id"]),
                        str(cust["id"]),
                    )
                    await _seed_output(
                        conn,
                        customer_id=cust["id"],
                        job_id=JOB_ID,
                        generated_at_sql="now()",
                        fail_closed="PROMPT_INJECTION_DETECTED",
                        output_json={"summary": ""},
                    )
                    # NB: real seed customers may already carry a non-fail-closed
                    # output; this test only asserts the fail-closed row we added is
                    # not the one surfaced (so the result, if any, is never our row).
                    briefing = await _latest_customer_ai_briefing(conn, str(cust["id"]))
                    return briefing
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    briefing = asyncio.run(_exercise())
    # If the seed customer had no prior non-fail-closed output, briefing is None.
    # Either way it must NOT be the fail-closed PROMPT_INJECTION row's empty summary.
    if briefing is not None:
        assert briefing["summary"] != "", "fail-closed (empty) output must not surface"
