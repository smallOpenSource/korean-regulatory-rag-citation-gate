"""Consultation routes — CRUD + AI briefing + compliance-check.

Gate routes (suitability, explanation, four-gate) live in consultation_gates.py
to stay within the 500-line module containment limit.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from apps.api.harness.api.dependencies import (
    actor_from_authorization,
    get_pool,
    get_request_config,
    parse_uuid_field,
    request_audit_context,
)
from apps.api.harness.core.error_codes import ErrorCode
from apps.api.harness.core.errors import structured_http_exception
from apps.api.harness.core.idempotency_middleware import idempotent
from apps.api.harness.core.identity import same_actor
from apps.api.harness.repositories import ai as ai_repo
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import consultations as consultation_repo
from apps.api.harness.repositories import customers as customer_repo
from apps.api.harness.repositories import suitability as suitability_repo
from apps.api.harness.services.ai_jobs import ai_unavailable_payload, prompt_hash_from_payload
from apps.api.harness.services.compliance_check import run_compliance_check
from apps.api.harness.services.four_gate import aggregate_gate_result

router = APIRouter(tags=["consultations"])


def require_consultation_staff(role_code: str) -> None:
    """Allow consultation write/AI flows only for PB/WM front-office roles."""

    if role_code not in {"PB", "WM"}:
        raise HTTPException(status_code=403, detail="PB/WM role required")


@router.post("/consultations", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
@idempotent
async def create_consultation(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create a draft consultation for an accessible customer."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_consultation_staff(actor.role_code)
    customer_id = parse_uuid_field(payload, "customer_id")
    channel_code = str(payload.get("channel_code", "PHONE"))
    async with get_pool(request).acquire() as connection:
        customer = await customer_repo.get_customer(
            connection, actor=actor, customer_id=customer_id
        )
        if customer is None:
            raise HTTPException(status_code=404, detail="customer not found")
        consultation = await consultation_repo.create_consultation(
            connection,
            customer_id=customer_id,
            employee_id=actor.employee_id,
            channel_code=channel_code,
        )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="consultation_create",
            resource_type="consultation",
            resource_id=str(consultation["id"]),
            detail={"customer_id": customer_id, "channel_code": channel_code},
            **request_audit_context(request),
        )
    return consultation


@router.patch("/consultations/{consultation_id}")  # type: ignore[union-attr]
@idempotent
async def update_consultation(
    request: Request,
    consultation_id: UUID,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Update note/checklist/status while preserving completion gates."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_consultation_staff(actor.role_code)
    consultation_id_text = str(consultation_id)
    async with get_pool(request).acquire() as connection:
        existing = await consultation_repo.get_consultation_for_actor(
            connection,
            role_code=actor.role_code,
            employee_id=actor.employee_id,
            branch_id=actor.branch_id,
            consultation_id=consultation_id_text,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="consultation not found")

        # svc-viability-v4 I4 (ADR-019) — preventive 4-eye gate fires when the
        # PENDING_APPROVAL row is being COMPLETED by its own creator. Input-6
        # SKIP rule: in this preventive path the detective
        # same_actor_mutation_blocked is NOT emitted (cardinality contract:
        # exactly 1 four_eyes_violation_blocked row, zero detective row).
        if (
            existing["status_code"] == "PENDING_APPROVAL"
            and payload.get("status_code") == "COMPLETED"
            and same_actor(actor.employee_id, existing["employee_id"])
        ):
            async with connection.transaction():
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="four_eyes_violation_blocked",
                    resource_type="consultation",
                    resource_id=consultation_id_text,
                    detail={
                        "creator_id": str(existing["employee_id"]),
                        "approver_id": str(actor.employee_id),
                        "preventive_path": "PENDING_APPROVAL → COMPLETED",
                    },
                    **request_audit_context(request),
                )
            raise HTTPException(
                status_code=403,
                detail="consultation completion requires a different approver (four-eye rule)",
            )

        # svc-viability-v3 B5 — same-actor mutation invariant detective control
        # (documented carry-over; NOT transactional per ADR-017 Input-5 split).
        # Emit audit row when the consultation creator is also the actor
        # performing the PATCH on any non-preventive transition (HTTP 200
        # behavior preserved; this is an audit-only signal).
        elif same_actor(actor.employee_id, existing["employee_id"]):
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="same_actor_mutation_blocked",
                resource_type="consultation",
                resource_id=str(existing["id"]),
                detail={"original_creator_id": str(existing["employee_id"])},
                **request_audit_context(request),
            )

        # svc-viability-v4 I4 (ADR-019) — DRAFT|SAVED → PENDING_APPROVAL
        # transition records the submission event. Wrapped in its own
        # transaction so the emit + update are atomic.
        if (
            existing["status_code"] in ("DRAFT", "SAVED")
            and payload.get("status_code") == "PENDING_APPROVAL"
        ):
            async with connection.transaction():
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="consultation_submitted_for_approval",
                    resource_type="consultation",
                    resource_id=consultation_id_text,
                    detail={
                        "submitted_by_actor_id": str(actor.employee_id),
                        "transition_from": existing["status_code"],
                    },
                    **request_audit_context(request),
                )
        note_text = payload.get("note_text")
        if isinstance(note_text, str) and note_text.strip():
            await consultation_repo.add_note(
                connection,
                consultation_id=consultation_id_text,
                author_id=actor.employee_id,
                note_text=note_text.strip(),
            )
            await consultation_repo.touch_updated_at(
                connection, consultation_id=consultation_id_text
            )
        # Wave-Audit-Defect-Fix A7 (CR-7): block PATCH status_code=COMPLETED
        # until all four gates (suitability / explanation / unfair_solicitation /
        # marketing) are PASSED or ACKNOWLEDGED. Prior code accepted any payload
        # and audit-logged hardcoded ``suitability_checked: True``, masking the
        # real gate state.
        four_gate_payload: dict[str, Any] | None = None
        if payload.get("status_code") == "COMPLETED":
            gate_rows = await suitability_repo.list_gates(
                connection, consultation_id=consultation_id_text
            )
            gate_result = aggregate_gate_result(consultation_id_text, gate_rows)
            if not gate_result.all_passed:
                blocking = [
                    g.gate_name for g in gate_result.gates
                    if g.gate_status not in {"PASSED", "ACKNOWLEDGED"}
                ]
                raise structured_http_exception(
                    409,
                    ErrorCode.four_gate_not_passed,
                    "4-gate 미충족 상태에서는 상담을 종결할 수 없습니다.",
                    blocking_gates=blocking,
                )
            four_gate_payload = {
                g.gate_name: g.gate_status for g in gate_result.gates
            }

        updated = await consultation_repo.update_consultation(
            connection,
            consultation_id=consultation_id_text,
            summary=payload.get("summary"),
            suitability_checked=payload.get("suitability_checked"),
            explanation_checked=payload.get("explanation_checked"),
            status_code=payload.get("status_code"),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="consultation not updated")
        if updated["status_code"] == "COMPLETED":
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="consultation_complete",
                resource_type="consultation",
                resource_id=consultation_id_text,
                detail={"four_gate": four_gate_payload or {}},
                **request_audit_context(request),
            )
        elif (
            payload.get("status_code") is not None
            and existing.get("status_code") != updated.get("status_code")
        ):
            # Wave-Audit-Defect-Fix B10: non-COMPLETED transitions (e.g.,
            # SCHEDULED → IN_PROGRESS, IN_PROGRESS → CANCELLED) previously
            # left no audit trail — only COMPLETED was emitted. Closes the
            # gap so any status mutation is recoverable from audit_logs.
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="consultation_status_changed",
                resource_type="consultation",
                resource_id=consultation_id_text,
                detail={
                    "from": existing.get("status_code"),
                    "to": updated.get("status_code"),
                },
                **request_audit_context(request),
            )
    return updated


@router.post("/consultations/{consultation_id}/briefing", status_code=status.HTTP_202_ACCEPTED)  # type: ignore[union-attr]
async def create_consultation_briefing_job(
    request: Request,
    consultation_id: UUID,
    authorization: str | None = Header(default=None),
    dry_run: bool = Query(default=False, description="DELTA-4 test-double: skip Azure, return synthetic Korean fixture"),
) -> dict[str, Any]:
    """Create a durable consultation_briefing AI job.

    Pass ``?dry_run=true`` to activate the test-double dispatcher (DELTA-4 /
    G0a-1) — the in-process worker returns a canned Korean fixture instead of
    calling Azure. DB writes and WS broadcast are preserved; Azure SDK is
    bypassed. The dry-run path is gated by the ``WMAH_ENABLE_DRY_RUN_PROBE=1``
    environment variable so it cannot be invoked in production. The legacy
    ``Authorization: Bearer v8-synthetic-traversal-token`` shortcut was
    removed under Wave-Audit-Defect-Fix A2 (audit defect CR-3).
    """
    import os
    from apps.api.harness.services.ai_jobs_worker import (
        DRY_RUN_ENV_GATE,
        _DRY_RUN_JOB_IDS,
    )

    if dry_run and os.environ.get(DRY_RUN_ENV_GATE) != "1":
        dry_run = False

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_consultation_staff(actor.role_code)
    consultation_id_text = str(consultation_id)
    async with get_pool(request).acquire() as connection:
        existing = await consultation_repo.get_consultation_for_actor(
            connection,
            role_code=actor.role_code,
            employee_id=actor.employee_id,
            branch_id=actor.branch_id,
            consultation_id=consultation_id_text,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="consultation not found")
        job = await ai_repo.create_ai_job(
            connection,
            job_type_code="consultation_briefing",
            requested_by_id=actor.employee_id,
            resource_type="consultation",
            resource_id=consultation_id_text,
        )
        if dry_run:
            _DRY_RUN_JOB_IDS.add(str(job["id"]))
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="AI_CALL_STARTED",
            resource_type="ai_job",
            resource_id=str(job["id"]),
            detail={"agent_id": "consultation_briefing", "dry_run": dry_run},
            **request_audit_context(request),
        )
    return {"job_id": str(job["id"]), "status_code": job["status_code"], "dry_run": dry_run}


@router.post("/consultations/{consultation_id}/compliance-check")  # type: ignore[union-attr]
async def compliance_check(
    request: Request,
    consultation_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Synchronous compliance_check (Wave 6.5 US-W65-3, T265).

    Loads the consultation under the actor's row scope, runs the
    ``compliance_check`` agent through ``run_compliance_check`` (single-LLM
    + ADR-005 §2 spotlighting + output-sanitize), and persists the result
    via ``ai_repo.create_ai_output``. Failure modes (LLM error, LLM07
    leakage, Content-Safety block, JSON parse) collapse into a fail-closed
    payload that still answers the HTTP contract
    ``{passed, issues, recommendation, data_quality_notice}``. The
    ``data_quality_notice`` is the synthetic-data disclosure the service
    stamps on every path so the gate verdict is never read as a verified
    fact (P2 silent-synthetic close-out).
    """

    config = get_request_config(request)
    actor = actor_from_authorization(config, authorization)
    require_consultation_staff(actor.role_code)
    consultation_id_text = str(consultation_id)
    async with get_pool(request).acquire() as connection:
        existing = await consultation_repo.get_consultation_for_actor(
            connection,
            role_code=actor.role_code,
            employee_id=actor.employee_id,
            branch_id=actor.branch_id,
            consultation_id=consultation_id_text,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="consultation not found")

        result = await run_compliance_check(connection, consultation=existing)

        ai_output = await ai_repo.create_ai_output(
            connection,
            agent_id="compliance_check",
            model_name=result["_model"] or config.ai.azure_deployment_name,
            resource_type="consultation",
            resource_id=consultation_id_text,
            job_id=None,
            prompt_hash=prompt_hash_from_payload({"consultation_id": consultation_id_text}),
            output=result["_output_payload"],
            fail_closed_reason_code=result["_fail_closed_reason_code"],
            question_text=f"compliance_check: consultation {consultation_id_text}",
        )
        action_code = (
            "AI_CALL_FAILED" if result["_fail_closed_reason_code"] else "AI_CALL_SUCCEEDED"
        )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code=action_code,
            resource_type="ai_output",
            resource_id=str(ai_output["id"]),
            detail={
                "agent_id": "compliance_check",
                "fail_closed_reason_code": result["_fail_closed_reason_code"],
            },
            **request_audit_context(request),
        )
    return {
        "passed": result["passed"],
        "issues": result["issues"],
        "recommendation": result["recommendation"],
        # P2 silent-synthetic close-out: the service stamps this on every
        # path (success + fail-closed), so it is always a non-null string.
        "data_quality_notice": result["data_quality_notice"],
    }

