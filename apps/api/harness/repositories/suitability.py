"""Suitability assessments + consultation gates — raw SQL repository."""

from __future__ import annotations

import json
from typing import Any

from apps.api.harness.core.db import execute, fetch_all, fetch_one

from .common import row_to_dict, rows_to_dicts

INSERT_SUITABILITY_SQL = """
/* sql_id: insert_suitability_assessment */
INSERT INTO suitability_assessments(
    consultation_id, customer_id, employee_id,
    investment_objective, financial_situation, investment_experience,
    age_bracket, loss_tolerance_pct, investment_horizon_months,
    investor_classification, form_option_orders
) VALUES (
    $1::uuid, $2::uuid, $3::uuid,
    $4, $5::jsonb, $6::jsonb,
    $7, $8::numeric, $9::integer,
    $10, $11::jsonb
)
RETURNING id, consultation_id, customer_id, employee_id,
          investment_objective, financial_situation, investment_experience,
          age_bracket, loss_tolerance_pct, investment_horizon_months,
          investor_classification, form_option_orders, created_at;
"""

GET_LATEST_SUITABILITY_SQL = """
/* sql_id: get_latest_suitability_assessment */
SELECT id, consultation_id, customer_id, employee_id,
       investment_objective, financial_situation, investment_experience,
       age_bracket, loss_tolerance_pct, investment_horizon_months,
       investor_classification, form_option_orders, created_at
FROM suitability_assessments
WHERE consultation_id = $1::uuid
ORDER BY created_at DESC
LIMIT 1;
"""

UPSERT_GATE_SQL = """
/* sql_id: upsert_consultation_gate */
INSERT INTO consultation_gates(consultation_id, gate_name, gate_status, gate_evidence_json)
VALUES ($1::uuid, $2, $3, $4::jsonb)
ON CONFLICT (consultation_id, gate_name) DO UPDATE
SET gate_status        = EXCLUDED.gate_status,
    gate_evidence_json = EXCLUDED.gate_evidence_json,
    updated_at         = now()
RETURNING id, consultation_id, gate_name, gate_status,
          gate_evidence_json, gate_acknowledged_at, gate_acknowledged_by,
          created_at, updated_at;
"""

ACKNOWLEDGE_GATE_SQL = """
/* sql_id: acknowledge_consultation_gate */
UPDATE consultation_gates
SET gate_status          = 'ACKNOWLEDGED',
    gate_acknowledged_at = now(),
    gate_acknowledged_by = $3::uuid,
    updated_at           = now()
WHERE consultation_id = $1::uuid
  AND gate_name       = $2
RETURNING id, consultation_id, gate_name, gate_status,
          gate_evidence_json, gate_acknowledged_at, gate_acknowledged_by,
          created_at, updated_at;
"""

LIST_GATES_SQL = """
/* sql_id: list_consultation_gates */
SELECT id, consultation_id, gate_name, gate_status,
       gate_evidence_json, gate_acknowledged_at, gate_acknowledged_by,
       created_at, updated_at
FROM consultation_gates
WHERE consultation_id = $1::uuid
ORDER BY gate_name;
"""

GET_CUSTOMER_GRADE_SQL = """
/* sql_id: get_customer_grade */
SELECT id, risk_grade_code, investor_classification
FROM customers
WHERE id = $1::uuid;
"""

GET_PRODUCT_GRADE_SQL = """
/* sql_id: get_product_grade */
SELECT id, risk_grade_code, risk_level_code, product_name, product_type_code,
       has_knock_in, fee_pct, maturity_date, volatility_meta
FROM products
WHERE id = $1::uuid;
"""


async def insert_suitability_assessment(
    connection: Any,
    *,
    consultation_id: str,
    customer_id: str,
    employee_id: str,
    investment_objective: str,
    financial_situation: dict[str, Any],
    investment_experience: dict[str, Any],
    age_bracket: str,
    loss_tolerance_pct: float,
    investment_horizon_months: int,
    investor_classification: str,
    form_option_orders: dict[str, Any],
) -> dict[str, Any]:
    """Insert a new suitability assessment record."""
    row = await fetch_one(
        connection,
        INSERT_SUITABILITY_SQL,
        consultation_id,
        customer_id,
        employee_id,
        investment_objective,
        json.dumps(financial_situation, ensure_ascii=False),
        json.dumps(investment_experience, ensure_ascii=False),
        age_bracket,
        loss_tolerance_pct,
        investment_horizon_months,
        investor_classification,
        json.dumps(form_option_orders, ensure_ascii=False),
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("suitability assessment insert returned no row")
    return result


async def get_latest_suitability(
    connection: Any, *, consultation_id: str
) -> dict[str, Any] | None:
    """Fetch the most recent suitability assessment for a consultation."""
    return row_to_dict(
        await fetch_one(connection, GET_LATEST_SUITABILITY_SQL, consultation_id)
    )


async def upsert_gate(
    connection: Any,
    *,
    consultation_id: str,
    gate_name: str,
    gate_status: str,
    gate_evidence_json: dict[str, Any],
) -> dict[str, Any]:
    """Create or update a consultation gate row."""
    row = await fetch_one(
        connection,
        UPSERT_GATE_SQL,
        consultation_id,
        gate_name,
        gate_status,
        json.dumps(gate_evidence_json, ensure_ascii=False, default=str),
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("gate upsert returned no row")
    return result


async def acknowledge_gate(
    connection: Any,
    *,
    consultation_id: str,
    gate_name: str,
    acknowledged_by: str,
) -> dict[str, Any] | None:
    """Mark a gate as ACKNOWLEDGED and record who acknowledged it."""
    return row_to_dict(
        await fetch_one(
            connection, ACKNOWLEDGE_GATE_SQL,
            consultation_id, gate_name, acknowledged_by,
        )
    )


async def list_gates(
    connection: Any, *, consultation_id: str
) -> list[dict[str, Any]]:
    """Fetch all gate rows for a consultation."""
    rows = await fetch_all(connection, LIST_GATES_SQL, consultation_id)
    return rows_to_dicts(rows)


async def get_customer_grade(
    connection: Any, *, customer_id: str
) -> dict[str, Any] | None:
    """Fetch customer risk grade + classification for suitability check."""
    return row_to_dict(
        await fetch_one(connection, GET_CUSTOMER_GRADE_SQL, customer_id)
    )


async def get_product_grade(
    connection: Any, *, product_id: str
) -> dict[str, Any] | None:
    """Fetch product grade + volatility metadata for suitability check."""
    return row_to_dict(
        await fetch_one(connection, GET_PRODUCT_GRADE_SQL, product_id)
    )
