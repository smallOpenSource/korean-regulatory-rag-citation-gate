"""REG-04 quarantine readiness dashboard surface (Stage 3, ADR-005).

Surfaces quarantine telemetry from document_chunks.quarantine_flag (V032)
for the dual-LLM quarantine pipeline introduced in Stage 3.
"""

from __future__ import annotations

from typing import Any

from .core import BLOCKED, READY


def build_quarantine_readiness_payload(metrics: dict[str, Any]) -> dict[str, Any]:
    """Return a quarantine-readiness summary for the dashboard surface.

    Driven entirely by persisted DB metrics so the payload can be consumed by
    both the API router and offline validators without live DB access.
    """

    quarantine_flag_count = int(metrics.get("quarantine_flag_count") or 0)
    quarantine_reviewed_count = int(metrics.get("quarantine_reviewed_count") or 0)
    injection_event_count = int(metrics.get("injection_event_count") or 0)
    schema_ready = int(metrics.get("quarantine_schema_ready") or 0) > 0

    status_code = READY if schema_ready else BLOCKED
    return {
        "status_code": status_code,
        "schema_ready": schema_ready,
        "quarantine_flag_count": quarantine_flag_count,
        "quarantine_reviewed_count": quarantine_reviewed_count,
        "injection_event_count": injection_event_count,
        "message": (
            "REG-04 quarantine schema is present; telemetry surface is active."
            if schema_ready
            else (
                "REG-04 quarantine schema is not yet applied; "
                "V032 migration required before quarantine telemetry is available."
            )
        ),
    }
