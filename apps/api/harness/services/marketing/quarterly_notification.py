"""분기 통지 발송 시뮬 — quarterly customer-notification orchestrator (T257).

Composes a draft notification email, walks it through the REG-03 §5 sequence
of compliance + 4-gate + 4-eyes checks, then marks it sent in simulation
mode (NO real SMTP traffic — the actual mail send happens in
``services/marketing/core.py`` `run_marketing_gate` when wired upstream).

This module reuses:
  - T200 `pii_masking.mask_pii`             — external-recipient redaction
  - T205 `compliance.reasoning_lint`        — unfair-practice keyword block
  - T221 `suitability_update_notice.classify` — confirms the customer is due
  - T235 `readability.evaluate_ai_output`   — Lee-Park ≥ 60 gate
  - T258 `compliance.four_eyes` state machine — second-eye approval
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from apps.api.harness.services.compliance.four_eyes import (
    request_approval as fe_request,
    first_approve as fe_first,
    second_approve as fe_second,
    finalize as fe_finalize,
)
from apps.api.harness.services.compliance.pii_masking import is_external_domain, mask_pii
from apps.api.harness.services.compliance.reasoning_lint import lint_reasoning
from apps.api.harness.services.compliance.suitability_update_notice import classify
from apps.api.harness.services.readability import evaluate_ai_output


READABILITY_THRESHOLD: float = 60.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compose_notification(
    *,
    customer_id: str,
    customer_email: str,
    employee_id: str,
    quarter: str,
    subject: str,
    body: str,
    last_notice_at: date | None,
    today: date,
    internal_domains: tuple[str, ...] = (),
) -> dict[str, object]:
    """Produce a quarterly-notification draft with all gating context."""
    if not customer_id or not employee_id or not subject or not body:
        raise ValueError("customer_id, employee_id, subject, body required")
    if not customer_email:
        raise ValueError("customer_email required")
    return {
        "state": "DRAFTED",
        "customer_id": customer_id,
        "customer_email": customer_email,
        "employee_id": employee_id,
        "quarter": quarter,
        "subject": subject,
        "body": body,
        "is_external": is_external_domain(customer_email, internal_domains),
        "due_status": classify(last_notice_at, today),
        "today_iso": today.strftime("%Y-%m-%d"),
        "drafted_at": _utc_now_iso(),
        "audit_action_code": "quarterly_notification_drafted",
    }


def apply_pii_mask(record: dict[str, object]) -> dict[str, object]:
    """Mask PII in subject+body when recipient is external-domain.

    Internal-domain recipients keep the raw payload (audit reviewers see
    full text); external-domain recipients get masked text + a report
    suitable for `info_leak_warning_shown` audit row emission.
    """
    if record.get("state") != "DRAFTED":
        raise ValueError(f"masking requires state=DRAFTED, got {record.get('state')!r}")
    body = record.get("body")
    subject = record.get("subject")
    if not isinstance(body, str) or not isinstance(subject, str):
        raise ValueError("subject and body must be strings")

    if not record.get("is_external"):
        updated = dict(record)
        updated["pii_report"] = {"masked": False, "reason": "internal_domain"}
        updated["audit_action_code"] = "quarterly_notification_pii_skipped_internal"
        return updated

    body_report = mask_pii(body)
    subject_report = mask_pii(subject)
    updated = dict(record)
    updated["body"] = body_report["masked_text"]
    updated["subject"] = subject_report["masked_text"]
    updated["pii_report"] = {
        "masked": True,
        "body_categories_hit": body_report["category_counts"],
        "subject_categories_hit": subject_report["category_counts"],
    }
    updated["audit_action_code"] = "quarterly_notification_pii_masked"
    return updated


def run_four_gates(record: dict[str, object]) -> dict[str, object]:
    """Apply readability + reasoning-lint + suitability-due + recipient gates.

    The "4 gates" here mirror the REG-03 §5 marketing gate set without
    invoking the live `services/marketing/core.run_marketing_gate` (which
    needs Azure). Each gate produces a pass/fail boolean + reason code.
    """
    body = record.get("body")
    if not isinstance(body, str):
        raise ValueError("body must be string at gate stage")

    readability = evaluate_ai_output(body, threshold=READABILITY_THRESHOLD)
    reasoning = lint_reasoning(body)

    due_status = record.get("due_status")
    suitability_due = due_status in {"overdue", "due_today", "due_soon", "never_issued"}
    recipient_valid = bool(record.get("customer_email"))

    gates = {
        "readability": {"passed": bool(readability["passes"]), "score": readability["score"]},
        "reasoning": {"passed": not reasoning["flagged"], "violations": reasoning["violations"]},
        "suitability_due": {"passed": suitability_due, "due_status": due_status},
        "recipient": {"passed": recipient_valid},
    }
    all_passed = all(g["passed"] for g in gates.values())

    updated = dict(record)
    updated["gates"] = gates
    updated["all_gates_passed"] = all_passed
    if all_passed:
        updated["state"] = "GATES_PASSED"
        updated["audit_action_code"] = "quarterly_notification_gates_passed"
    else:
        updated["state"] = "GATES_BLOCKED"
        updated["audit_action_code"] = "quarterly_notification_gates_blocked"
    return updated


def request_four_eyes(record: dict[str, object]) -> dict[str, object]:
    """Open the 4-eyes record once 4 gates pass."""
    if record.get("state") != "GATES_PASSED":
        raise ValueError(
            f"4-eyes requires state=GATES_PASSED, got {record.get('state')!r}"
        )
    employee_id = record.get("employee_id")
    customer_id = record.get("customer_id")
    if not isinstance(employee_id, str) or not isinstance(customer_id, str):
        raise ValueError("employee_id and customer_id must be strings")
    fe = fe_request(scope="email_send", originator_id=employee_id, subject_ref=customer_id)
    updated = dict(record)
    updated["four_eyes"] = fe
    return updated


def approve_first(record: dict[str, object], *, approver_id: str) -> dict[str, object]:
    fe = record.get("four_eyes")
    if not isinstance(fe, dict):
        raise ValueError("four_eyes record missing")
    updated_fe = fe_first(fe, approver_id=approver_id)
    updated = dict(record)
    updated["four_eyes"] = updated_fe
    return updated


def approve_second(record: dict[str, object], *, approver_id: str) -> dict[str, object]:
    fe = record.get("four_eyes")
    if not isinstance(fe, dict):
        raise ValueError("four_eyes record missing")
    updated_fe = fe_second(fe, approver_id=approver_id)
    final_fe = fe_finalize(updated_fe)
    updated = dict(record)
    updated["four_eyes"] = final_fe
    return updated


def simulate_send(record: dict[str, object]) -> dict[str, object]:
    """Mark the notification as 'sent' in simulation mode after both eyes approve."""
    fe = record.get("four_eyes")
    if not isinstance(fe, dict) or fe.get("state") != "APPROVED":
        raise ValueError("simulate_send requires 4-eyes APPROVED")
    updated = dict(record)
    updated["state"] = "SENT_SIMULATION"
    updated["sent_at"] = _utc_now_iso()
    updated["audit_action_code"] = "quarterly_notification_sent_simulation"
    return updated
