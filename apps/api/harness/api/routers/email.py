"""Email draft state-machine routes — ADR-002 Wave 1 patch.

State machine: DRAFT → PENDING_APPROVAL → APPROVED → SENT | FAILED
Marketing classification + 광고심의 leading-block lint (REG-03 T247).
Mailpit-only sandbox transport (ADR-002 / ADR-003).
PII outbound regex block (주민번호, 카드번호, 계좌번호).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from apps.api.harness.api.dependencies import (
    actor_from_authorization,
    get_pool,
    get_request_config,
    request_audit_context,
)
from apps.api.harness.core.error_codes import ErrorCode
from apps.api.harness.core.errors import structured_http_exception
from apps.api.harness.core.idempotency_middleware import idempotent
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import consultations as consultation_repo
from apps.api.harness.repositories import customers as customer_repo
from apps.api.harness.repositories import email as email_repo
from apps.api.harness.repositories import suitability as suitability_repo
from apps.api.harness.services.email_delivery import (
    EmailContentRejectedError,
    validate_display_safe_email_content,
)
from apps.api.harness.services.email_transport_mailpit import (
    MailpitTransportError,
    send_via_mailpit,
)
from apps.api.harness.services.marketing import check_pii_outbound, run_marketing_gate

router = APIRouter(tags=["email"])


# ---------------------------------------------------------------------------
# Role guard
# ---------------------------------------------------------------------------


def require_email_staff(role_code: str) -> None:
    """Allow email draft/send only for PB/WM front-office roles."""
    if role_code not in {"PB", "WM"}:
        raise HTTPException(status_code=403, detail="PB/WM role required")


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------


def _uuid_or_none(payload: dict[str, Any], field_name: str) -> str | None:
    value = payload.get(field_name)
    if value is None or value == "":
        return None
    try:
        return str(UUID(str(value).strip()))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} must be a UUID") from exc


def _required_text(payload: dict[str, Any], field_name: str) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    return value


# ---------------------------------------------------------------------------
# Response formatter
# ---------------------------------------------------------------------------


def _format_draft_response(draft: dict[str, Any]) -> dict[str, Any]:
    return {
        "draft_id": str(draft["id"]),
        "id": str(draft["id"]),
        "customer_id": str(draft["customer_id"]),
        "consultation_id": (
            str(draft["consultation_id"]) if draft.get("consultation_id") else None
        ),
        "status_code": draft["status_code"],
        "subject": draft.get("subject", ""),
        "body": draft.get("body", ""),
        "marketing_classified": bool(draft.get("marketing_classified", False)),
        "ai_output_id": draft.get("ai_output_id"),
        "created_at": draft["created_at"],
        "submitted_at": draft.get("submitted_at"),
        "approved_at": draft.get("approved_at"),
        "sent_at": draft.get("sent_at"),
        "failure_reason_code": draft.get("failure_reason_code"),
    }


# ---------------------------------------------------------------------------
# GET /email-drafts — scoped list (PB/WM front-office staff)
# ---------------------------------------------------------------------------


@router.get("/email-drafts")  # type: ignore[union-attr]
async def list_email_drafts(
    request: Request,
    status_code: str | None = None,
    limit: int = 50,
    offset: int = 0,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """List email drafts visible to the actor (scoped by role)."""

    config = get_request_config(request)
    actor = actor_from_authorization(config, authorization)
    require_email_staff(actor.role_code)
    pool = get_pool(request)
    async with pool.acquire() as connection:  # type: ignore[union-attr]
        rows = await email_repo.list_email_drafts_for_actor(
            connection,
            actor=actor,
            status_code=(status_code.strip().upper() if status_code else None),
            limit=limit,
            offset=offset,
        )
    return {
        "items": [_format_draft_response(row) for row in rows],
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# POST /email-drafts — create DRAFT
# ---------------------------------------------------------------------------


@router.post("/email-drafts", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
@idempotent
async def create_email_draft(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create a DRAFT email; no provider send happens on draft creation."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_email_staff(actor.role_code)

    customer_id = _uuid_or_none(payload, "customer_id")
    consultation_id = _uuid_or_none(payload, "consultation_id")
    if customer_id is None and consultation_id is None:
        raise HTTPException(status_code=422, detail="customer_id or consultation_id is required")

    subject = _required_text(payload, "subject")
    body = _required_text(payload, "body")

    marketing_classified = bool(payload.get("marketing_classified", False))
    pre_review_number: str | None = str(payload.get("사전심의필번호", "")).strip() or None

    if marketing_classified and not pre_review_number:
        raise HTTPException(
            status_code=400,
            detail="사전심의필번호 is required when marketing_classified is true",
        )

    # PII + display-safe content check before persistence
    try:
        validate_display_safe_email_content(subject, body)
    except EmailContentRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pii_hits = check_pii_outbound(subject, body)
    if pii_hits:
        raise structured_http_exception(
            400,
            ErrorCode.redaction_blocked,
            "outbound PII redaction blocked the draft",
            categories=pii_hits,
        )

    async with get_pool(request).acquire() as conn:
        if consultation_id is not None:
            consultation = await consultation_repo.get_consultation_for_actor(
                conn,
                role_code=actor.role_code,
                employee_id=actor.employee_id,
                branch_id=actor.branch_id,
                consultation_id=consultation_id,
            )
            if consultation is None:
                raise HTTPException(status_code=404, detail="consultation not found")
            consultation_customer_id = str(consultation["customer_id"])
            if customer_id is not None and customer_id != consultation_customer_id:
                raise HTTPException(
                    status_code=400,
                    detail="customer_id must match consultation customer_id",
                )
            customer_id = consultation_customer_id

        assert customer_id is not None
        customer = await customer_repo.get_customer(conn, actor=actor, customer_id=customer_id)
        if customer is None:
            raise HTTPException(status_code=404, detail="customer not found")

        draft = await email_repo.create_email_draft(
            conn,
            customer_id=customer_id,
            employee_id=actor.employee_id,
            consultation_id=consultation_id,
            subject=subject,
            body=body,
            marketing_classified=marketing_classified,
            pre_review_number=pre_review_number,
        )
        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="email_drafted",
            resource_type="email_draft",
            resource_id=str(draft["id"]),
            detail={"marketing_classified": marketing_classified},
            **request_audit_context(request),
        )

    return _format_draft_response(draft)


# ---------------------------------------------------------------------------
# POST /email-drafts/{draft_id}/submit — DRAFT → PENDING_APPROVAL
# ---------------------------------------------------------------------------


@router.post("/email-drafts/{draft_id}/submit")  # type: ignore[union-attr]
@idempotent
async def submit_email_draft(
    request: Request,
    draft_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Submit a DRAFT for approval; runs marketing classification + leading-block lint."""

    config = get_request_config(request)
    actor = actor_from_authorization(config, authorization)
    require_email_staff(actor.role_code)
    draft_id_text = str(draft_id)

    async with get_pool(request).acquire() as conn:
        draft = await email_repo.get_email_draft_for_actor(
            conn, actor=actor, draft_id=draft_id_text
        )
        if draft is None:
            raise HTTPException(status_code=404, detail="email draft not found")
        if draft["status_code"] != "DRAFT":
            raise HTTPException(
                status_code=409, detail="email draft must be in DRAFT status to submit"
            )

        subject = str(draft["subject"])
        body = str(draft["body"])
        marketing_classified = bool(draft.get("marketing_classified", False))
        pre_review_number: str | None = draft.get("사전심의필번호") or None

        # Run marketing gate (classify + lint if MARKETING)
        gate = await run_marketing_gate(
            subject=subject,
            body=body,
            marketing_classified=marketing_classified,
            pre_review_number=pre_review_number,
        )

        # Persist marketing review record
        review = await email_repo.create_marketing_review(
            conn,
            email_draft_id=draft_id_text,
            classification=gate.classification,
            leading_block_text=(
                gate.lint_result.description if gate.lint_result else None
            ),
            static_rule_pass=gate.static_rule_pass,
            ai_compliance_pass=gate.ai_compliance_pass,
            ai_reasoning_redacted=gate.ai_reasoning_redacted,
            decision=gate.decision,
            reviewed_by=actor.employee_id,
        )
        review_id = str(review["id"])
        await email_repo.link_marketing_review(
            conn, draft_id=draft_id_text, marketing_review_id=review_id
        )

        if gate.decision == "MARKETING_REVIEW_BLOCK":
            await audit_repo.insert_audit_log(
                conn,
                actor_id=actor.employee_id,
                action_code="marketing_review_blocked",
                resource_type="email_draft",
                resource_id=draft_id_text,
                detail={
                    "classification": gate.classification,
                    "issue_codes": gate.issue_codes,
                    "marketing_review_id": review_id,
                },
                **request_audit_context(request),
            )
            # Service-viability F6 / D3: persist the consultation_gates row
            # for the marketing gate even on BLOCK so the downstream
            # /four-gate aggregate reflects the BLOCKED status (instead of
            # leaving the gate orphaned in PENDING forever). The HTTP error
            # still propagates to the caller.
            blocked_link_id = draft.get("consultation_id")
            if blocked_link_id:
                await suitability_repo.upsert_gate(
                    conn,
                    consultation_id=str(blocked_link_id),
                    gate_name="marketing",
                    gate_status="BLOCKED",
                    gate_evidence_json={
                        "classification": gate.classification,
                        "decision": gate.decision,
                        "issue_codes": gate.issue_codes,
                        "marketing_review_id": review_id,
                        "email_draft_id": draft_id_text,
                    },
                )
            raise structured_http_exception(
                400,
                ErrorCode.marketing_lint_failed,
                "marketing leading-block lint blocked the draft",
                issue_codes=gate.issue_codes,
                marketing_review_id=review_id,
            )

        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="marketing_review_submitted",
            resource_type="email_draft",
            resource_id=draft_id_text,
            detail={
                "classification": gate.classification,
                "decision": gate.decision,
                "marketing_review_id": review_id,
            },
            **request_audit_context(request),
        )

        # Service-viability F6 / D3: persist a consultation_gates row for
        # gate_name="marketing" when the draft is consultation-scoped so the
        # downstream /four-gate/marketing/acknowledge call can succeed.
        # The marketing gate was previously orphaned in marketing_reviews
        # without an aggregate-table row, so /four-gate aggregate kept the
        # gate in PENDING state forever and ack returned 404.
        consultation_link_id = draft.get("consultation_id")
        if consultation_link_id:
            await suitability_repo.upsert_gate(
                conn,
                consultation_id=str(consultation_link_id),
                gate_name="marketing",
                gate_status="PASSED",
                gate_evidence_json={
                    "classification": gate.classification,
                    "decision": gate.decision,
                    "marketing_review_id": review_id,
                    "email_draft_id": draft_id_text,
                },
            )

        submitted = await email_repo.submit_email_draft(conn, draft_id=draft_id_text)
        if submitted is None:
            raise HTTPException(status_code=409, detail="email draft could not be submitted")

        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="email_draft_submitted",
            resource_type="email_draft",
            resource_id=draft_id_text,
            detail={"marketing_classified": marketing_classified},
            **request_audit_context(request),
        )

    return _format_draft_response(submitted)


# ---------------------------------------------------------------------------
# POST /email-drafts/{draft_id}/approve — PENDING_APPROVAL → APPROVED
# ---------------------------------------------------------------------------


@router.post("/email-drafts/{draft_id}/approve")  # type: ignore[union-attr]
@idempotent
async def approve_email_draft(
    request: Request,
    draft_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Approve a PENDING_APPROVAL draft. For marketing drafts: four-eye enforced (approver ≠ author)."""

    config = get_request_config(request)
    actor = actor_from_authorization(config, authorization)
    require_email_staff(actor.role_code)
    draft_id_text = str(draft_id)

    async with get_pool(request).acquire() as conn:
        draft = await email_repo.get_email_draft_for_actor(
            conn, actor=actor, draft_id=draft_id_text
        )
        if draft is None:
            raise HTTPException(status_code=404, detail="email draft not found")
        if draft["status_code"] != "PENDING_APPROVAL":
            raise HTTPException(
                status_code=409,
                detail="email draft must be in PENDING_APPROVAL status to approve",
            )

        # Four-eye enforcement for marketing drafts (REG-03 T247 / ADR-002)
        if bool(draft.get("marketing_classified", False)):
            if actor.employee_id == str(draft["employee_id"]):
                # svc-viability-v3 B5 — emit audit row BEFORE raise so the
                # 4-eye violation attempt is preserved in audit_logs even
                # though the HTTP behavior (403) remains unchanged.
                await audit_repo.insert_audit_log(
                    conn,
                    actor_id=actor.employee_id,
                    action_code="four_eyes_violation_blocked",
                    resource_type="email_draft",
                    resource_id=draft_id_text,
                    detail={
                        "approver_id": actor.employee_id,
                        "original_creator_id": str(draft["employee_id"]),
                    },
                    **request_audit_context(request),
                )
                raise HTTPException(
                    status_code=403,
                    detail="marketing drafts require a different approver (four-eye rule)",
                )

        approved = await email_repo.approve_email_draft(
            conn,
            draft_id=draft_id_text,
            approver_id=actor.employee_id,
        )
        if approved is None:
            raise HTTPException(status_code=409, detail="email draft could not be approved")

        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="email_draft_approved",
            resource_type="email_draft",
            resource_id=draft_id_text,
            detail={
                "marketing_classified": bool(draft.get("marketing_classified", False)),
                # ADR-021 Phase 2: the approver (actor) reviewed a draft authored by
                # original_creator. For marketing drafts the two are provably distinct
                # (four_eyes_violation_blocked 403s self-approval); recording both lets
                # the SoD pack confirm a distinct second-person review.
                "human_reviewer": str(actor.employee_id),
                "original_creator": str(draft["employee_id"]),
            },
            **request_audit_context(request),
        )

    return _format_draft_response(approved)


# ---------------------------------------------------------------------------
# POST /email-drafts/{draft_id}/reject — PENDING_APPROVAL → DRAFT
# ---------------------------------------------------------------------------


@router.post("/email-drafts/{draft_id}/reject")  # type: ignore[union-attr]
@idempotent
async def reject_email_draft(
    request: Request,
    draft_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Reject a PENDING_APPROVAL draft; status reverts to DRAFT for revision."""

    config = get_request_config(request)
    actor = actor_from_authorization(config, authorization)
    require_email_staff(actor.role_code)
    draft_id_text = str(draft_id)

    async with get_pool(request).acquire() as conn:
        draft = await email_repo.get_email_draft_for_actor(
            conn, actor=actor, draft_id=draft_id_text
        )
        if draft is None:
            raise HTTPException(status_code=404, detail="email draft not found")
        if draft["status_code"] != "PENDING_APPROVAL":
            raise HTTPException(
                status_code=409,
                detail="email draft must be in PENDING_APPROVAL status to reject",
            )

        rejected = await email_repo.reject_email_draft(conn, draft_id=draft_id_text)
        if rejected is None:
            raise HTTPException(status_code=409, detail="email draft could not be rejected")

        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="email_draft_rejected",
            resource_type="email_draft",
            resource_id=draft_id_text,
            detail={
                # ADR-021 Phase 2: the rejecting reviewer (actor) acted on a draft
                # authored by original_creator; record both for SoD distinctness.
                "human_reviewer": str(actor.employee_id),
                "original_creator": str(draft["employee_id"]),
            },
            **request_audit_context(request),
        )

    return _format_draft_response(rejected)


# ---------------------------------------------------------------------------
# POST /email-drafts/{draft_id}/send — APPROVED → SENT | FAILED
# ---------------------------------------------------------------------------


@router.post("/email-drafts/{draft_id}/send")  # type: ignore[union-attr]
@idempotent
async def send_approved_email_draft(
    request: Request,
    draft_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Send an APPROVED draft via Mailpit sandbox; fail closed on any gate failure."""

    config = get_request_config(request)
    actor = actor_from_authorization(config, authorization)
    require_email_staff(actor.role_code)
    draft_id_text = str(draft_id)

    async with get_pool(request).acquire() as conn:
        draft = await email_repo.get_email_draft_for_actor(
            conn, actor=actor, draft_id=draft_id_text
        )
        if draft is None:
            raise HTTPException(status_code=404, detail="email draft not found")
        if draft["status_code"] != "APPROVED":
            raise HTTPException(
                status_code=409, detail="email draft must be APPROVED before send"
            )

        subject = str(draft["subject"])
        body = str(draft["body"])
        marketing_classified = bool(draft.get("marketing_classified", False))
        pre_review_number: str | None = draft.get("사전심의필번호") or None

        # --- Gate 1: PII outbound block ---
        pii_hits = check_pii_outbound(subject, body)
        if pii_hits:
            failed = await email_repo.mark_email_draft_failed(
                conn, draft_id=draft_id_text, failure_reason_code="redaction_blocked"
            )
            await audit_repo.insert_audit_log(
                conn,
                actor_id=actor.employee_id,
                action_code="email_send_blocked",
                resource_type="email_draft",
                resource_id=draft_id_text,
                detail={"failure_reason_code": "redaction_blocked", "pii_categories": pii_hits},
                **request_audit_context(request),
            )
            raise structured_http_exception(
                400,
                ErrorCode.redaction_blocked,
                "outbound PII redaction blocked the send",
                categories=pii_hits,
            )

        # --- Gate 2: Marketing leading-block lint at send time ---
        if marketing_classified:
            gate = await run_marketing_gate(
                subject=subject,
                body=body,
                marketing_classified=True,
                pre_review_number=pre_review_number,
            )
            if gate.decision == "MARKETING_REVIEW_BLOCK":
                failed = await email_repo.mark_email_draft_failed(
                    conn,
                    draft_id=draft_id_text,
                    failure_reason_code="marketing_lint_failed",
                )
                await audit_repo.insert_audit_log(
                    conn,
                    actor_id=actor.employee_id,
                    action_code="email_send_blocked",
                    resource_type="email_draft",
                    resource_id=draft_id_text,
                    detail={
                        "failure_reason_code": "marketing_lint_failed",
                        "issue_codes": gate.issue_codes,
                    },
                    **request_audit_context(request),
                )
                raise structured_http_exception(
                    400,
                    ErrorCode.marketing_lint_failed,
                    "marketing leading-block lint blocked the send",
                    issue_codes=gate.issue_codes,
                )

        # --- Gate 3: Mailpit transport ---
        email_cfg = config.email
        recipient = str(email_cfg.test_recipient_email or "demo@example.invalid")
        sender_email = str(email_cfg.sender_email or "harness@example.invalid")
        sender_name = str(email_cfg.sender_name or "Harness")

        try:
            delivery = await send_via_mailpit(
                transport=email_cfg.transport,
                mailpit_host=email_cfg.mailpit_host,
                mailpit_port=email_cfg.mailpit_port,
                mailpit_auth_user=email_cfg.mailpit_auth_user,
                mailpit_auth_password=email_cfg.mailpit_auth_password,
                sender_email=sender_email,
                sender_name=sender_name,
                recipient=recipient,
                subject=subject,
                body=body,
                timeout=email_cfg.timeout_seconds,
                sandbox_guardrail_enabled=email_cfg.sandbox_guardrail_enabled,
            )
        except MailpitTransportError as exc:
            reason = exc.failure_reason_code
            await email_repo.mark_email_draft_failed(
                conn, draft_id=draft_id_text, failure_reason_code=reason
            )
            await audit_repo.insert_audit_log(
                conn,
                actor_id=actor.employee_id,
                action_code="email_send_failed",
                resource_type="email_draft",
                resource_id=draft_id_text,
                detail={"failure_reason_code": reason},
                **request_audit_context(request),
            )
            raise HTTPException(
                status_code=503,
                detail={"error_code": reason},
            ) from exc

        sent = await email_repo.mark_email_draft_sent(
            conn,
            draft_id=draft_id_text,
            transport_message_id=delivery.transport_message_id,
        )
        if sent is None:
            raise HTTPException(status_code=409, detail="email draft transition to SENT failed")

        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="email_sent_via_sandbox",
            resource_type="email_draft",
            resource_id=draft_id_text,
            detail={
                **delivery.as_audit_detail(),
                # ADR-021 Phase 2: the sender (actor) only executes transport; the
                # genuine human review happened at approval, so record the prior
                # approver (approved_by_id) as human_reviewer — not the sender (str|None).
                "human_reviewer": (
                    str(draft["approved_by_id"]) if draft.get("approved_by_id") else None
                ),
            },
            **request_audit_context(request),
        )

    return {
        "draft_id": str(sent["id"]),
        "status_code": sent["status_code"],
        "sent_at": sent["sent_at"],
        "transport_message_id": delivery.transport_message_id,
        "delivery": delivery.as_audit_detail(),
    }
