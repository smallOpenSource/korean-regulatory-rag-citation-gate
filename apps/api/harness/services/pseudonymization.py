"""Pseudonymization metadata helpers — REG-01 신용정보법 §40-2 가명정보 (T218).

PoC scope: attach pseudonym_label='가명/재식별금지' to house_view and NBA
output payloads so the UI can surface the 재식별 금지 warning. Actual
re-identification risk assessment is deferred (see REG-01 §5 T218 note).
"""

from __future__ import annotations

from typing import Any

PSEUDONYM_LABEL: str = "가명/재식별금지"

REIDENTIFICATION_RISK_NOTE: str = (
    "재식별 위험 평가(re-identification risk assessment)는 PoC 범위에서 제외됩니다. "
    "실제 운영 도입 전 별도 평가 필요 (신용정보법 §40-2 제3항)."
)


def attach_pseudonym_label(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of payload with pseudonym_label and reidentification_risk_note injected.

    Used for house_view and NBA recommendation responses to satisfy §40-2.
    The original dict is not mutated.
    """
    return {
        **payload,
        "pseudonym_label": PSEUDONYM_LABEL,
        "reidentification_risk_note": REIDENTIFICATION_RISK_NOTE,
    }


def attach_pseudonym_label_list(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply attach_pseudonym_label to every item in a list."""
    return [attach_pseudonym_label(row) for row in rows]
