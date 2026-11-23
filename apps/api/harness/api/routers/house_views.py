"""House view routes — T16 DRAFT→GENERATED→REVIEWED→ACTIVATED→ARCHIVED lifecycle."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from apps.api.harness.api.dependencies import (
    actor_from_authorization,
    get_pool,
    get_request_config,
    request_audit_context,
)
from apps.api.harness.core.error_codes import ErrorCode
from apps.api.harness.core.errors import structured_http_exception
from apps.api.harness.core.idempotency_middleware import idempotent
from apps.api.harness.core.identity import same_actor
from apps.api.harness.repositories import ai as ai_repo
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import house_views as house_repo
from apps.api.harness.services.house_view import (
    attach_house_view_quality,
    generate_house_view_content,
)

logger = logging.getLogger("house_views_router")

router = APIRouter(tags=["house-views"])


@router.get("/house-views")  # type: ignore[union-attr]
async def list_house_views(
    request: Request,
    authorization: str | None = Header(default=None),
    status_code: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    include_test_fixtures: bool = Query(default=False),
) -> dict[str, Any]:
    """List house views.

    Test fixtures (GOLDEN_TEST / RALPH / Synthetic boundary etc.) are hidden by
    default from front-office staff. ADMIN and AUDIT_VIEWER roles may opt in
    via ?include_test_fixtures=true.
    """

    actor = actor_from_authorization(get_request_config(request), authorization)
    show_fixtures = bool(include_test_fixtures) and actor.role_code in {"ADMIN", "AUDIT_VIEWER"}
    async with get_pool(request).acquire() as connection:
        items = await house_repo.list_house_views(
            connection,
            status_code=status_code,
            limit=limit,
            offset=offset,
            include_test_fixtures=show_fixtures,
        )
    return {
        "items": [attach_house_view_quality(item) for item in items],
        "limit": limit,
        "offset": offset,
    }


@router.get("/house-views/{house_view_id}")  # type: ignore[union-attr]
async def get_house_view(
    request: Request,
    house_view_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Read one house view by UUID."""

    actor_from_authorization(get_request_config(request), authorization)
    async with get_pool(request).acquire() as connection:
        house_view = await house_repo.get_house_view(
            connection, house_view_id=str(house_view_id)
        )
    if house_view is None:
        raise HTTPException(status_code=404, detail="house view not found")
    return attach_house_view_quality(house_view)


@router.post("/house-views", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
@idempotent
async def create_house_view(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create a draft house view; ADMIN only."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code != "ADMIN":
        raise HTTPException(status_code=403, detail="ADMIN role required")
    async with get_pool(request).acquire() as connection:
        house_view = await house_repo.create_house_view(
            connection,
            period_code=str(payload.get("period_code", "MVP")),
            title=str(payload.get("title", "Draft house view")),
            summary=str(payload.get("summary", "Draft")),
            created_by_id=actor.employee_id,
            asset_views=payload.get("asset_views_json") or {},
            model_portfolios=payload.get("model_portfolios_json") or {},
            risks=payload.get("risks_json") or {},
        )
        # Wave-Audit-Defect-Fix B11: DRAFT lifecycle event was unaudited —
        # only generate / review / activate emitted audit rows so the DRAFT
        # → who-created-this-and-when trail was missing. Canonical at
        # core/audit.py:44 (house_view_drafted).
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="house_view_drafted",
            resource_type="house_view",
            resource_id=str(house_view["id"]),
            detail={
                "period_code": house_view.get("period_code"),
                "title": house_view.get("title"),
            },
            **request_audit_context(request),
        )
    return attach_house_view_quality(house_view)


@router.post("/house-views/{house_view_id}/generate", status_code=status.HTTP_202_ACCEPTED)  # type: ignore[union-attr]
async def generate_house_view(
    request: Request,
    house_view_id: UUID,
    authorization: str | None = Header(default=None),
    dry_run: bool = Query(default=False, description="DELTA-4 test-double: accept param (house_view_generation not in dry-run dispatcher set)"),
) -> dict[str, Any]:
    """Create a durable house_view_generation AI job."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code != "ADMIN":
        raise HTTPException(status_code=403, detail="ADMIN role required")
    house_view_id_text = str(house_view_id)
    audit_ctx = request_audit_context(request)
    async with get_pool(request).acquire() as connection:
        # svc-viability-v4 I2 (ADR-018) — transaction-wrap so the previous
        # generator lookup sees the prior ai_jobs row deterministically and
        # the cross-admin audit emit is atomic with the AI job INSERT.
        async with connection.transaction():
            house_view = await house_repo.get_house_view(
                connection, house_view_id=house_view_id_text
            )
            if house_view is None:
                raise HTTPException(status_code=404, detail="house view not found")
            job = await ai_repo.create_ai_job(
                connection,
                job_type_code="house_view_generation",
                requested_by_id=actor.employee_id,
                resource_type="house_view",
                resource_id=house_view_id_text,
            )
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="AI_CALL_STARTED",
                resource_type="ai_job",
                resource_id=str(job["id"]),
                detail={"agent_id": "house_view_generation"},
                **audit_ctx,
            )
            previous_actor_id = await ai_repo.get_previous_house_view_generator(
                connection, house_view_id=house_view_id_text
            )
            if previous_actor_id is not None and not same_actor(
                actor.employee_id, previous_actor_id
            ):
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="house_view_regenerated_by_admin",
                    resource_type="house_view",
                    resource_id=house_view_id_text,
                    detail={
                        "previous_generated_by_actor_id": str(previous_actor_id),
                        "current_actor_id": str(actor.employee_id),
                        "ai_job_id": str(job["id"]),
                    },
                    **audit_ctx,
                )
    return {"job_id": str(job["id"]), "status_code": job["status_code"]}


@router.post("/house-views/{house_view_id}/activate")  # type: ignore[union-attr]
@idempotent
async def activate_house_view(
    request: Request,
    house_view_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Activate a house view and write required audit log; ADMIN only."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code != "ADMIN":
        raise HTTPException(status_code=403, detail="ADMIN role required")
    house_view_id_text = str(house_view_id)
    async with get_pool(request).acquire() as connection:
        try:
            house_view = await house_repo.activate_house_view(
                connection, house_view_id=house_view_id_text
            )
        except house_repo.SingleLiveHouseViewViolation as exc:
            # Canonical single-global-live-view invariant (ADR-020): activation
            # would expose >1 live view. Rolled back; surface as 409.
            # ADR-020 F2: the activation tx already rolled back, so write the
            # refusal audit row on a fresh transaction — it must persist as an
            # append-only ledger entry even though the activation did not.
            async with connection.transaction():
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="house_view_activation_blocked",
                    resource_type="house_view",
                    resource_id=house_view_id_text,
                    detail={"reason": "single_live_invariant", "endpoint": "activate"},
                    **request_audit_context(request),
                )
            raise structured_http_exception(
                409,
                ErrorCode.house_view_single_live_invariant,
                "activation would leave more than one live house view",
            ) from exc
        if house_view is None:
            raise HTTPException(status_code=404, detail="activatable house view not found")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="house_view_activate",
            resource_type="house_view",
            resource_id=house_view_id_text,
            detail={"version_no": house_view["version_no"]},
            **request_audit_context(request),
        )
    return attach_house_view_quality(house_view)


# ── T16 lifecycle: DRAFT→GENERATED→REVIEWED→ACTIVATED→ARCHIVED ───────────────


@router.post(
    "/house-views/{house_view_id}/generate-content",
    status_code=status.HTTP_202_ACCEPTED,
)  # type: ignore[union-attr]
async def generate_house_view_content_endpoint(
    request: Request,
    house_view_id: UUID,
    payload: dict[str, Any] | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Call Azure GPT5 synchronously, persist generation metadata, advance to GENERATED.

    Body (optional): {market_data_summary, previous_house_view_summary}
    ADMIN only — transitions DRAFT → GENERATED.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code != "ADMIN":
        raise HTTPException(status_code=403, detail="ADMIN role required")

    config = get_request_config(request)
    body = payload or {}
    house_view_id_text = str(house_view_id)

    async with get_pool(request).acquire() as connection:
        hv = await house_repo.get_house_view(connection, house_view_id=house_view_id_text)
    if hv is None:
        raise HTTPException(status_code=404, detail="house view not found")
    if hv.get("status_code") != "DRAFT":
        raise HTTPException(status_code=409, detail="house view must be in DRAFT status")

    try:
        result = await generate_house_view_content(
            market=hv.get("market"),
            asset_class=hv.get("asset_class"),
            region=hv.get("region"),
            market_data_summary=str(body.get("market_data_summary") or ""),
            previous_house_view_summary=str(body.get("previous_house_view_summary") or ""),
            deployment_name=config.ai.azure_deployment_name,
        )
    except Exception as exc:  # noqa: BLE001 — AI provider error → fail closed
        # Wave-Audit-Defect-Fix A4: mask Azure stack trace from the client
        # (audit defect CR-4 — raw exception leak via HTTPException.detail).
        # The raw exception is logged server-side for debugging; the response
        # uses a structured ErrorCode so clients cannot exfiltrate provider
        # internals. B2 will swap ``service_unavailable`` for the more
        # specific ``external_provider_error`` once that enum entry lands.
        logger.error(
            "house_views: Azure generation failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        raise structured_http_exception(
            502,
            ErrorCode.external_provider_error,
            "AI 서비스 일시 장애로 하우스뷰 생성을 완료하지 못했습니다.",
        ) from exc

    async with get_pool(request).acquire() as connection:
        updated = await house_repo.advance_to_generated(
            connection,
            house_view_id=house_view_id_text,
            generated_at=result.generated_at,
            model_name=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            inputs_hash=result.inputs_hash,
            content=result.content,
            fail_closed_reason_code=result.fail_closed_reason_code,
            faithfulness=result.faithfulness,
        )
        if updated is None:
            raise HTTPException(status_code=409, detail="advance to GENERATED failed")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="house_view_generated",
            resource_type="house_view",
            resource_id=house_view_id_text,
            detail={
                "model": result.model,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "inputs_hash": result.inputs_hash,
                "fail_closed_reason_code": result.fail_closed_reason_code,
            },
            **request_audit_context(request),
        )
    return attach_house_view_quality(updated)


@router.post("/house-views/{house_view_id}/review")  # type: ignore[union-attr]
@idempotent
async def review_house_view(
    request: Request,
    house_view_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Advance house view GENERATED → REVIEWED (reviewer approval); ADMIN only."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code != "ADMIN":
        raise HTTPException(status_code=403, detail="ADMIN role required")
    house_view_id_text = str(house_view_id)

    async with get_pool(request).acquire() as connection:
        updated = await house_repo.advance_to_reviewed(
            connection, house_view_id=house_view_id_text
        )
        if updated is None:
            raise HTTPException(
                status_code=404, detail="house view not found or not in GENERATED status"
            )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="house_view_reviewed",
            resource_type="house_view",
            resource_id=house_view_id_text,
            detail={"version_no": updated.get("version_no")},
            **request_audit_context(request),
        )
    return attach_house_view_quality(updated)


@router.post("/house-views/{house_view_id}/activate-lifecycle")  # type: ignore[union-attr]
@idempotent
async def activate_lifecycle_house_view(
    request: Request,
    house_view_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Advance REVIEWED → ACTIVATED; archives previous ACTIVATED for same market tuple.

    Enforces at most one ACTIVATED view per (market, asset_class, region).
    ADMIN only.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code != "ADMIN":
        raise HTTPException(status_code=403, detail="ADMIN role required")
    house_view_id_text = str(house_view_id)

    async with get_pool(request).acquire() as connection:
        try:
            updated = await house_repo.activate_lifecycle_house_view(
                connection, house_view_id=house_view_id_text
            )
        except house_repo.SingleLiveHouseViewViolation as exc:
            # Canonical single-global-live-view invariant (ADR-020): a per-tuple
            # ACTIVATED would survive next to a different-tuple live view. Rolled
            # back; surface as 409 (legacy↔lifecycle mutual exclusivity).
            # ADR-020 F2: append-only refusal ledger entry on a fresh transaction.
            async with connection.transaction():
                await audit_repo.insert_audit_log(
                    connection,
                    actor_id=actor.employee_id,
                    action_code="house_view_activation_blocked",
                    resource_type="house_view",
                    resource_id=house_view_id_text,
                    detail={"reason": "single_live_invariant", "endpoint": "activate-lifecycle"},
                    **request_audit_context(request),
                )
            raise structured_http_exception(
                409,
                ErrorCode.house_view_single_live_invariant,
                "activation would leave more than one live house view",
            ) from exc
        if updated is None:
            raise HTTPException(
                status_code=404, detail="house view not found or not in REVIEWED status"
            )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="house_view_activated",
            resource_type="house_view",
            resource_id=house_view_id_text,
            detail={
                "version_no": updated.get("version_no"),
                "market": updated.get("market"),
                "asset_class": updated.get("asset_class"),
                "region": updated.get("region"),
            },
            **request_audit_context(request),
        )
    return attach_house_view_quality(updated)
