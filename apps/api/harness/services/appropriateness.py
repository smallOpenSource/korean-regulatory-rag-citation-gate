"""Appropriateness gate — REG-01 T203 unsolicited-transaction warning flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AppropriatenessResult:
    gate_status: str  # PASSED | WARNING_REQUIRED
    solicited: bool
    warning_required: bool
    acknowledged: bool
    evidence: dict[str, Any]


def check_appropriateness(
    customer: dict[str, Any],
    product: dict[str, Any],
    *,
    solicited: bool,
    appropriateness_warning_acknowledged: bool = False,
) -> AppropriatenessResult:
    """Evaluate the appropriateness gate for a transaction (REG-01 T203).

    Unsolicited (비권유) transactions require the customer to acknowledge an
    appropriateness warning before the consultation can proceed to recommendation.
    Solicited transactions bypass this warning gate.

    Args:
        customer: customer record dict (id, risk_grade_code, …).
        product:  product record dict (id, risk_grade_code, …).
        solicited: True when the employee initiated the product recommendation.
        appropriateness_warning_acknowledged: True when the actor recorded the
            ``appropriateness_warning_acknowledged`` audit event.

    Returns:
        AppropriatenessResult with ``gate_status`` PASSED or WARNING_REQUIRED.
    """
    warning_required = not solicited
    if warning_required and not appropriateness_warning_acknowledged:
        gate_status = "WARNING_REQUIRED"
    else:
        gate_status = "PASSED"

    return AppropriatenessResult(
        gate_status=gate_status,
        solicited=solicited,
        warning_required=warning_required,
        acknowledged=appropriateness_warning_acknowledged,
        evidence={
            "solicited": solicited,
            "warning_required": warning_required,
            "acknowledged": appropriateness_warning_acknowledged,
            "product_id": str(product.get("id", "")),
            "customer_id": str(customer.get("id", "")),
        },
    )
