"""NBA and aftercare repositories."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from apps.api.harness.core.db import fetch_all, fetch_one
from apps.api.harness.core.rbac import ActorContext

from .common import row_to_dict, rows_to_dicts

LIST_NBA_ACTIONS_SQL = """
/* sql_id: list_scoped_nba_actions */
SELECT n.id, n.customer_id, c.customer_name, n.employee_id, n.action_type_code, n.priority_code,
       n.status_code, n.trigger_code, n.script_text, n.script_generated_at,
       n.script_model_name, n.due_date, n.snoozed_until, n.completed_at, n.created_at,
       n.updated_at
FROM nba_actions n
JOIN customers c ON c.id = n.customer_id
WHERE ($1::varchar = 'ADMIN'
       OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
       OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid))
  AND ($4::varchar IS NULL OR n.status_code = $4::varchar)
  AND ($5::varchar IS NULL OR n.priority_code = $5::varchar)
ORDER BY n.priority_code, n.due_date NULLS LAST, n.created_at DESC
LIMIT $6 OFFSET $7;
"""

UPDATE_NBA_STATUS_SQL = """
/* sql_id: update_scoped_nba_status */
UPDATE nba_actions n
SET status_code = $5::varchar,
    completed_at = CASE WHEN $5::varchar = 'DONE' THEN now() ELSE completed_at END,
    snoozed_until = CASE WHEN $5::varchar = 'SNOOZED' THEN $6::timestamptz ELSE snoozed_until END,
    updated_at = now()
FROM customers c
WHERE c.id = n.customer_id
  AND n.id = $4::uuid
  AND ($1::varchar = 'ADMIN'
       OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
       OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid))
RETURNING n.id, n.customer_id, c.customer_name, n.employee_id, n.action_type_code, n.priority_code,
          n.status_code, n.trigger_code, n.script_text, n.script_generated_at,
          n.script_model_name, n.due_date, n.snoozed_until, n.completed_at, n.created_at,
          n.updated_at;
"""

RESOLVE_AFTERCARE_EVENT_SQL = """
/* sql_id: resolve_scoped_aftercare_event */
UPDATE aftercare_events a
SET status_code = 'RESOLVED', notes = COALESCE($5, notes), resolved_at = now(), updated_at = now()
FROM customers c
WHERE c.id = a.customer_id
  AND a.id = $4::uuid
  AND ($1::varchar = 'ADMIN'
       OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
       OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid))
RETURNING a.id, a.customer_id, a.product_id, a.employee_id, a.event_type_code, a.event_date,
          a.status_code, a.notes, a.resolved_at, a.created_at, a.updated_at;
"""


def _actor_params(actor: ActorContext) -> tuple[str, str, str | None]:
    return actor.role_code, actor.employee_id, actor.branch_id


async def list_nba_actions(
    connection: Any,
    *,
    actor: ActorContext,
    status_code: str | None,
    priority_code: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """List NBA actions in actor customer scope."""

    rows = await fetch_all(
        connection,
        LIST_NBA_ACTIONS_SQL,
        *_actor_params(actor),
        status_code,
        priority_code,
        limit,
        offset,
    )
    return rows_to_dicts(rows)


async def update_nba_status(
    connection: Any,
    *,
    actor: ActorContext,
    nba_id: str,
    status_code: str,
    snoozed_until: datetime | None,
) -> dict[str, Any] | None:
    """Update NBA status under row scope."""

    return row_to_dict(
        await fetch_one(
            connection,
            UPDATE_NBA_STATUS_SQL,
            *_actor_params(actor),
            nba_id,
            status_code,
            snoozed_until,
        )
    )


async def resolve_aftercare_event(
    connection: Any,
    *,
    actor: ActorContext,
    event_id: str,
    notes: str | None,
) -> dict[str, Any] | None:
    """Resolve an aftercare event under row scope."""

    return row_to_dict(
        await fetch_one(
            connection, RESOLVE_AFTERCARE_EVENT_SQL, *_actor_params(actor), event_id, notes
        )
    )


# ── T17/T243: NBA card creation with P1/P2/P3 + SLA (V036) ──────────────────

INSERT_NBA_CARD_SQL = """
/* sql_id: insert_nba_card */
INSERT INTO nba_actions (
    customer_id, employee_id, action_type_code, priority_code,
    status_code, trigger_code, script_text,
    score, why_link_json, sla_timer_seconds, due_date
)
VALUES (
    $1::uuid, $2::uuid, $3, $4,
    'PENDING', $5, $6,
    $7::numeric, $8::jsonb, $9::integer,
    now()::date + ($9::integer / 86400)
)
RETURNING id, customer_id, employee_id, action_type_code, priority_code,
          status_code, trigger_code, script_text, script_generated_at,
          script_model_name, score, why_link_json, sla_timer_seconds,
          due_date, snoozed_until, completed_at, created_at, updated_at;
"""

ACKNOWLEDGE_NBA_CARD_SQL = """
/* sql_id: acknowledge_nba_card */
UPDATE nba_actions n
SET status_code = 'IN_PROGRESS', updated_at = now()
FROM customers c
WHERE c.id = n.customer_id
  AND n.id = $4::uuid
  AND n.status_code = 'PENDING'
  AND ($1::varchar = 'ADMIN'
       OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
       OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid))
RETURNING n.id, n.customer_id, n.employee_id, n.action_type_code, n.priority_code,
          n.status_code, n.trigger_code, n.score, n.why_link_json,
          n.sla_timer_seconds, n.due_date, n.completed_at, n.created_at, n.updated_at;
"""

COMPLETE_NBA_CARD_SQL = """
/* sql_id: complete_nba_card */
UPDATE nba_actions n
SET status_code = 'DONE', completed_at = now(), updated_at = now()
FROM customers c
WHERE c.id = n.customer_id
  AND n.id = $4::uuid
  AND n.status_code IN ('PENDING', 'IN_PROGRESS')
  AND ($1::varchar = 'ADMIN'
       OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
       OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid))
RETURNING n.id, n.customer_id, n.employee_id, n.action_type_code, n.priority_code,
          n.status_code, n.trigger_code, n.score, n.why_link_json,
          n.sla_timer_seconds, n.due_date, n.completed_at, n.created_at, n.updated_at;
"""

DISMISS_NBA_CARD_SQL = """
/* sql_id: dismiss_nba_card */
UPDATE nba_actions n
SET status_code = 'DISMISSED', completed_at = now(), updated_at = now()
FROM customers c
WHERE c.id = n.customer_id
  AND n.id = $4::uuid
  AND n.status_code IN ('PENDING', 'IN_PROGRESS')
  AND ($1::varchar = 'ADMIN'
       OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
       OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid))
RETURNING n.id, n.customer_id, n.employee_id, n.action_type_code, n.priority_code,
          n.status_code, n.trigger_code, n.score, n.why_link_json,
          n.sla_timer_seconds, n.due_date, n.completed_at, n.created_at, n.updated_at;
"""

# ── T244/T257: Aftercare quarterly queue (V036) ───────────────────────────────

CLOSE_AFTERCARE_QUARTERLY_SQL = """
/* sql_id: close_aftercare_quarterly_event */
UPDATE aftercare_events a
SET status_code = 'COMPLETED',
    completion_notes = COALESCE($5, completion_notes),
    resolved_at = now(),
    updated_at = now()
FROM customers c
WHERE c.id = a.customer_id
  AND a.id = $4::uuid
  AND a.status_code IN ('PENDING', 'OPEN', 'IN_PROGRESS')
  AND ($1::varchar = 'ADMIN'
       OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
       OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid))
RETURNING a.id, a.customer_id, a.event_type_code, a.quarter_code,
          a.due_date, a.status_code, a.notes, a.completion_notes,
          a.resolved_at, a.created_at, a.updated_at;
"""

SKIP_AFTERCARE_QUARTERLY_SQL = """
/* sql_id: skip_aftercare_quarterly_event */
UPDATE aftercare_events a
SET status_code = 'SKIPPED',
    completion_notes = COALESCE($5, completion_notes),
    resolved_at = now(),
    updated_at = now()
FROM customers c
WHERE c.id = a.customer_id
  AND a.id = $4::uuid
  AND a.status_code IN ('PENDING', 'OPEN')
  AND ($1::varchar = 'ADMIN'
       OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
       OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid))
RETURNING a.id, a.customer_id, a.event_type_code, a.quarter_code,
          a.due_date, a.status_code, a.notes, a.completion_notes,
          a.resolved_at, a.created_at, a.updated_at;
"""


async def insert_nba_card(
    connection: Any,
    *,
    customer_id: str,
    employee_id: str,
    action_type_code: str,
    priority_code: str,
    trigger_code: str,
    script_text: str,
    score: float,
    why_link: dict[str, str | None],
    sla_timer_seconds: int,
) -> dict[str, Any]:
    """Insert an NBA card with P1/P2/P3 priority and SLA timer."""
    row = await fetch_one(
        connection,
        INSERT_NBA_CARD_SQL,
        customer_id,
        employee_id,
        action_type_code,
        priority_code,
        trigger_code,
        script_text,
        score,
        json.dumps(why_link, ensure_ascii=False),
        sla_timer_seconds,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("nba_card insert returned no row")
    return result


async def acknowledge_nba_card(
    connection: Any, *, actor: ActorContext, nba_id: str
) -> dict[str, Any] | None:
    """Transition NBA card PENDING → IN_PROGRESS (acknowledged)."""
    return row_to_dict(
        await fetch_one(
            connection, ACKNOWLEDGE_NBA_CARD_SQL, *_actor_params(actor), nba_id
        )
    )


async def complete_nba_card(
    connection: Any, *, actor: ActorContext, nba_id: str
) -> dict[str, Any] | None:
    """Transition NBA card → DONE."""
    return row_to_dict(
        await fetch_one(
            connection, COMPLETE_NBA_CARD_SQL, *_actor_params(actor), nba_id
        )
    )


async def dismiss_nba_card(
    connection: Any, *, actor: ActorContext, nba_id: str
) -> dict[str, Any] | None:
    """Transition NBA card → DISMISSED."""
    return row_to_dict(
        await fetch_one(
            connection, DISMISS_NBA_CARD_SQL, *_actor_params(actor), nba_id
        )
    )


async def close_aftercare_quarterly(
    connection: Any,
    *,
    actor: ActorContext,
    event_id: str,
    completion_notes: str | None,
) -> dict[str, Any] | None:
    """Transition aftercare event → COMPLETED."""
    return row_to_dict(
        await fetch_one(
            connection,
            CLOSE_AFTERCARE_QUARTERLY_SQL,
            *_actor_params(actor),
            event_id,
            completion_notes,
        )
    )


async def skip_aftercare_quarterly(
    connection: Any,
    *,
    actor: ActorContext,
    event_id: str,
    completion_notes: str | None,
) -> dict[str, Any] | None:
    """Transition aftercare event → SKIPPED."""
    return row_to_dict(
        await fetch_one(
            connection,
            SKIP_AFTERCARE_QUARTERLY_SQL,
            *_actor_params(actor),
            event_id,
            completion_notes,
        )
    )
