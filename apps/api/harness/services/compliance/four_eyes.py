"""4-eyes (이중확인) 승인 흐름 — standardized state machine (T258).

REG-03 §5 requires every consultation completion, every outbound email send,
and every high-risk transaction simulation to pass through a two-person
approval gate where the second approver MUST differ from the first. This
module owns the state machine + invariants so callers (consultation
complete, email_drafts approve, simulation high-risk) can call a single
`request_approval` / `approve` / `reject` API and emit a uniform
`four_eyes_*` audit code series.

State machine:

    DRAFTED ──(first_approve)──▶ FIRST_APPROVED
       │                              │
       │                       (second_approve)
       │                              ▼
       │                         SECOND_APPROVED
       │                              │
       │                          (finalize)
       │                              ▼
       └──(reject)─▶ REJECTED ◀───── APPROVED

Invariants:
  - first_approver_id MUST NOT equal second_approver_id (the core 4-eyes principle)
  - first_approver_id MUST NOT equal originator_id (initial draft author)
  - reject is allowed from any non-terminal state
  - APPROVED and REJECTED are terminal
"""

from __future__ import annotations

from datetime import UTC, datetime

# ─── States + transitions ─────────────────────────────────────────────────────

VALID_STATES: frozenset[str] = frozenset({
    "DRAFTED",
    "FIRST_APPROVED",
    "SECOND_APPROVED",
    "APPROVED",
    "REJECTED",
})

TERMINAL_STATES: frozenset[str] = frozenset({"APPROVED", "REJECTED"})

# Allowed scope codes — every 4-eyes request must declare its scope so audit
# review can filter by surface (consultation vs send vs trade vs other).
VALID_SCOPES: frozenset[str] = frozenset({
    "consultation_complete",
    "email_send",
    "high_risk_transaction",
})


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── Public API ───────────────────────────────────────────────────────────────


def request_approval(
    *,
    scope: str,
    originator_id: str,
    subject_ref: str,
    now: str | None = None,
) -> dict[str, object]:
    """Open a new 4-eyes approval record in DRAFTED state.

    `subject_ref` is the opaque id of the artifact being approved
    (consultation_id, email_draft_id, simulation_id).
    """
    if scope not in VALID_SCOPES:
        raise ValueError(f"unknown scope: {scope!r}")
    if not originator_id or not subject_ref:
        raise ValueError("originator_id and subject_ref are required")
    return {
        "state": "DRAFTED",
        "scope": scope,
        "originator_id": originator_id,
        "subject_ref": subject_ref,
        "first_approver_id": None,
        "second_approver_id": None,
        "rejected_by": None,
        "rejection_reason": "",
        "history": [{
            "event": "drafted",
            "actor_id": originator_id,
            "at": now or _utc_now_iso(),
        }],
        "audit_action_code": "four_eyes_drafted",
    }


def first_approve(
    record: dict[str, object],
    *,
    approver_id: str,
    now: str | None = None,
) -> dict[str, object]:
    """Apply the first approval. Returns updated copy."""
    _require_state(record, "DRAFTED")
    if not approver_id:
        raise ValueError("approver_id required")
    if approver_id == record["originator_id"]:
        raise ValueError("first approver must differ from originator (4-eyes)")
    updated = _clone(record)
    updated["state"] = "FIRST_APPROVED"
    updated["first_approver_id"] = approver_id
    _append_history(updated, "first_approved", approver_id, now)
    updated["audit_action_code"] = "four_eyes_first_approved"
    return updated


def second_approve(
    record: dict[str, object],
    *,
    approver_id: str,
    now: str | None = None,
) -> dict[str, object]:
    """Apply the second approval; enforces approver ≠ first approver."""
    _require_state(record, "FIRST_APPROVED")
    if not approver_id:
        raise ValueError("approver_id required")
    if approver_id == record["first_approver_id"]:
        raise ValueError("second approver MUST differ from first (4-eyes)")
    if approver_id == record["originator_id"]:
        raise ValueError("second approver MUST differ from originator (4-eyes)")
    updated = _clone(record)
    updated["state"] = "SECOND_APPROVED"
    updated["second_approver_id"] = approver_id
    _append_history(updated, "second_approved", approver_id, now)
    updated["audit_action_code"] = "four_eyes_second_approved"
    return updated


def finalize(
    record: dict[str, object],
    *,
    now: str | None = None,
) -> dict[str, object]:
    """Mark the record APPROVED after both eyes have signed."""
    _require_state(record, "SECOND_APPROVED")
    updated = _clone(record)
    updated["state"] = "APPROVED"
    _append_history(updated, "approved", None, now)
    updated["audit_action_code"] = "four_eyes_approved"
    return updated


def reject(
    record: dict[str, object],
    *,
    rejector_id: str,
    reason: str,
    now: str | None = None,
) -> dict[str, object]:
    """Reject the record from any non-terminal state."""
    if record["state"] in TERMINAL_STATES:
        raise ValueError(f"cannot reject from terminal state {record['state']!r}")
    if not rejector_id or not reason:
        raise ValueError("rejector_id and reason required")
    updated = _clone(record)
    updated["state"] = "REJECTED"
    updated["rejected_by"] = rejector_id
    updated["rejection_reason"] = reason
    _append_history(updated, "rejected", rejector_id, now)
    updated["audit_action_code"] = "four_eyes_rejected"
    return updated


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _clone(record: dict[str, object]) -> dict[str, object]:
    cloned = dict(record)
    history = record.get("history")
    cloned["history"] = list(history) if isinstance(history, list) else []
    return cloned


def _require_state(record: dict[str, object], expected: str) -> None:
    actual = record.get("state")
    if actual != expected:
        raise ValueError(f"invalid transition: state={actual!r}, expected={expected!r}")


def _append_history(
    record: dict[str, object],
    event: str,
    actor_id: str | None,
    now: str | None,
) -> None:
    history = record.get("history")
    if not isinstance(history, list):
        history = []
        record["history"] = history
    history.append({
        "event": event,
        "actor_id": actor_id,
        "at": now or _utc_now_iso(),
    })
