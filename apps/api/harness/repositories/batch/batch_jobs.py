"""Batch job CRUD, status SQL, and provider-evidence repository helpers.

sql_id namespace: harness.batch.repo.jobs.*
"""

from __future__ import annotations

import json
from typing import Any

from apps.api.harness.core.db import fetch_all, fetch_one

from ..common import row_to_dict, rows_to_dicts

PROVIDER_STATUS_CODES: tuple[str, ...] = (
    "PROVIDER_DONE",
    "PROVIDER_NO_DATA",
    "PROVIDER_SKIPPED_CONFIG",
    "PROVIDER_SKIPPED_DISABLED",
    "PROVIDER_FAILED_AUTH",
    "PROVIDER_FAILED_RATE_LIMIT",
    "PROVIDER_FAILED_SCHEMA",
    "PROVIDER_FAILED_NETWORK",
)

LIST_BATCH_STATUS_SQL = """
/* sql_id: list_batch_status */
SELECT id, job_name, job_type_code, status_code, started_at, finished_at,
       rows_collected, rows_skipped, rows_failed, error_message, created_at
FROM batch_job_logs
WHERE ($1::varchar IS NULL OR status_code = $1::varchar)
ORDER BY created_at DESC
LIMIT $2 OFFSET $3;
"""

LIST_BATCH_PROVIDER_EVIDENCE_FOR_LOGS_SQL = """
/* sql_id: list_batch_provider_evidence_for_logs */
SELECT id, batch_job_log_id, provider_code, provider_status_code, target_ref,
       rows_collected, rows_skipped, rows_failed, reason_message,
       provider_detail_json, observed_at
FROM batch_provider_evidence
WHERE batch_job_log_id = ANY($1::uuid[])
ORDER BY observed_at DESC, provider_code, target_ref;
"""

INSERT_BATCH_LOG_SQL = """
/* sql_id: insert_batch_job_log */
INSERT INTO batch_job_logs(job_name, job_type_code, status_code, started_at)
VALUES ($1, $2, 'RUNNING', now())
RETURNING id, job_name, job_type_code, status_code, started_at, finished_at,
          rows_collected, rows_skipped, rows_failed, error_message, created_at;
"""

INSERT_SKIPPED_BATCH_LOG_SQL = """
/* sql_id: insert_skipped_batch_job_log */
INSERT INTO batch_job_logs(job_name, job_type_code, status_code, started_at, finished_at,
                           rows_skipped, error_message)
VALUES ($1, $2, 'SKIPPED', now(), now(), 1, $3)
RETURNING id, job_name, job_type_code, status_code, started_at, finished_at,
          rows_collected, rows_skipped, rows_failed, error_message, created_at;
"""

MARK_BATCH_DONE_SQL = """
/* sql_id: mark_batch_job_done */
UPDATE batch_job_logs
SET status_code = 'DONE', finished_at = now(), rows_collected = $2,
    rows_skipped = $3, rows_failed = $4
WHERE id = $1::uuid
RETURNING id, job_name, job_type_code, status_code, started_at, finished_at,
          rows_collected, rows_skipped, rows_failed, error_message, created_at;
"""

MARK_BATCH_FAILED_SQL = """
/* sql_id: mark_batch_job_failed */
UPDATE batch_job_logs
SET status_code = 'FAILED', finished_at = now(), rows_collected = $2,
    rows_skipped = $3, rows_failed = $4, error_message = $5
WHERE id = $1::uuid
RETURNING id, job_name, job_type_code, status_code, started_at, finished_at,
          rows_collected, rows_skipped, rows_failed, error_message, created_at;
"""

INSERT_BATCH_PROVIDER_EVIDENCE_SQL = """
/* sql_id: insert_batch_provider_evidence */
INSERT INTO batch_provider_evidence(
    batch_job_log_id, provider_code, provider_status_code, target_ref,
    rows_collected, rows_skipped, rows_failed, reason_message, provider_detail_json
)
VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
ON CONFLICT (batch_job_log_id, provider_code, target_ref) DO UPDATE SET
    provider_status_code = EXCLUDED.provider_status_code,
    rows_collected = EXCLUDED.rows_collected,
    rows_skipped = EXCLUDED.rows_skipped,
    rows_failed = EXCLUDED.rows_failed,
    reason_message = EXCLUDED.reason_message,
    provider_detail_json = EXCLUDED.provider_detail_json,
    observed_at = now()
RETURNING id, batch_job_log_id, provider_code, provider_status_code, target_ref,
          rows_collected, rows_skipped, rows_failed, reason_message,
          provider_detail_json, observed_at;
"""


async def list_batch_status(
    connection: Any,
    *,
    status_code: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """List recent batch job logs."""

    rows = await fetch_all(connection, LIST_BATCH_STATUS_SQL, status_code, limit, offset)
    items = rows_to_dicts(rows)
    log_ids = [str(item["id"]) for item in items if item.get("id")]
    if not log_ids:
        return items

    evidence_rows = await fetch_all(connection, LIST_BATCH_PROVIDER_EVIDENCE_FOR_LOGS_SQL, log_ids)
    evidence_by_log_id: dict[str, list[dict[str, Any]]] = {log_id: [] for log_id in log_ids}
    for evidence in rows_to_dicts(evidence_rows):
        evidence_by_log_id.setdefault(str(evidence["batch_job_log_id"]), []).append(evidence)
    for item in items:
        item["provider_evidence"] = evidence_by_log_id.get(str(item["id"]), [])
    return items


async def create_batch_log(connection: Any, *, job_name: str, job_type_code: str) -> dict[str, Any]:
    """Insert RUNNING batch log."""

    row = await fetch_one(connection, INSERT_BATCH_LOG_SQL, job_name, job_type_code)
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("batch log insert returned no row")
    return result


async def create_skipped_batch_log(
    connection: Any, *, job_name: str, job_type_code: str, reason: str
) -> dict[str, Any]:
    """Insert SKIPPED batch log when distributed lock is held elsewhere."""

    row = await fetch_one(connection, INSERT_SKIPPED_BATCH_LOG_SQL, job_name, job_type_code, reason)
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("skipped batch log insert returned no row")
    return result


async def mark_batch_done(connection: Any, *, log_id: str, rows: dict[str, int]) -> dict[str, Any]:
    """Mark a batch log DONE."""

    row = await fetch_one(
        connection,
        MARK_BATCH_DONE_SQL,
        log_id,
        rows.get("rows_collected", 0),
        rows.get("rows_skipped", 0),
        rows.get("rows_failed", 0),
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("batch done update returned no row")
    return result


async def mark_batch_failed(
    connection: Any, *, log_id: str, rows: dict[str, int], error_message: str
) -> dict[str, Any]:
    """Mark a batch log FAILED with redacted error text from caller."""

    row = await fetch_one(
        connection,
        MARK_BATCH_FAILED_SQL,
        log_id,
        rows.get("rows_collected", 0),
        rows.get("rows_skipped", 0),
        rows.get("rows_failed", 0),
        error_message[:1000],
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("batch failed update returned no row")
    return result


async def insert_batch_provider_evidence(
    connection: Any,
    *,
    batch_job_log_id: str,
    provider_code: str,
    provider_status_code: str,
    target_ref: str,
    rows_collected: int = 0,
    rows_skipped: int = 0,
    rows_failed: int = 0,
    reason_message: str | None = None,
    provider_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert or update one provider-detail evidence row for a batch job."""

    if provider_status_code not in PROVIDER_STATUS_CODES:
        raise ValueError(f"unsupported provider_status_code: {provider_status_code}")
    if not target_ref:
        raise ValueError("target_ref is required for provider evidence")
    row = await fetch_one(
        connection,
        INSERT_BATCH_PROVIDER_EVIDENCE_SQL,
        batch_job_log_id,
        provider_code,
        provider_status_code,
        target_ref,
        max(rows_collected, 0),
        max(rows_skipped, 0),
        max(rows_failed, 0),
        reason_message[:1000] if reason_message else None,
        json.dumps(provider_detail or {}, ensure_ascii=False, default=str),
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("batch provider evidence insert returned no row")
    return result
