"""Explanation gate — REG-02 T222 leading-block checklist builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChecklistItem:
    item_id: str
    category: str
    text: str
    leading: bool  # True → must be rendered first in UI (금소법 감독규정 §설명의무)


def build_explanation_checklist(product: dict[str, Any]) -> list[ChecklistItem]:
    """Build the 핵심설명서 checklist per REG-02 T222.

    The first items have ``leading=True`` and correspond to the mandatory
    leading-block (부적합 소비자 유형 + 손실 가능성 우선 기재) required by
    the 2025 금소법 감독규정 revision.  UI implementations must display all
    ``leading=True`` items at the top before any body items.
    """
    product_name = str(product.get("product_name") or "해당 상품")
    product_type = str(product.get("product_type_code") or "")
    risk_grade = str(
        product.get("risk_grade_code") or product.get("risk_level_code") or "?"
    )
    has_knock_in: bool = bool(product.get("has_knock_in", False))
    fee_pct = product.get("fee_pct", "N/A")
    maturity_date = product.get("maturity_date", "해당 없음")

    items: list[ChecklistItem] = []

    # ── Leading block (leading=True) ─────────────────────────────────────────
    items.append(ChecklistItem(
        item_id="LEAD_UNSUITABLE_TYPES",
        category="부적합소비자유형",
        text=(
            f"[필수 선행 표시] 이 상품({product_name})에 부적합한 투자자 유형: "
            f"위험등급 {risk_grade}등급 초과 고객 / 투자 경험 없는 고객 / "
            f"단기(12개월 미만) 투자 목적 고객."
        ),
        leading=True,
    ))
    items.append(ChecklistItem(
        item_id="LEAD_LOSS_RISK",
        category="손실가능성",
        text=(
            f"[필수 선행 표시] 원금 손실 가능성: {product_name}은(는) 원금의 전부 또는 일부를 "
            f"잃을 수 있는 투자상품입니다. 과거 수익률은 미래 성과를 보장하지 않습니다."
        ),
        leading=True,
    ))

    if has_knock_in:
        items.append(ChecklistItem(
            item_id="LEAD_KNOCK_IN",
            category="손실가능성",
            text=(
                "[필수 선행 표시] 낙인(Knock-In) 조건: 기초자산 가격이 낙인 배리어 이하로 "
                "하락할 경우 원금 손실 규모가 크게 확대되어 대부분의 원금을 잃을 수 있습니다."
            ),
            leading=True,
        ))

    # ── Body checklist (leading=False) ───────────────────────────────────────
    items.append(ChecklistItem(
        item_id="BODY_PRODUCT_OVERVIEW",
        category="상품개요",
        text=f"상품명: {product_name} / 유형: {product_type} / 위험등급: {risk_grade}등급.",
        leading=False,
    ))
    items.append(ChecklistItem(
        item_id="BODY_FEE",
        category="비용",
        text=f"수수료·보수: {fee_pct}%. 투자 전 반드시 비용을 확인하십시오.",
        leading=False,
    ))
    items.append(ChecklistItem(
        item_id="BODY_MATURITY",
        category="만기",
        text=(
            f"만기일: {maturity_date}. 만기 전 중도 환매 시 수수료 및 손실이 발생할 수 있습니다."
        ),
        leading=False,
    ))
    items.append(ChecklistItem(
        item_id="BODY_SUITABILITY_GRADE",
        category="적합성",
        text=(
            f"이 상품은 위험등급 {risk_grade}등급 이하의 투자 성향을 가진 고객에게 적합합니다. "
            f"고객의 투자 성향과 일치하는지 반드시 확인하십시오."
        ),
        leading=False,
    ))
    items.append(ChecklistItem(
        item_id="BODY_EMPLOYEE_CONFIRM",
        category="직원확인",
        text=(
            "직원이 본 핵심설명서의 모든 항목을 고객에게 충분히 설명하였음을 확인합니다."
        ),
        leading=False,
    ))
    items.append(ChecklistItem(
        item_id="BODY_CUSTOMER_CONFIRM",
        category="고객확인",
        text=(
            "고객이 상품 위험, 비용, 손실 가능성을 이해하고 자신의 판단으로 투자를 결정합니다."
        ),
        leading=False,
    ))

    return items
