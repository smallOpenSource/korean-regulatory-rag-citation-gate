"""Quarantine-events and injection-metrics repository (Stage 3, ADR-005).

Surfaces dual-LLM quarantine telemetry from document_chunks.quarantine_flag (V032)
and injection_events table introduced in Stage 3.

Schema reconciliation (Wave 6.5 R34 fix, 2026-05-19):
  Source column names verified against live document_chunks schema:
    - chunk_no (was: chunk_index in this module's SQL)
    - quarantine_pattern_code (was: quarantine_reason_code — ADR-005 §3 names
      quarantine_pattern_code as the SoT and labels PI-KO IDs additive-only)
  The historical ``quarantine_reviewed_at`` column is not present on
  document_chunks; the metrics query returns 0 for the reviewed count and
  the release path no longer attempts to stamp a reviewed-at timestamp.
  Adding the column belongs in a separate migration cycle, not in this
  read-path repair.

sql_id namespace: harness.batch.repo.quarantine.*
"""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import fetch_all, fetch_one

from ..common import row_to_dict, rows_to_dicts

GET_QUARANTINE_METRICS_SQL = """
/* sql_id: get_quarantine_metrics */
SELECT
    (
        SELECT count(*)::integer
        FROM document_chunks
        WHERE quarantine_flag IS TRUE
    ) AS quarantine_flag_count,
    0::integer AS quarantine_reviewed_count,
    (
        SELECT CASE WHEN to_regclass('injection_events') IS NOT NULL THEN 1 ELSE 0 END
    ) AS quarantine_schema_ready;
"""

LIST_QUARANTINE_CHUNKS_SQL = """
/* sql_id: list_quarantine_chunks */
SELECT id,
       document_id,
       chunk_no AS chunk_index,
       quarantine_flag,
       quarantine_pattern_code AS quarantine_reason_code,
       NULL::timestamptz AS quarantine_reviewed_at,
       created_at
FROM document_chunks
WHERE quarantine_flag IS TRUE
ORDER BY created_at DESC
LIMIT $1 OFFSET $2;
"""


async def get_quarantine_metrics(connection: Any) -> dict[str, Any]:
    """Return quarantine readiness metrics from persisted DB evidence."""

    row = await fetch_one(connection, GET_QUARANTINE_METRICS_SQL)
    result = row_to_dict(row)
    if result is None:
        return {
            "quarantine_flag_count": 0,
            "quarantine_reviewed_count": 0,
            "quarantine_schema_ready": 0,
        }
    return result


async def list_quarantine_chunks(
    connection: Any,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List document chunks flagged for quarantine review."""

    rows = await fetch_all(connection, LIST_QUARANTINE_CHUNKS_SQL, limit, offset)
    return rows_to_dicts(rows)


RELEASE_QUARANTINE_CHUNK_SQL = """
/* sql_id: release_quarantine_chunk */
UPDATE document_chunks
SET quarantine_flag = FALSE
WHERE id = $1
  AND quarantine_flag IS TRUE
RETURNING id,
          document_id,
          chunk_no AS chunk_index,
          quarantine_flag,
          quarantine_pattern_code AS quarantine_reason_code,
          NULL::timestamptz AS quarantine_reviewed_at,
          created_at;
"""


async def release_quarantine_chunk(
    connection: Any,
    *,
    chunk_id: str,
) -> dict[str, Any] | None:
    """Release a quarantined chunk (sets quarantine_flag=FALSE, stamps reviewed_at)."""

    row = await fetch_one(connection, RELEASE_QUARANTINE_CHUNK_SQL, chunk_id)
    return row_to_dict(row)
