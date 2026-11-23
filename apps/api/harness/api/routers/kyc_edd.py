"""KYC/EDD trigger routes — evaluate, reassess, complete (T248, V029)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from apps.api.harness.api.dependencies import (
    actor_from_authorization,
    get_pool,
    get_request_config,
    request_audit_context,
)
from apps.api.harness.core.idempotency_middleware import idempotent
from apps.api.harness.core.identity import same_actor
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import kyc_edd as kyc_edd_repo
from apps.api.harness.services.kyc_edd import KycTrigger, evaluate_triggers

router = APIRouter(tags=["kyc-edd"])


def _require_compliance_role(role_code: str) -> None:
    if role_code not in {"ADMIN", "WM", "BRANCH_MANAGER"}:
        raise HTTPException(status_code=403, detail="Compliance role required (ADMIN/WM/BM)")


@router.get("/kyc-edd/triggers")  # type: ignore[union-attr]
async def list_kyc_edd_triggers(
    request: Request,
    authorization: str | None = Header(default=None),
    customer_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List KYC/EDD triggers with optional customer/status filter."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    audit_ctx = request_audit_context(request)
    async with get_pool(request).acquire() as connection:
        # svc-viability-v3 B6 — role check moved inside acquire so RBAC
        # rejections can be emitted to audit_logs without changing the
        # validator signature (Option-c: pure validator + try/except wrapper).
        try:
            _require_compliance_role(actor.role_code)
        except HTTPException as exc:
            if exc.status_code == 403:
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="role_forbidden",
                    resource_type="kyc_edd_trigger",
                    resource_id=None,
                    detail={
                        "role_code": actor.role_code,
                        "rejected_for": ["ADMIN", "WM", "BRANCH_MANAGER"],
                        "endpoint_path": request.url.path,
                    },
                    **audit_ctx,
                )
            raise
        items = await kyc_edd_repo.list_kyc_edd_triggers(
            connection,
            customer_id=customer_id,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="kyc_edd_trigger_listed",
            resource_type="kyc_edd_trigger",
            resource_id=None,
            detail={
                "customer_id": customer_id,
                "status_filter": status_filter,
                "limit": limit,
                "offset": offset,
                "result_count": len(items),
            },
            **audit_ctx,
        )
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/kyc-edd/triggers/{trigger_id}")  # type: ignore[union-attr]
async def get_kyc_edd_trigger(
    request: Request,
    trigger_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Read one KYC/EDD trigger by UUID."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    audit_ctx = request_audit_context(request)
    async with get_pool(request).acquire() as connection:
        # svc-viability-v3 B6 — see list_kyc_edd_triggers for rationale.
        try:
            _require_compliance_role(actor.role_code)
        except HTTPException as exc:
            if exc.status_code == 403:
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="role_forbidden",
                    resource_type="kyc_edd_trigger",
                    resource_id=None,
                    detail={
                        "role_code": actor.role_code,
                        "rejected_for": ["ADMIN", "WM", "BRANCH_MANAGER"],
                        "endpoint_path": request.url.path,
                    },
                    **audit_ctx,
                )
            raise
        trigger = await kyc_edd_repo.get_kyc_edd_trigger(
            connection, trigger_id=str(trigger_id)
        )
        if trigger is None:
            raise HTTPException(status_code=404, detail="KYC/EDD trigger not found")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="kyc_edd_trigger_detail_viewed",
            resource_type="kyc_edd_trigger",
            resource_id=str(trigger_id),
            detail={"trigger_type": trigger.get("trigger_type")},
            **audit_ctx,
        )
    return trigger


@router.post(
    "/kyc-edd/evaluate",
    status_code=status.HTTP_201_CREATED,
)  # type: ignore[union-attr]
@idempotent
async def evaluate_and_record_triggers(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Run the KYC/EDD rule book for a customer and persist fired triggers.

    Body: {customer: {...}, recent_transactions: [...]}
    Returns list of created trigger rows.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    audit_ctx = request_audit_context(request)
    created: list[dict[str, Any]] = []

    async with get_pool(request).acquire() as connection:
        # svc-viability-v3 B6 — Path-A: role check + payload validation both
        # moved inside acquire so role 403 / payload 400 ordering is preserved
        # AND the RBAC rejection can emit a role_forbidden audit row.
        try:
            _require_compliance_role(actor.role_code)
        except HTTPException as exc:
            if exc.status_code == 403:
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="role_forbidden",
                    resource_type="kyc_edd_trigger",
                    resource_id=None,
                    detail={
                        "role_code": actor.role_code,
                        "rejected_for": ["ADMIN", "WM", "BRANCH_MANAGER"],
                        "endpoint_path": request.url.path,
                    },
                    **audit_ctx,
                )
            raise

        customer = dict(payload.get("customer") or {})
        recent_transactions = list(payload.get("recent_transactions") or [])

        fired: list[KycTrigger] = evaluate_triggers(customer, recent_transactions)
        customer_id = str(customer.get("id") or "")
        if fired and not customer_id:
            raise HTTPException(status_code=400, detail="customer.id is required")

        for t in fired:
            row = await kyc_edd_repo.insert_kyc_edd_trigger(
                connection,
                customer_id=customer_id,
                trigger_type=t.trigger_type,
                trigger_value=t.trigger_value,
            )
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="kyc_edd_triggered",
                resource_type="kyc_edd_trigger",
                resource_id=str(row["id"]),
                detail={
                    "trigger_type": t.trigger_type,
                    "rationale": t.rationale,
                    "customer_id": customer_id,
                },
                **audit_ctx,
            )
            created.append(row)

        # Wave-Audit-Defect-Fix A.21: emit kyc_edd_evaluated summary on every
        # POST regardless of whether any triggers fired — the evaluation
        # itself is the auditable event.
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="kyc_edd_evaluated",
            resource_type="kyc_edd_evaluation",
            resource_id=customer_id or None,
            detail={
                "customer_id": customer_id or None,
                "fired_count": len(fired),
                "trigger_types": [t.trigger_type for t in fired],
            },
            **audit_ctx,
        )

    return {"triggers": created, "count": len(created)}


@router.post("/kyc-edd/triggers/{trigger_id}/reassess")  # type: ignore[union-attr]
async def reassess_trigger(
    request: Request,
    trigger_id: UUID,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Accept reason_text and mark trigger IN_PROGRESS."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    audit_ctx = request_audit_context(request)

    reason_text = str(payload.get("reason_text") or "").strip()
    if not reason_text:
        raise HTTPException(status_code=400, detail="reason_text is required")

    trigger_id_text = str(trigger_id)

    async with get_pool(request).acquire() as connection:
        # svc-viability-v3 B6 — see list_kyc_edd_triggers for rationale.
        try:
            _require_compliance_role(actor.role_code)
        except HTTPException as exc:
            if exc.status_code == 403:
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="role_forbidden",
                    resource_type="kyc_edd_trigger",
                    resource_id=None,
                    detail={
                        "role_code": actor.role_code,
                        "rejected_for": ["ADMIN", "WM", "BRANCH_MANAGER"],
                        "endpoint_path": request.url.path,
                    },
                    **audit_ctx,
                )
            raise

        # svc-viability-v4 I1 (ADR-017) — transaction-wrap SELECT + UPDATE + emit.
        async with connection.transaction():
            existing = await kyc_edd_repo.get_kyc_edd_trigger(
                connection, trigger_id=trigger_id_text
            )
            if existing is None:
                raise HTTPException(
                    status_code=404, detail="trigger not found or not in OPEN status"
                )
            old_actor = existing.get("reassessor_employee_id")
            row = await kyc_edd_repo.reassess_kyc_edd_trigger(
                connection,
                trigger_id=trigger_id_text,
                reason_text=reason_text,
                previous_actor_id=str(old_actor) if old_actor is not None else None,
            )
            if row is None:
                raise HTTPException(
                    status_code=404, detail="trigger not found or not in OPEN status"
                )
            if same_actor(actor.employee_id, existing.get("previous_actor_id")):
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="same_actor_mutation_blocked",
                    resource_type="kyc_edd_trigger",
                    resource_id=trigger_id_text,
                    detail={
                        "previous_actor_id": (
                            str(existing["previous_actor_id"])
                            if existing.get("previous_actor_id") is not None
                            else None
                        ),
                        "current_actor_id": str(actor.employee_id),
                        "transition_path": "OPEN → IN_PROGRESS",
                    },
                    **audit_ctx,
                )
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="kyc_edd_reassessed",
                resource_type="kyc_edd_trigger",
                resource_id=trigger_id_text,
                detail={"status": "IN_PROGRESS", "reason_text": reason_text[:200]},
                **audit_ctx,
            )
    return row


@router.post("/kyc-edd/triggers/{trigger_id}/complete")  # type: ignore[union-attr]
async def complete_trigger(
    request: Request,
    trigger_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Mark trigger CLOSED with reassessor = calling employee."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    audit_ctx = request_audit_context(request)

    trigger_id_text = str(trigger_id)

    async with get_pool(request).acquire() as connection:
        # svc-viability-v3 B6 — see list_kyc_edd_triggers for rationale.
        try:
            _require_compliance_role(actor.role_code)
        except HTTPException as exc:
            if exc.status_code == 403:
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="role_forbidden",
                    resource_type="kyc_edd_trigger",
                    resource_id=None,
                    detail={
                        "role_code": actor.role_code,
                        "rejected_for": ["ADMIN", "WM", "BRANCH_MANAGER"],
                        "endpoint_path": request.url.path,
                    },
                    **audit_ctx,
                )
            raise

        # svc-viability-v4 I1 (ADR-017) — transaction-wrap SELECT + UPDATE + emit.
        async with connection.transaction():
            existing = await kyc_edd_repo.get_kyc_edd_trigger(
                connection, trigger_id=trigger_id_text
            )
            if existing is None:
                raise HTTPException(
                    status_code=404, detail="trigger not found or already closed"
                )
            old_actor = existing.get("reassessor_employee_id")
            row = await kyc_edd_repo.complete_kyc_edd_trigger(
                connection,
                trigger_id=trigger_id_text,
                reassessor_employee_id=actor.employee_id,
                previous_actor_id=str(old_actor) if old_actor is not None else None,
            )
            if row is None:
                raise HTTPException(
                    status_code=404, detail="trigger not found or already closed"
                )
            if same_actor(actor.employee_id, existing.get("previous_actor_id")):
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="same_actor_mutation_blocked",
                    resource_type="kyc_edd_trigger",
                    resource_id=trigger_id_text,
                    detail={
                        "previous_actor_id": (
                            str(existing["previous_actor_id"])
                            if existing.get("previous_actor_id") is not None
                            else None
                        ),
                        "current_actor_id": str(actor.employee_id),
                        "transition_path": "IN_PROGRESS → CLOSED",
                    },
                    **audit_ctx,
                )
            # Wave-Audit-Defect-Fix C2 (OQ-1): /complete previously emitted
            # kyc_edd_reassessed — same code as /reassess — making it impossible
            # to distinguish "trigger was reassessed and stays open" from "trigger
            # was closed". Split into kyc_edd_completed (V060 canonical).
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="kyc_edd_completed",
                resource_type="kyc_edd_trigger",
                resource_id=trigger_id_text,
                detail={"status": "CLOSED", "completed_by": actor.employee_id},
                **audit_ctx,
            )
    return row
