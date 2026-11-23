"""적합성 확인서 변경 연 1회 통지 (T221).

REG-02 §5 requires brokers to surface a "suitability confirmation update"
notice to every customer at least once per year. This module owns the
date-arithmetic, due-customer detection, and notice-payload composition
needed to drive the periodic batch job and to emit the
`SUITABILITY_UPDATE_NOTICE_SHOWN` audit row.

This module is dependency-free and deterministic — date inputs are
explicit (no `datetime.now()` calls inside business logic) so the daily
batch behaves identically across re-runs of the same input window.
"""

from __future__ import annotations

from datetime import date, timedelta

NOTICE_INTERVAL_DAYS: int = 365
"""Yearly cadence per REG-02 §5; centralised here for ADR-driven tuning."""

GRACE_DAYS: int = 14
"""Customers within this many days of their due-date appear in the
'due-soon' bucket so PB has lead time to acknowledge in-person."""


def days_until_notice_due(last_notice_at: date, today: date) -> int:
    """Return days remaining until the next yearly notice is due.

    Negative result = notice is overdue by that many days.
    """
    next_due = last_notice_at + timedelta(days=NOTICE_INTERVAL_DAYS)
    return (next_due - today).days


def is_notice_due(last_notice_at: date | None, today: date) -> bool:
    """True if a customer needs the yearly notice today.

    `last_notice_at=None` (no prior notice) is treated as due (new customer
    onboarding must include the suitability confirmation).
    """
    if last_notice_at is None:
        return True
    return days_until_notice_due(last_notice_at, today) <= 0


def is_notice_due_soon(last_notice_at: date | None, today: date) -> bool:
    """True if the notice falls due within GRACE_DAYS (and not already overdue)."""
    if last_notice_at is None:
        return False
    remaining = days_until_notice_due(last_notice_at, today)
    return 0 < remaining <= GRACE_DAYS


def classify(last_notice_at: date | None, today: date) -> str:
    """Return one of: 'overdue', 'due_today', 'due_soon', 'current', 'never_issued'."""
    if last_notice_at is None:
        return "never_issued"
    remaining = days_until_notice_due(last_notice_at, today)
    if remaining < 0:
        return "overdue"
    if remaining == 0:
        return "due_today"
    if remaining <= GRACE_DAYS:
        return "due_soon"
    return "current"


def build_notice_payload(
    *,
    customer_id: str,
    employee_id: str,
    today: date,
    last_notice_at: date | None,
    notice_channel: str = "internal_chat",
) -> dict[str, object]:
    """Compose the audit-grade payload for an issued notice.

    `notice_channel` is the canonical short code for how the customer was
    informed (e.g. internal_chat, branch_inperson, registered_mail).
    """
    if not customer_id or not employee_id:
        raise ValueError("customer_id and employee_id are required")
    status = classify(last_notice_at, today)
    return {
        "customer_id": customer_id,
        "employee_id": employee_id,
        "issued_on": today.strftime("%Y-%m-%d"),
        "previous_notice_at": last_notice_at.strftime("%Y-%m-%d") if last_notice_at else None,
        "next_due_on": (today + timedelta(days=NOTICE_INTERVAL_DAYS)).strftime("%Y-%m-%d"),
        "trigger_status": status,
        "notice_channel": notice_channel,
        "audit_action_code": "SUITABILITY_UPDATE_NOTICE_SHOWN",
    }


def partition_customers(
    customers: list[dict[str, object]],
    today: date,
) -> dict[str, list[dict[str, object]]]:
    """Bucket a list of {customer_id, last_notice_at} rows by classification.

    `customers` rows must carry at least `customer_id` (str) and
    `last_notice_at` (date | None).
    """
    buckets: dict[str, list[dict[str, object]]] = {
        "overdue": [],
        "due_today": [],
        "due_soon": [],
        "current": [],
        "never_issued": [],
    }
    for row in customers:
        last = row.get("last_notice_at")
        if last is not None and not isinstance(last, date):
            raise TypeError(
                f"last_notice_at must be date or None, got {type(last).__name__}"
            )
        status = classify(last, today)
        buckets[status].append(row)
    return buckets
