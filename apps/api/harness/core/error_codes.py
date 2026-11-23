"""Single-source-of-truth error codes for sanitized HTTP error responses (REG-05 T294)."""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Enumerated error codes returned to API clients.

    Never expose raw asyncpg messages, stack traces, or provider response bodies.
    All 5xx responses collapse to ``internal_error`` or ``service_unavailable``.
    """

    bad_request = "bad_request"
    invalid_credentials = "invalid_credentials"
    token_invalid = "token_invalid"
    token_expired = "token_expired"
    forbidden = "forbidden"
    not_found = "not_found"
    rate_limited = "rate_limited"
    validation_error = "validation_error"
    internal_error = "internal_error"
    service_unavailable = "service_unavailable"
    # Wave-Audit-Defect-Fix B2: structured codes that previously leaked as
    # raw HTTPException(detail="...") strings.
    external_provider_error = "external_provider_error"  # A4 — Azure/SMTP fail
    marketing_lint_failed = "marketing_lint_failed"      # email lint reject
    redaction_blocked = "redaction_blocked"              # output-side sanitizer block
    # Cycle Z5 B.1 additive — codes that were buried inside
    # HTTPException(detail={...}) dicts and stringified by the handler.
    four_gate_not_passed = "four_gate_not_passed"                # 409 consultation gating
    # Cycle Z5 B.2 (ADR-011) Idempotency-Key middleware additive codes.
    idempotency_key_required = "idempotency_key_required"                  # 409 missing header
    idempotency_key_in_flight = "idempotency_key_in_flight"                # 409 concurrent retry
    idempotency_key_payload_mismatch = "idempotency_key_payload_mismatch"  # 422 same key, different body
    idempotency_key_invalid = "idempotency_key_invalid"  # 400 malformed (non-UUID) key
    # ADR-020 — house_view activation would leave two live views (legacy↔lifecycle).
    house_view_single_live_invariant = "house_view_single_live_invariant"  # 409
