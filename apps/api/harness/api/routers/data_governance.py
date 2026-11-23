"""Data governance routes — 신용정보법 §37/§40-2/§20-2 (T217, T218, T219).

Routes:
  POST /data-governance/purge-schedule   — §20-2 파기 schedule placeholder (T219)
  GET  /data-governance/purge-schedule   — list purge schedules
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status

from apps.api.harness.api.dependencies import (
    actor_from_authorization,
    get_pool,
    get_request_config,
    parse_uuid_field,
    request_audit_context,
)
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.services import credit_info_purge as purge_svc
from apps.api.harness.services.pseudonymization import PSEUDONYM_LABEL, REIDENTIFICATION_RISK_NOTE

router = APIRouter(prefix="/data-governance", tags=["data-governance"])


def _require_admin_or_branch(role_code: str) -> None:
    """Only BRANCH_MANAGER or ADMIN may schedule purges."""
    if role_code not in {"BRANCH_MANAGER", "ADMIN"}:
        raise HTTPException(
            status_code=403,
            detail="BRANCH_MANAGER or ADMIN role required for data governance operations",
        )


# ── POST /data-governance/purge-schedule ────────────────────────────────────

@router.post("/purge-schedule", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
async def create_purge_schedule(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """신용정보법 §20-2 파기 placeholder — schedule purge 5 years from now (T219).

    Actual deletion is Stage 7 runbook scope. PoC records intent + audits.
    Response always includes synthetic=true.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_admin_or_branch(actor.role_code)

    customer_id = parse_uuid_field(payload, "customer_id")
    target_table = str(payload.get("target_table", "")).strip()
    target_row_id = parse_uuid_field(payload, "target_row_id")
    reason = str(payload.get("reason", "상거래 종료 5년 경과 (신용정보법 §20-2)")).strip()

    if not target_table:
        raise HTTPException(status_code=422, detail="target_table is required")

    async with get_pool(request).acquire() as conn:
        result = await purge_svc.schedule_purge(
            conn,
            target_table=target_table,
            target_row_id=target_row_id,
            reason=reason,
        )
        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="credit_info_purge_simulated",
            resource_type="data_purge_schedules",
            resource_id=str(result["id"]),
            detail=json.loads(
                json.dumps(
                    {
                        "customer_id_hash": customer_id[:8] + "****",  # partial for audit
                        "purge_due_at": result.get("purge_due_at"),
                        "reason": reason,
                        "target_table": target_table,
                        "poc_note": "Actual deletion deferred to Stage 7 runbook",
                    },
                    ensure_ascii=False,
                )
            ),
            **request_audit_context(request),
        )
    return result


# ── GET /data-governance/purge-schedule ──────────────────────────────────────

@router.get("/purge-schedule")  # type: ignore[union-attr]
async def list_purge_schedules(
    request: Request,
    target_row_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """List purge schedule rows (BRANCH_MANAGER / ADMIN only)."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_admin_or_branch(actor.role_code)

    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be 1-200")

    async with get_pool(request).acquire() as conn:
        items = await purge_svc.list_purge_schedules(
            conn,
            target_row_id=target_row_id,
            limit=limit,
            offset=offset,
        )
    return {"items": items, "count": len(items), "synthetic": True}


# ── GET /data-governance/pseudonym-metadata ──────────────────────────────────

@router.get("/pseudonym-metadata")  # type: ignore[union-attr]
async def pseudonym_metadata(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return §40-2 가명정보 labelling policy for house_view and NBA (T218).

    Confirms pseudonym_label applied to AI training datasets + re-id risk note.
    """
    actor_from_authorization(get_request_config(request), authorization)
    return {
        "pseudonym_label": PSEUDONYM_LABEL,
        "applies_to": ["house_views", "nba_recommendations"],
        "reidentification_risk_note": REIDENTIFICATION_RISK_NOTE,
        "statutory_basis": "신용정보법 §40-2",
        "poc_deferred": "재식별 위험 평가(re-identification risk assessment) — Stage 7",
        "synthetic": True,
    }
