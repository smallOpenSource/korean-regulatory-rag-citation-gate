"""Dashboard routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request

from apps.api.harness.api.dependencies import actor_from_authorization, get_pool, get_request_config
from apps.api.harness.repositories import dashboard as dashboard_repo
from apps.api.harness.services.house_view import attach_house_view_quality

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")  # type: ignore[union-attr]
async def get_dashboard(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return role-scoped dashboard metrics for the authenticated employee."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    async with get_pool(request).acquire() as connection:
        result = await dashboard_repo.get_dashboard_summary(connection, actor=actor)
    # P2-6: the dashboard's latest_house_view.summary is an AI-generated market
    # view; attach the same synthetic disclosure + faithfulness the house_views
    # routes carry so this surface is not a silent-synthetic bypass.
    latest_house_view = result.get("latest_house_view")
    if isinstance(latest_house_view, dict):
        result["latest_house_view"] = attach_house_view_quality(latest_house_view)
    return result
