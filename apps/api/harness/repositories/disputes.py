"""Dispute cases repository — raw SQL persistence."""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import execute, fetch_all, fetch_one

from .common import row_to_dict, rows_to_dicts

INSERT_DISPUTE_SQL = """
/* sql_id: insert_dispute_case */
INSERT INTO dispute_cases(
    customer_id, consultation_id, employee_id, dispute_type, status
) VALUES (
    $1::uuid, $2::uuid, $3::uuid, $4, 'OPEN'
)
RETURNING id, customer_id, consultation_id, employee_id,
          opened_at, dispute_type, status, response_due_at,
          responded_at, resolved_at,
          responded_by_actor_id, resolved_by_actor_id;
"""

LIST_DISPUTES_SQL = """
/* sql_id: list_dispute_cases */
SELECT id, customer_id, consultation_id, employee_id,
       opened_at, dispute_type, status, response_due_at,
       responded_at, resolved_at,
       responded_by_actor_id, resolved_by_actor_id
FROM dispute_cases
WHERE ($1::uuid IS NULL OR customer_id = $1::uuid)
  AND ($2::varchar IS NULL OR status = $2::varchar)
ORDER BY opened_at DESC
LIMIT $3 OFFSET $4;
"""

GET_DISPUTE_CASE_SQL = """
/* sql_id: get_dispute_case */
SELECT id, customer_id, consultation_id, employee_id,
       opened_at, dispute_type, status, response_due_at,
       responded_at, resolved_at,
       responded_by_actor_id, resolved_by_actor_id
FROM dispute_cases
WHERE id = $1::uuid;
"""

# svc-viability-v4 I3 (ADR-017): $3::uuid is the actor performing the status
# transition. The CASE WHEN selects which column to write based on $2 status,
# so a single bind value covers RESPONDED and RESOLVED branches.
# EXPIRED is APScheduler-driven (actor=NULL system) and is deferred to F-V5-8
# (services/disputes.py:31 docstring + ADR-017 §Follow-ups).
UPDATE_DISPUTE_STATUS_SQL = """
/* sql_id: update_dispute_status */
UPDATE dispute_cases
SET status       = $2::varchar,
    responded_at = CASE WHEN $2::text = 'RESPONDED' THEN now() ELSE responded_at END,
    responded_by_actor_id = CASE
        WHEN $2::text = 'RESPONDED' THEN $3::uuid
        ELSE responded_by_actor_id
    END,
    resolved_at  = CASE WHEN $2::text = 'RESOLVED'  THEN now() ELSE resolved_at  END,
    resolved_by_actor_id  = CASE
        WHEN $2::text = 'RESOLVED' THEN $3::uuid
        ELSE resolved_by_actor_id
    END
WHERE id = $1::uuid
RETURNING id, customer_id, consultation_id, employee_id,
          opened_at, dispute_type, status, response_due_at,
          responded_at, resolved_at,
          responded_by_actor_id, resolved_by_actor_id;
"""

INSERT_SYNTHETIC_DISPUTES_SQL = """
/* sql_id: insert_synthetic_dispute_demo */
INSERT INTO dispute_cases(customer_id, consultation_id, employee_id, dispute_type, status)
SELECT
    c.id,
    co.id,
    c.assigned_pb_id,
    '부당권유',
    'OPEN'
FROM customers c
JOIN consultations co ON co.customer_id = c.id
WHERE c.customer_no LIKE 'SYN-%'
  AND co.status_code = 'COMPLETED'
  AND NOT EXISTS (
      SELECT 1 FROM dispute_cases dc WHERE dc.customer_id = c.id
  )
ORDER BY c.created_at
LIMIT 1;
"""


async def insert_dispute_case(
    connection: Any,
    *,
    customer_id: str,
    consultation_id: str,
    employee_id: str,
    dispute_type: str,
) -> dict[str, Any]:
    """Open a new dispute case."""
    row = await fetch_one(
        connection,
        INSERT_DISPUTE_SQL,
        customer_id,
        consultation_id,
        employee_id,
        dispute_type,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("dispute case insert returned no row")
    return result


async def list_disputes(
    connection: Any,
    *,
    customer_id: str | None,
    status: str | None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List dispute cases with optional filters."""
    rows = await fetch_all(
        connection, LIST_DISPUTES_SQL, customer_id, status, limit, offset
    )
    return rows_to_dicts(rows)


async def get_dispute_case(
    connection: Any, *, dispute_id: str
) -> dict[str, Any] | None:
    """Fetch a single dispute case by id.

    svc-viability-v4 I3 (ADR-017) — used by the router to read the existing
    responder/resolver before issuing the UPDATE so the same-actor predicate
    has a deterministic previous-actor reference.
    """
    return row_to_dict(await fetch_one(connection, GET_DISPUTE_CASE_SQL, dispute_id))


async def update_dispute_status(
    connection: Any,
    *,
    dispute_id: str,
    new_status: str,
    actor_id: str | None = None,
) -> dict[str, Any] | None:
    """Update dispute status (RESPONDED | RESOLVED).

    svc-viability-v4 I3 (ADR-017): ``actor_id`` writes the responder OR
    resolver actor column based on the target ``new_status``. EXPIRED
    transitions remain APScheduler-driven (F-V5-8) and must not invoke this
    code path with a non-system actor.
    """
    return row_to_dict(
        await fetch_one(
            connection,
            UPDATE_DISPUTE_STATUS_SQL,
            dispute_id,
            new_status,
            actor_id,
        )
    )


async def seed_synthetic_dispute(connection: Any) -> None:
    """Insert one sample dispute per synthetic family persona (PoC demo data)."""
    await execute(connection, INSERT_SYNTHETIC_DISPUTES_SQL)
