"""Customer routes."""

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
from apps.api.harness.repositories import ai as ai_repo
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import customers as customer_repo
from apps.api.harness.repositories import products as product_repo
from apps.api.harness.services.readiness.core import synthetic_customer_notice

router = APIRouter(tags=["customers"])


def require_customer_reader(role_code: str) -> None:
    """Allow customer/portfolio reads only for staff roles with customer scope."""

    if role_code in {"AUDIT_VIEWER", "COMPLIANCE_OFFICER"}:
        raise HTTPException(status_code=403, detail="customer access role required")


@router.get("/customers")  # type: ignore[union-attr]
async def list_customers(
    request: Request,
    authorization: str | None = Header(default=None),
    q: str | None = None,
    risk_grade_code: str | None = None,
    segment_code: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List customers under RBAC row scope."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_customer_reader(actor.role_code)
    async with get_pool(request).acquire() as connection:
        items = await customer_repo.list_customers(
            connection,
            actor=actor,
            q=q,
            risk_grade_code=risk_grade_code,
            segment_code=segment_code,
            limit=limit,
            offset=offset,
        )
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        # P2-8: list responses surface synthetic seed figures (total_assets_krw,
        # fee_pct, maturity_date); carry the synthetic-data notice top-level so a
        # banker is not led to read list values as verified, consistent with the
        # Customer-360 detail surface and the dashboard.
        "synthetic_customer_notice": synthetic_customer_notice(),
    }


@router.get("/customers/{customer_id}")  # type: ignore[union-attr]
async def get_customer_360(
    request: Request,
    customer_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Read Customer 360 and append required audit record."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_customer_reader(actor.role_code)
    audit_context = request_audit_context(request)
    async with get_pool(request).acquire() as connection:
        payload = await customer_repo.get_customer_360(
            connection, actor=actor, customer_id=str(customer_id)
        )
        if payload is None:
            raise HTTPException(status_code=404, detail="customer not found")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="customer_360_view",
            resource_type="customer",
            resource_id=str(customer_id),
            detail={"route": "/customers/{customer_id}"},
            **audit_context,
        )
    return payload


@router.post("/customers/{customer_id}/portfolio-analysis", status_code=status.HTTP_202_ACCEPTED)  # type: ignore[union-attr]
async def create_portfolio_analysis_job(
    request: Request,
    customer_id: UUID,
    authorization: str | None = Header(default=None),
    dry_run: bool = Query(default=False, description="DELTA-4 test-double: skip Azure, return synthetic Korean fixture"),
) -> dict[str, Any]:
    """Create a durable portfolio_analysis AI job.

    Pass ``?dry_run=true`` to activate the test-double dispatcher (DELTA-4 /
    G0a-1). The dry-run path is gated by the ``WMAH_ENABLE_DRY_RUN_PROBE=1``
    environment variable so it cannot be invoked in production. The legacy
    Bearer-token shortcut was removed under Wave-Audit-Defect-Fix A2 (CR-3).
    """
    import os
    from apps.api.harness.services.ai_jobs_worker import (
        DRY_RUN_ENV_GATE,
        _DRY_RUN_JOB_IDS,
    )

    if dry_run and os.environ.get(DRY_RUN_ENV_GATE) != "1":
        dry_run = False

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_customer_reader(actor.role_code)
    async with get_pool(request).acquire() as connection:
        customer = await customer_repo.get_customer(
            connection, actor=actor, customer_id=str(customer_id)
        )
        if customer is None:
            raise HTTPException(status_code=404, detail="customer not found")
        job = await ai_repo.create_ai_job(
            connection,
            job_type_code="portfolio_analysis",
            requested_by_id=actor.employee_id,
            resource_type="customer",
            resource_id=str(customer_id),
        )
        if dry_run:
            _DRY_RUN_JOB_IDS.add(str(job["id"]))
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="AI_CALL_STARTED",
            resource_type="ai_job",
            resource_id=str(job["id"]),
            detail={"agent_id": "portfolio_analysis", "resource_type": "customer", "dry_run": dry_run},
            **request_audit_context(request),
        )
    return {"job_id": str(job["id"]), "status_code": job["status_code"], "dry_run": dry_run}


@router.get("/products")  # type: ignore[union-attr]
async def list_products(
    request: Request,
    authorization: str | None = Header(default=None),
    product_type_code: str | None = None,
    risk_level_code: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List active products for staff-side simulations."""

    actor_from_authorization(get_request_config(request), authorization)
    async with get_pool(request).acquire() as connection:
        items = await product_repo.list_products(
            connection,
            product_type_code=product_type_code,
            risk_level_code=risk_level_code,
            limit=limit,
            offset=offset,
        )
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        # P2-8: list responses surface synthetic seed figures (total_assets_krw,
        # fee_pct, maturity_date); carry the synthetic-data notice top-level so a
        # banker is not led to read list values as verified, consistent with the
        # Customer-360 detail surface and the dashboard.
        "synthetic_customer_notice": synthetic_customer_notice(),
    }
