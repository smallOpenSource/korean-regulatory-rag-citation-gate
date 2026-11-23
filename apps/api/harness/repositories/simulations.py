"""Recommendation and order simulation repositories."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from apps.api.harness.core.db import fetch_one

from .common import row_to_dict

GET_RECOMMENDATION_INPUT_SQL = """
/* sql_id: get_recommendation_gate_input */
SELECT c.risk_grade_code AS customer_risk_grade, p.risk_level_code AS product_risk_level,
       c.id AS customer_id, p.id AS product_id, co.id AS consultation_id
FROM customers c
JOIN consultations co ON co.customer_id = c.id
JOIN products p ON p.id = $3::uuid
WHERE c.id = $1::uuid
  AND co.id = $2::uuid
  AND co.employee_id = $4::uuid;
"""

INSERT_RECOMMENDATION_SIMULATION_SQL = """
/* sql_id: insert_recommendation_simulation */
INSERT INTO recommendation_simulations(
    customer_id, employee_id, consultation_id, product_id, status_code,
    suitability_passed, explanation_checked, simulated_customer_consented,
    employee_final_approved, gate_detail_json
)
VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, $5, $6, $7, $8, $9, $10::jsonb)
RETURNING id, customer_id, employee_id, consultation_id, product_id, status_code,
          suitability_passed, explanation_checked, simulated_customer_consented,
          employee_final_approved, gate_detail_json, created_at, updated_at;
"""

GET_RECOMMENDATION_FOR_ORDER_SQL = """
/* sql_id: get_recommendation_for_order */
SELECT r.id, r.customer_id, r.employee_id, r.consultation_id, r.product_id, r.status_code,
       r.suitability_passed, r.explanation_checked, r.simulated_customer_consented,
       r.employee_final_approved, r.gate_detail_json, r.created_at, r.updated_at
FROM recommendation_simulations r
WHERE r.id = $1::uuid
  AND r.employee_id = $2::uuid;
"""

INSERT_ORDER_SIMULATION_SQL = """
/* sql_id: insert_order_simulation */
INSERT INTO order_simulations(
    recommendation_simulation_id, customer_id, employee_id, product_id, side_code,
    quantity, amount_krw, status_code, gate_detail_json
)
VALUES ($1::uuid, $2::uuid, $3::uuid, $4::uuid, $5, $6, $7, $8, $9::jsonb)
RETURNING id, recommendation_simulation_id, customer_id, employee_id, product_id,
          side_code, quantity, amount_krw, status_code, gate_detail_json,
          simulated_executed_at, created_at, updated_at;
"""

EXECUTE_ORDER_SIMULATION_SQL = """
/* sql_id: execute_order_simulation_simulated */
UPDATE order_simulations
SET status_code = 'SIMULATED_EXECUTED', simulated_executed_at = now(), updated_at = now()
WHERE id = $1::uuid
  AND employee_id = $2::uuid
  AND status_code = 'APPROVED'
RETURNING id, recommendation_simulation_id, customer_id, employee_id, product_id,
          side_code, quantity, amount_krw, status_code, gate_detail_json,
          simulated_executed_at, created_at, updated_at;
"""

GET_ORDER_SIMULATION_SQL = """
/* sql_id: get_order_simulation */
SELECT id, recommendation_simulation_id, customer_id, employee_id, product_id,
       side_code, quantity, amount_krw, status_code, approver_id, approved_at,
       gate_detail_json, simulated_executed_at, created_at, updated_at
FROM order_simulations
WHERE id = $1::uuid;
"""

APPROVE_ORDER_SIMULATION_SQL = """
/* sql_id: approve_order_simulation_four_eyes */
UPDATE order_simulations
SET status_code = 'APPROVED', approver_id = $2::uuid, approved_at = now(), updated_at = now()
WHERE id = $1::uuid
  AND status_code = 'PENDING_APPROVAL'
  AND employee_id <> $2::uuid
RETURNING id, recommendation_simulation_id, customer_id, employee_id, product_id,
          side_code, quantity, amount_krw, status_code, approver_id, approved_at,
          gate_detail_json, simulated_executed_at, created_at, updated_at;
"""


async def get_recommendation_gate_input(
    connection: Any,
    *,
    customer_id: str,
    consultation_id: str,
    product_id: str,
    employee_id: str,
) -> dict[str, Any] | None:
    """Read risk/product facts needed for recommendation gates."""

    return row_to_dict(
        await fetch_one(
            connection,
            GET_RECOMMENDATION_INPUT_SQL,
            customer_id,
            consultation_id,
            product_id,
            employee_id,
        )
    )


async def insert_recommendation_simulation(
    connection: Any,
    *,
    customer_id: str,
    employee_id: str,
    consultation_id: str,
    product_id: str,
    status_code: str,
    suitability_passed: bool,
    explanation_checked: bool,
    simulated_customer_consented: bool,
    employee_final_approved: bool,
    gate_detail: dict[str, Any],
) -> dict[str, Any]:
    """Insert a recommendation simulation after gate evaluation."""

    row = await fetch_one(
        connection,
        INSERT_RECOMMENDATION_SIMULATION_SQL,
        customer_id,
        employee_id,
        consultation_id,
        product_id,
        status_code,
        suitability_passed,
        explanation_checked,
        simulated_customer_consented,
        employee_final_approved,
        json.dumps(gate_detail, ensure_ascii=False),
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("recommendation simulation insert returned no row")
    return result


async def get_recommendation_for_order(
    connection: Any,
    *,
    recommendation_simulation_id: str,
    employee_id: str,
) -> dict[str, Any] | None:
    """Read a recommendation before creating an order simulation."""

    return row_to_dict(
        await fetch_one(
            connection,
            GET_RECOMMENDATION_FOR_ORDER_SQL,
            recommendation_simulation_id,
            employee_id,
        )
    )


async def insert_order_simulation(
    connection: Any,
    *,
    recommendation_simulation_id: str,
    customer_id: str,
    employee_id: str,
    product_id: str,
    side_code: str,
    quantity: Decimal | None,
    amount_krw: Decimal | None,
    status_code: str,
    gate_detail: dict[str, Any],
) -> dict[str, Any]:
    """Insert an order simulation without calling any external order API."""

    row = await fetch_one(
        connection,
        INSERT_ORDER_SIMULATION_SQL,
        recommendation_simulation_id,
        customer_id,
        employee_id,
        product_id,
        side_code,
        quantity,
        amount_krw,
        status_code,
        json.dumps(gate_detail, ensure_ascii=False),
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("order simulation insert returned no row")
    return result


async def execute_order_simulation(
    connection: Any,
    *,
    order_simulation_id: str,
    employee_id: str,
) -> dict[str, Any] | None:
    """Record simulated execution only; never call an external trading API."""

    return row_to_dict(
        await fetch_one(connection, EXECUTE_ORDER_SIMULATION_SQL, order_simulation_id, employee_id)
    )


async def get_order_simulation(
    connection: Any,
    *,
    order_simulation_id: str,
) -> dict[str, Any] | None:
    """Read one order simulation row (for the second-person 4-eye approval gate)."""

    return row_to_dict(
        await fetch_one(connection, GET_ORDER_SIMULATION_SQL, order_simulation_id)
    )


async def approve_order_simulation(
    connection: Any,
    *,
    order_simulation_id: str,
    approver_id: str,
) -> dict[str, Any] | None:
    """Second-person 4-eye approval: PENDING_APPROVAL → APPROVED.

    The SQL enforces ``employee_id <> approver_id`` so the creator cannot
    self-approve even if a caller skips the route-level check. Returns None when
    the row is not PENDING_APPROVAL or the approver equals the creator.
    """

    return row_to_dict(
        await fetch_one(
            connection, APPROVE_ORDER_SIMULATION_SQL, order_simulation_id, approver_id
        )
    )
