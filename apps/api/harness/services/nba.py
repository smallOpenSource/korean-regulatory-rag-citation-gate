"""NBA card composition service — P1/P2/P3 priority + SLA timers (T17, T243)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SLA_TIMER_BY_PRIORITY: dict[str, int] = {
    "P1": 3600,    # 1 hour  — critical / margin call
    "P2": 14400,   # 4 hours — high priority
    "P3": 86400,   # 24 hours — standard
}

# Signal types that trigger P1 (critical, time-sensitive)
_P1_SIGNAL_TYPES = frozenset(
    {
        "MARGIN_CALL",
        "DRAWDOWN_BREACH",
        "KI_TRIGGERED",
        "EXPIRED",
        "PEP_FLAG",
        "HIGH_RISK_PRODUCT",
        "OVERSEAS_TRANSFER",
    }
)

# Signal types that trigger P2 (high importance)
_P2_SIGNAL_TYPES = frozenset(
    {
        "REVIEW_DUE",
        "MATURITY_DUE",
        "ASSET_CHANGE",
        "REBALANCE_NEEDED",
        "SUITABILITY_EXPIRY",
    }
)

# Customer segments that elevate priority one level
_ULTRA_SEGMENTS = frozenset({"ULTRA_HNW", "VIP"})
_HIGH_SEGMENTS = frozenset({"HNW", "PREMIER"})


@dataclass(frozen=True)
class NBACard:
    """Next-Best-Action card computed by compose_card()."""

    priority: str          # P1 / P2 / P3
    score: float           # 0.0–1.0 composite score
    sla_timer_seconds: int
    why_link: dict[str, str | None]   # {house_view_id, signal_event_id, rule_id}
    action_type_code: str
    trigger_code: str
    suggested_script_hint: str


def _base_priority(signal_type: str) -> str:
    if signal_type in _P1_SIGNAL_TYPES:
        return "P1"
    if signal_type in _P2_SIGNAL_TYPES:
        return "P2"
    return "P3"


def _elevate_priority(priority: str, customer_segment: str) -> str:
    if customer_segment in _ULTRA_SEGMENTS:
        # ULTRA → always at least P1
        return "P1"
    if customer_segment in _HIGH_SEGMENTS:
        # HNW → elevate one level
        return {"P3": "P2", "P2": "P1", "P1": "P1"}.get(priority, priority)
    return priority


def _composite_score(
    priority: str,
    urgency_factor: float,
    confidence: float,
    impact: float,
) -> float:
    """Composite score = urgency × confidence × impact, scaled to 0.0–1.0."""
    priority_weight = {"P1": 1.0, "P2": 0.65, "P3": 0.35}.get(priority, 0.35)
    raw = urgency_factor * confidence * impact * priority_weight
    return round(min(1.0, max(0.0, raw)), 4)


def compose_card(customer: dict[str, Any], signal: dict[str, Any]) -> NBACard:
    """Compose an NBA card from customer profile and trigger signal.

    Args:
        customer: Customer row dict with keys like ``id``, ``customer_segment``,
                  ``assigned_pb_id``, ``risk_grade``.
        signal: Signal event dict with keys ``signal_type``, ``urgency`` (0-1),
                ``confidence`` (0-1), ``impact`` (0-1), ``house_view_id``,
                ``signal_event_id``, ``rule_id``.

    Returns:
        NBACard with priority P1/P2/P3, score, SLA timer, and why_link.
    """
    signal_type = str(signal.get("signal_type") or "REVIEW_DUE")
    customer_segment = str(customer.get("customer_segment") or customer.get("risk_grade") or "")

    base_priority = _base_priority(signal_type)
    final_priority = _elevate_priority(base_priority, customer_segment)

    urgency = float(signal.get("urgency") or 0.7)
    confidence = float(signal.get("confidence") or 0.8)
    impact = float(signal.get("impact") or 0.7)
    score = _composite_score(final_priority, urgency, confidence, impact)

    why_link = {
        "house_view_id": str(signal.get("house_view_id")) if signal.get("house_view_id") else None,
        "signal_event_id": str(signal.get("signal_event_id")) if signal.get("signal_event_id") else None,
        "rule_id": str(signal.get("rule_id")) if signal.get("rule_id") else None,
    }

    action_type_code = str(signal.get("action_type_code") or f"NBA_{signal_type}")
    trigger_code = signal_type

    script_hints = {
        "MARGIN_CALL": "즉시 고객 연락 — 마진콜 발생 상황 안내 및 추가 증거금 납입 또는 포지션 정리 협의",
        "DRAWDOWN_BREACH": "손실 한도 초과 — 포트폴리오 리밸런싱 또는 손절 여부 고객 의향 확인",
        "KI_TRIGGERED": "녹인 발생 — 원금 손실 가능성 안내 및 만기 전략 협의",
        "REVIEW_DUE": "정기 점검 — 포트폴리오 성과 리뷰 및 리밸런싱 필요성 검토",
        "MATURITY_DUE": "만기 도래 — 재투자 방향 협의 및 적합성 재확인",
        "PEP_FLAG": "PEP 고객 — KYC/EDD 재심사 필요",
        "HIGH_RISK_PRODUCT": "고위험 상품 보유 — 위험등급 5-6 재확인 및 투자 적합성 점검",
        "OVERSEAS_TRANSFER": "해외 송금 누적 한도 초과 — AML/KYC 재심사",
        "ASSET_CHANGE": "자산 변동률 초과 — 포트폴리오 재검토 필요",
    }
    script_hint = script_hints.get(signal_type, f"{signal_type} 관련 고객 상담 진행")

    return NBACard(
        priority=final_priority,
        score=score,
        sla_timer_seconds=SLA_TIMER_BY_PRIORITY[final_priority],
        why_link=why_link,
        action_type_code=action_type_code,
        trigger_code=trigger_code,
        suggested_script_hint=script_hint,
    )
