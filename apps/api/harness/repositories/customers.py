"""Customer and Customer 360 repositories."""

from __future__ import annotations

import json
from typing import Any

from apps.api.harness.core.db import fetch_all, fetch_one
from apps.api.harness.core.rbac import ActorContext
from apps.api.harness.services.readiness import (
    blocked_market_valuation_source,
    build_portfolio_valuation_payload,
    synthetic_customer_notice,
)

from .common import row_to_dict, rows_to_dicts

CUSTOMER_SCOPE_FRAGMENT = """
(
    $1::varchar = 'ADMIN'
    OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
    OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid)
)
"""

LIST_CUSTOMERS_SQL = f"""
/* sql_id: list_scoped_customers */
SELECT c.id, c.customer_no, c.customer_name, c.scenario_label, c.assigned_pb_id, c.branch_id, c.risk_grade_code,
       c.segment_code, c.total_assets_krw, c.last_contacted_at, c.is_active, c.created_at,
       c.updated_at
FROM customers c
WHERE {CUSTOMER_SCOPE_FRAGMENT}
  AND c.is_active IS TRUE
  AND (
      $4::varchar IS NULL
      OR c.customer_no ILIKE '%' || $4::varchar || '%'
      OR c.customer_name ILIKE '%' || $4::varchar || '%'
  )
  AND ($5::varchar IS NULL OR c.risk_grade_code = $5::varchar)
  AND ($6::varchar IS NULL OR c.segment_code = $6::varchar)
ORDER BY c.total_assets_krw DESC, c.created_at DESC
LIMIT $7 OFFSET $8;
"""

GET_CUSTOMER_SQL = f"""
/* sql_id: get_scoped_customer */
SELECT c.id, c.customer_no, c.customer_name, c.scenario_label, c.assigned_pb_id, c.branch_id, c.risk_grade_code,
       c.segment_code, c.total_assets_krw, c.last_contacted_at, c.is_active, c.created_at,
       c.updated_at
FROM customers c
WHERE c.id = $4::uuid
  AND c.is_active IS TRUE
  AND {CUSTOMER_SCOPE_FRAGMENT};
"""

LIST_PORTFOLIOS_SQL = """
/* sql_id: list_customer_portfolios */
SELECT p.id, p.customer_id, p.portfolio_name, p.base_currency, p.valuation_date,
       p.created_at, p.updated_at
FROM portfolios p
WHERE p.customer_id = $1::uuid
ORDER BY p.valuation_date DESC, p.created_at DESC;
"""

LIST_HOLDINGS_SQL = """
/* sql_id: list_customer_portfolio_holdings */
SELECT h.id, h.portfolio_id, h.product_id, pr.product_code, pr.product_name,
       pr.product_type_code, pr.risk_level_code, h.quantity, h.market_value_krw,
       h.weight_pct, h.as_of_date
FROM portfolio_holdings h
JOIN portfolios p ON p.id = h.portfolio_id
JOIN products pr ON pr.id = h.product_id
WHERE p.customer_id = $1::uuid
ORDER BY h.weight_pct DESC;
"""

LIST_CUSTOMER_NBA_SQL = """
/* sql_id: list_customer_nba_actions */
SELECT n.id, n.customer_id, n.employee_id, n.action_type_code, n.priority_code,
       n.status_code, n.trigger_code, n.script_text, n.script_generated_at,
       n.script_model_name, n.due_date, n.snoozed_until, n.completed_at, n.created_at,
       n.updated_at
FROM nba_actions n
WHERE n.customer_id = $1::uuid
ORDER BY n.priority_code, n.due_date NULLS LAST, n.created_at DESC;
"""

LIST_CUSTOMER_AFTERCARE_SQL = """
/* sql_id: list_customer_aftercare_events */
SELECT a.id, a.customer_id, a.product_id, a.employee_id, a.event_type_code, a.event_date,
       a.status_code, a.notes, a.resolved_at, a.created_at, a.updated_at
FROM aftercare_events a
WHERE a.customer_id = $1::uuid
ORDER BY a.event_date DESC, a.created_at DESC;
"""


LATEST_CUSTOMER_AI_BRIEFING_SQL = """
/* sql_id: latest_customer_ai_briefing */
SELECT id, generated_at, model_name, output_json
FROM ai_outputs
WHERE resource_type = 'customers'
  AND resource_id = $1::uuid
  AND fail_closed_reason_code IS NULL
ORDER BY generated_at DESC
LIMIT 1;
"""


async def _latest_customer_ai_briefing(
    connection: Any, customer_id: str
) -> dict[str, Any] | None:
    """Latest non-fail-closed customer-scoped AI output (portfolio_analysis),
    surfaced as the Customer-360 AI briefing card + AIMetadataFooter source so a
    PB/WM reviewer sees the P0 quality signals (data-quality disclosure /
    faithfulness / PII mask) carried in output_json before acting on it."""

    row = row_to_dict(await fetch_one(connection, LATEST_CUSTOMER_AI_BRIEFING_SQL, customer_id))
    if row is None:
        return None
    output_json = row.get("output_json")
    if isinstance(output_json, str):
        try:
            output_json = json.loads(output_json)
        except json.JSONDecodeError:
            output_json = {}
    summary = ""
    if isinstance(output_json, dict):
        summary = str(output_json.get("summary", "") or "")[:600]
    return {
        "output_id": str(row["id"]),
        "generated_at": row["generated_at"],
        "model_name": row["model_name"],
        "summary": summary,
    }


def _actor_params(actor: ActorContext) -> tuple[str, str, str | None]:
    return actor.role_code, actor.employee_id, actor.branch_id


async def list_customers(
    connection: Any,
    *,
    actor: ActorContext,
    q: str | None,
    risk_grade_code: str | None,
    segment_code: str | None,
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    """List customers in the actor's RBAC row scope."""

    rows = await fetch_all(
        connection,
        LIST_CUSTOMERS_SQL,
        *_actor_params(actor),
        q,
        risk_grade_code,
        segment_code,
        limit,
        offset,
    )
    return rows_to_dicts(rows)


async def get_customer(
    connection: Any, *, actor: ActorContext, customer_id: str
) -> dict[str, Any] | None:
    """Get one customer in the actor's RBAC row scope."""

    return row_to_dict(
        await fetch_one(connection, GET_CUSTOMER_SQL, *_actor_params(actor), customer_id)
    )


async def get_customer_360(
    connection: Any, *, actor: ActorContext, customer_id: str
) -> dict[str, Any] | None:
    """Assemble Customer 360 data from scoped customer and related tables."""

    customer = await get_customer(connection, actor=actor, customer_id=customer_id)
    if not customer:
        return None
    portfolios = rows_to_dicts(await fetch_all(connection, LIST_PORTFOLIOS_SQL, customer_id))
    holdings = rows_to_dicts(await fetch_all(connection, LIST_HOLDINGS_SQL, customer_id))
    holdings_with_provenance = [
        {
            **holding,
            "valuation_source": blocked_market_valuation_source(holding.get("as_of_date")),
        }
        for holding in holdings
    ]
    nba_actions = rows_to_dicts(await fetch_all(connection, LIST_CUSTOMER_NBA_SQL, customer_id))
    aftercare_events = rows_to_dicts(
        await fetch_all(connection, LIST_CUSTOMER_AFTERCARE_SQL, customer_id)
    )
    ai_briefing = await _latest_customer_ai_briefing(connection, customer_id)
    return {
        "customer": customer,
        "portfolios": portfolios,
        "holdings": holdings_with_provenance,
        "portfolio_valuation": build_portfolio_valuation_payload(portfolios, holdings),
        "synthetic_customer_notice": synthetic_customer_notice(),
        "nba_actions": nba_actions,
        "aftercare_events": aftercare_events,
        "ai_briefing": ai_briefing,
    }
