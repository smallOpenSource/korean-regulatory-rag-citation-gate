"""Consultation repositories with compliance-gated completion."""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import execute, fetch_one

from .common import row_to_dict

CREATE_CONSULTATION_SQL = """
/* sql_id: create_consultation */
INSERT INTO consultations(customer_id, employee_id, channel_code, status_code)
VALUES ($1::uuid, $2::uuid, $3, 'DRAFT')
RETURNING id, customer_id, employee_id, house_view_id, consultation_at, channel_code,
          status_code, summary, suitability_checked, explanation_checked, created_at, updated_at;
"""

GET_CONSULTATION_FOR_ACTOR_SQL = """
/* sql_id: get_scoped_consultation */
SELECT co.id, co.customer_id, co.employee_id, co.house_view_id, co.consultation_at,
       co.channel_code, co.status_code, co.summary, co.suitability_checked,
       co.explanation_checked, co.created_at, co.updated_at
FROM consultations co
JOIN customers c ON c.id = co.customer_id
WHERE co.id = $4::uuid
  AND (
      $1::varchar = 'ADMIN'
      OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
      OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid)
  );
"""

UPDATE_CONSULTATION_SQL = """
/* sql_id: update_consultation */
UPDATE consultations
SET summary = COALESCE($2, summary),
    suitability_checked = COALESCE($3, suitability_checked),
    explanation_checked = COALESCE($4, explanation_checked),
    status_code = COALESCE($5, status_code),
    updated_at = now()
WHERE id = $1::uuid
RETURNING id, customer_id, employee_id, house_view_id, consultation_at, channel_code,
          status_code, summary, suitability_checked, explanation_checked, created_at, updated_at;
"""

INSERT_CONSULTATION_NOTE_SQL = """
/* sql_id: insert_consultation_note */
INSERT INTO consultation_notes(consultation_id, author_id, note_text)
VALUES ($1::uuid, $2::uuid, $3)
RETURNING id, consultation_id, author_id, note_text, created_at, updated_at;
"""


def _actor_params(
    role_code: str, employee_id: str, branch_id: str | None
) -> tuple[str, str, str | None]:
    return role_code, employee_id, branch_id


async def create_consultation(
    connection: Any,
    *,
    customer_id: str,
    employee_id: str,
    channel_code: str,
) -> dict[str, Any]:
    """Create a draft consultation."""

    row = await fetch_one(
        connection, CREATE_CONSULTATION_SQL, customer_id, employee_id, channel_code
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("consultation create returned no row")
    return result


async def get_consultation_for_actor(
    connection: Any,
    *,
    role_code: str,
    employee_id: str,
    branch_id: str | None,
    consultation_id: str,
) -> dict[str, Any] | None:
    """Read one consultation under the actor's row scope."""

    return row_to_dict(
        await fetch_one(
            connection,
            GET_CONSULTATION_FOR_ACTOR_SQL,
            *_actor_params(role_code, employee_id, branch_id),
            consultation_id,
        )
    )


async def update_consultation(
    connection: Any,
    *,
    consultation_id: str,
    summary: str | None,
    suitability_checked: bool | None,
    explanation_checked: bool | None,
    status_code: str | None,
) -> dict[str, Any] | None:
    """Update checklist/status fields; DB constraints enforce completion gates."""

    return row_to_dict(
        await fetch_one(
            connection,
            UPDATE_CONSULTATION_SQL,
            consultation_id,
            summary,
            suitability_checked,
            explanation_checked,
            status_code,
        )
    )


async def add_note(
    connection: Any,
    *,
    consultation_id: str,
    author_id: str,
    note_text: str,
) -> dict[str, Any]:
    """Append a consultation note."""

    row = await fetch_one(
        connection, INSERT_CONSULTATION_NOTE_SQL, consultation_id, author_id, note_text
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("consultation note insert returned no row")
    return result


async def touch_updated_at(connection: Any, *, consultation_id: str) -> None:
    """Mark a consultation updated after a related note insert."""

    await execute(
        connection,
        """
        /* sql_id: touch_consultation_updated_at */
        UPDATE consultations SET updated_at = now() WHERE id = $1::uuid;
        """,
        consultation_id,
    )
