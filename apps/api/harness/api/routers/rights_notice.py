"""Rights notice router — REG-01 T225 / 금소법 §청약철회·위법계약해지·자료요구·분쟁조정."""

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
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import rights_notice as rights_notice_repo
from apps.api.harness.services.rights_notice import build_rights_notice

router = APIRouter(tags=["rights-notice"])


@router.post("/rights-notice", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
async def issue_rights_notice(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Issue statutory investor rights notice at consultation end (REG-01 T225, T250).

    Issues all four notice kinds:
    - 청약철회권 (7d)
    - 위법계약해지권 (1y/5y)
    - 자료요구권 (30d)
    - 분쟁조정신청권 (30d)
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    consultation_id = parse_uuid_field(payload, "consultation_id")
    customer_id = parse_uuid_field(payload, "customer_id")

    notice_result = build_rights_notice(
        consultation_id=consultation_id,
        customer_id=customer_id,
        employee_id=actor.employee_id,
    )

    async with get_pool(request).acquire() as connection:
        notice = await rights_notice_repo.insert_rights_notice(
            connection,
            consultation_id=consultation_id,
            customer_id=customer_id,
            employee_id=actor.employee_id,
            notice_kinds=notice_result.notice_kinds,
        )

        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="rights_notice_issued",
            resource_type="rights_notice",
            resource_id=str(notice["id"]),
            detail={
                "consultation_id": consultation_id,
                "customer_id": customer_id,
                "kinds": [k["kind_code"] for k in notice_result.notice_kinds],
            },
            **request_audit_context(request),
        )

    return {
        "notice_id": str(notice["id"]),
        "consultation_id": consultation_id,
        "customer_id": customer_id,
        "issued_at": notice["issued_at"].isoformat() if notice.get("issued_at") else None,
        "notice_kinds": notice_result.notice_kinds,
    }


@router.get("/rights-notice")  # type: ignore[union-attr]
async def list_rights_notices(
    request: Request,
    customer_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """List rights notices issued to a customer."""
    actor_from_authorization(get_request_config(request), authorization)

    async with get_pool(request).acquire() as connection:
        notices = await rights_notice_repo.list_rights_notices(
            connection, customer_id=customer_id
        )

    return {"customer_id": customer_id, "notices": notices, "total": len(notices)}


@router.post("/rights-notice/acknowledge", status_code=status.HTTP_202_ACCEPTED)  # type: ignore[union-attr]
async def acknowledge_rights_notice(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Record PB acknowledgement of the four-rights notice (REG-01 T225 / C6).

    Closes Wave-Audit-Defect-Fix C6: the RightsNoticePage previously had a
    stub setTimeout instead of a real POST, so the acknowledgement event was
    invisible in audit. This endpoint emits ``rights_notice_acknowledged``
    (canonical V058) so the post-acknowledgement audit row pairs with the
    earlier ``rights_notice_issued`` (V022) row.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    consultation_id = parse_uuid_field(payload, "consultation_id")

    async with get_pool(request).acquire() as connection:
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="rights_notice_acknowledged",
            resource_type="consultation",
            resource_id=consultation_id,
            detail={
                "consultation_id": consultation_id,
                "ack_method": "ui_checkbox",
            },
            **request_audit_context(request),
        )

    return {
        "consultation_id": consultation_id,
        "status": "acknowledged",
    }
