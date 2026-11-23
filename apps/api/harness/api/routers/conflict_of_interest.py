"""Conflict of interest pre-disclosure + Chinese Wall routes (T249, V030)."""

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
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import conflict_of_interest as coi_repo
from apps.api.harness.services.conflict_of_interest import (
    CHINESE_WALL_BLOCK_MESSAGE,
    check_chinese_wall,
    disclosure_from_payload,
)

router = APIRouter(tags=["conflict-of-interest"])


@router.get("/conflict-disclosures")  # type: ignore[union-attr]
async def list_conflict_disclosures(
    request: Request,
    authorization: str | None = Header(default=None),
    employee_id: str | None = None,
    customer_id: str | None = None,
    wall_violations_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List conflict disclosures. ADMIN/AUDIT_VIEWER see all; PB/WM see own."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code == "AUDIT_VIEWER":
        raise HTTPException(status_code=403, detail="Compliance role required")

    # Non-admin employees can only see their own disclosures.
    # COMPLIANCE_OFFICER is a read-only oversight role and sees all disclosures
    # (like ADMIN) for cross-employee Chinese-wall/conflict review.
    effective_employee_id = employee_id
    if actor.role_code not in {"ADMIN", "COMPLIANCE_OFFICER"} and not effective_employee_id:
        effective_employee_id = actor.employee_id

    async with get_pool(request).acquire() as connection:
        items = await coi_repo.list_conflict_disclosures(
            connection,
            employee_id=effective_employee_id,
            customer_id=customer_id,
            chinese_wall_only=True if wall_violations_only else None,
            limit=limit,
            offset=offset,
        )
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/conflict-disclosures/{disclosure_id}")  # type: ignore[union-attr]
async def get_conflict_disclosure(
    request: Request,
    disclosure_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Read one conflict disclosure by UUID."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code == "AUDIT_VIEWER":
        raise HTTPException(status_code=403, detail="Compliance role required")
    async with get_pool(request).acquire() as connection:
        row = await coi_repo.get_conflict_disclosure(
            connection, disclosure_id=str(disclosure_id)
        )
    if row is None:
        raise HTTPException(status_code=404, detail="conflict disclosure not found")
    return row


@router.post(
    "/conflict-disclosures",
    status_code=status.HTTP_201_CREATED,
)  # type: ignore[union-attr]
async def create_conflict_disclosure(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create a conflict of interest pre-disclosure.

    If ``chinese_wall_violation=true``, audits ``conflict_of_interest_blocked``
    and sets ``blocked_at``.  Downstream consultations must gate on
    ``GET /conflict-disclosures/check`` before proceeding.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code not in {"ADMIN", "PB", "WM", "BRANCH_MANAGER"}:
        raise HTTPException(status_code=403, detail="Staff role required")

    customer_id = str(payload.get("customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")

    try:
        normalised = disclosure_from_payload(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with get_pool(request).acquire() as connection:
        row = await coi_repo.insert_conflict_disclosure(
            connection,
            employee_id=actor.employee_id,
            customer_id=customer_id,
            **normalised,
        )
        action_code = (
            "conflict_of_interest_blocked"
            if normalised["chinese_wall_violation"]
            else "conflict_disclosed"
        )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code=action_code,
            resource_type="conflict_disclosure",
            resource_id=str(row["id"]),
            detail={
                "disclosure_type": normalised["disclosure_type"],
                "chinese_wall_violation": normalised["chinese_wall_violation"],
                "customer_id": customer_id,
            },
            **request_audit_context(request),
        )

    result: dict[str, Any] = dict(row)
    if normalised["chinese_wall_violation"]:
        result["block_banner"] = CHINESE_WALL_BLOCK_MESSAGE
    return result


@router.get("/conflict-disclosures/check")  # type: ignore[union-attr]
async def check_chinese_wall_gate(
    request: Request,
    authorization: str | None = Header(default=None),
    customer_id: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
) -> dict[str, Any]:
    """Check if the calling employee is Chinese-wall-blocked for a customer.

    Used as a pre-consultation gate.  Returns ``blocked=true`` and the banner
    message if a violation exists; the UI must show the block banner.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id query param is required")

    async with get_pool(request).acquire() as connection:
        result = await check_chinese_wall(
            connection,
            employee_id=actor.employee_id,
            customer_id=customer_id,
            product_id=product_id,
        )

    return {
        "blocked": result.blocked,
        "disclosure_id": result.disclosure_id,
        "message": result.message if result.blocked else None,
    }
