"""Consent routes — REG-01 신용정보법 §32/§37/§38 + T214-T217, T229.

Routes:
  POST /consents/grant              — record a consent (T214)
  POST /consents/withdraw           — withdraw a consent (T217)
  POST /consents/marketing/stop     — 연락중지 shortcut (T215, T217)
  GET  /consents/customer/{id}      — active consents (T214)
  POST /consents/general-bundle     — 일괄동의 §32+자본시장법§40 (T229)
  POST /info-access-requests        — 열람·정정 청구 (T216)
  POST /info-access-requests/{id}/respond — respond to request (T216)
"""

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
from apps.api.harness.services import consents as consents_svc

router = APIRouter(tags=["consents"])

_VALID_CONSENT_TYPES = frozenset(
    {"GENERAL_BUNDLE", "INFORMATION_USE", "MARKETING_CONTACT", "DATA_SHARING_THIRD_PARTY"}
)
_VALID_REQUEST_TYPES = frozenset({"ACCESS", "CORRECTION"})

# Statutes bundled into a 일괄동의 (T229 §32 + §40)
_GENERAL_BUNDLE_SCOPE: dict[str, Any] = {
    "statutes": [
        "자본시장법 §40",
        "신용정보법 §32",
        "신용정보법 §33",
        "금소법 §17",
        "금소법 §19",
    ],
    "purpose": (
        "자본시장법·신용정보법·금소법 의무 이행을 위한 정보 수집·이용 일괄동의 "
        "(PoC 합성 데이터 시뮬레이션)"
    ),
    "retention_years": 5,
    "third_parties": [],
    "notice": "본 동의는 합성(Synthetic) 데이터에만 적용됩니다. 실제 개인정보 없음.",
}


def _require_staff(role_code: str) -> None:
    if role_code not in {"PB", "WM", "BRANCH_MANAGER", "ADMIN"}:
        raise HTTPException(status_code=403, detail="Staff role required for consent operations")


# ── POST /consents/grant ─────────────────────────────────────────────────────

@router.post("/consents/grant", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
async def grant_consent(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Record a synthetic consent for a customer (T214, 신용정보법 §32).

    Response always carries synthetic=true for UI watermark.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_staff(actor.role_code)

    customer_id = parse_uuid_field(payload, "customer_id")
    consent_type = str(payload.get("consent_type", "")).strip()
    if consent_type not in _VALID_CONSENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"consent_type must be one of {sorted(_VALID_CONSENT_TYPES)}",
        )
    consent_scope = payload.get("consent_scope") or {}
    if not isinstance(consent_scope, dict):
        raise HTTPException(status_code=422, detail="consent_scope must be a JSON object")

    async with get_pool(request).acquire() as conn:
        result = await consents_svc.grant_consent(
            conn,
            customer_id=customer_id,
            consent_type=consent_type,
            consent_scope=consent_scope,
            employee_id=actor.employee_id,
        )
        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="consent_recorded",
            resource_type="customer_consents",
            resource_id=str(result["id"]),
            detail={"customer_id": customer_id, "consent_type": consent_type},
            **request_audit_context(request),
        )
    return result


# ── POST /consents/withdraw ──────────────────────────────────────────────────

@router.post("/consents/withdraw")  # type: ignore[union-attr]
async def withdraw_consent(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Withdraw an active consent (T217, 신용정보법 §37).

    MARKETING_CONTACT withdrawals emit marketing_consent_withdrawn for email block gate.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_staff(actor.role_code)

    customer_id = parse_uuid_field(payload, "customer_id")
    consent_type = str(payload.get("consent_type", "")).strip()
    if consent_type not in _VALID_CONSENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"consent_type must be one of {sorted(_VALID_CONSENT_TYPES)}",
        )

    action_code = (
        "marketing_consent_withdrawn"
        if consent_type == "MARKETING_CONTACT"
        else "consent_withdrawn"
    )

    async with get_pool(request).acquire() as conn:
        result = await consents_svc.withdraw_consent(
            conn, customer_id=customer_id, consent_type=consent_type
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="No active consent of that type found for this customer",
            )
        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code=action_code,
            resource_type="customer_consents",
            resource_id=str(result["id"]),
            detail={"customer_id": customer_id, "consent_type": consent_type},
            **request_audit_context(request),
        )
    return result


# ── POST /consents/marketing/stop ────────────────────────────────────────────

@router.post("/consents/marketing/stop")  # type: ignore[union-attr]
async def marketing_stop(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """연락중지청구 shortcut — withdraw MARKETING_CONTACT consent (T215, T217, §37).

    Worker-hotel coordinate: email_draft creation must check this consent before sending.
    Returns marketing_stopped=true so the caller can gate downstream email flows.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_staff(actor.role_code)

    customer_id = parse_uuid_field(payload, "customer_id")

    async with get_pool(request).acquire() as conn:
        result = await consents_svc.withdraw_consent(
            conn, customer_id=customer_id, consent_type="MARKETING_CONTACT"
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="No active MARKETING_CONTACT consent found for this customer",
            )
        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="marketing_consent_withdrawn",
            resource_type="customer_consents",
            resource_id=str(result["id"]),
            detail={
                "customer_id": customer_id,
                "stop_reason": "연락중지청구 신용정보법 §37",
                "email_block": True,
            },
            **request_audit_context(request),
        )
    return {"marketing_stopped": True, "consent": result, "synthetic": True}


# ── GET /consents/customer/{customer_id} ─────────────────────────────────────

@router.get("/consents/customer/{customer_id}")  # type: ignore[union-attr]
async def list_customer_consents(
    request: Request,
    customer_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return all active (not withdrawn) consents for a customer (T214)."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_staff(actor.role_code)

    async with get_pool(request).acquire() as conn:
        items = await consents_svc.list_active_consents(conn, customer_id=str(customer_id))
    return {"customer_id": str(customer_id), "consents": items, "synthetic": True}


# ── POST /consents/general-bundle ────────────────────────────────────────────

@router.post("/consents/general-bundle", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
async def general_bundle_consent(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """일괄동의 — records GENERAL_BUNDLE consent covering §32/§33/자본시장법§40 (T229).

    consent_scope is pre-populated with applicable statutes; caller may extend.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_staff(actor.role_code)

    customer_id = parse_uuid_field(payload, "customer_id")
    override_scope: dict[str, Any] = payload.get("consent_scope") or {}
    scope = {**_GENERAL_BUNDLE_SCOPE, **override_scope}

    async with get_pool(request).acquire() as conn:
        result = await consents_svc.grant_consent(
            conn,
            customer_id=customer_id,
            consent_type="GENERAL_BUNDLE",
            consent_scope=scope,
            employee_id=actor.employee_id,
        )
        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="general_bundle_consent",
            resource_type="customer_consents",
            resource_id=str(result["id"]),
            detail={
                "customer_id": customer_id,
                "statutes": scope.get("statutes", []),
            },
            **request_audit_context(request),
        )
    return result


# ── POST /info-access-requests ───────────────────────────────────────────────

@router.post("/info-access-requests", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
async def create_info_access_request(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """열람·정정 청구 — create ACCESS or CORRECTION request (T216, 신용정보법 §38)."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_staff(actor.role_code)

    customer_id = parse_uuid_field(payload, "customer_id")
    request_type = str(payload.get("request_type", "")).strip()
    if request_type not in _VALID_REQUEST_TYPES:
        raise HTTPException(
            status_code=422, detail="request_type must be ACCESS or CORRECTION"
        )

    async with get_pool(request).acquire() as conn:
        result = await consents_svc.create_info_access_request(
            conn,
            customer_id=customer_id,
            request_type=request_type,
            employee_id=actor.employee_id,
        )
        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="info_access_requested",
            resource_type="info_access_requests",
            resource_id=str(result["id"]),
            detail={"customer_id": customer_id, "request_type": request_type},
            **request_audit_context(request),
        )
    return result


# ── POST /info-access-requests/{id}/respond ──────────────────────────────────

@router.post("/info-access-requests/{request_id}/respond")  # type: ignore[union-attr]
async def respond_info_access_request(
    request: Request,
    request_id: UUID,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Record a staff response to an info access/correction request (T216, §38)."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_staff(actor.role_code)

    summary = str(payload.get("response_summary_redacted", "")).strip()
    if not summary:
        raise HTTPException(
            status_code=422, detail="response_summary_redacted is required"
        )

    async with get_pool(request).acquire() as conn:
        result = await consents_svc.respond_to_info_request(
            conn,
            request_id=str(request_id),
            response_summary_redacted=summary,
        )
        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Request not found or already responded",
            )
        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="info_access_responded",
            resource_type="info_access_requests",
            resource_id=str(request_id),
            detail={"responding_employee_id": actor.employee_id},
            **request_audit_context(request),
        )
    return result
