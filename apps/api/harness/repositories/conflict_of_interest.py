"""Conflict of interest repository — raw SQL with sql_id (T249, V030)."""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import fetch_all, fetch_one

from .common import row_to_dict, rows_to_dicts

INSERT_CONFLICT_DISCLOSURE_SQL = """
/* sql_id: insert_conflict_disclosure */
INSERT INTO conflict_disclosures (
    employee_id, customer_id, disclosure_type,
    description_redacted, chinese_wall_violation,
    blocked_at
)
VALUES (
    $1::uuid, $2::uuid, $3,
    $4,
    $5::boolean,
    CASE WHEN $5::boolean THEN now() ELSE NULL END
)
RETURNING id, employee_id, customer_id, disclosure_type,
          description_redacted, disclosed_at,
          chinese_wall_violation, blocked_at,
          created_at, updated_at;
"""

LIST_CONFLICT_DISCLOSURES_SQL = """
/* sql_id: list_conflict_disclosures */
-- Wave-Audit-Defect-Fix C3 follow-up: employees table column is `name`,
-- not `employee_name` (live DB schema verified 2026-05-21). Aliased
-- so the API response shape stays compatible.
SELECT d.id, d.employee_id, e.name AS employee_name, d.customer_id, c.customer_name,
       d.disclosure_type, d.description_redacted, d.disclosed_at,
       d.chinese_wall_violation, d.blocked_at,
       d.created_at, d.updated_at
FROM conflict_disclosures d
JOIN employees e ON e.id = d.employee_id
JOIN customers c ON c.id = d.customer_id
WHERE ($1::uuid IS NULL OR d.employee_id = $1::uuid)
  AND ($2::uuid IS NULL OR d.customer_id = $2::uuid)
  AND ($3::boolean IS NULL OR d.chinese_wall_violation = $3::boolean)
ORDER BY d.disclosed_at DESC
LIMIT $4 OFFSET $5;
"""

GET_CONFLICT_DISCLOSURE_SQL = """
/* sql_id: get_conflict_disclosure */
SELECT id, employee_id, customer_id, disclosure_type,
       description_redacted, disclosed_at,
       chinese_wall_violation, blocked_at,
       created_at, updated_at
FROM conflict_disclosures
WHERE id = $1::uuid;
"""


async def insert_conflict_disclosure(
    connection: Any,
    *,
    employee_id: str,
    customer_id: str,
    disclosure_type: str,
    description_redacted: str | None,
    chinese_wall_violation: bool,
) -> dict[str, Any]:
    """Insert a conflict disclosure and return the new row."""
    row = await fetch_one(
        connection,
        INSERT_CONFLICT_DISCLOSURE_SQL,
        employee_id,
        customer_id,
        disclosure_type,
        description_redacted,
        chinese_wall_violation,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("conflict_disclosure insert returned no row")
    return result


async def list_conflict_disclosures(
    connection: Any,
    *,
    employee_id: str | None = None,
    customer_id: str | None = None,
    chinese_wall_only: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List conflict disclosures with optional filters."""
    rows = await fetch_all(
        connection,
        LIST_CONFLICT_DISCLOSURES_SQL,
        employee_id,
        customer_id,
        chinese_wall_only,
        limit,
        offset,
    )
    return rows_to_dicts(rows)


async def get_conflict_disclosure(
    connection: Any, *, disclosure_id: str
) -> dict[str, Any] | None:
    """Fetch one disclosure by UUID."""
    return row_to_dict(
        await fetch_one(connection, GET_CONFLICT_DISCLOSURE_SQL, disclosure_id)
    )
