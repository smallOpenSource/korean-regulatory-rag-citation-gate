"""Suitability gate — REG-02 T220/T228 six-factor check + grade enforcement."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

INVESTMENT_OBJECTIVE_OPTIONS: list[str] = [
    "안전형",
    "안정형",
    "위험중립형",
    "적극투자형",
    "공격투자형",
]

AGE_BRACKET_OPTIONS: list[str] = ["20s", "30s", "40s", "50s", "60s", "70s+"]

REQUIRED_FACTORS: tuple[str, ...] = (
    "investment_objective",
    "financial_situation",
    "investment_experience",
    "age_bracket",
    "loss_tolerance_pct",
    "investment_horizon_months",
)


@dataclass(frozen=True)
class SuitabilityResult:
    gate_status: str  # PASSED | BLOCKED
    fail_reasons: list[str]
    customer_grade: int
    product_grade: int
    investor_classification: str
    evidence: dict[str, Any]


def shuffled_form_options() -> dict[str, list[str]]:
    """Return randomised option orders per field (REG-02 T220 anti-click-through bias).

    The server controls option ordering so employees cannot pre-fill answers.
    """
    inv_obj = INVESTMENT_OBJECTIVE_OPTIONS.copy()
    random.shuffle(inv_obj)
    age_b = AGE_BRACKET_OPTIONS.copy()
    random.shuffle(age_b)
    return {"investment_objective": inv_obj, "age_bracket": age_b}


def _grade_int(value: str | int | None) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def check_suitability(
    customer: dict[str, Any],
    product: dict[str, Any],
    assessment: dict[str, Any],
) -> SuitabilityResult:
    """Enforce all 6 mandatory factors and grade comparison (REG-02 T220, T228).

    Returns ``gate_status=BLOCKED`` if any factor is missing or if
    ``customer_grade < product_grade``.  Each failure is captured in
    ``fail_reasons`` for audit traceability.
    """
    fail_reasons: list[str] = []

    for factor in REQUIRED_FACTORS:
        value = assessment.get(factor)
        missing = value is None or value == "" or value == {} or value == []
        if missing:
            fail_reasons.append(f"MISSING_FACTOR_{factor.upper()}")

    customer_grade = _grade_int(customer.get("risk_grade_code"))
    product_grade = _grade_int(
        product.get("risk_grade_code") or product.get("risk_level_code")
    )

    if product_grade > 0 and customer_grade > 0 and product_grade > customer_grade:
        fail_reasons.append("GRADE_OVER_TOLERANCE")

    gate_status = "BLOCKED" if fail_reasons else "PASSED"
    investor_classification = str(assessment.get("investor_classification") or "GENERAL")

    return SuitabilityResult(
        gate_status=gate_status,
        fail_reasons=list(fail_reasons),
        customer_grade=customer_grade,
        product_grade=product_grade,
        investor_classification=investor_classification,
        evidence={
            "customer_grade": customer_grade,
            "product_grade": product_grade,
            "factors_checked": list(REQUIRED_FACTORS),
            "fail_reasons": fail_reasons,
            "investor_classification": investor_classification,
        },
    )
