"""Product repository helpers."""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import fetch_all

from .common import rows_to_dicts

LIST_PRODUCTS_SQL = """
/* sql_id: list_products */
SELECT id, product_code, product_name, product_type_code, risk_level_code, maturity_date,
       has_knock_in, knock_in_barrier_pct, issuer_name, fee_pct, currency, is_active, created_at
FROM products
WHERE is_active IS TRUE
  AND ($1::varchar IS NULL OR product_type_code = $1::varchar)
  AND ($2::varchar IS NULL OR risk_level_code = $2::varchar)
ORDER BY product_type_code, risk_level_code, product_name
LIMIT $3 OFFSET $4;
"""


async def list_products(
    connection: Any,
    *,
    product_type_code: str | None,
    risk_level_code: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """List active products for recommendation simulation selection."""

    rows = await fetch_all(
        connection,
        LIST_PRODUCTS_SQL,
        product_type_code,
        risk_level_code,
        limit,
        offset,
    )
    return rows_to_dicts(rows)
