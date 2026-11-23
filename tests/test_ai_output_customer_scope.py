"""P1-c follow-up (2026-05-30): GET /ai-outputs authorization matrix.

A customer-scoped AI output (resource_type='customers') must be readable by a
staff member authorized for the LINKED customer — even if a different colleague
generated it — mirroring CUSTOMER_SCOPE_FRAGMENT (PB→assigned, WM/BM→branch,
ADMIN/AUDIT_VIEWER→all, plus the original job-requester path). A non-customer
output is NOT broadened (only requester/audit). Verified against the live PG
schema; the transaction rolls back.
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

CUST_JOB = uuid.UUID("00000000-0000-4000-8000-0000000009d0")
NBA_JOB = uuid.UUID("00000000-0000-4000-8000-0000000009d1")


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


async def _seed_output(conn, *, job_id, requester, resource_type, resource_id):
    await conn.execute(
        "INSERT INTO ai_jobs(id, job_type_code, status_code, requested_by_id, "
        "resource_type, resource_id) VALUES ($1::uuid, 'portfolio_analysis', 'SUCCEEDED', "
        "$2::uuid, $3, $4::uuid)",
        str(job_id),
        str(requester),
        resource_type,
        str(resource_id),
    )
    row = await conn.fetchrow(
        "INSERT INTO ai_outputs(agent_id, model_name, generated_at, resource_type, "
        "resource_id, job_id, prompt_hash, output_json, citations_json, "
        "fail_closed_reason_code, question_text) "
        "VALUES ('portfolio_analysis', 'gpt-5.5', now(), $1, $2::uuid, $3::uuid, $4, "
        "$5::jsonb, '[]'::jsonb, NULL, 'q') RETURNING id",
        resource_type,
        str(resource_id),
        str(job_id),
        f"scope:{resource_type}:{resource_id}",
        json.dumps({"summary": "s"}, ensure_ascii=False),
    )
    return str(row["id"])


def test_ai_output_customer_scope_authorization_matrix(db_config):
    from apps.api.harness.repositories.ai import get_ai_output

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    cust = await conn.fetchrow(
                        "SELECT id, assigned_pb_id, branch_id FROM customers "
                        "WHERE assigned_pb_id IS NOT NULL AND branch_id IS NOT NULL "
                        "AND is_active IS TRUE LIMIT 1"
                    )
                    if cust is None:
                        pytest.skip("no customer with assigned_pb + branch seeded")
                    requester = await conn.fetchrow(
                        "SELECT id FROM employees WHERE id <> $1::uuid LIMIT 1",
                        str(cust["assigned_pb_id"]),
                    )
                    if requester is None:
                        pytest.skip("need a second employee")
                    assigned = str(cust["assigned_pb_id"])
                    branch = str(cust["branch_id"])
                    req = str(requester["id"])
                    rnd = str(uuid.uuid4())

                    cust_oid = await _seed_output(
                        conn, job_id=CUST_JOB, requester=req,
                        resource_type="customers", resource_id=cust["id"],
                    )
                    nba_oid = await _seed_output(
                        conn, job_id=NBA_JOB, requester=req,
                        resource_type="nba_actions", resource_id=uuid.uuid4(),
                    )

                    async def can(oid, role, emp, br):
                        r = await get_ai_output(
                            conn, output_id=oid, role_code=role, employee_id=emp, branch_id=br
                        )
                        return r is not None

                    return {
                        "assigned_pb": await can(cust_oid, "PB", assigned, None),
                        "other_pb": await can(cust_oid, "PB", rnd, None),
                        "wm_in_branch": await can(cust_oid, "WM", rnd, branch),
                        "wm_other_branch": await can(cust_oid, "WM", rnd, str(uuid.uuid4())),
                        "bm_in_branch": await can(cust_oid, "BRANCH_MANAGER", rnd, branch),
                        "wm_null_branch": await can(cust_oid, "WM", rnd, None),
                        "requester": await can(cust_oid, "PB", req, None),
                        "admin": await can(cust_oid, "ADMIN", rnd, None),
                        "audit": await can(cust_oid, "AUDIT_VIEWER", rnd, None),
                        "noncustomer_other_pb": await can(nba_oid, "PB", rnd, None),
                        "noncustomer_requester": await can(nba_oid, "PB", req, None),
                    }
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    r = asyncio.run(_exercise())
    # customer-scoped output: authorized-for-customer staff CAN read (the new path)
    assert r["assigned_pb"] is True, "assigned PB must read the customer's output"
    assert r["wm_in_branch"] is True, "WM in the customer's branch must read it"
    assert r["bm_in_branch"] is True, "BRANCH_MANAGER in the customer's branch must read it"
    assert r["requester"] is True, "the job requester must still read it"
    assert r["admin"] is True
    assert r["audit"] is True
    # NOT authorized for the customer → blocked
    assert r["other_pb"] is False, "an unassigned PB must NOT read the customer's output"
    assert r["wm_other_branch"] is False, "a WM in another branch must NOT read it"
    assert r["wm_null_branch"] is False, "a WM with no branch must NOT read any customer output"
    # non-customer output is NOT broadened — only requester (and audit) read it
    assert r["noncustomer_other_pb"] is False, "non-customer output must stay requester-scoped"
    assert r["noncustomer_requester"] is True
