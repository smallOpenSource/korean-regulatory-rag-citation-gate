"""Rights notice repository — raw SQL persistence."""

from __future__ import annotations

import json
from typing import Any

from apps.api.harness.core.db import fetch_all, fetch_one

from .common import row_to_dict, rows_to_dicts

INSERT_RIGHTS_NOTICE_SQL = """
/* sql_id: insert_rights_notice */
INSERT INTO rights_notices(
    consultation_id, customer_id, employee_id, notice_kinds, audit_chain_hash
) VALUES (
    $1::uuid, $2::uuid, $3::uuid, $4::jsonb, $5
)
RETURNING id, consultation_id, customer_id, employee_id,
          notice_kinds, issued_at, audit_chain_hash;
"""

LIST_RIGHTS_NOTICES_SQL = """
/* sql_id: list_rights_notices_for_customer */
SELECT id, consultation_id, customer_id, employee_id,
       notice_kinds, issued_at, audit_chain_hash
FROM rights_notices
WHERE customer_id = $1::uuid
ORDER BY issued_at DESC
LIMIT $2 OFFSET $3;
"""

GET_RIGHTS_NOTICE_SQL = """
/* sql_id: get_rights_notice */
SELECT id, consultation_id, customer_id, employee_id,
       notice_kinds, issued_at, audit_chain_hash
FROM rights_notices
WHERE id = $1::uuid;
"""


async def insert_rights_notice(
    connection: Any,
    *,
    consultation_id: str,
    customer_id: str,
    employee_id: str,
    notice_kinds: list[dict[str, Any]],
    audit_chain_hash: str | None = None,
) -> dict[str, Any]:
    """Persist a rights notice record (issued at consultation end)."""
    row = await fetch_one(
        connection,
        INSERT_RIGHTS_NOTICE_SQL,
        consultation_id,
        customer_id,
        employee_id,
        json.dumps(notice_kinds, ensure_ascii=False),
        audit_chain_hash,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("rights notice insert returned no row")
    return result


async def list_rights_notices(
    connection: Any,
    *,
    customer_id: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List rights notices issued to a customer."""
    rows = await fetch_all(
        connection, LIST_RIGHTS_NOTICES_SQL, customer_id, limit, offset
    )
    return rows_to_dicts(rows)


async def get_rights_notice(
    connection: Any, *, notice_id: str
) -> dict[str, Any] | None:
    """Fetch a single rights notice by ID."""
    return row_to_dict(
        await fetch_one(connection, GET_RIGHTS_NOTICE_SQL, notice_id)
    )
