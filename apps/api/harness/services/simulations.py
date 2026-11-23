"""Compliance gate evaluation for recommendation and order simulations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RecommendationGateInput:
    customer_risk_grade: str
    product_risk_level: str
    explanation_checked: bool
    simulated_customer_consented: bool
    employee_final_approved: bool


@dataclass(frozen=True)
class GateResult:
    status_code: str
    passed: bool
    detail: dict[str, Any]


def _as_int(value: str) -> int:
    return int(value)


def evaluate_recommendation_gates(gates: RecommendationGateInput) -> GateResult:
    """Evaluate suitability, explanation, consent, and employee approval gates."""

    suitability_passed = _as_int(gates.customer_risk_grade) >= _as_int(gates.product_risk_level)
    checks = {
        "suitability_passed": suitability_passed,
        "explanation_checked": gates.explanation_checked,
        "simulated_customer_consented": gates.simulated_customer_consented,
        "employee_final_approved": gates.employee_final_approved,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return GateResult(
        status_code="APPROVED" if not failed else "BLOCKED",
        passed=not failed,
        detail={"checks": checks, "failed": failed},
    )


def evaluate_order_gates(
    *,
    recommendation_status_code: str,
    requested_product_id: str,
    recommendation_product_id: str,
    quantity: Decimal | None,
    amount_krw: Decimal | None,
) -> GateResult:
    """Revalidate recommendation and order request gates before simulated execution."""

    checks = {
        "recommendation_approved": recommendation_status_code == "APPROVED",
        "same_product": requested_product_id == recommendation_product_id,
        "quantity_or_amount_present": quantity is not None or amount_krw is not None,
        "positive_quantity": quantity is None or quantity > 0,
        "positive_amount_krw": amount_krw is None or amount_krw > 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    # P1-b: a passing order simulation enters PENDING_APPROVAL (not APPROVED) so a
    # DIFFERENT employee must sign off (second-person 4-eye) before
    # execute-simulated. The creator's upstream recommendation self-attestation is
    # not its own second eye — REG-03 §3 requires a distinct approver here.
    return GateResult(
        status_code="PENDING_APPROVAL" if not failed else "BLOCKED",
        passed=not failed,
        detail={"checks": checks, "failed": failed},
    )
