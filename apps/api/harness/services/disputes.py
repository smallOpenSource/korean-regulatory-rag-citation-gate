"""Dispute case service — REG-01 T226 / 금소법 §36 분쟁조정 30-day scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VALID_DISPUTE_TYPES: tuple[str, ...] = ("부당권유", "광고", "계약", "기타")
VALID_STATUSES: tuple[str, ...] = ("OPEN", "RESPONDED", "RESOLVED", "EXPIRED")

# 30-day response window per 금소법 §36 (placeholder; APScheduler wired in Stage 7 RUN-09)
RESPONSE_WINDOW_DAYS = 30


@dataclass(frozen=True)
class DisputeOpenResult:
    dispute_type: str
    status: str
    response_window_days: int
    note: str


def validate_dispute_open(payload: dict[str, Any]) -> DisputeOpenResult:
    """Validate dispute open payload and return a structured result.

    The 30-day response timer is stored as ``response_due_at`` (a generated
    column in the DB) and displayed in the UI.  No scheduler is wired in Wave 2
    (Stage 7 RUN-09 will attach APScheduler for expiry transitions).
    """
    dispute_type = str(payload.get("dispute_type") or "기타")
    if dispute_type not in VALID_DISPUTE_TYPES:
        dispute_type = "기타"

    return DisputeOpenResult(
        dispute_type=dispute_type,
        status="OPEN",
        response_window_days=RESPONSE_WINDOW_DAYS,
        note="30-day timer is stored in response_due_at (Stage 7 RUN-09 wires APScheduler).",
    )


def validate_dispute_resolve(payload: dict[str, Any]) -> str:
    """Return validated resolution status."""
    resolution = str(payload.get("resolution_status") or "RESOLVED")
    if resolution not in ("RESOLVED", "RESPONDED"):
        resolution = "RESOLVED"
    return resolution
