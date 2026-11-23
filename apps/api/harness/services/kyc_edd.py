"""KYC/EDD trigger rule book — evaluate_triggers() (T248, REG-03)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class KycTrigger:
    """One evaluated KYC/EDD trigger result."""

    trigger_type: str   # ASSET_CHANGE_PCT | OVERSEAS_TRANSFER | PEP_FLAG | HIGH_RISK_PRODUCT
    trigger_value: dict[str, Any]
    rationale: str


# ── Rule thresholds ───────────────────────────────────────────────────────────
_ASSET_CHANGE_THRESHOLD_PCT = 30.0   # > 30% within 90 days → trigger
_OVERSEAS_WINDOW_DAYS = 30
_OVERSEAS_THRESHOLD_USD = 10_000.0   # > 10,000 USD cumulative in 30d → trigger
_HIGH_RISK_GRADES = {5, 6}           # 위험등급 5-6


# ── Rule implementations ──────────────────────────────────────────────────────

def _rule_asset_change_pct(
    customer: dict[str, Any],
    transactions: list[dict[str, Any]],
    now: datetime,
) -> KycTrigger | None:
    """자산 변동률 > 30% within 90d → trigger."""
    cutoff = now - timedelta(days=90)
    recent = [
        t for t in transactions
        if _parse_dt(t.get("transaction_date") or t.get("created_at")) >= cutoff
    ]
    if not recent:
        return None

    baseline_assets = float(customer.get("total_assets_krw") or customer.get("aum_krw") or 0)
    if baseline_assets <= 0:
        return None

    total_change_abs = sum(abs(float(t.get("amount_krw") or t.get("amount") or 0)) for t in recent)
    change_pct = (total_change_abs / baseline_assets) * 100.0

    if change_pct > _ASSET_CHANGE_THRESHOLD_PCT:
        return KycTrigger(
            trigger_type="ASSET_CHANGE_PCT",
            trigger_value={
                "change_pct": round(change_pct, 2),
                "threshold_pct": _ASSET_CHANGE_THRESHOLD_PCT,
                "window_days": 90,
                "transaction_count": len(recent),
            },
            rationale=f"자산 변동률 {change_pct:.1f}%로 90일 기준 {_ASSET_CHANGE_THRESHOLD_PCT}% 초과",
        )
    return None


def _rule_overseas_transfer(
    customer: dict[str, Any],
    transactions: list[dict[str, Any]],
    now: datetime,
) -> KycTrigger | None:
    """해외송금 누적 > 10,000 USD within 30d → trigger."""
    cutoff = now - timedelta(days=_OVERSEAS_WINDOW_DAYS)
    overseas = [
        t for t in transactions
        if t.get("transaction_type") in {"OVERSEAS_TRANSFER", "FOREIGN_REMITTANCE"}
        and _parse_dt(t.get("transaction_date") or t.get("created_at")) >= cutoff
    ]
    if not overseas:
        return None

    cumulative_usd = sum(
        float(t.get("amount_usd") or t.get("amount") or 0) for t in overseas
    )
    if cumulative_usd > _OVERSEAS_THRESHOLD_USD:
        return KycTrigger(
            trigger_type="OVERSEAS_TRANSFER",
            trigger_value={
                "cumulative_usd": round(cumulative_usd, 2),
                "threshold_usd": _OVERSEAS_THRESHOLD_USD,
                "window_days": _OVERSEAS_WINDOW_DAYS,
                "transfer_count": len(overseas),
            },
            rationale=(
                f"해외송금 누적 USD {cumulative_usd:,.0f}으로 30일 기준 "
                f"USD {_OVERSEAS_THRESHOLD_USD:,.0f} 초과"
            ),
        )
    return None


def _rule_pep_flag(customer: dict[str, Any]) -> KycTrigger | None:
    """PEP_FLAG synthetic marker → trigger on every consultation."""
    is_pep = bool(
        customer.get("is_pep")
        or customer.get("pep_flag")
        or customer.get("kyc_metadata", {}).get("pep_flag")
    )
    if is_pep:
        return KycTrigger(
            trigger_type="PEP_FLAG",
            trigger_value={
                "pep_flag": True,
                "synthetic": True,  # per ADR Round 4/8 — synthetic-only metadata
            },
            rationale="고객 프로파일에 PEP(정치적 노출인물) 플래그 설정 — 매 상담 시 EDD 필요",
        )
    return None


def _rule_high_risk_product(
    transactions: list[dict[str, Any]],
) -> KycTrigger | None:
    """위험등급 5-6 상품 구매 → trigger."""
    high_risk_txns = [
        t for t in transactions
        if int(t.get("product_risk_grade") or t.get("risk_grade") or 0) in _HIGH_RISK_GRADES
        and t.get("transaction_type") in {"PURCHASE", "BUY", "SUBSCRIBE"}
    ]
    if high_risk_txns:
        grades = [
            int(t.get("product_risk_grade") or t.get("risk_grade") or 0)
            for t in high_risk_txns
        ]
        return KycTrigger(
            trigger_type="HIGH_RISK_PRODUCT",
            trigger_value={
                "risk_grades": grades,
                "transaction_count": len(high_risk_txns),
                "product_ids": [str(t.get("product_id") or "") for t in high_risk_txns],
            },
            rationale=(
                f"위험등급 {grades} 고위험 상품 {len(high_risk_txns)}건 구매 — EDD 적용"
            ),
        )
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_triggers(
    customer: dict[str, Any],
    recent_transactions: list[dict[str, Any]],
    *,
    reference_time: datetime | None = None,
) -> list[KycTrigger]:
    """Apply all KYC/EDD rule checks and return fired triggers.

    Args:
        customer: Customer profile dict (synthetic-only PEP flag allowed).
        recent_transactions: List of transaction dicts relevant to the evaluation.
        reference_time: Override for 'now' (defaults to UTC now).

    Returns:
        List of KycTrigger (may be empty if no rules fire).
    """
    now = reference_time or datetime.now(UTC)
    triggers: list[KycTrigger] = []

    result = _rule_asset_change_pct(customer, recent_transactions, now)
    if result:
        triggers.append(result)

    result = _rule_overseas_transfer(customer, recent_transactions, now)
    if result:
        triggers.append(result)

    result = _rule_pep_flag(customer)
    if result:
        triggers.append(result)

    result = _rule_high_risk_product(recent_transactions)
    if result:
        triggers.append(result)

    return triggers


def _parse_dt(value: Any) -> datetime:
    """Best-effort parse of a date/datetime value to an aware datetime."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
        except ValueError:
            pass
    return datetime.min.replace(tzinfo=UTC)
