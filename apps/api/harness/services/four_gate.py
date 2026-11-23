"""Four-gate compliance aggregator — REG-02 T15 / REG-03 T242."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GATE_NAMES: tuple[str, ...] = (
    "suitability",
    "explanation",
    "unfair_solicitation",
    "marketing",
)

TERMINAL_STATUSES: frozenset[str] = frozenset({"PASSED", "ACKNOWLEDGED"})


@dataclass(frozen=True)
class GateState:
    gate_name: str
    gate_status: str  # PENDING | PASSED | BLOCKED | ACKNOWLEDGED
    gate_evidence_json: dict[str, Any]
    gate_acknowledged_at: Any | None  # TIMESTAMPTZ or None


@dataclass(frozen=True)
class FourGateResult:
    consultation_id: str
    gates: list[GateState]
    all_passed: bool


def aggregate_gate_result(
    consultation_id: str,
    gate_rows: list[dict[str, Any]],
) -> FourGateResult:
    """Aggregate DB gate rows for a consultation into a ``FourGateResult``.

    Missing gate rows default to ``PENDING`` so callers always receive the
    full four-gate picture regardless of which gates have been evaluated.
    """
    gate_map: dict[str, dict[str, Any]] = {row["gate_name"]: row for row in gate_rows}
    gates: list[GateState] = []

    for gate_name in GATE_NAMES:
        row = gate_map.get(gate_name)
        if row:
            gates.append(GateState(
                gate_name=gate_name,
                gate_status=row["gate_status"],
                gate_evidence_json=row.get("gate_evidence_json") or {},
                gate_acknowledged_at=row.get("gate_acknowledged_at"),
            ))
        else:
            gates.append(GateState(
                gate_name=gate_name,
                gate_status="PENDING",
                gate_evidence_json={},
                gate_acknowledged_at=None,
            ))

    all_passed = all(g.gate_status in TERMINAL_STATUSES for g in gates)
    return FourGateResult(
        consultation_id=consultation_id,
        gates=gates,
        all_passed=all_passed,
    )


def gate_state_to_dict(gate: GateState) -> dict[str, Any]:
    """Serialise a GateState for JSON response."""
    ack_at = gate.gate_acknowledged_at
    return {
        "gate_name": gate.gate_name,
        "gate_status": gate.gate_status,
        "gate_evidence_json": gate.gate_evidence_json,
        "gate_acknowledged_at": ack_at.isoformat() if ack_at else None,
    }
