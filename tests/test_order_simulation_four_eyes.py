"""P1-b: second-person 4-eye approval for order simulations (2026-05-30).

Previously evaluate_order_gates auto-set APPROVED on pass, so the SAME employee
could self-approve and self-execute a simulated order. Now a passing order
simulation enters PENDING_APPROVAL and a DIFFERENT employee must approve it
(REG-03 §3) before the creator can execute-simulated. These tests verify the
SQL-level 4-eye invariant + the previously-broken approve→execute flow, against
the live PostgreSQL schema (V080). Transactions roll back.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("asyncpg")


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


def test_order_simulation_four_eyes_approve_then_execute(db_config):
    """Creator cannot self-approve (SQL employee_id <> approver_id); a distinct
    approver transitions PENDING_APPROVAL → APPROVED with approver_id recorded;
    and only then can the creator execute-simulated (the flow that was a dead-end
    when no /approve route existed)."""

    async def _exercise():
        from apps.api.harness.core.db import create_pool
        from apps.api.harness.repositories import simulations as sim_repo

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    ctx = await conn.fetchrow(
                        "SELECT c.id AS customer_id, co.id AS consultation_id "
                        "FROM customers c JOIN consultations co ON co.customer_id = c.id LIMIT 1"
                    )
                    product = await conn.fetchrow("SELECT id FROM products LIMIT 1")
                    emps = await conn.fetch("SELECT id FROM employees LIMIT 2")
                    if ctx is None or product is None or len(emps) < 2:
                        pytest.skip("need customer+consultation+product+2 employees seeded")
                    creator = str(emps[0]["id"])
                    approver = str(emps[1]["id"])

                    reco = await conn.fetchrow(
                        "INSERT INTO recommendation_simulations(customer_id, employee_id, "
                        "consultation_id, product_id, status_code, suitability_passed, "
                        "explanation_checked, simulated_customer_consented, "
                        "employee_final_approved) "
                        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, 'APPROVED', "
                        "true, true, true, true) RETURNING id",
                        str(ctx["customer_id"]),
                        creator,
                        str(ctx["consultation_id"]),
                        str(product["id"]),
                    )
                    order = await conn.fetchrow(
                        "INSERT INTO order_simulations(recommendation_simulation_id, customer_id, "
                        "employee_id, product_id, side_code, amount_krw, status_code) "
                        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, 'BUY', 10000, "
                        "'PENDING_APPROVAL') RETURNING id",
                        str(reco["id"]),
                        str(ctx["customer_id"]),
                        creator,
                        str(product["id"]),
                    )
                    oid = str(order["id"])

                    # 1. self-approval (creator) is blocked at the SQL level → None,
                    #    and the row stays PENDING_APPROVAL.
                    self_res = await sim_repo.approve_order_simulation(
                        conn, order_simulation_id=oid, approver_id=creator
                    )
                    still_pending = await sim_repo.get_order_simulation(
                        conn, order_simulation_id=oid
                    )
                    # 2. a distinct approver transitions PENDING_APPROVAL → APPROVED.
                    distinct_res = await sim_repo.approve_order_simulation(
                        conn, order_simulation_id=oid, approver_id=approver
                    )
                    # 3. only now can the creator execute the APPROVED simulation.
                    executed = await sim_repo.execute_order_simulation(
                        conn, order_simulation_id=oid, employee_id=creator
                    )
                    return self_res, still_pending, distinct_res, executed, approver
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    self_res, still_pending, distinct_res, executed, approver = asyncio.run(_exercise())

    # 1. creator self-approval blocked (4-eye SQL invariant).
    assert self_res is None, "creator must not be able to self-approve"
    assert still_pending is not None
    assert still_pending["status_code"] == "PENDING_APPROVAL"
    # 2. distinct approver → APPROVED with approver_id recorded.
    assert distinct_res is not None, "distinct approver should transition to APPROVED"
    assert distinct_res["status_code"] == "APPROVED"
    assert str(distinct_res["approver_id"]) == approver
    # 3. the previously-broken approve→execute flow now completes.
    assert executed is not None, "creator should execute the APPROVED simulation"
    assert executed["status_code"] == "SIMULATED_EXECUTED"


def test_approve_rejects_non_pending_state(db_config):
    """approve_order_simulation only acts on PENDING_APPROVAL rows — a BLOCKED
    order simulation cannot be force-approved (returns None)."""

    async def _exercise():
        from apps.api.harness.core.db import create_pool
        from apps.api.harness.repositories import simulations as sim_repo

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    ctx = await conn.fetchrow(
                        "SELECT c.id AS customer_id, co.id AS consultation_id "
                        "FROM customers c JOIN consultations co ON co.customer_id = c.id LIMIT 1"
                    )
                    product = await conn.fetchrow("SELECT id FROM products LIMIT 1")
                    emps = await conn.fetch("SELECT id FROM employees LIMIT 2")
                    if ctx is None or product is None or len(emps) < 2:
                        pytest.skip("need customer+consultation+product+2 employees seeded")
                    creator = str(emps[0]["id"])
                    approver = str(emps[1]["id"])
                    reco = await conn.fetchrow(
                        "INSERT INTO recommendation_simulations(customer_id, employee_id, "
                        "consultation_id, product_id, status_code) "
                        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, 'BLOCKED') RETURNING id",
                        str(ctx["customer_id"]),
                        creator,
                        str(ctx["consultation_id"]),
                        str(product["id"]),
                    )
                    order = await conn.fetchrow(
                        "INSERT INTO order_simulations(recommendation_simulation_id, customer_id, "
                        "employee_id, product_id, side_code, amount_krw, status_code) "
                        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, 'BUY', 10000, 'BLOCKED') "
                        "RETURNING id",
                        str(reco["id"]),
                        str(ctx["customer_id"]),
                        creator,
                        str(product["id"]),
                    )
                    res = await sim_repo.approve_order_simulation(
                        conn, order_simulation_id=str(order["id"]), approver_id=approver
                    )
                    return res
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    res = asyncio.run(_exercise())
    assert res is None, "a BLOCKED order simulation must not be approvable"
