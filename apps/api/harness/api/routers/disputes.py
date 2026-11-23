"""Dispute cases router — REG-01 T226 / 금소법 §36 분쟁조정 30-day scaffold."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from apps.api.harness.api.dependencies import (
    actor_from_authorization,
    get_pool,
    get_request_config,
    parse_uuid_field,
    request_audit_context,
)
from apps.api.harness.core.identity import same_actor
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import disputes as disputes_repo
from apps.api.harness.services.disputes import validate_dispute_open, validate_dispute_resolve

router = APIRouter(tags=["disputes"])


# Wave-Audit-Defect-Fix C7: role gating helpers. The dispute endpoints had no
# role gate beyond authentication, so any staff member (including AUDIT_VIEWER)
# could open / update / list disputes — a regulatory audit defect for REG-01
# §36 분쟁조정. Write paths now require front-office consultation roles + ADMIN;
# the read path remains open to all staff including AUDIT_VIEWER for review.
_DISPUTE_WRITE_ROLES = {"PB", "WM", "ADMIN"}
_DISPUTE_READ_ROLES = {"PB", "WM", "ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"}


def _require_dispute_write_role(role_code: str) -> None:
    if role_code not in _DISPUTE_WRITE_ROLES:
        raise HTTPException(
            status_code=403,
            detail="PB/WM/ADMIN role required for dispute mutations",
        )


def _require_dispute_read_role(role_code: str) -> None:
    if role_code not in _DISPUTE_READ_ROLES:
        raise HTTPException(
            status_code=403,
            detail="staff role required for dispute reads",
        )


@router.post("/disputes", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
async def open_dispute_case(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Open a dispute case with 30-day response timer (REG-01 T226, T251).

    The ``response_due_at`` column is generated automatically (opened_at + 30 days).
    APScheduler expiry wiring is deferred to Stage 7 RUN-09.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_dispute_write_role(actor.role_code)
    customer_id = parse_uuid_field(payload, "customer_id")
    consultation_id = parse_uuid_field(payload, "consultation_id")

    validated = validate_dispute_open(payload)

    async with get_pool(request).acquire() as connection:
        dispute = await disputes_repo.insert_dispute_case(
            connection,
            customer_id=customer_id,
            consultation_id=consultation_id,
            employee_id=actor.employee_id,
            dispute_type=validated.dispute_type,
        )

        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="dispute_case_opened",
            resource_type="dispute_case",
            resource_id=str(dispute["id"]),
            detail={
                "customer_id": customer_id,
                "consultation_id": consultation_id,
                "dispute_type": validated.dispute_type,
                "response_window_days": validated.response_window_days,
                "note": validated.note,
            },
            **request_audit_context(request),
        )

    return {
        "dispute_id": str(dispute["id"]),
        "customer_id": customer_id,
        "consultation_id": consultation_id,
        "dispute_type": validated.dispute_type,
        "status": "OPEN",
        "response_due_at": (
            dispute["response_due_at"].isoformat()
            if dispute.get("response_due_at") else None
        ),
        "timer_note": validated.note,
    }


@router.get("/disputes")  # type: ignore[union-attr]
async def list_dispute_cases(
    request: Request,
    customer_id: str | None = None,
    dispute_status: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """List dispute cases with optional customer/status filters."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_dispute_read_role(actor.role_code)

    async with get_pool(request).acquire() as connection:
        disputes = await disputes_repo.list_disputes(
            connection,
            customer_id=customer_id,
            status=dispute_status,
        )

    return {"disputes": disputes, "total": len(disputes)}


@router.patch("/disputes/{dispute_id}")  # type: ignore[union-attr]
async def update_dispute_status(
    request: Request,
    dispute_id: UUID,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Update dispute status (RESPONDED | RESOLVED) and emit audit (REG-01 T226).

    Wave-Audit-Defect-Fix C7: role gate added (PB/WM/ADMIN write); RESPONDED
    transitions now emit canonical dispute_responded (V059) — previously only
    RESOLVED emitted, leaving the OPEN→RESPONDED step invisible in audit.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_dispute_write_role(actor.role_code)
    new_status = validate_dispute_resolve(payload)
    dispute_id_text = str(dispute_id)
    audit_ctx = request_audit_context(request)

    async with get_pool(request).acquire() as connection:
        # svc-viability follow-up — the same-actor four-eye on RESPONDED→RESOLVED
        # is now PREVENTIVE (it was previously audit-only, so a responder could
        # resolve their own dispute). We read the prior responder first; on a
        # same-actor resolve we emit the forensic marker (autocommit, OUTSIDE the
        # mutation transaction so the row survives the 403) and reject with 403
        # WITHOUT mutating. The mutation path stays transaction-wrapped (ADR-017).
        # EXPIRED is APScheduler-driven (F-V5-8) and excluded by
        # services/disputes.validate_dispute_resolve (RESOLVED|RESPONDED only).
        existing = await disputes_repo.get_dispute_case(
            connection, dispute_id=dispute_id_text
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="dispute case not found")

        previous_actor_id: str | None
        if new_status == "RESOLVED":
            # RESPONDED → RESOLVED transition; previous actor is the responder.
            prior = existing.get("responded_by_actor_id")
            previous_actor_id = str(prior) if prior is not None else None
        else:
            # OPEN → RESPONDED transition; there is no prior actor on the row.
            previous_actor_id = None

        if same_actor(actor.employee_id, previous_actor_id):
            # Emit the marker BEFORE the 403. This runs in autocommit (no open
            # transaction), so the forensic row persists even though we reject
            # the mutation — and no UPDATE runs, so the responder cannot resolve
            # their own dispute.
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="same_actor_mutation_blocked",
                resource_type="dispute_case",
                resource_id=dispute_id_text,
                detail={
                    "previous_actor_id": previous_actor_id,
                    "transition_to": new_status,
                },
                **audit_ctx,
            )
            raise HTTPException(
                status_code=403,
                detail=(
                    "dispute resolution requires a different actor than the "
                    "responder (four-eye rule)"
                ),
            )

        async with connection.transaction():
            updated = await disputes_repo.update_dispute_status(
                connection,
                dispute_id=dispute_id_text,
                new_status=new_status,
                actor_id=str(actor.employee_id),
            )
            if updated is None:
                raise HTTPException(status_code=404, detail="dispute case not found")

            if new_status == "RESPONDED":
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="dispute_responded",
                    resource_type="dispute_case",
                    resource_id=dispute_id_text,
                    detail={"new_status": new_status},
                    **audit_ctx,
                )
            elif new_status == "RESOLVED":
                # ADR-021 Phase 2: the resolver (actor) is guaranteed distinct from
                # the responder by the same-actor 4-eye block above, so record the
                # responder as the human-reviewer counterpart. This lets the SoD
                # evidence pack (Bucket B) confirm a distinct second person resolved
                # the case. previous_actor_id is str|None (None if responder unknown).
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="dispute_case_resolved",
                    resource_type="dispute_case",
                    resource_id=dispute_id_text,
                    detail={
                        "new_status": new_status,
                        "human_reviewer": previous_actor_id,
                    },
                    **audit_ctx,
                )

    return {
        "dispute_id": dispute_id_text,
        "status": updated["status"],
        "responded_at": (
            updated["responded_at"].isoformat() if updated.get("responded_at") else None
        ),
        "resolved_at": (
            updated["resolved_at"].isoformat() if updated.get("resolved_at") else None
        ),
    }


@router.post("/disputes/seed-synthetic", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
async def seed_synthetic_disputes(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Insert one demo dispute case per synthetic family persona (PoC data seeding)."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code not in {"ADMIN"}:
        raise HTTPException(status_code=403, detail="ADMIN role required for seeding")

    async with get_pool(request).acquire() as connection:
        await disputes_repo.seed_synthetic_dispute(connection)

    return {"seeded": True, "note": "1 synthetic dispute per persona inserted where missing."}
