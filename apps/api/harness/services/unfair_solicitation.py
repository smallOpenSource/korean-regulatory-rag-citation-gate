"""Unfair solicitation rule engine — REG-02 T223 / 금소법 감독규정 §부당권유."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ── Rule definitions ──────────────────────────────────────────────────────────

RULE_DEFINITIVE_LANGUAGE = "REGEX_DEFINITIVE_LANGUAGE"
RULE_RISK_GRADE_OVER = "RISK_GRADE_OVER"
RULE_OFFLINE_TO_ONLINE_WINDOW = "OFFLINE_TO_ONLINE_WINDOW"
RULE_LOSS_GUARANTEE = "LOSS_GUARANTEE"

# Regex patterns for 단정문구 detection (REG-02 §부당권유)
_DEFINITIVE_PATTERN = re.compile(
    r"반드시\s*수익|손실\s*없음|100\s*%\s*안전|보장\s*됩니다|원금\s*보장|무조건\s*수익"
    r"|확실히\s*오릅|확실한\s*수익|절대\s*손실\s*없|수익\s*확실",
    re.IGNORECASE,
)

# Regex for 이익보장/손실보전 patterns
_LOSS_GUARANTEE_PATTERN = re.compile(
    r"이익\s*보장|손실\s*보전|손실\s*보장|수익\s*보장|원금\s*보전|손실\s*없이",
    re.IGNORECASE,
)

# Offline-to-online window: 24 hours (REG-02 §부당권유 대면→비대면)
OFFLINE_TO_ONLINE_WINDOW_SECONDS = 86400


@dataclass(frozen=True)
class UnfairRuleViolation:
    rule_id: str
    matched_text_redacted: str  # Matched text with PII stripped
    severity: str  # BLOCK | WARN


@dataclass(frozen=True)
class UnfairResult:
    gate_status: str  # PASSED | BLOCKED
    violations: list[UnfairRuleViolation]
    offending_employee_id: str | None
    evidence: dict[str, Any]


def _redact_text(text: str, max_len: int = 80) -> str:
    """Truncate matched text and strip potential PII (names, IDs)."""
    safe = text[:max_len]
    # Strip anything that looks like a Korean RRN, account number, or phone
    safe = re.sub(r"\d{6}-\d{7}", "[RRN]", safe)
    safe = re.sub(r"\d{10,14}", "[ACCT]", safe)
    return safe


def _check_definitive_language(message_text: str) -> UnfairRuleViolation | None:
    m = _DEFINITIVE_PATTERN.search(message_text)
    if m:
        return UnfairRuleViolation(
            rule_id=RULE_DEFINITIVE_LANGUAGE,
            matched_text_redacted=_redact_text(m.group(0)),
            severity="BLOCK",
        )
    return None


def _check_loss_guarantee(message_text: str) -> UnfairRuleViolation | None:
    m = _LOSS_GUARANTEE_PATTERN.search(message_text)
    if m:
        return UnfairRuleViolation(
            rule_id=RULE_LOSS_GUARANTEE,
            matched_text_redacted=_redact_text(m.group(0)),
            severity="BLOCK",
        )
    return None


def _check_risk_grade_over(
    customer: dict[str, Any], product: dict[str, Any]
) -> UnfairRuleViolation | None:
    try:
        c_grade = int(customer.get("risk_grade_code") or 0)
        p_grade = int(
            product.get("risk_grade_code") or product.get("risk_level_code") or 0
        )
    except (TypeError, ValueError):
        return None
    if p_grade > 0 and c_grade > 0 and p_grade > c_grade:
        return UnfairRuleViolation(
            rule_id=RULE_RISK_GRADE_OVER,
            matched_text_redacted=f"customer_grade={c_grade} product_grade={p_grade}",
            severity="BLOCK",
        )
    return None


def _check_offline_to_online(
    channel_code: str | None,
    last_face_to_face_seconds_ago: int | None,
    has_opt_in_audit: bool,
) -> UnfairRuleViolation | None:
    """Detect 대면→비대면 solicitation within 24h without opt-in audit (REG-02 §부당권유)."""
    online_channels = {"PHONE", "VIDEO", "WRITTEN"}
    if channel_code not in online_channels:
        return None
    if last_face_to_face_seconds_ago is None:
        return None
    within_window = last_face_to_face_seconds_ago < OFFLINE_TO_ONLINE_WINDOW_SECONDS
    if within_window and not has_opt_in_audit:
        return UnfairRuleViolation(
            rule_id=RULE_OFFLINE_TO_ONLINE_WINDOW,
            matched_text_redacted=(
                f"face_to_face_{last_face_to_face_seconds_ago}s_ago channel={channel_code}"
            ),
            severity="BLOCK",
        )
    return None


def check_unfair_solicitation(
    consultation: dict[str, Any],
    product: dict[str, Any],
    message_text: str,
    *,
    offending_employee_id: str | None = None,
    last_face_to_face_seconds_ago: int | None = None,
    has_opt_in_audit: bool = False,
) -> UnfairResult:
    """Run all four unfair-solicitation rules and return a consolidated result.

    Any BLOCK-severity violation sets ``gate_status=BLOCKED``.  All violations
    are recorded with their ``decision_rule_id`` for audit traceability.
    """
    violations: list[UnfairRuleViolation] = []

    for check_fn in (
        lambda: _check_definitive_language(message_text),
        lambda: _check_loss_guarantee(message_text),
        lambda: _check_risk_grade_over(
            consultation.get("customer") or {}, product
        ),
        lambda: _check_offline_to_online(
            consultation.get("channel_code"),
            last_face_to_face_seconds_ago,
            has_opt_in_audit,
        ),
    ):
        v = check_fn()
        if v is not None:
            violations.append(v)

    blocked = any(v.severity == "BLOCK" for v in violations)
    gate_status = "BLOCKED" if blocked else "PASSED"

    return UnfairResult(
        gate_status=gate_status,
        violations=list(violations),
        offending_employee_id=offending_employee_id,
        evidence={
            "gate_status": gate_status,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "matched_text_redacted": v.matched_text_redacted,
                    "severity": v.severity,
                }
                for v in violations
            ],
            "offending_employee_id": offending_employee_id,
        },
    )
