"""AI job and AI output repositories."""

from __future__ import annotations

import json
from typing import Any

from apps.api.harness.core.db import fetch_all, fetch_one
from apps.api.harness.core.logging import redact_secret_text

from .common import row_to_dict, rows_to_dicts

CREATE_AI_JOB_SQL = """
/* sql_id: create_ai_job */
INSERT INTO ai_jobs(job_type_code, status_code, requested_by_id, resource_type, resource_id)
VALUES ($1, 'PENDING', $2::uuid, $3, $4::uuid)
RETURNING id, job_type_code, status_code, requested_by_id, resource_type, resource_id,
          result_resource_type, result_resource_id, result_summary, error_code, error_message,
          created_at, started_at, finished_at;
"""

GET_AI_JOB_SQL = """
/* sql_id: get_authorized_ai_job */
SELECT j.id, j.job_type_code, j.status_code, j.requested_by_id, j.resource_type, j.resource_id,
       j.result_resource_type, j.result_resource_id, j.result_summary, j.error_code,
       j.error_message, j.created_at, j.started_at, j.finished_at
FROM ai_jobs j
WHERE j.id = $1::uuid
  AND ($2::varchar IN ('ADMIN', 'AUDIT_VIEWER') OR j.requested_by_id = $3::uuid);
"""

MARK_AI_JOB_RUNNING_SQL = """
/* sql_id: mark_ai_job_running */
UPDATE ai_jobs
SET status_code = 'RUNNING', started_at = COALESCE(started_at, now())
WHERE id = $1::uuid
RETURNING id, job_type_code, status_code, requested_by_id, resource_type, resource_id,
          result_resource_type, result_resource_id, result_summary, error_code, error_message,
          created_at, started_at, finished_at;
"""

MARK_AI_JOB_SUCCEEDED_SQL = """
/* sql_id: mark_ai_job_succeeded */
UPDATE ai_jobs
SET status_code = 'SUCCEEDED', result_resource_type = $2, result_resource_id = $3::uuid,
    result_summary = $4, finished_at = now()
WHERE id = $1::uuid
RETURNING id, job_type_code, status_code, requested_by_id, resource_type, resource_id,
          result_resource_type, result_resource_id, result_summary, error_code, error_message,
          created_at, started_at, finished_at;
"""

MARK_AI_JOB_FAILED_SQL = """
/* sql_id: mark_ai_job_failed */
UPDATE ai_jobs
SET status_code = 'FAILED', error_code = $2, error_message = $3, finished_at = now()
WHERE id = $1::uuid
RETURNING id, job_type_code, status_code, requested_by_id, resource_type, resource_id,
          result_resource_type, result_resource_id, result_summary, error_code, error_message,
          created_at, started_at, finished_at;
"""

CREATE_AI_OUTPUT_SQL = """
/* sql_id: create_ai_output */
INSERT INTO ai_outputs(agent_id, model_name, generated_at, resource_type, resource_id, job_id,
                       prompt_hash, output_json, citations_json, fail_closed_reason_code,
                       question_text)
VALUES ($1, $2, now(), $3, $4::uuid, $5::uuid, $6, $7::jsonb, $8::jsonb, $9, $10)
RETURNING id, agent_id, model_name, generated_at, resource_type, resource_id, job_id,
          prompt_hash, output_json, citations_json, fail_closed_reason_code, created_at;
"""

GET_AI_OUTPUT_SQL = """
/* sql_id: get_authorized_ai_output */
SELECT o.id, o.agent_id, o.model_name, o.generated_at, o.resource_type, o.resource_id,
       o.job_id, o.prompt_hash, o.output_json, o.citations_json, o.created_at
FROM ai_outputs o
LEFT JOIN ai_jobs j ON j.id = o.job_id
LEFT JOIN customers c
       ON o.resource_type = 'customers' AND c.id = o.resource_id AND c.is_active IS TRUE
WHERE o.id = $1::uuid
  AND (
      -- AUDIT_VIEWER intentionally reads ALL AI outputs (incl. customer-scoped) for
      -- audit-trail inspection; by design it has NO GET /customers/{id} access. This
      -- read-vs-operational asymmetry is the audit role's purpose, not a leak
      -- (pre-existing policy; AUDIT_VIEWER is a trusted read-only compliance role).
      $2::varchar IN ('ADMIN', 'AUDIT_VIEWER')
      OR j.requested_by_id = $3::uuid
      OR (
          -- P1-c follow-up: a staff member authorized for the LINKED CUSTOMER may
          -- read its AI output even if a different colleague generated it. Mirrors
          -- CUSTOMER_SCOPE_FRAGMENT exactly so /ai-outputs access == customer access
          -- (ADMIN already covered above; PB→assigned, WM/BM→branch).
          c.id IS NOT NULL
          AND (
              ($2::varchar = 'PB' AND c.assigned_pb_id = $3::uuid)
              OR ($2::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $4::uuid)
          )
      )
  );
"""

LIST_AI_OUTPUTS_FOR_RESOURCE_SQL = """
/* sql_id: list_ai_outputs_for_resource */
SELECT o.id, o.agent_id, o.model_name, o.generated_at, o.resource_type, o.resource_id,
       o.job_id, o.prompt_hash, o.output_json, o.citations_json, o.created_at
FROM ai_outputs o
WHERE o.resource_type = $1 AND o.resource_id = $2::uuid
ORDER BY o.generated_at DESC
LIMIT $3;
"""

# svc-viability-v4 I2 (ADR-018): identify the immediately prior generator of a
# given house_view by inspecting ai_jobs (natural SoT for per-generation
# actor). OFFSET 1 skips the current generation row that the caller just
# INSERTed in the same transaction; the same-transaction visibility is
# READ COMMITTED so the prior row is observable while the current row is not.
GET_PREVIOUS_HOUSE_VIEW_GENERATOR_SQL = """
/* sql_id: get_previous_house_view_generator */
SELECT requested_by_id
FROM ai_jobs
WHERE job_type_code = 'house_view_generation'
  AND resource_id = $1::uuid
ORDER BY created_at DESC
OFFSET 1
LIMIT 1;
"""


async def get_previous_house_view_generator(
    connection: Any, *, house_view_id: str
) -> str | None:
    """Return the actor id of the prior generator of ``house_view_id``.

    svc-viability-v4 I2 (ADR-018). Returns ``None`` when no prior generation
    exists (first-ever generate call). The caller compares the returned value
    against the current actor via ``core.identity.same_actor``.
    """

    row = await fetch_one(connection, GET_PREVIOUS_HOUSE_VIEW_GENERATOR_SQL, house_view_id)
    if row is None:
        return None
    requested_by_id = row["requested_by_id"]
    if requested_by_id is None:
        return None
    return str(requested_by_id)


async def create_ai_job(
    connection: Any,
    *,
    job_type_code: str,
    requested_by_id: str,
    resource_type: str | None,
    resource_id: str | None,
) -> dict[str, Any]:
    """Create a durable pending AI job."""

    row = await fetch_one(
        connection,
        CREATE_AI_JOB_SQL,
        job_type_code,
        requested_by_id,
        resource_type,
        resource_id,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("ai job create returned no row")
    return result


async def get_ai_job(
    connection: Any,
    *,
    job_id: str,
    role_code: str,
    employee_id: str,
) -> dict[str, Any] | None:
    """Read an AI job if actor is requester, admin, or audit viewer."""

    return row_to_dict(await fetch_one(connection, GET_AI_JOB_SQL, job_id, role_code, employee_id))


async def mark_job_running(connection: Any, *, job_id: str) -> dict[str, Any] | None:
    """Transition a job to RUNNING."""

    return row_to_dict(await fetch_one(connection, MARK_AI_JOB_RUNNING_SQL, job_id))


async def mark_job_succeeded(
    connection: Any,
    *,
    job_id: str,
    result_resource_type: str,
    result_resource_id: str,
    result_summary: str | None,
) -> dict[str, Any] | None:
    """Transition a job to SUCCEEDED with resource link."""

    return row_to_dict(
        await fetch_one(
            connection,
            MARK_AI_JOB_SUCCEEDED_SQL,
            job_id,
            result_resource_type,
            result_resource_id,
            result_summary,
        )
    )


async def mark_job_failed(
    connection: Any,
    *,
    job_id: str,
    error_code: str,
    error_message: str,
) -> dict[str, Any] | None:
    """Transition a job to FAILED with redacted error text."""

    safe_message = redact_secret_text(error_message)[:1000]
    return row_to_dict(
        await fetch_one(connection, MARK_AI_JOB_FAILED_SQL, job_id, error_code, safe_message)
    )


async def create_ai_output(
    connection: Any,
    *,
    agent_id: str,
    model_name: str,
    resource_type: str,
    resource_id: str | None,
    job_id: str | None,
    prompt_hash: str,
    output: dict[str, Any],
    citations: list[dict[str, Any]] | None = None,
    fail_closed_reason_code: str | None = None,
    question_text: str | None = None,
) -> dict[str, Any]:
    """Persist canonical AI output metadata and JSON result.

    The ``question_text`` parameter (added 2026-05-23 observability cycle
    via V065) captures the user's original input prompt/question alongside
    the model's response. The G1 RAGAS AnswerRelevancy metric reads it
    directly instead of substituting a placeholder. Defaults to NULL so
    legacy callers that have not been updated yet still work.
    """

    row = await fetch_one(
        connection,
        CREATE_AI_OUTPUT_SQL,
        agent_id,
        model_name,
        resource_type,
        resource_id,
        job_id,
        prompt_hash,
        json.dumps(output, ensure_ascii=False),
        json.dumps(citations or [], ensure_ascii=False),
        fail_closed_reason_code,
        question_text,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("ai output create returned no row")
    return result


async def get_ai_output(
    connection: Any,
    *,
    output_id: str,
    role_code: str,
    employee_id: str,
    branch_id: str | None = None,
) -> dict[str, Any] | None:
    """Read AI output if authorized via the linked job, an audit role, or (for
    customer-scoped outputs) authorization for the linked customer (P1-c)."""

    return row_to_dict(
        await fetch_one(
            connection, GET_AI_OUTPUT_SQL, output_id, role_code, employee_id, branch_id
        )
    )


async def list_outputs_for_resource(
    connection: Any,
    *,
    resource_type: str,
    resource_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List recent outputs for a resource."""

    rows = await fetch_all(
        connection, LIST_AI_OUTPUTS_FOR_RESOURCE_SQL, resource_type, resource_id, limit
    )
    return rows_to_dicts(rows)
