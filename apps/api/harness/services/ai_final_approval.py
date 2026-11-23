"""Employee final-approval gate for AI outputs (T231, REG-02 §5 보조수단성).

Wraps the ``ai_outputs.employee_final_approval`` column added in V039. The 7-agent
contract is non-negotiable: every customer-facing path must verify the row was
explicitly approved by a logged-in PB/WM/BRANCH_MANAGER before delivery.

Pure SQL + raw asyncpg, no ORM. Caller threads the actor through so audit chain
references the human reviewer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class FinalApprovalResult:
    approved: bool
    employee_final_approval_by: str | None
    employee_final_approval_at: str | None


async def mark_final_approval(
    conn: Any,
    *,
    ai_output_id: str,
    approver_employee_id: str,
) -> FinalApprovalResult:
    """Set employee_final_approval=true; idempotent on the second call."""
    # sql_id: ai_outputs_set_final_approval
    row = await conn.fetchrow(
        """/* sql_id: ai_outputs_set_final_approval */
        UPDATE ai_outputs
           SET employee_final_approval = TRUE,
               employee_final_approval_by = $1,
               employee_final_approval_at = NOW()
         WHERE id = $2
        RETURNING employee_final_approval, employee_final_approval_by, employee_final_approval_at""",
        approver_employee_id,
        ai_output_id,
    )
    if row is None:
        return FinalApprovalResult(approved=False, employee_final_approval_by=None, employee_final_approval_at=None)
    return FinalApprovalResult(
        approved=bool(row["employee_final_approval"]),
        employee_final_approval_by=str(row["employee_final_approval_by"]) if row["employee_final_approval_by"] else None,
        employee_final_approval_at=row["employee_final_approval_at"].isoformat() if row["employee_final_approval_at"] else None,
    )


async def revoke_final_approval(conn: Any, *, ai_output_id: str) -> FinalApprovalResult:
    """Revert employee_final_approval to false (recall scenario)."""
    # sql_id: ai_outputs_revoke_final_approval
    row = await conn.fetchrow(
        """/* sql_id: ai_outputs_revoke_final_approval */
        UPDATE ai_outputs
           SET employee_final_approval = FALSE,
               employee_final_approval_by = NULL,
               employee_final_approval_at = NULL
         WHERE id = $1
        RETURNING employee_final_approval""",
        ai_output_id,
    )
    if row is None:
        return FinalApprovalResult(approved=False, employee_final_approval_by=None, employee_final_approval_at=None)
    return FinalApprovalResult(approved=False, employee_final_approval_by=None, employee_final_approval_at=None)


async def require_final_approval(conn: Any, *, ai_output_id: str) -> bool:
    """Return True if the row is approved; False otherwise.

    Customer-facing delivery code calls this before returning AI output. Frontend
    badge keys off the same column so PB sees ``초안·검토용`` until approved.
    """
    # sql_id: ai_outputs_check_final_approval
    row = await conn.fetchrow(
        """/* sql_id: ai_outputs_check_final_approval */
        SELECT employee_final_approval FROM ai_outputs WHERE id = $1""",
        ai_output_id,
    )
    if row is None:
        return False
    return bool(row["employee_final_approval"])
