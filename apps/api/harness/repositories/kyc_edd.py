"""KYC/EDD trigger repository — raw SQL with sql_id (T248, V029)."""

from __future__ import annotations

import json
from typing import Any

from apps.api.harness.core.db import fetch_all, fetch_one

from .common import row_to_dict, rows_to_dicts

INSERT_KYC_EDD_TRIGGER_SQL = """
/* sql_id: insert_kyc_edd_trigger */
INSERT INTO kyc_edd_triggers (
    customer_id, trigger_type, trigger_value
)
VALUES ($1::uuid, $2, $3::jsonb)
RETURNING id, customer_id, trigger_type, trigger_value,
          triggered_at, status, reason_text,
          reassessed_at, reassessor_employee_id,
          previous_actor_id, created_at, updated_at;
"""

LIST_KYC_EDD_TRIGGERS_SQL = """
/* sql_id: list_kyc_edd_triggers */
SELECT t.id, t.customer_id, c.customer_name, t.trigger_type,
       t.trigger_value, t.triggered_at, t.status,
       t.reason_text, t.reassessed_at, t.reassessor_employee_id,
       t.previous_actor_id, t.created_at, t.updated_at
FROM kyc_edd_triggers t
JOIN customers c ON c.id = t.customer_id
WHERE ($1::uuid IS NULL OR t.customer_id = $1::uuid)
  AND ($2::varchar IS NULL OR t.status = $2::varchar)
ORDER BY t.triggered_at DESC
LIMIT $3 OFFSET $4;
"""

GET_KYC_EDD_TRIGGER_SQL = """
/* sql_id: get_kyc_edd_trigger */
SELECT id, customer_id, trigger_type, trigger_value,
       triggered_at, status, reason_text,
       reassessed_at, reassessor_employee_id,
       previous_actor_id, created_at, updated_at
FROM kyc_edd_triggers
WHERE id = $1::uuid;
"""

# svc-viability-v4 I1 (ADR-017): $3::uuid is the previous_actor_id passed
# in by the router (existing["reassessor_employee_id"] or None on the first
# invocation). No SQL-side COALESCE — router carries the responsibility.
REASSESS_KYC_EDD_TRIGGER_SQL = """
/* sql_id: reassess_kyc_edd_trigger */
UPDATE kyc_edd_triggers
SET status = 'IN_PROGRESS',
    reason_text = $2,
    previous_actor_id = $3::uuid,
    updated_at = now()
WHERE id = $1::uuid
  AND status = 'OPEN'
RETURNING id, customer_id, trigger_type, trigger_value,
          triggered_at, status, reason_text,
          reassessed_at, reassessor_employee_id,
          previous_actor_id, created_at, updated_at;
"""

COMPLETE_KYC_EDD_TRIGGER_SQL = """
/* sql_id: complete_kyc_edd_trigger */
UPDATE kyc_edd_triggers
SET status = 'CLOSED',
    reassessed_at = now(),
    reassessor_employee_id = $2::uuid,
    previous_actor_id = $3::uuid,
    updated_at = now()
WHERE id = $1::uuid
  AND status IN ('OPEN', 'IN_PROGRESS')
RETURNING id, customer_id, trigger_type, trigger_value,
          triggered_at, status, reason_text,
          reassessed_at, reassessor_employee_id,
          previous_actor_id, created_at, updated_at;
"""


async def insert_kyc_edd_trigger(
    connection: Any,
    *,
    customer_id: str,
    trigger_type: str,
    trigger_value: dict[str, Any],
) -> dict[str, Any]:
    """Insert a new KYC/EDD trigger row and return it."""
    row = await fetch_one(
        connection,
        INSERT_KYC_EDD_TRIGGER_SQL,
        customer_id,
        trigger_type,
        json.dumps(trigger_value, ensure_ascii=False),
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("kyc_edd_trigger insert returned no row")
    return result


async def list_kyc_edd_triggers(
    connection: Any,
    *,
    customer_id: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """List KYC/EDD triggers with optional customer/status filter."""
    rows = await fetch_all(
        connection, LIST_KYC_EDD_TRIGGERS_SQL, customer_id, status, limit, offset
    )
    return rows_to_dicts(rows)


async def get_kyc_edd_trigger(
    connection: Any, *, trigger_id: str
) -> dict[str, Any] | None:
    """Fetch one trigger by UUID."""
    return row_to_dict(await fetch_one(connection, GET_KYC_EDD_TRIGGER_SQL, trigger_id))


async def reassess_kyc_edd_trigger(
    connection: Any,
    *,
    trigger_id: str,
    reason_text: str,
    previous_actor_id: str | None = None,
) -> dict[str, Any] | None:
    """Mark trigger IN_PROGRESS with reason_text and record previous actor.

    svc-viability-v4 I1 (ADR-017): the router passes the prior actor (typically
    ``existing["reassessor_employee_id"]``) so the next same-actor compare has
    a non-NULL value to test. NULL on the very first invocation is correct
    and is the sentinel that suppresses the audit emit.
    """
    return row_to_dict(
        await fetch_one(
            connection,
            REASSESS_KYC_EDD_TRIGGER_SQL,
            trigger_id,
            reason_text,
            previous_actor_id,
        )
    )


async def complete_kyc_edd_trigger(
    connection: Any,
    *,
    trigger_id: str,
    reassessor_employee_id: str,
    previous_actor_id: str | None = None,
) -> dict[str, Any] | None:
    """Mark trigger CLOSED with reassessor, previous actor, and timestamp.

    svc-viability-v4 I1 (ADR-017): previous_actor_id is the actor recorded on
    the row before this complete call (router responsibility). NULL is the
    valid sentinel for "first ever close on a trigger that was never
    reassessed by a different actor".
    """
    return row_to_dict(
        await fetch_one(
            connection,
            COMPLETE_KYC_EDD_TRIGGER_SQL,
            trigger_id,
            reassessor_employee_id,
            previous_actor_id,
        )
    )
