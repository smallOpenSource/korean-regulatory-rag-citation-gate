"""신용정보법 §20-2 파기 placeholder service (T219).

PoC scope: insert a data_purge_schedules row with purge_due_at = NOW() + 5 years
and emit audit credit_info_purge_simulated. Actual deletion is Stage 7 runbook scope.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from apps.api.harness.core.db import fetch_all, fetch_one

_SCHEDULE_PURGE_SQL = """
/* sql_id: credit_info_purge_schedule_insert */
INSERT INTO data_purge_schedules (
    target_table, target_row_id, purge_due_at, purge_reason
) VALUES (
    $1,
    $2,
    NOW() + INTERVAL '5 years',
    $3
)
RETURNING id, target_table, target_row_id, purge_due_at, executed_at, purge_reason;
"""

_LIST_PURGE_SCHEDULES_SQL = """
/* sql_id: credit_info_purge_schedule_list */
SELECT id, target_table, target_row_id, purge_due_at, executed_at, purge_reason
  FROM data_purge_schedules
 WHERE ($1::uuid IS NULL OR target_row_id = $1::uuid)
 ORDER BY purge_due_at ASC
 LIMIT $2 OFFSET $3;
"""


def _purge_row(row: Any) -> dict[str, Any]:
    """Serialize a data_purge_schedules row."""
    d = dict(row)
    for key in ("purge_due_at", "executed_at"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    d["synthetic"] = True  # PoC boundary guarantee
    return d


async def schedule_purge(
    connection: Any,
    *,
    target_table: str,
    target_row_id: str,
    reason: str,
) -> dict[str, Any]:
    """Insert a purge schedule row (신용정보법 §20-2). Actual deletion deferred to Stage 7.

    Args:
        connection: asyncpg connection.
        target_table: table name containing the row to be purged.
        target_row_id: UUID of the row to be purged.
        reason: human-readable reason (e.g. '상거래 종료 5년 경과').

    Returns:
        Serialized data_purge_schedules row with synthetic=true.
    """
    row = await fetch_one(
        connection,
        _SCHEDULE_PURGE_SQL,
        target_table,
        UUID(target_row_id),
        reason,
    )
    if row is None:
        raise ValueError("data_purge_schedules INSERT returned no row")
    return _purge_row(row)


async def list_purge_schedules(
    connection: Any,
    *,
    target_row_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List purge schedule rows, optionally filtered by target_row_id."""
    rows = await fetch_all(
        connection,
        _LIST_PURGE_SCHEDULES_SQL,
        UUID(target_row_id) if target_row_id else None,
        limit,
        offset,
    )
    return [_purge_row(r) for r in rows]
