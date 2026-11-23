"""Email draft repositories with raw SQL, row scope, and full state-machine transitions.

V034 columns: submitted_at, approved_at, approved_by_id, transport_message_id,
              failure_reason_code, marketing_classified, 사전심의필번호, marketing_review_id.
V025: marketing_reviews FK wired.
"""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import execute, fetch_all, fetch_one
from apps.api.harness.core.rbac import ActorContext

from .common import row_to_dict

# ---------------------------------------------------------------------------
# SQL — shared column list (includes V034 state-machine columns)
# ---------------------------------------------------------------------------

_DRAFT_COLS = """
    d.id, d.customer_id, d.employee_id, d.consultation_id,
    d.subject, d.body, d.ai_generated_at, d.ai_model_name,
    d.status_code, d.sent_at, d.created_at, d.updated_at,
    d.submitted_at, d.approved_at, d.approved_by_id,
    d.transport_message_id, d.failure_reason_code,
    d.marketing_classified, d."사전심의필번호", d.marketing_review_id
"""

CREATE_EMAIL_DRAFT_SQL = """
/* sql_id: create_email_draft */
INSERT INTO email_drafts(
    customer_id, employee_id, consultation_id, subject, body,
    ai_generated_at, ai_model_name, status_code,
    marketing_classified, "사전심의필번호"
)
VALUES (
    $1::uuid, $2::uuid, $3::uuid, $4, $5,
    NULL, NULL, 'DRAFT',
    $6::boolean, $7
)
RETURNING
    id, customer_id, employee_id, consultation_id, subject, body,
    ai_generated_at, ai_model_name, status_code, sent_at, created_at, updated_at,
    submitted_at, approved_at, approved_by_id, transport_message_id,
    failure_reason_code, marketing_classified, "사전심의필번호", marketing_review_id;
"""

GET_SCOPED_EMAIL_DRAFT_SQL = """
/* sql_id: get_scoped_email_draft */
SELECT
    d.id, d.customer_id, d.employee_id, d.consultation_id,
    d.subject, d.body, d.ai_generated_at, d.ai_model_name,
    d.status_code, d.sent_at, d.created_at, d.updated_at,
    d.submitted_at, d.approved_at, d.approved_by_id,
    d.transport_message_id, d.failure_reason_code,
    d.marketing_classified, d."사전심의필번호", d.marketing_review_id,
    c.customer_name, c.assigned_pb_id, c.branch_id
FROM email_drafts d
JOIN customers c ON c.id = d.customer_id
WHERE d.id = $4::uuid
  AND c.is_active IS TRUE
  AND (
      $1::varchar = 'ADMIN'
      OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
      OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid)
  );
"""

LIST_SCOPED_EMAIL_DRAFTS_SQL = """
/* sql_id: list_scoped_email_drafts */
SELECT
    d.id, d.customer_id, d.employee_id, d.consultation_id,
    d.subject, d.body, d.ai_generated_at, d.ai_model_name,
    d.status_code, d.sent_at, d.created_at, d.updated_at,
    d.submitted_at, d.approved_at, d.approved_by_id,
    d.transport_message_id, d.failure_reason_code,
    d.marketing_classified, d."사전심의필번호", d.marketing_review_id,
    c.customer_name, c.assigned_pb_id, c.branch_id
FROM email_drafts d
JOIN customers c ON c.id = d.customer_id
WHERE c.is_active IS TRUE
  AND (
      $1::varchar = 'ADMIN'
      OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
      OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid)
  )
  AND ($4::varchar IS NULL OR d.status_code = $4::varchar)
  AND (
      $1::varchar IN ('ADMIN', 'AUDIT_VIEWER')
      OR (
          COALESCE(d.subject, '') !~* '(golden[ _-]?test|ralph[ _-]?qa|test[ _-]?fixture|regression[ _-]?test|golden[ _-]?regression)'
          AND COALESCE(d.body, '') !~* '(golden[ _-]?regression|ralph[ _-]?qa|test[ _-]?fixture|REG-0[0-9]|ADR-[0-9]+|W[0-9]-T[0-9])'
      )
  )
ORDER BY d.created_at DESC
LIMIT $5::int OFFSET $6::int;
"""

SUBMIT_EMAIL_DRAFT_SQL = """
/* sql_id: submit_email_draft */
UPDATE email_drafts d
SET status_code = 'PENDING_APPROVAL', submitted_at = now(), updated_at = now()
WHERE d.id = $1::uuid
  AND d.status_code = 'DRAFT'
RETURNING
    id, customer_id, employee_id, consultation_id, subject, body,
    ai_generated_at, ai_model_name, status_code, sent_at, created_at, updated_at,
    submitted_at, approved_at, approved_by_id, transport_message_id,
    failure_reason_code, marketing_classified, "사전심의필번호", marketing_review_id;
"""

APPROVE_EMAIL_DRAFT_SQL = """
/* sql_id: approve_email_draft */
UPDATE email_drafts d
SET status_code = 'APPROVED', approved_at = now(), approved_by_id = $2::uuid,
    updated_at = now()
WHERE d.id = $1::uuid
  AND d.status_code = 'PENDING_APPROVAL'
RETURNING
    id, customer_id, employee_id, consultation_id, subject, body,
    ai_generated_at, ai_model_name, status_code, sent_at, created_at, updated_at,
    submitted_at, approved_at, approved_by_id, transport_message_id,
    failure_reason_code, marketing_classified, "사전심의필번호", marketing_review_id;
"""

REJECT_EMAIL_DRAFT_SQL = """
/* sql_id: reject_email_draft */
UPDATE email_drafts d
SET status_code = 'DRAFT', submitted_at = NULL, updated_at = now()
WHERE d.id = $1::uuid
  AND d.status_code = 'PENDING_APPROVAL'
RETURNING
    id, customer_id, employee_id, consultation_id, subject, body,
    ai_generated_at, ai_model_name, status_code, sent_at, created_at, updated_at,
    submitted_at, approved_at, approved_by_id, transport_message_id,
    failure_reason_code, marketing_classified, "사전심의필번호", marketing_review_id;
"""

MARK_EMAIL_DRAFT_SENT_SQL = """
/* sql_id: mark_email_draft_sent */
UPDATE email_drafts d
SET status_code = 'SENT', sent_at = now(), transport_message_id = $2, updated_at = now()
WHERE d.id = $1::uuid
  AND d.status_code = 'APPROVED'
RETURNING
    id, customer_id, employee_id, consultation_id, subject, body,
    ai_generated_at, ai_model_name, status_code, sent_at, created_at, updated_at,
    submitted_at, approved_at, approved_by_id, transport_message_id,
    failure_reason_code, marketing_classified, "사전심의필번호", marketing_review_id;
"""

MARK_EMAIL_DRAFT_FAILED_SQL = """
/* sql_id: mark_email_draft_failed */
UPDATE email_drafts d
SET status_code = 'FAILED', failure_reason_code = $2, updated_at = now()
WHERE d.id = $1::uuid
  AND d.status_code = 'APPROVED'
RETURNING
    id, customer_id, employee_id, consultation_id, subject, body,
    ai_generated_at, ai_model_name, status_code, sent_at, created_at, updated_at,
    submitted_at, approved_at, approved_by_id, transport_message_id,
    failure_reason_code, marketing_classified, "사전심의필번호", marketing_review_id;
"""

CREATE_MARKETING_REVIEW_SQL = """
/* sql_id: create_marketing_review */
INSERT INTO marketing_reviews(
    email_draft_id, classification, leading_block_text,
    static_rule_pass, ai_compliance_pass, ai_reasoning_redacted,
    decision, reviewed_by
)
VALUES ($1::uuid, $2, $3, $4::boolean, $5::boolean, $6, $7, $8::uuid)
RETURNING id, email_draft_id, classification, leading_block_text,
          static_rule_pass, ai_compliance_pass, ai_reasoning_redacted,
          decision, reviewed_by, reviewed_at, created_at;
"""

LINK_MARKETING_REVIEW_SQL = """
/* sql_id: link_marketing_review */
UPDATE email_drafts
SET marketing_review_id = $2::uuid, updated_at = now()
WHERE id = $1::uuid;
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _actor_params(actor: ActorContext) -> tuple[str, str, str | None]:
    return actor.role_code, actor.employee_id, actor.branch_id


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------


async def create_email_draft(
    connection: Any,
    *,
    customer_id: str,
    employee_id: str,
    consultation_id: str | None,
    subject: str,
    body: str,
    marketing_classified: bool = False,
    pre_review_number: str | None = None,
) -> dict[str, Any]:
    """Create a DRAFT email row; caller owns role and row-scope checks."""

    row = await fetch_one(
        connection,
        CREATE_EMAIL_DRAFT_SQL,
        customer_id,
        employee_id,
        consultation_id,
        subject,
        body,
        marketing_classified,
        pre_review_number,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("email draft create returned no row")
    return result


async def get_email_draft_for_actor(
    connection: Any,
    *,
    actor: ActorContext,
    draft_id: str,
) -> dict[str, Any] | None:
    """Read one email draft under the actor's customer row scope."""

    return row_to_dict(
        await fetch_one(
            connection,
            GET_SCOPED_EMAIL_DRAFT_SQL,
            *_actor_params(actor),
            draft_id,
        )
    )


async def list_email_drafts_for_actor(
    connection: Any,
    *,
    actor: ActorContext,
    status_code: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List email drafts under the actor's customer row scope (ordered by created_at DESC)."""

    rows = await fetch_all(
        connection,
        LIST_SCOPED_EMAIL_DRAFTS_SQL,
        *_actor_params(actor),
        status_code,
        max(1, min(limit, 200)),
        max(0, offset),
    )
    return [d for d in (row_to_dict(row) for row in rows) if d is not None]


async def submit_email_draft(
    connection: Any,
    *,
    draft_id: str,
) -> dict[str, Any] | None:
    """Transition DRAFT → PENDING_APPROVAL; returns updated row or None if guard fails."""

    return row_to_dict(await fetch_one(connection, SUBMIT_EMAIL_DRAFT_SQL, draft_id))


async def approve_email_draft(
    connection: Any,
    *,
    draft_id: str,
    approver_id: str,
) -> dict[str, Any] | None:
    """Transition PENDING_APPROVAL → APPROVED; returns updated row or None if guard fails."""

    return row_to_dict(
        await fetch_one(connection, APPROVE_EMAIL_DRAFT_SQL, draft_id, approver_id)
    )


async def reject_email_draft(
    connection: Any,
    *,
    draft_id: str,
) -> dict[str, Any] | None:
    """Transition PENDING_APPROVAL → DRAFT; returns updated row or None if guard fails."""

    return row_to_dict(await fetch_one(connection, REJECT_EMAIL_DRAFT_SQL, draft_id))


async def mark_email_draft_sent(
    connection: Any,
    *,
    draft_id: str,
    transport_message_id: str,
) -> dict[str, Any] | None:
    """Transition APPROVED → SENT after successful Mailpit delivery."""

    return row_to_dict(
        await fetch_one(connection, MARK_EMAIL_DRAFT_SENT_SQL, draft_id, transport_message_id)
    )


async def mark_email_draft_failed(
    connection: Any,
    *,
    draft_id: str,
    failure_reason_code: str,
) -> dict[str, Any] | None:
    """Transition APPROVED → FAILED on delivery error."""

    return row_to_dict(
        await fetch_one(
            connection, MARK_EMAIL_DRAFT_FAILED_SQL, draft_id, failure_reason_code
        )
    )


async def create_marketing_review(
    connection: Any,
    *,
    email_draft_id: str,
    classification: str,
    leading_block_text: str | None,
    static_rule_pass: bool,
    ai_compliance_pass: bool | None,
    ai_reasoning_redacted: str | None,
    decision: str,
    reviewed_by: str,
) -> dict[str, Any]:
    """Persist a marketing_reviews row for audit chain."""

    row = await fetch_one(
        connection,
        CREATE_MARKETING_REVIEW_SQL,
        email_draft_id,
        classification,
        leading_block_text,
        static_rule_pass,
        ai_compliance_pass,
        ai_reasoning_redacted,
        decision,
        reviewed_by,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("marketing review create returned no row")
    return result


async def link_marketing_review(
    connection: Any,
    *,
    draft_id: str,
    marketing_review_id: str,
) -> None:
    """Set email_drafts.marketing_review_id after a marketing_reviews row is created."""

    await execute(connection, LINK_MARKETING_REVIEW_SQL, draft_id, marketing_review_id)
