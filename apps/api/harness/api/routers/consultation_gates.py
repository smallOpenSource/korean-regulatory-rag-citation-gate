"""Consultation compliance gate routes — suitability, explanation, and four-gate.

REG-02 T220/T222/T228 (suitability + explanation) and REG-03 T242 (four-gate).
Separated from consultations.py to respect the 500-line module containment limit.
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
from apps.api.harness.repositories import consultations as consultation_repo
from apps.api.harness.repositories import suitability as suitability_repo
from apps.api.harness.services.appropriateness import check_appropriateness
from apps.api.harness.services.explanation import build_explanation_checklist
from apps.api.harness.services.four_gate import (
    GATE_NAMES,
    aggregate_gate_result,
    gate_state_to_dict,
)
from apps.api.harness.services.suitability import check_suitability, shuffled_form_options
from apps.api.harness.services.unfair_solicitation import check_unfair_solicitation

router = APIRouter(tags=["consultation-gates"])


def _require_consultation_staff(role_code: str) -> None:
    if role_code not in {"PB", "WM"}:
        raise HTTPException(status_code=403, detail="PB/WM role required")


# ── Suitability gate (REG-02 T220 / T228) ────────────────────────────────────

@router.get("/consultations/{consultation_id}/suitability/form-options")  # type: ignore[union-attr]
async def get_suitability_form_options(
    request: Request,
    consultation_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return server-shuffled option orders to prevent click-through bias (REG-02 T220)."""
    actor_from_authorization(get_request_config(request), authorization)
    return {"consultation_id": str(consultation_id), "option_orders": shuffled_form_options()}


@router.post("/consultations/{consultation_id}/suitability", status_code=status.HTTP_201_CREATED)  # type: ignore[union-attr]
async def submit_suitability_assessment(
    request: Request,
    consultation_id: UUID,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Record six-factor suitability assessment + run grade gate (REG-02 T220, T228)."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_consultation_staff(actor.role_code)
    consultation_id_text = str(consultation_id)
    product_id = parse_uuid_field(payload, "product_id")

    async with get_pool(request).acquire() as connection:
        existing = await consultation_repo.get_consultation_for_actor(
            connection,
            role_code=actor.role_code,
            employee_id=actor.employee_id,
            branch_id=actor.branch_id,
            consultation_id=consultation_id_text,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="consultation not found")

        customer = await suitability_repo.get_customer_grade(
            connection, customer_id=str(existing["customer_id"])
        )
        if customer is None:
            raise HTTPException(status_code=404, detail="customer not found")

        product = await suitability_repo.get_product_grade(connection, product_id=product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="product not found")

        fin_sit: dict[str, Any] = dict(payload.get("financial_situation") or {})
        inv_exp: dict[str, Any] = dict(payload.get("investment_experience") or {})
        loss_pct: float = float(payload.get("loss_tolerance_pct") or 0)
        horizon_months: int = int(payload.get("investment_horizon_months") or 0)
        form_orders: dict[str, Any] = dict(payload.get("form_option_orders") or {})

        assessment_data: dict[str, Any] = {
            "investment_objective": payload.get("investment_objective"),
            "financial_situation": fin_sit,
            "investment_experience": inv_exp,
            "age_bracket": payload.get("age_bracket"),
            "loss_tolerance_pct": loss_pct,
            "investment_horizon_months": horizon_months,
            "investor_classification": payload.get("investor_classification", "GENERAL"),
        }

        result = check_suitability(customer, product, assessment_data)

        assessment = await suitability_repo.insert_suitability_assessment(
            connection,
            consultation_id=consultation_id_text,
            customer_id=str(existing["customer_id"]),
            employee_id=actor.employee_id,
            investment_objective=str(assessment_data["investment_objective"] or ""),
            financial_situation=fin_sit,
            investment_experience=inv_exp,
            age_bracket=str(assessment_data["age_bracket"] or ""),
            loss_tolerance_pct=loss_pct,
            investment_horizon_months=horizon_months,
            investor_classification=result.investor_classification,
            form_option_orders=form_orders,
        )

        gate_row = await suitability_repo.upsert_gate(
            connection,
            consultation_id=consultation_id_text,
            gate_name="suitability",
            gate_status=result.gate_status,
            gate_evidence_json=result.evidence,
        )

        action_code = (
            "suitability_grade_block" if result.gate_status == "BLOCKED"
            else "suitability_confirmed"
        )
        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code=action_code,
            resource_type="suitability_assessment",
            resource_id=str(assessment["id"]),
            detail=result.evidence,
            **request_audit_context(request),
        )

    return {
        "assessment_id": str(assessment["id"]),
        "gate_status": result.gate_status,
        "fail_reasons": result.fail_reasons,
        "customer_grade": result.customer_grade,
        "product_grade": result.product_grade,
        "investor_classification": result.investor_classification,
        "gate_id": str(gate_row["id"]),
    }


# ── Appropriateness gate (REG-01 T203) ───────────────────────────────────────

@router.post("/consultations/{consultation_id}/appropriateness-acknowledge")  # type: ignore[union-attr]
async def acknowledge_appropriateness_warning(
    request: Request,
    consultation_id: UUID,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Record appropriateness warning acknowledgement for unsolicited transactions (REG-01 T203)."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_consultation_staff(actor.role_code)
    consultation_id_text = str(consultation_id)
    product_id = parse_uuid_field(payload, "product_id")
    solicited: bool = bool(payload.get("solicited", True))

    async with get_pool(request).acquire() as connection:
        existing = await consultation_repo.get_consultation_for_actor(
            connection,
            role_code=actor.role_code,
            employee_id=actor.employee_id,
            branch_id=actor.branch_id,
            consultation_id=consultation_id_text,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="consultation not found")

        customer = await suitability_repo.get_customer_grade(
            connection, customer_id=str(existing["customer_id"])
        )
        product = await suitability_repo.get_product_grade(connection, product_id=product_id)
        result = check_appropriateness(
            customer or {},
            product or {},
            solicited=solicited,
            appropriateness_warning_acknowledged=True,
        )

        gate_row = await suitability_repo.upsert_gate(
            connection,
            consultation_id=consultation_id_text,
            gate_name="suitability",
            gate_status="PASSED" if result.gate_status == "PASSED" else "BLOCKED",
            gate_evidence_json=result.evidence,
        )

        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="appropriateness_warning_acknowledged",
            resource_type="consultation",
            resource_id=consultation_id_text,
            detail=result.evidence,
            **request_audit_context(request),
        )

    return {
        "gate_status": result.gate_status,
        "solicited": result.solicited,
        "warning_required": result.warning_required,
        "acknowledged": result.acknowledged,
        "gate_id": str(gate_row["id"]),
    }


# ── Explanation checklist (REG-02 T222) ──────────────────────────────────────

@router.get("/consultations/{consultation_id}/explanation-checklist")  # type: ignore[union-attr]
async def get_explanation_checklist(
    request: Request,
    consultation_id: UUID,
    product_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return leading-block explanation checklist for a product (REG-02 T222)."""
    actor_from_authorization(get_request_config(request), authorization)

    async with get_pool(request).acquire() as connection:
        product = await suitability_repo.get_product_grade(connection, product_id=product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="product not found")

    checklist = build_explanation_checklist(product)
    return {
        "consultation_id": str(consultation_id),
        "product_id": product_id,
        "checklist": [
            {"item_id": i.item_id, "category": i.category, "text": i.text, "leading": i.leading}
            for i in checklist
        ],
        "leading_count": sum(1 for i in checklist if i.leading),
    }


@router.post("/consultations/{consultation_id}/explanation-confirm")  # type: ignore[union-attr]
async def confirm_explanation(
    request: Request,
    consultation_id: UUID,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Record that all explanation items were reviewed by employee (REG-02 T222)."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_consultation_staff(actor.role_code)
    consultation_id_text = str(consultation_id)
    checked_item_ids: list[str] = list(payload.get("checked_item_ids") or [])

    async with get_pool(request).acquire() as connection:
        existing = await consultation_repo.get_consultation_for_actor(
            connection,
            role_code=actor.role_code,
            employee_id=actor.employee_id,
            branch_id=actor.branch_id,
            consultation_id=consultation_id_text,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="consultation not found")

        evidence = {"checked_item_ids": checked_item_ids, "employee_id": actor.employee_id}
        gate_row = await suitability_repo.upsert_gate(
            connection,
            consultation_id=consultation_id_text,
            gate_name="explanation",
            gate_status="PASSED",
            gate_evidence_json=evidence,
        )

        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="explanation_confirmed",
            resource_type="consultation",
            resource_id=consultation_id_text,
            detail=evidence,
            **request_audit_context(request),
        )

    return {
        "gate_status": "PASSED",
        "gate_id": str(gate_row["id"]),
        "checked_count": len(checked_item_ids),
    }


# ── Four-gate endpoints (REG-02 T15 / REG-03 T242) ───────────────────────────

@router.get("/consultations/{consultation_id}/four-gate")  # type: ignore[union-attr]
async def get_four_gate(
    request: Request,
    consultation_id: UUID,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return all 4 compliance gate states for a consultation (REG-02 T15)."""
    actor = actor_from_authorization(get_request_config(request), authorization)
    consultation_id_text = str(consultation_id)

    async with get_pool(request).acquire() as connection:
        existing = await consultation_repo.get_consultation_for_actor(
            connection,
            role_code=actor.role_code,
            employee_id=actor.employee_id,
            branch_id=actor.branch_id,
            consultation_id=consultation_id_text,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="consultation not found")
        gate_rows = await suitability_repo.list_gates(
            connection, consultation_id=consultation_id_text
        )

    result = aggregate_gate_result(consultation_id_text, gate_rows)
    return {
        "consultation_id": consultation_id_text,
        "all_passed": result.all_passed,
        "gates": [gate_state_to_dict(g) for g in result.gates],
    }


@router.post("/consultations/{consultation_id}/four-gate/{gate_name}/acknowledge")  # type: ignore[union-attr]
async def acknowledge_gate(
    request: Request,
    consultation_id: UUID,
    gate_name: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Record gate acknowledgement (REG-03 T242).

    Allowed gate names: suitability, explanation, unfair_solicitation, marketing.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_consultation_staff(actor.role_code)
    consultation_id_text = str(consultation_id)

    if gate_name not in GATE_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"gate_name must be one of: {', '.join(GATE_NAMES)}",
        )

    async with get_pool(request).acquire() as connection:
        existing = await consultation_repo.get_consultation_for_actor(
            connection,
            role_code=actor.role_code,
            employee_id=actor.employee_id,
            branch_id=actor.branch_id,
            consultation_id=consultation_id_text,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="consultation not found")

        gate_row = await suitability_repo.acknowledge_gate(
            connection,
            consultation_id=consultation_id_text,
            gate_name=gate_name,
            acknowledged_by=actor.employee_id,
        )
        if gate_row is None:
            raise HTTPException(status_code=404, detail="gate not found — run check first")

        await audit_repo.insert_audit_log(
            connection,
            actor_id=actor.employee_id,
            action_code="four_gate_acknowledged",
            resource_type="consultation_gate",
            resource_id=str(gate_row["id"]),
            detail={"gate_name": gate_name, "consultation_id": consultation_id_text},
            **request_audit_context(request),
        )

    ack_at = gate_row.get("gate_acknowledged_at")
    return {
        "gate_name": gate_name,
        "gate_status": gate_row["gate_status"],
        "gate_acknowledged_at": ack_at.isoformat() if ack_at else None,
    }


# ── Unfair solicitation gate (REG-02 T223) ───────────────────────────────────

@router.post("/consultations/{consultation_id}/unfair-solicitation-check")  # type: ignore[union-attr]
async def check_unfair_solicitation_gate(
    request: Request,
    consultation_id: UUID,
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Run unfair solicitation rules against message text (REG-02 T223).

    Checks four rule categories:
    - REGEX_DEFINITIVE_LANGUAGE (단정문구)
    - RISK_GRADE_OVER (grade mismatch)
    - OFFLINE_TO_ONLINE_WINDOW (channel switching abuse)
    - LOSS_GUARANTEE (이익보장/손실보전)

    Persists gate result to consultation_gates and emits audit on BLOCKED.
    """
    actor = actor_from_authorization(get_request_config(request), authorization)
    _require_consultation_staff(actor.role_code)
    consultation_id_text = str(consultation_id)

    message_text: str = str(payload.get("message_text") or "")
    product_id: str | None = payload.get("product_id")
    solicited: bool = bool(payload.get("solicited", True))
    last_face_to_face: int | None = payload.get("last_face_to_face_seconds_ago")
    has_opt_in_audit: bool = bool(payload.get("has_opt_in_audit", False))

    async with get_pool(request).acquire() as connection:
        existing = await consultation_repo.get_consultation_for_actor(
            connection,
            role_code=actor.role_code,
            employee_id=actor.employee_id,
            branch_id=actor.branch_id,
            consultation_id=consultation_id_text,
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="consultation not found")

        product: dict[str, Any] = {}
        if product_id:
            product = await suitability_repo.get_product_grade(
                connection, product_id=product_id
            ) or {}

        result = check_unfair_solicitation(
            existing,
            product,
            message_text,
            offending_employee_id=actor.employee_id,
            last_face_to_face_seconds_ago=last_face_to_face,
            has_opt_in_audit=has_opt_in_audit,
        )

        gate_row = await suitability_repo.upsert_gate(
            connection,
            consultation_id=consultation_id_text,
            gate_name="unfair_solicitation",
            gate_status=result.gate_status,
            gate_evidence_json=result.evidence,
        )

        if result.gate_status == "BLOCKED":
            await audit_repo.insert_audit_log(
                connection,
                actor_id=actor.employee_id,
                action_code="unfair_solicitation_blocked",
                resource_type="consultation",
                resource_id=consultation_id_text,
                detail=result.evidence,
                **request_audit_context(request),
            )

    violations = [
        {
            "rule_id": v.rule_id,
            "severity": v.severity,
            "detail": v.detail,
        }
        for v in result.violations
    ]
    return {
        "gate_status": result.gate_status,
        "violations": violations,
        "gate_id": str(gate_row["id"]),
    }
