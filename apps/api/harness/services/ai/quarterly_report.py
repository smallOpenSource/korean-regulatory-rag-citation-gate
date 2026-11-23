"""AI 분기 리포트 초안 + 컴플라이언스 자동검토 + 인간 승인 게이트 (T246).

Orchestrates the lifecycle of an AI-generated quarterly customer report:

  1. `compose_draft`        — assemble a draft record from a generated body
  2. `run_compliance_check` — apply readability + reasoning-lint gates
  3. `mark_approved`        — record human PB/WM approval (post-4-eyes)
  4. `mark_blocked`         — record auto-block when compliance gate fails

The AI text-generation call itself lives upstream (e.g. routers/ai.py
invokes Azure GPT5). This module owns the post-generation governance:
compliance gating, audit-code emission, and state-machine integrity.
"""

from __future__ import annotations

from datetime import UTC, datetime

from apps.api.harness.services.compliance.reasoning_lint import lint_reasoning
from apps.api.harness.services.readability import evaluate_ai_output

READABILITY_THRESHOLD: float = 60.0
"""Per BACKLOG T235 — Lee-Park ≥ 60 is the AI-output evaluation floor."""

VALID_STATES: frozenset[str] = frozenset({
    "DRAFTED", "COMPLIANCE_OK", "COMPLIANCE_BLOCKED", "APPROVED",
})


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def compose_draft(
    *,
    customer_id: str,
    employee_id: str,
    quarter: str,
    body: str,
    ai_model_name: str = "gpt5-mini",
    now: str | None = None,
) -> dict[str, object]:
    """Assemble the initial draft record from a generated body.

    `quarter` is a YYYYQn label (e.g. "2026Q2"). `body` is the raw AI
    text — compliance gating is the next step (`run_compliance_check`).
    """
    if not customer_id or not employee_id or not quarter or not body:
        raise ValueError("customer_id, employee_id, quarter, body are required")
    if not _is_valid_quarter(quarter):
        raise ValueError(f"quarter must be YYYYQn (e.g. 2026Q2), got {quarter!r}")
    return {
        "state": "DRAFTED",
        "customer_id": customer_id,
        "employee_id": employee_id,
        "quarter": quarter,
        "body": body,
        "ai_model_name": ai_model_name,
        "drafted_at": now or _utc_now_iso(),
        "compliance_result": None,
        "approved_by": None,
        "approved_at": None,
        "blocked_reason_codes": [],
        "audit_action_code": "quarterly_report_drafted",
    }


def run_compliance_check(
    record: dict[str, object],
    *,
    now: str | None = None,
) -> dict[str, object]:
    """Apply readability + reasoning-lint gates; transition state accordingly.

    Pass criteria:
      - readability score ≥ READABILITY_THRESHOLD (60)
      - reasoning_lint produces flagged == False
    """
    if record.get("state") != "DRAFTED":
        raise ValueError(f"compliance check requires state=DRAFTED, got {record.get('state')!r}")
    body = record.get("body")
    if not isinstance(body, str):
        raise ValueError("record.body must be a string")

    readability = evaluate_ai_output(body, threshold=READABILITY_THRESHOLD)
    reasoning = lint_reasoning(body)

    blocked: list[str] = []
    if not readability["passes"]:
        blocked.append("READABILITY_BELOW_THRESHOLD")
    if reasoning["flagged"]:
        blocked.append("UNFAIR_PRACTICE_DETECTED")

    updated = dict(record)
    updated["compliance_result"] = {
        "readability": readability,
        "reasoning": reasoning,
        "checked_at": now or _utc_now_iso(),
    }
    updated["blocked_reason_codes"] = blocked

    if blocked:
        updated["state"] = "COMPLIANCE_BLOCKED"
        updated["audit_action_code"] = "quarterly_report_blocked"
    else:
        updated["state"] = "COMPLIANCE_OK"
        updated["audit_action_code"] = "quarterly_report_compliance_ok"
    return updated


def mark_approved(
    record: dict[str, object],
    *,
    approver_id: str,
    now: str | None = None,
) -> dict[str, object]:
    """Human PB/WM approval after compliance gate passes."""
    if record.get("state") != "COMPLIANCE_OK":
        raise ValueError(
            f"approval requires state=COMPLIANCE_OK, got {record.get('state')!r}"
        )
    if not approver_id:
        raise ValueError("approver_id required")
    if approver_id == record.get("employee_id"):
        # 4-eyes: drafting PB cannot self-approve their own AI output
        raise ValueError("approver_id MUST differ from drafting employee_id (4-eyes)")
    updated = dict(record)
    updated["state"] = "APPROVED"
    updated["approved_by"] = approver_id
    updated["approved_at"] = now or _utc_now_iso()
    updated["audit_action_code"] = "quarterly_report_approved"
    return updated


def mark_blocked(
    record: dict[str, object],
    *,
    reason_codes: list[str],
    blocker_id: str = "",
    now: str | None = None,
) -> dict[str, object]:
    """Manually block a draft (e.g. on supervisor review)."""
    if record.get("state") in {"APPROVED"}:
        raise ValueError("cannot block an already-approved report")
    if not reason_codes:
        raise ValueError("reason_codes required")
    updated = dict(record)
    updated["state"] = "COMPLIANCE_BLOCKED"
    existing = updated.get("blocked_reason_codes")
    base = list(existing) if isinstance(existing, list) else []
    updated["blocked_reason_codes"] = base + [c for c in reason_codes if c not in base]
    updated["blocked_by"] = blocker_id
    updated["blocked_at"] = now or _utc_now_iso()
    updated["audit_action_code"] = "quarterly_report_blocked"
    return updated


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _is_valid_quarter(quarter: str) -> bool:
    """Validate YYYYQn (1-4) format."""
    if len(quarter) != 6:
        return False
    if not quarter[:4].isdigit():
        return False
    if quarter[4] != "Q":
        return False
    if quarter[5] not in {"1", "2", "3", "4"}:
        return False
    return True
