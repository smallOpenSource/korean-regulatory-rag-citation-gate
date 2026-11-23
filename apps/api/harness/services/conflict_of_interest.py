"""Conflict of interest Chinese Wall check service (T249, REG-03)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

CHINESE_WALL_BLOCK_MESSAGE = "이해상충 사전신고 위반: 거래 차단됨"


@dataclass(frozen=True)
class ChineseWallResult:
    """Result of check_chinese_wall()."""

    blocked: bool
    disclosure_id: str | None
    message: str


async def check_chinese_wall(
    connection: Any,
    *,
    employee_id: str,
    customer_id: str,
    product_id: str | None = None,  # noqa: ARG001 — future product-level checks
) -> ChineseWallResult:
    """Check whether employee is Chinese-wall-blocked for the given customer.

    Looks up ``conflict_disclosures`` for an active violation between the
    (employee_id, customer_id) pair.  If a row with ``chinese_wall_violation=true``
    exists and is not yet cleared, returns a blocked result with the banner message.

    Args:
        connection: asyncpg connection.
        employee_id: Authenticated employee UUID.
        customer_id: Target customer UUID.
        product_id: Optional product UUID (reserved for future product-level checks).

    Returns:
        ChineseWallResult with ``blocked=True`` if a violation exists.
    """
    from apps.api.harness.core.db import fetch_one

    SQL = """
/* sql_id: check_chinese_wall_violation */
SELECT id::text AS id, employee_id::text, customer_id::text,
       disclosure_type, chinese_wall_violation, blocked_at, disclosed_at
FROM conflict_disclosures
WHERE employee_id = $1::uuid
  AND customer_id = $2::uuid
  AND chinese_wall_violation = true
ORDER BY blocked_at DESC NULLS LAST, disclosed_at DESC
LIMIT 1;
"""
    row = await fetch_one(connection, SQL, employee_id, customer_id)
    if row is None:
        return ChineseWallResult(blocked=False, disclosure_id=None, message="")

    return ChineseWallResult(
        blocked=True,
        disclosure_id=str(row["id"]),
        message=CHINESE_WALL_BLOCK_MESSAGE,
    )


def disclosure_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalise a conflict disclosure creation payload."""
    allowed_types = {"PRE_TRADE", "POST_TRADE", "RELATED_PARTY"}
    disclosure_type = str(payload.get("disclosure_type") or "").strip().upper()
    if disclosure_type not in allowed_types:
        raise ValueError(
            f"disclosure_type must be one of {sorted(allowed_types)}, got: {disclosure_type!r}"
        )
    description = str(payload.get("description") or payload.get("description_redacted") or "").strip()
    return {
        "disclosure_type": disclosure_type,
        "description_redacted": description[:2000] if description else None,
        "chinese_wall_violation": bool(payload.get("chinese_wall_violation", False)),
    }
