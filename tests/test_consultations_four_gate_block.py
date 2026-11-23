"""Wave-Audit-Defect-Fix A7 — PATCH /consultations status COMPLETED four-gate block.

Audit defect CR-7: PATCH /consultations/{id} accepted ``status_code=COMPLETED``
from the client payload without verifying the four-gate state, then audit-logged
``{"suitability_checked": True, "explanation_checked": True}`` as if the gates
had been confirmed. A PB could mark a consultation COMPLETED with no gate
ever evaluated, leaving misleading audit evidence.

Acceptance:
  * When at least one gate is not in {PASSED, ACKNOWLEDGED}, the handler raises
    409 Conflict before update_consultation is called.
  * 409 detail carries ``error_code="four_gate_not_passed"`` and lists the
    blocking gate names.
  * When all four gates are terminal, the handler proceeds and the audit detail
    serialises the actual ``gate_name → gate_status`` map instead of hardcoded
    booleans.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from apps.api.harness.api.routers import consultations as consultations_router
from apps.api.harness.services.four_gate import (
    GATE_NAMES,
    TERMINAL_STATUSES,
    aggregate_gate_result,
)


def test_router_imports_four_gate_helpers() -> None:
    assert "aggregate_gate_result" in consultations_router.__dict__, (
        "router module must import aggregate_gate_result to enforce the gate"
    )
    assert "suitability_repo" in consultations_router.__dict__, (
        "router module must import suitability_repo.list_gates to fetch gate rows"
    )


def test_router_source_blocks_completed_when_not_all_passed() -> None:
    source = Path(consultations_router.__file__).read_text(encoding="utf-8")
    assert 'payload.get("status_code") == "COMPLETED"' in source, (
        "handler must gate the four-gate check on PATCH payload status_code=COMPLETED"
    )
    assert "if not gate_result.all_passed" in source, (
        "handler must short-circuit when aggregate_gate_result reports !all_passed"
    )
    assert "four_gate_not_passed" in source, (
        "409 detail must carry the canonical error_code"
    )
    assert "blocking_gates" in source, (
        "409 detail must list which gates are blocking so the UI can guide the PB"
    )
    assert (
        "detail={\"four_gate\": four_gate_payload or {}}" in source
        or 'detail={"four_gate": four_gate_payload or {}}' in source
    ), (
        "audit_log detail must persist the real gate state, not hardcoded True"
    )


def test_blocking_gates_when_some_pending() -> None:
    # Only suitability passed → 3 gates still PENDING → not all_passed
    gate_rows = [
        {"gate_name": "suitability", "gate_status": "PASSED", "gate_evidence_json": {}}
    ]
    result = aggregate_gate_result("c-1", gate_rows)
    assert result.all_passed is False
    blocking = [
        g.gate_name for g in result.gates
        if g.gate_status not in TERMINAL_STATUSES
    ]
    assert set(blocking) == {"explanation", "unfair_solicitation", "marketing"}


def test_all_passed_when_every_gate_terminal() -> None:
    rows = [
        {"gate_name": name, "gate_status": "PASSED", "gate_evidence_json": {}}
        for name in GATE_NAMES
    ]
    assert aggregate_gate_result("c-2", rows).all_passed is True


def test_audit_detail_no_hardcoded_true_in_handler() -> None:
    source = Path(consultations_router.__file__).read_text(encoding="utf-8")
    # The old defect:  detail={"suitability_checked": True, "explanation_checked": True}
    # must no longer appear after the A7 fix.
    assert '{"suitability_checked": True, "explanation_checked": True}' not in source, (
        "hardcoded True audit detail must be removed — it falsely claimed both "
        "checklist gates were confirmed regardless of actual gate state"
    )


def test_handler_signature_unchanged() -> None:
    # Make sure A7 did not accidentally change the public PATCH signature.
    sig = inspect.signature(consultations_router.update_consultation)
    assert {"request", "consultation_id", "payload", "authorization"} <= set(
        sig.parameters
    )
