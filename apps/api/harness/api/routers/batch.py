"""Batch status routes."""

from __future__ import annotations

from typing import Any

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request

from apps.api.harness.api.dependencies import actor_from_authorization, get_pool, get_request_config, request_audit_context
from apps.api.harness.core.logging import summarize_db_error
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import batch as batch_repo
from apps.api.harness.repositories import readiness as readiness_repo
from apps.api.harness.services.readiness import (
    BLOCKED,
    DEGRADED,
    READY,
    build_provider_mode_payload,
)

# English admin/debug copy that legacy rows persist verbatim. Keep the keys
# verbatim — the same English strings are still emitted at write time (and
# classified by `provider_status_from_batch_log` via substring match) but get
# rewritten to Korean only at the admin surface so future-proofing the
# classifier and the UI surface evolve independently.
LEGACY_ADMIN_MESSAGE_TRANSLATIONS: dict[str, str] = {
    "PYKRX returned no persisted rows": "PYKRX 보조 출처가 적재 가능한 행을 반환하지 않았습니다.",
    "Official KRX returned no universe rows": "공식 KRX가 유니버스 종목 행을 반환하지 않았습니다.",
    "Official KRX returned no member rows": "공식 KRX가 유니버스 구성 종목 행을 반환하지 않았습니다.",
    "Official KRX returned no persisted rows": "공식 KRX가 적재 가능한 행을 반환하지 않았습니다.",
    "KRX collector is disabled; set HARNESS_BATCH_KRX_ENABLED=true": "KRX 수집기가 비활성화되어 있습니다. 관리자 환경 변수 HARNESS_BATCH_KRX_ENABLED=true 를 설정하세요.",
}


def _sanitize_admin_message(value: str | None) -> str | None:
    """Translate legacy English copy and strip PG raw row dumps."""

    if not isinstance(value, str) or not value:
        return value
    mapped = LEGACY_ADMIN_MESSAGE_TRANSLATIONS.get(value)
    if mapped is not None:
        return mapped
    return summarize_db_error(value)


def _sanitize_batch_status_items(items: list[dict[str, Any]]) -> None:
    """Sanitize admin /batch payload in place.

    Applied at read time so already-persisted batch_jobs and provider
    evidence rows don't leak `Failing row contains (...)` microsecond
    timestamps or pre-translation English literals onto the admin surface.
    """

    for item in items:
        item["error_message"] = _sanitize_admin_message(item.get("error_message"))
        for evidence in item.get("provider_evidence") or []:
            evidence["reason_message"] = _sanitize_admin_message(
                evidence.get("reason_message")
            )

router = APIRouter(tags=["batch"])


@router.get("/batch/status")  # type: ignore[union-attr]
async def list_batch_status(
    request: Request,
    authorization: str | None = Header(default=None),
    status_code: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List recent batch status; ADMIN only."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code != "ADMIN":
        raise HTTPException(status_code=403, detail="ADMIN role required")
    async with get_pool(request).acquire() as connection:
        items = await batch_repo.list_batch_status(
            connection,
            status_code=status_code,
            limit=limit,
            offset=offset,
        )
    _sanitize_batch_status_items(items)
    provider_mode = build_provider_mode_payload()
    provider_log_problem_count = sum(
        1
        for item in items
        if not item.get("provider_evidence")
        and str(item.get("job_type_code", "")).startswith("PROVIDER_")
        and item.get("status_code") in {"FAILED", "SKIPPED"}
    )
    provider_detail_problem_count = sum(
        1
        for item in items
        for evidence in item.get("provider_evidence", [])
        if evidence.get("provider_status_code") != "PROVIDER_DONE"
    )
    provider_problem_count = provider_log_problem_count + provider_detail_problem_count
    provider_status_code = (
        BLOCKED
        if provider_mode["strict_external"] and provider_problem_count
        else DEGRADED
        if provider_problem_count or not provider_mode["strict_external"]
        else READY
    )
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "provider_mode": {
            **provider_mode,
            "status_code": provider_status_code,
            "problem_count": provider_problem_count,
        },
    }


@router.get("/document-chunks")  # type: ignore[union-attr]
async def list_document_chunks(
    request: Request,
    authorization: str | None = Header(default=None),
    quarantine_flag: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List document chunks flagged for quarantine (ADMIN only). REG-04 T243 V032."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code != "ADMIN":
        raise HTTPException(status_code=403, detail="ADMIN role required")
    async with get_pool(request).acquire() as connection:
        if quarantine_flag:
            items = await batch_repo.list_quarantine_chunks(connection, limit=limit, offset=offset)
            metrics = await batch_repo.get_quarantine_metrics(connection)
        else:
            items = []
            metrics = {}
    return {"items": items, "limit": limit, "offset": offset, "quarantine_metrics": metrics}


@router.post("/document-chunks/{chunk_id}/release")  # type: ignore[union-attr]
async def release_document_chunk(
    request: Request,
    chunk_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Release a quarantined chunk (ADMIN only). Writes quarantine_released audit event."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    if actor.role_code != "ADMIN":
        raise HTTPException(status_code=403, detail="ADMIN role required")
    async with get_pool(request).acquire() as connection:
        row = await batch_repo.release_quarantine_chunk(connection, chunk_id=str(chunk_id))
        if row is None:
            raise HTTPException(status_code=404, detail="quarantine chunk not found or already released")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="quarantine_released",
            resource_type="document_chunk",
            resource_id=str(chunk_id),
            detail={
                "chunk_id": str(chunk_id),
                "quarantine_reason_code": row.get("quarantine_reason_code"),
            },
            **request_audit_context(request),
        )
    return row


@router.get("/data/readiness")  # type: ignore[union-attr]
async def get_data_readiness(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return data readiness for API/Web/E2E workflows."""

    actor_from_authorization(get_request_config(request), authorization)
    async with get_pool(request).acquire() as connection:
        return await readiness_repo.get_data_readiness(connection)
