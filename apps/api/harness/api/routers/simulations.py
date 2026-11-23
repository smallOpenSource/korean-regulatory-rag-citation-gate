"""Recommendation and order simulation routes."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
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
from apps.api.harness.core.identity import same_actor
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import simulations as simulation_repo
from apps.api.harness.services.ai.output_quality import SYNTHETIC_ADVISORY_NOTICE
from apps.api.harness.services.readiness.core import synthetic_portfolio_provenance
from apps.api.harness.services.simulations import (
    RecommendationGateInput,
    evaluate_order_gates,
    evaluate_recommendation_gates,
)

router = APIRouter(tags=["simulations"])


def require_simulation_staff(role_code: str) -> None:
    """Allow recommendation/order simulation flows only for PB/WM staff roles."""

    if role_code not in {"PB", "WM"}:
        raise HTTPException(status_code=403, detail="PB/WM role required")


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(status_code=422, detail="decimal value required") from exc


def _attach_sim_provenance(sim: dict[str, Any]) -> dict[str, Any]:
    """P2-7: a simulation's suitability verdict is computed over synthetic,
    unverified customer data (risk grade, total assets); carry the synthetic
    disclosure + provenance so a banker does not read the gate result as a verified
    fact. Callers pass a non-None row (insert RETURNING / post-404-guard)."""
    sim["data_quality_notice"] = SYNTHETIC_ADVISORY_NOTICE
    sim["data_provenance"] = synthetic_portfolio_provenance()
    return sim


@router.post("/recommendation-simulations", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
async def create_recommendation_simulation(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create a staff-side recommendation simulation with four-gate evaluation."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_simulation_staff(actor.role_code)
    customer_id = parse_uuid_field(payload, "customer_id")
    consultation_id = parse_uuid_field(payload, "consultation_id")
    product_id = parse_uuid_field(payload, "product_id")
    async with get_pool(request).acquire() as connection:
        gate_input = await simulation_repo.get_recommendation_gate_input(
            connection,
            customer_id=customer_id,
            consultation_id=consultation_id,
            product_id=product_id,
            employee_id=actor.employee_id,
        )
        if gate_input is None:
            raise HTTPException(status_code=404, detail="simulation input not found")
        gate_result = evaluate_recommendation_gates(
            RecommendationGateInput(
                customer_risk_grade=str(gate_input["customer_risk_grade"]),
                product_risk_level=str(gate_input["product_risk_level"]),
                explanation_checked=bool(payload.get("explanation_checked")),
                simulated_customer_consented=bool(payload.get("simulated_customer_consented")),
                employee_final_approved=bool(payload.get("employee_final_approved")),
            )
        )
        simulation = await simulation_repo.insert_recommendation_simulation(
            connection,
            customer_id=str(gate_input["customer_id"]),
            employee_id=actor.employee_id,
            consultation_id=str(gate_input["consultation_id"]),
            product_id=str(gate_input["product_id"]),
            status_code=gate_result.status_code,
            suitability_passed=gate_result.detail["checks"]["suitability_passed"],
            explanation_checked=bool(payload.get("explanation_checked")),
            simulated_customer_consented=bool(payload.get("simulated_customer_consented")),
            employee_final_approved=bool(payload.get("employee_final_approved")),
            gate_detail=gate_result.detail,
        )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code=(
                "recommendation_simulation_create"
                if gate_result.passed
                else "recommendation_simulation_block"
            ),
            resource_type="recommendation_simulation",
            resource_id=str(simulation["id"]),
            detail=gate_result.detail,
            **request_audit_context(request),
        )
    return _attach_sim_provenance(simulation)


@router.post("/order-simulations", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
async def create_order_simulation(
    request: Request,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create an order simulation after server-side recommendation revalidation."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_simulation_staff(actor.role_code)
    quantity = _decimal_or_none(payload.get("quantity"))
    amount_krw = _decimal_or_none(payload.get("amount_krw"))
    recommendation_id = parse_uuid_field(payload, "recommendation_simulation_id")
    product_id = parse_uuid_field(payload, "product_id")
    async with get_pool(request).acquire() as connection:
        recommendation = await simulation_repo.get_recommendation_for_order(
            connection,
            recommendation_simulation_id=recommendation_id,
            employee_id=actor.employee_id,
        )
        if recommendation is None:
            raise HTTPException(status_code=404, detail="recommendation simulation not found")
        gate_result = evaluate_order_gates(
            recommendation_status_code=str(recommendation["status_code"]),
            requested_product_id=product_id,
            recommendation_product_id=str(recommendation["product_id"]),
            quantity=quantity,
            amount_krw=amount_krw,
        )
        simulation = await simulation_repo.insert_order_simulation(
            connection,
            recommendation_simulation_id=recommendation_id,
            customer_id=str(recommendation["customer_id"]),
            employee_id=actor.employee_id,
            product_id=product_id,
            side_code=str(payload.get("side_code", "BUY")),
            quantity=quantity,
            amount_krw=amount_krw,
            status_code=gate_result.status_code,
            gate_detail=gate_result.detail,
        )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="order_simulation_create"
            if gate_result.passed
            else "order_simulation_block",
            resource_type="order_simulation",
            resource_id=str(simulation["id"]),
            detail=gate_result.detail,
            **request_audit_context(request),
        )
    return _attach_sim_provenance(simulation)


@router.post("/order-simulations/{order_simulation_id}/execute-simulated")  # type: ignore[union-attr]
async def execute_order_simulation(
    request: Request,
    order_simulation_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Record simulated execution only; no external order API is called."""

    actor = actor_from_authorization(get_request_config(request), authorization)
    require_simulation_staff(actor.role_code)
    async with get_pool(request).acquire() as connection:
        simulation = await simulation_repo.execute_order_simulation(
            connection,
            order_simulation_id=str(order_simulation_id),
            employee_id=actor.employee_id,
        )
        if simulation is None:
            raise HTTPException(status_code=404, detail="approved order simulation not found")
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="order_simulation_execute_simulated",
            resource_type="order_simulation",
            resource_id=str(order_simulation_id),
            detail={"status_code": "SIMULATED_EXECUTED", "external_order_api_called": False},
            **request_audit_context(request),
        )
    return _attach_sim_provenance(simulation)


@router.post("/order-simulations/{order_simulation_id}/approve")  # type: ignore[union-attr]
async def approve_order_simulation(
    request: Request,
    order_simulation_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Supervisory second-person 4-eye approval for a PENDING_APPROVAL order
    simulation (REG-03 §3 — 게이트별 1차/2차 승인자 분리 + BRANCH_MANAGER 승인).

    Only a BRANCH_MANAGER may sign off: a non-BM actor (including the PB/WM creator
    role) is blocked with ``role_forbidden`` + 403. The approver must also differ
    from the creator — self-approval emits ``four_eyes_violation_blocked`` + 403.
    On a valid distinct BRANCH_MANAGER the row transitions PENDING_APPROVAL →
    APPROVED and emits ``order_simulation_approved`` so the creator can then
    execute-simulated.
    """

    actor = actor_from_authorization(get_request_config(request), authorization)
    async with get_pool(request).acquire() as connection:
        # Supervisory 4-eye (REG-03 §3): only a BRANCH_MANAGER may sign off on a
        # simulated order before execution. A non-BM actor (including the PB/WM
        # creator role) is blocked with a role_forbidden audit + 403.
        if actor.role_code != "BRANCH_MANAGER":
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="role_forbidden",
                resource_type="order_simulation",
                resource_id=str(order_simulation_id),
                detail={
                    "role_code": actor.role_code,
                    "rejected_for": ["BRANCH_MANAGER"],
                    "endpoint_path": request.url.path,
                },
                **request_audit_context(request),
            )
            raise HTTPException(
                status_code=403,
                detail="BRANCH_MANAGER role required to approve an order simulation",
            )
        sim = await simulation_repo.get_order_simulation(
            connection, order_simulation_id=str(order_simulation_id)
        )
        if sim is None:
            raise HTTPException(status_code=404, detail="order simulation not found")
        if sim["status_code"] != "PENDING_APPROVAL":
            raise HTTPException(
                status_code=409,
                detail="order simulation must be PENDING_APPROVAL to approve",
            )
        # 4-eye: the approver must differ from the creator. Emit the block audit
        # (auto-commits on this connection — these routes are not wrapped in a
        # request transaction, mirroring routers/email.py approve) BEFORE raising.
        if same_actor(actor.employee_id, sim["employee_id"]):
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="four_eyes_violation_blocked",
                resource_type="order_simulation",
                resource_id=str(order_simulation_id),
                detail={
                    "reason": "self_approval",
                    "creator_id": str(sim["employee_id"]),
                    "approver_id": actor.employee_id,
                },
                **request_audit_context(request),
            )
            raise HTTPException(
                status_code=403,
                detail="order simulation approval requires a different approver (four-eye rule)",
            )
        approved = await simulation_repo.approve_order_simulation(
            connection,
            order_simulation_id=str(order_simulation_id),
            approver_id=actor.employee_id,
        )
        if approved is None:
            raise HTTPException(
                status_code=409, detail="order simulation could not be approved"
            )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="order_simulation_approved",
            resource_type="order_simulation",
            resource_id=str(order_simulation_id),
            detail={
                "status_code": "APPROVED",
                "creator_id": str(sim["employee_id"]),
                "approver_id": actor.employee_id,
            },
            **request_audit_context(request),
        )
    return _attach_sim_provenance(approved)
