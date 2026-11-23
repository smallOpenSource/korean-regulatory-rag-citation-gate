"""Synthetic consent service — REG-01 신용정보법 §32/§37/§38 + T214-T217, T229.

All records are synthetic (synthetic=true enforced at DB CHECK constraint).
Responses always include synthetic: true for UI watermark.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from apps.api.harness.core.db import fetch_all, fetch_one

# ── SQL ──────────────────────────────────────────────────────────────────────

_GRANT_CONSENT_SQL = """
/* sql_id: consents_grant */
INSERT INTO customer_consents (
    customer_id, consent_type, consent_scope, granted_by_employee_id, synthetic
) VALUES ($1, $2, $3::jsonb, $4, true)
RETURNING id, customer_id, consent_type, consent_scope,
          granted_at, withdrawn_at, granted_by_employee_id, synthetic;
"""

_WITHDRAW_CONSENT_SQL = """
/* sql_id: consents_withdraw */
UPDATE customer_consents
   SET withdrawn_at = NOW()
 WHERE customer_id = $1
   AND consent_type = $2
   AND withdrawn_at IS NULL
RETURNING id, customer_id, consent_type, consent_scope,
          granted_at, withdrawn_at, granted_by_employee_id, synthetic;
"""

_LIST_ACTIVE_CONSENTS_SQL = """
/* sql_id: consents_list_active */
SELECT id, customer_id, consent_type, consent_scope,
       granted_at, withdrawn_at, granted_by_employee_id, synthetic
  FROM customer_consents
 WHERE customer_id = $1
   AND withdrawn_at IS NULL
 ORDER BY granted_at DESC;
"""

_CREATE_INFO_REQUEST_SQL = """
/* sql_id: info_access_request_create */
INSERT INTO info_access_requests (customer_id, request_type, employee_id)
VALUES ($1, $2, $3)
RETURNING id, customer_id, request_type, requested_at, responded_at,
          response_summary_redacted, employee_id;
"""

_RESPOND_INFO_REQUEST_SQL = """
/* sql_id: info_access_request_respond */
UPDATE info_access_requests
   SET responded_at              = NOW(),
       response_summary_redacted = $2
 WHERE id = $1
   AND responded_at IS NULL
RETURNING id, customer_id, request_type, requested_at, responded_at,
          response_summary_redacted, employee_id;
"""

_GET_INFO_REQUEST_SQL = """
/* sql_id: info_access_request_get */
SELECT id, customer_id, request_type, requested_at, responded_at,
       response_summary_redacted, employee_id
  FROM info_access_requests
 WHERE id = $1;
"""

# ── serialisers ──────────────────────────────────────────────────────────────

def _consent_row(row: Any) -> dict[str, Any]:
    """Convert a customer_consents row; always emits synthetic=true for UI watermark."""
    d = dict(row)
    for key in ("granted_at", "withdrawn_at"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    if isinstance(d.get("consent_scope"), str):
        d["consent_scope"] = json.loads(d["consent_scope"])
    d["synthetic"] = True  # boundary guarantee — never suppressed
    return d


def _info_row(row: Any) -> dict[str, Any]:
    """Convert an info_access_requests row; always emits synthetic=true."""
    d = dict(row)
    for key in ("requested_at", "responded_at"):
        if d.get(key) is not None:
            d[key] = d[key].isoformat()
    d["synthetic"] = True
    return d


# ── public functions ─────────────────────────────────────────────────────────

async def grant_consent(
    connection: Any,
    *,
    customer_id: str,
    consent_type: str,
    consent_scope: dict[str, Any],
    employee_id: str,
) -> dict[str, Any]:
    """Record a synthetic consent grant (신용정보법 §32)."""
    row = await fetch_one(
        connection,
        _GRANT_CONSENT_SQL,
        UUID(customer_id),
        consent_type,
        json.dumps(consent_scope, ensure_ascii=False),
        UUID(employee_id),
    )
    if row is None:
        raise ValueError("consent INSERT returned no row")
    return _consent_row(row)


async def withdraw_consent(
    connection: Any,
    *,
    customer_id: str,
    consent_type: str,
) -> dict[str, Any] | None:
    """Mark the active consent of the given type as withdrawn (신용정보법 §37).

    Returns None if no active consent exists (caller raises 404).
    """
    row = await fetch_one(
        connection,
        _WITHDRAW_CONSENT_SQL,
        UUID(customer_id),
        consent_type,
    )
    return _consent_row(row) if row else None


async def list_active_consents(
    connection: Any,
    *,
    customer_id: str,
) -> list[dict[str, Any]]:
    """Return all active (not yet withdrawn) consents for a customer."""
    rows = await fetch_all(connection, _LIST_ACTIVE_CONSENTS_SQL, UUID(customer_id))
    return [_consent_row(r) for r in rows]


async def create_info_access_request(
    connection: Any,
    *,
    customer_id: str,
    request_type: str,
    employee_id: str,
) -> dict[str, Any]:
    """Create an ACCESS or CORRECTION request (신용정보법 §38)."""
    row = await fetch_one(
        connection,
        _CREATE_INFO_REQUEST_SQL,
        UUID(customer_id),
        request_type,
        UUID(employee_id),
    )
    if row is None:
        raise ValueError("info_access_requests INSERT returned no row")
    return _info_row(row)


async def respond_to_info_request(
    connection: Any,
    *,
    request_id: str,
    response_summary_redacted: str,
) -> dict[str, Any] | None:
    """Record a staff response to an info access/correction request.

    Returns None when request_id not found or already responded (caller raises 404).
    """
    row = await fetch_one(
        connection,
        _RESPOND_INFO_REQUEST_SQL,
        UUID(request_id),
        response_summary_redacted,
    )
    return _info_row(row) if row else None
