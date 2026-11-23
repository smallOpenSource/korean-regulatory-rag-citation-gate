"""Aftercare quarterly queue service (T244, T257)."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from apps.api.harness.core.rbac import ActorContext


def parse_quarter(quarter_code: str) -> tuple[int, int]:
    """Parse 'YYYYQN' into (year, quarter_number). Raises ValueError on bad format."""
    match = re.fullmatch(r"(\d{4})Q([1-4])", quarter_code.strip().upper())
    if not match:
        raise ValueError(
            f"quarter_code must be in YYYYQN format (e.g. 2025Q2), got: {quarter_code!r}"
        )
    return int(match.group(1)), int(match.group(2))


def quarter_date_range(quarter_code: str) -> tuple[date, date]:
    """Return the (start_date, end_date) of the given quarter."""
    year, q = parse_quarter(quarter_code)
    first_month = (q - 1) * 3 + 1
    start = date(year, first_month, 1)
    end_month = first_month + 2
    if end_month == 12:
        end = date(year, 12, 31)
    elif end_month in (3, 6, 9):
        end = date(year, end_month, 30)
    else:
        end = date(year, end_month, 31)
    return start, end


async def build_quarterly_queue(
    connection: Any,
    quarter_code: str,
    *,
    actor: ActorContext,
) -> list[dict[str, Any]]:
    """Return aftercare events due in the given quarter, scoped to the actor.

    Queries ``aftercare_events`` for PENDING/OPEN events whose ``due_date``
    falls inside the quarter's date range.  Scope follows the standard
    customer-scope contract: ADMIN sees all, PB sees their assigned
    customers, WM/BRANCH_MANAGER see their branch.

    UltraQA cycle 5 S23: the prior version omitted the actor scope and
    returned every customer's events to every PB, which breaks the data
    boundary contract from SEC-02 / REG-05.
    """
    from apps.api.harness.core.db import fetch_all
    from apps.api.harness.repositories.common import rows_to_dicts

    start, end = quarter_date_range(quarter_code)

    SQL = """
/* sql_id: aftercare_quarterly_queue */
SELECT a.id, a.customer_id, c.customer_name, a.employee_id,
       a.event_type_code, a.event_date, a.status_code,
       a.quarter_code, a.due_date, a.notes, a.completion_notes,
       a.resolved_at, a.created_at, a.updated_at
FROM aftercare_events a
JOIN customers c ON c.id = a.customer_id
WHERE a.status_code IN ('PENDING', 'OPEN', 'IN_PROGRESS')
  AND (
        a.due_date BETWEEN $1::date AND $2::date
        OR (a.quarter_code = $3 AND a.due_date IS NULL)
      )
  AND (
        $4::varchar = 'ADMIN'
        OR ($4::varchar = 'PB' AND c.assigned_pb_id = $5::uuid)
        OR ($4::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $6::uuid)
      )
ORDER BY a.due_date NULLS LAST, a.event_type_code, c.customer_name;
"""
    rows = await fetch_all(
        connection,
        SQL,
        start,
        end,
        quarter_code,
        actor.role_code,
        actor.employee_id,
        actor.branch_id,
    )
    return rows_to_dicts(rows)


def aftercare_email_draft_payload(
    aftercare_event: dict[str, Any],
    *,
    employee_id: str,
    quarter_code: str,
) -> dict[str, Any]:
    """Build an email_draft creation payload for T257 분기 통지.

    Returned dict is passed to the email_draft creation endpoint / service
    (worker-hotel chain).
    """
    customer_id = str(aftercare_event.get("customer_id") or "")
    event_type = str(aftercare_event.get("event_type_code") or "REVIEW_DUE")

    subject_map = {
        "MATURITY_DUE": f"[분기 통지] {quarter_code} 만기 도래 안내",
        "KI_TRIGGERED": f"[분기 통지] {quarter_code} 녹인 발생 안내",
        "DRAWDOWN_BREACH": f"[분기 통지] {quarter_code} 손실 한도 초과 안내",
        "REVIEW_DUE": f"[분기 통지] {quarter_code} 정기 점검 안내",
        "NO_CONTACT": f"[분기 통지] {quarter_code} 고객 연락 재개 요청",
    }
    subject = subject_map.get(event_type, f"[분기 통지] {quarter_code} 사후 관리 안내")

    body_lines = [
        "안녕하세요,",
        "",
        f"{quarter_code} 분기 사후 관리 대상으로 선정되어 안내 드립니다.",
        "",
        f"유형: {event_type}",
        f"사건 번호: {aftercare_event.get('id', '')}",
        "",
        "상세 내용은 담당 PB에게 문의하여 주시기 바랍니다.",
        "",
        "감사합니다.",
    ]

    return {
        "customer_id": customer_id,
        "employee_id": employee_id,
        "subject": subject,
        "body_text": "\n".join(body_lines),
        "draft_type_code": "AFTERCARE_QUARTERLY",
        "resource_type": "aftercare_event",
        "resource_id": str(aftercare_event.get("id") or ""),
        "quarter_code": quarter_code,
    }
