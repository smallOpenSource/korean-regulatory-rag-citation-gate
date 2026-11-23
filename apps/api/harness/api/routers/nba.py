"""NBA and aftercare routes — T17/T243 P1/P2/P3 cards + T244/T257 quarterly queue."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

logger = logging.getLogger("nba_router")

from apps.api.harness.api.dependencies import (
    actor_from_authorization,
    get_pool,
    get_request_config,
    request_audit_context,
)
from apps.api.harness.api.routers.realtime import manager as realtime_manager
from apps.api.harness.core.idempotency_middleware import idempotent
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import nba as nba_repo
from apps.api.harness.services.aftercare import aftercare_email_draft_payload, build_quarterly_queue
from apps.api.harness.services.ai.output_quality import SYNTHETIC_ADVISORY_NOTICE
from apps.api.harness.services.nba import compose_card
from apps.api.harness.services.nba_script import run_nba_script

router = APIRouter(tags=["nba"])


def require_nba_reader(role_code: str) -> None:
    """Allow NBA reads only for operational staff roles."""

    if role_code == "AUDIT_VIEWER":
        raise HTTPException(status_code=403, detail="NBA staff role required")


def require_nba_mutation_staff(role_code: str) -> None:
    """Allow NBA/aftercare mutations only for PB/WM front-office roles."""

    if role_code not in {"PB", "WM"}:
        raise HTTPException(status_code=403, detail="PB/WM role required")


def _attach_script_disclosure(item: dict[str, Any]) -> dict[str, Any]:
    """P2-1: carry the synthetic data-quality disclosure on any NBA item with a script.

    The nba_script dispatcher stamps ``data_quality_notice`` + faithfulness onto
    ``ai_outputs``, but the NBA list/detail routes return ``script_text`` straight
    from ``nba_actions`` — a separate path that bypassed that disclosure. A banker
    reading a synthetic/unverified script as a verified talking-point is exactly the
    silent-synthetic risk P2 closes, so every script-bearing NBA response carries the
    same ``SYNTHETIC_ADVISORY_NOTICE``. Mutates and returns the dict; a row with no
    ``script_text`` is left untouched.
    """
    if item.get("script_text"):
        item["script_disclosure"] = SYNTHETIC_ADVISORY_NOTICE
    return item


async def _emit_ws_broadcast_failed(
    request: Request,
    actor_id: str,
    nba_id: str,
    exc: BaseException,
) -> None:
    """Audit nba_ws_broadcast_failed (B12-followup A.22). Never raises.

    The realtime broadcast failures used to be merely logged. This emit
    persists structured evidence in audit_logs so SLO dashboards can count
    dropped real-time events without scraping app logs. Failure to emit is
    logged at ERROR but never propagated — API response stays intact.

    Phase is derived from the request URL — last path segment names the
    operation (acknowledge / complete / dismiss); the create endpoint
    (POST /nba-cards) is mapped to "create".
    """
    raw_segment = request.url.path.rstrip("/").rsplit("/", 1)[-1] or ""
    phase = "create" if raw_segment == "nba-cards" else raw_segment
    try:
        async with get_pool(request).acquire() as connection:
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor_id,
                action_code="nba_ws_broadcast_failed",
                resource_type="nba_action",
                resource_id=nba_id,
                detail={
                    "phase": phase,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:240],
                },
                **request_audit_context(request),
            )
    except Exception as audit_exc:  # noqa: BLE001 — audit emit failure is non-blocking
        logger.error(
            "nba_router: failed to emit nba_ws_broadcast_failed audit (phase=%s): %s: %s",
            phase, type(audit_exc).__name__, audit_exc,
        )


@router.get("/nba-actions")  # type: ignore[union-attr]
async def list_nba_actions(
    request: Request,
    authorization: str | None = Header(default=None),
    status_code: str | None = None,
    priority_code: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List scoped NBA actions."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_nba_reader(actor.role_code)
    async with get_pool(request).acquire() as connection:
        items = await nba_repo.list_nba_actions(
            connection,
            actor=actor,
            status_code=status_code,
            priority_code=priority_code,
            limit=limit,
            offset=offset,
        )
    return {
        "items": [_attach_script_disclosure(item) for item in items],
        "limit": limit,
        "offset": offset,
    }


@router.patch("/nba-actions/{nba_id}/status")  # type: ignore[union-attr]
@idempotent
async def update_nba_status(
    request: Request,
    nba_id: UUID,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Update an NBA status and audit DONE/DISMISSED transitions."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_nba_mutation_staff(actor.role_code)
    status_code = str(payload.get("status_code", ""))
    if status_code not in {"IN_PROGRESS", "DONE", "SNOOZED", "DISMISSED"}:
        raise HTTPException(status_code=400, detail="invalid NBA status")
    snoozed_raw = payload.get("snoozed_until")
    snoozed_until: datetime | None = None
    if snoozed_raw is not None:
        if isinstance(snoozed_raw, datetime):
            snoozed_until = snoozed_raw
        else:
            try:
                snoozed_until = datetime.fromisoformat(
                    str(snoozed_raw).replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail="snoozed_until must be ISO-8601 datetime",
                ) from exc
    async with get_pool(request).acquire() as connection:
        nba_action = await nba_repo.update_nba_status(
            connection,
            actor=actor,
            nba_id=str(nba_id),
            status_code=status_code,
            snoozed_until=snoozed_until,
        )
        if nba_action is None:
            raise HTTPException(status_code=404, detail="NBA action not found")
        if status_code in {"DONE", "DISMISSED"}:
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="nba_complete" if status_code == "DONE" else "nba_dismiss",
                resource_type="nba_action",
                resource_id=str(nba_id),
                detail={"status_code": status_code},
                **request_audit_context(request),
            )
    return _attach_script_disclosure(nba_action)


@router.post("/aftercare-events/{event_id}/resolve")  # type: ignore[union-attr]
async def resolve_aftercare_event(
    request: Request,
    event_id: UUID,
    payload: dict[str, Any] | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Resolve an aftercare event and audit it."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_nba_mutation_staff(actor.role_code)
    async with get_pool(request).acquire() as connection:
        event = await nba_repo.resolve_aftercare_event(
            connection,
            actor=actor,
            event_id=str(event_id),
            notes=(payload or {}).get("notes"),
        )
        if event is None:
            raise HTTPException(status_code=404, detail="aftercare event not found")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="aftercare_event_resolve",
            resource_type="aftercare_event",
            resource_id=str(event_id),
            detail={"status_code": "RESOLVED"},
            **request_audit_context(request),
        )
    return event


# ── T17/T243: NBA card creation with P1/P2/P3 ────────────────────────────────


@router.post(
    "/nba-cards",
    status_code=status.HTTP_201_CREATED,
)  # type: ignore[union-attr]
async def create_nba_card(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Compose and persist an NBA card from a customer + signal payload.

    Body: {customer: {...}, signal: {...}}
    Priority P1/P2/P3 computed by compose_card(); WS event broadcast on creation.
    PB/WM/ADMIN roles only.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    require_nba_mutation_staff(actor.role_code)

    customer = dict(payload.get("customer") or {})
    signal = dict(payload.get("signal") or {})

    if not customer.get("id"):
        raise HTTPException(status_code=400, detail="customer.id is required")

    card = compose_card(customer, signal)

    async with get_pool(request).acquire() as connection:
        row = await nba_repo.insert_nba_card(
            connection,
            customer_id=str(customer["id"]),
            employee_id=actor.employee_id,
            action_type_code=card.action_type_code,
            priority_code=card.priority,
            trigger_code=card.trigger_code,
            script_text=card.suggested_script_hint,
            score=card.score,
            why_link=card.why_link,
            sla_timer_seconds=card.sla_timer_seconds,
        )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="nba_card_created",
            resource_type="nba_action",
            resource_id=str(row["id"]),
            detail={
                "priority": card.priority,
                "sla_timer_seconds": card.sla_timer_seconds,
                "score": card.score,
                "trigger_code": card.trigger_code,
            },
            **request_audit_context(request),
        )

    # WS broadcast (best-effort; failures must not block HTTP response)
    try:
        pool = get_pool(request)
        await realtime_manager.broadcast(
            {
                "event_type": "nba_created",
                "payload": {
                    "id": str(row["id"]),
                    "customer_id": str(customer["id"]),
                    "priority_code": card.priority,
                    "sla_timer_seconds": card.sla_timer_seconds,
                    "trigger_code": card.trigger_code,
                    "employee_id": actor.employee_id,
                },
            },
            pool=pool,
        )
    except Exception as exc:  # noqa: BLE001 — WS broadcast never blocks API response
        # Wave-Audit-Defect-Fix B12: silent except removed — failures are now
        # logged with exception type + message so dropped real-time events
        # leave evidence for monitoring. HTTP response is still preserved.
        logger.warning(
            "nba_router: WS broadcast failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        # Wave-Audit-Defect-Fix A.22 — persist nba_ws_broadcast_failed audit row
        await _emit_ws_broadcast_failed(request, actor.employee_id, str(row["id"]), exc)

    return _attach_script_disclosure(row)


@router.post("/nba-cards/{nba_id}/acknowledge")  # type: ignore[union-attr]
async def acknowledge_nba_card(
    request: Request,
    nba_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Acknowledge an NBA card (PENDING → IN_PROGRESS) and audit it."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    require_nba_mutation_staff(actor.role_code)

    async with get_pool(request).acquire() as connection:
        row = await nba_repo.acknowledge_nba_card(
            connection, actor=actor, nba_id=str(nba_id)
        )
        if row is None:
            raise HTTPException(status_code=404, detail="NBA card not found or not PENDING")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="nba_card_acknowledged",
            resource_type="nba_action",
            resource_id=str(nba_id),
            detail={"status_code": "IN_PROGRESS"},
            **request_audit_context(request),
        )

    try:
        await realtime_manager.broadcast(
            {
                "event_type": "nba_updated",
                "payload": {
                    "id": str(nba_id),
                    "customer_id": str(row.get("customer_id") or ""),
                    "status_code": "IN_PROGRESS",
                    "employee_id": actor.employee_id,
                },
            },
            pool=get_pool(request),
        )
    except Exception as exc:  # noqa: BLE001 — WS broadcast never blocks API response
        # Wave-Audit-Defect-Fix B12: silent except removed (acknowledge).
        logger.warning(
            "nba_router: WS broadcast failed (acknowledge): %s: %s",
            type(exc).__name__,
            exc,
        )
        # Wave-Audit-Defect-Fix A.22 — persist nba_ws_broadcast_failed audit row
        await _emit_ws_broadcast_failed(request, actor.employee_id, str(row["id"]), exc)

    return _attach_script_disclosure(row)


@router.post("/nba-cards/{nba_id}/complete")  # type: ignore[union-attr]
async def complete_nba_card(
    request: Request,
    nba_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Complete an NBA card (→ DONE) and audit it."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    require_nba_mutation_staff(actor.role_code)

    async with get_pool(request).acquire() as connection:
        row = await nba_repo.complete_nba_card(
            connection, actor=actor, nba_id=str(nba_id)
        )
        if row is None:
            raise HTTPException(status_code=404, detail="NBA card not found or already closed")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="nba_card_completed",
            resource_type="nba_action",
            resource_id=str(nba_id),
            detail={"status_code": "DONE"},
            **request_audit_context(request),
        )

    try:
        await realtime_manager.broadcast(
            {
                "event_type": "nba_updated",
                "payload": {
                    "id": str(nba_id),
                    "customer_id": str(row.get("customer_id") or ""),
                    "status_code": "DONE",
                    "employee_id": actor.employee_id,
                },
            },
            pool=get_pool(request),
        )
    except Exception as exc:  # noqa: BLE001 — WS broadcast never blocks API response
        # Wave-Audit-Defect-Fix B12: silent except removed — failures are now
        # logged with exception type + message so dropped real-time events
        # leave evidence for monitoring. HTTP response is still preserved.
        logger.warning(
            "nba_router: WS broadcast failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        # Wave-Audit-Defect-Fix A.22 — persist nba_ws_broadcast_failed audit row
        await _emit_ws_broadcast_failed(request, actor.employee_id, str(row["id"]), exc)

    return _attach_script_disclosure(row)


@router.post("/nba-cards/{nba_id}/dismiss")  # type: ignore[union-attr]
async def dismiss_nba_card(
    request: Request,
    nba_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Dismiss an NBA card (→ DISMISSED) and audit it."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    require_nba_mutation_staff(actor.role_code)

    async with get_pool(request).acquire() as connection:
        row = await nba_repo.dismiss_nba_card(
            connection, actor=actor, nba_id=str(nba_id)
        )
        if row is None:
            raise HTTPException(status_code=404, detail="NBA card not found or already closed")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="nba_card_dismissed",
            resource_type="nba_action",
            resource_id=str(nba_id),
            detail={"status_code": "DISMISSED"},
            **request_audit_context(request),
        )

    try:
        await realtime_manager.broadcast(
            {
                "event_type": "nba_updated",
                "payload": {
                    "id": str(nba_id),
                    "customer_id": str(row.get("customer_id") or ""),
                    "status_code": "DISMISSED",
                    "employee_id": actor.employee_id,
                },
            },
            pool=get_pool(request),
        )
    except Exception as exc:  # noqa: BLE001 — WS broadcast never blocks API response
        # Wave-Audit-Defect-Fix B12: silent except removed — failures are now
        # logged with exception type + message so dropped real-time events
        # leave evidence for monitoring. HTTP response is still preserved.
        logger.warning(
            "nba_router: WS broadcast failed: %s: %s",
            type(exc).__name__,
            exc,
        )
        # Wave-Audit-Defect-Fix A.22 — persist nba_ws_broadcast_failed audit row
        await _emit_ws_broadcast_failed(request, actor.employee_id, str(row["id"]), exc)

    return _attach_script_disclosure(row)


# ── T244/T257: Aftercare quarterly queue ─────────────────────────────────────


@router.get("/aftercare/quarterly")  # type: ignore[union-attr]
async def list_quarterly_aftercare(
    request: Request,
    authorization: str | None = Header(default=None),
    quarter: str = Query(description="Quarter in YYYYQN format, e.g. 2025Q2"),
) -> dict[str, Any]:
    """Return aftercare tasks due in the given quarter for scoped personas."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    require_nba_reader(actor.role_code)

    async with get_pool(request).acquire() as connection:
        items = await build_quarterly_queue(connection, quarter, actor=actor)
    return {"quarter": quarter, "items": items, "count": len(items)}


@router.post("/aftercare-events/{event_id}/complete")  # type: ignore[union-attr]
async def complete_aftercare_event(
    request: Request,
    event_id: UUID,
    payload: dict[str, Any] | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Complete an aftercare event (→ COMPLETED) and optionally chain email_draft (T257)."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    require_nba_mutation_staff(actor.role_code)
    body = payload or {}
    completion_notes = str(body.get("completion_notes") or body.get("notes") or "").strip() or None
    create_email = bool(body.get("create_email_draft", False))

    async with get_pool(request).acquire() as connection:
        event = await nba_repo.close_aftercare_quarterly(
            connection,
            actor=actor,
            event_id=str(event_id),
            completion_notes=completion_notes,
        )
        if event is None:
            raise HTTPException(status_code=404, detail="aftercare event not found or already closed")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="aftercare_completed",
            resource_type="aftercare_event",
            resource_id=str(event_id),
            detail={"status_code": "COMPLETED", "create_email_draft": create_email},
            **request_audit_context(request),
        )

    result: dict[str, Any] = dict(event)
    if create_email:
        quarter_code = str(event.get("quarter_code") or body.get("quarter_code") or "")
        result["email_draft_payload"] = aftercare_email_draft_payload(
            event,
            employee_id=actor.employee_id,
            quarter_code=quarter_code,
        )
    return result


@router.post("/aftercare-events/{event_id}/skip")  # type: ignore[union-attr]
async def skip_aftercare_event(
    request: Request,
    event_id: UUID,
    payload: dict[str, Any] | None = None,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Skip an aftercare event (→ SKIPPED) and audit it."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    require_nba_mutation_staff(actor.role_code)
    completion_notes = str((payload or {}).get("reason") or "").strip() or None

    async with get_pool(request).acquire() as connection:
        event = await nba_repo.skip_aftercare_quarterly(
            connection,
            actor=actor,
            event_id=str(event_id),
            completion_notes=completion_notes,
        )
        if event is None:
            raise HTTPException(status_code=404, detail="aftercare event not found or not skippable")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="aftercare_skipped",
            resource_type="aftercare_event",
            resource_id=str(event_id),
            detail={"status_code": "SKIPPED", "reason": completion_notes},
            **request_audit_context(request),
        )
    return event


# ── NBA AI-script generation (synchronous) ───────────────────────────────────


@router.post(
    "/nba-cards/{nba_id}/generate-script",
    status_code=status.HTTP_202_ACCEPTED,
)  # type: ignore[union-attr]
async def generate_nba_script_endpoint(
    request: Request,
    nba_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Synchronously generate the conversational script for one NBA action.

    Mirrors the HouseView ``/generate-content`` shape: ADMIN-only, creates a
    matching ai_jobs row to satisfy ai_outputs.job_id FK, then dispatches the
    existing ``run_nba_script`` worker primitive in-line. On success the
    nba_actions row's script_text/script_generated_at/script_model_name are
    populated; on Azure or content-safety failure the structured ErrorCode
    response is surfaced (server logs hold the raw exception).
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code != "ADMIN":
        raise HTTPException(status_code=403, detail="ADMIN role required")

    nba_id_text = str(nba_id)
    pool = get_pool(request)
    async with pool.acquire() as connection:
        existing = await connection.fetchrow(
            "SELECT id, script_text FROM nba_actions WHERE id = $1::uuid",
            nba_id_text,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="nba_action not found")

        job_row = await connection.fetchrow(
            """
            INSERT INTO ai_jobs (
                job_type_code, status_code, requested_by_id,
                resource_type, resource_id, started_at
            )
            VALUES ('nba_script', 'RUNNING', $1::uuid, 'nba_actions', $2::uuid, now())
            RETURNING id
            """,
            actor.employee_id,
            nba_id_text,
        )
        job_id = str(job_row["id"])
        # AC23 / audit completeness: emit AI_CALL_STARTED the moment the AI call
        # starts (resource_type='ai_job', resource_id=job_id), mirroring the
        # create_ai_job routers (consultations/customers/house_views), so this
        # in-line generation leaves the same audit trail. No wrapping transaction
        # here, so it auto-commits — both the SUCCEEDED and FAILED terminal
        # outcomes therefore carry the trail (no orphan terminal ai_job).
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="AI_CALL_STARTED",
            resource_type="ai_job",
            resource_id=job_id,
            detail={"agent_id": "nba_script"},
            **request_audit_context(request),
        )

        try:
            await run_nba_script(
                connection,
                {
                    "id": job_id,
                    "resource_id": nba_id_text,
                    "resource_type": "nba_actions",
                    "dry_run": False,
                },
            )
        except Exception as exc:  # noqa: BLE001 — AI provider error → fail closed
            await connection.execute(
                "UPDATE ai_jobs SET status_code = 'FAILED', error_message = $2, finished_at = now() WHERE id = $1::uuid",
                job_id,
                f"{type(exc).__name__}: {exc}"[:1000],
            )
            logger.error(
                "nba_script: generation failed for nba_id=%s: %s: %s",
                nba_id_text,
                type(exc).__name__,
                exc,
            )
            raise HTTPException(
                status_code=502,
                detail="AI 서비스 일시 장애로 NBA 스크립트 생성을 완료하지 못했습니다.",
            ) from exc

        await connection.execute(
            "UPDATE ai_jobs SET status_code = 'SUCCEEDED', finished_at = now() WHERE id = $1::uuid",
            job_id,
        )
        updated = await connection.fetchrow(
            """
            SELECT id, customer_id, employee_id, action_type_code, priority_code,
                   status_code, trigger_code, script_text, script_generated_at,
                   script_model_name, due_date, created_at, updated_at
            FROM nba_actions WHERE id = $1::uuid
            """,
            nba_id_text,
        )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="nba_script_generated",
            resource_type="nba_action",
            resource_id=nba_id_text,
            detail={"job_id": job_id, "script_len": len(updated["script_text"] or "")},
            **request_audit_context(request),
        )

    return (
        _attach_script_disclosure(dict(updated))
        if updated is not None
        else {"id": nba_id_text}
    )
