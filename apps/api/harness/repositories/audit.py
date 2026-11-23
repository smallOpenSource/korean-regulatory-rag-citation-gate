"""Audit log repository with append-only raw SQL writes."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from apps.api.harness.core.audit import require_audit_action
from apps.api.harness.core.db import execute, fetch_all
from apps.api.harness.core.logging import redact_mapping

from .common import rows_to_dicts

INSERT_AUDIT_LOG_SQL = """
/* sql_id: insert_audit_log */
INSERT INTO audit_logs(
    actor_id, action_code, resource_type, resource_id, ip_address, user_agent, detail_json
)
VALUES ($1, $2, $3, $4, $5::inet, $6, $7::jsonb);
"""

LIST_AUDIT_LOGS_SQL = """
/* sql_id: list_audit_logs */
SELECT al.id, al.actor_id, al.action_code, al.resource_type, al.resource_id,
       al.ip_address::text AS ip_address, al.user_agent, al.detail_json, al.created_at,
       e.name        AS actor_name,
       e.employee_no AS actor_employee_no,
       aac.description AS action_description
FROM audit_logs al
LEFT JOIN employees e          ON e.id = al.actor_id
LEFT JOIN audit_action_codes aac ON aac.action_code = al.action_code
WHERE ($1::uuid IS NULL OR al.actor_id = $1::uuid)
  AND ($2::varchar IS NULL OR al.action_code = $2::varchar)
  AND ($3::date IS NULL OR al.created_at::date >= $3::date)
  AND ($4::date IS NULL OR al.created_at::date <= $4::date)
ORDER BY al.created_at DESC
LIMIT $5 OFFSET $6;
"""


async def insert_audit_log(
    connection: Any,
    *,
    actor_id: str | None,
    action_code: str,
    resource_type: str,
    resource_id: str | None,
    detail: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Append an audit log entry after redacting secrets from detail_json."""

    require_audit_action(action_code)
    safe_detail = redact_mapping(detail or {})
    await execute(
        connection,
        INSERT_AUDIT_LOG_SQL,
        actor_id,
        action_code,
        resource_type,
        resource_id,
        ip_address,
        user_agent,
        json.dumps(safe_detail, ensure_ascii=False),
    )


async def list_audit_logs(
    connection: Any,
    *,
    actor_id: str | None,
    action_code: str | None,
    from_date: date | None,
    to_date: date | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """Read audit logs for authorized audit/admin users."""

    rows = await fetch_all(
        connection,
        LIST_AUDIT_LOGS_SQL,
        actor_id,
        action_code,
        from_date,
        to_date,
        limit,
        offset,
    )
    return rows_to_dicts(rows)
