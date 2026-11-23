"""Audit log routes."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request

from apps.api.harness.api.dependencies import actor_from_authorization, get_pool, get_request_config
from apps.api.harness.core.rbac import can_read_audit_logs
from apps.api.harness.repositories import audit as audit_repo

router = APIRouter(tags=["audit"])


def _parse_date_param(value: str | None, field: str) -> date | None:
    """Parse a YYYY-MM-DD query string to a date, or 400 on a malformed value.

    The repository binds these against ``$::date`` parameters; asyncpg's date
    encoder calls ``.toordinal()`` and raises on a raw str, which surfaces as a
    500. Parsing here keeps the str->date conversion (and a clean 400) at the
    API boundary.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"{field} must be an ISO date (YYYY-MM-DD)"
        ) from exc


@router.get("/audit-logs")  # type: ignore[union-attr]
async def list_audit_logs(
    request: Request,
    authorization: str | None = Header(default=None),
    actor_id: str | None = None,
    action_code: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List audit logs for ADMIN/AUDIT_VIEWER only."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    if not can_read_audit_logs(actor):
        raise HTTPException(status_code=403, detail="audit viewer role required")
    parsed_from = _parse_date_param(from_date, "from_date")
    parsed_to = _parse_date_param(to_date, "to_date")
    async with get_pool(request).acquire() as connection:
        items = await audit_repo.list_audit_logs(
            connection,
            actor_id=actor_id,
            action_code=action_code,
            from_date=parsed_from,
            to_date=parsed_to,
            limit=limit,
            offset=offset,
        )
    return {"items": items, "limit": limit, "offset": offset}
