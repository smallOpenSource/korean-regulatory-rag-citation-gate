"""Dashboard repositories."""

from __future__ import annotations

import json
from typing import Any

from apps.api.harness.core.db import fetch_one
from apps.api.harness.core.rbac import ActorContext
from apps.api.harness.services.readiness import (
    build_domestic_market_payload,
    synthetic_customer_notice,
)

from .common import row_to_dict
from .house_views import LIVE_HOUSE_VIEW_STATUS_IN, NON_FIXTURE_HOUSE_VIEW_PREDICATE

_GET_DASHBOARD_SUMMARY_SQL_BASE = """/* sql_id: get_dashboard_summary */
WITH scoped_customers AS (
    SELECT c.id
    FROM customers c
    WHERE c.is_active IS TRUE
      AND (
          $1::varchar = 'ADMIN'
          OR ($1::varchar = 'PB' AND c.assigned_pb_id = $2::uuid)
          OR ($1::varchar IN ('WM', 'BRANCH_MANAGER') AND c.branch_id = $3::uuid)
      )
), latest_house_view AS (
    SELECT jsonb_build_object(
        'summary', h.summary,
        'ai_generated_at', h.ai_generated_at,
        'ai_model_name', h.ai_model_name,
        'faithfulness_json', h.faithfulness_json
    ) AS payload
    FROM house_views h
    -- "live" = legacy 'ACTIVE' OR T16 lifecycle 'ACTIVATED' (P2 ACTIVE/ACTIVATED 정합);
    -- both set activated_at so the most recent activation wins.
    WHERE h.status_code IN ('ACTIVE', 'ACTIVATED')
    ORDER BY h.activated_at DESC NULLS LAST, h.created_at DESC
    LIMIT 1
), latest_legacy_market_price AS (
    SELECT mp.source_code, mp.price_date
    FROM market_prices mp
    ORDER BY mp.price_date DESC, mp.created_at DESC
    LIMIT 1
), latest_price_bar AS (
    SELECT mpb.source_code, mpb.source_as_of
    FROM market_price_bars mpb
    WHERE mpb.is_synthetic IS FALSE
    ORDER BY CASE WHEN mpb.source_code = 'KRX' THEN 0 ELSE 1 END,
             mpb.price_date DESC, mpb.source_as_of DESC, mpb.created_at DESC
    LIMIT 1
), legacy_market_metrics AS (
    SELECT
        count(*)::integer AS legacy_market_price_rows,
        count(DISTINCT source_code)::integer AS legacy_market_price_sources
    FROM market_prices
), market_price_metrics AS (
    SELECT
        (
            SELECT count(*)::integer
            FROM securities
            WHERE country_code = 'KR'
              AND security_type_code = 'EQUITY'
              AND currency = 'KRW'
              AND is_active IS TRUE
        ) AS security_master_rows,
        (
            SELECT count(*)::integer
            FROM market_price_bars
            WHERE is_synthetic IS FALSE
        ) AS price_bar_rows,
        (
            SELECT count(*)::integer
            FROM market_price_bars
            WHERE is_synthetic IS FALSE
              AND quality_status_code IN ('VALID', 'RECONCILED')
        ) AS accepted_price_bar_rows,
        (
            SELECT count(*)::integer
            FROM market_data_quality_checks
        ) AS quality_check_count,
        (
            SELECT count(*)::integer
            FROM market_data_quality_checks
            WHERE status_code = 'FAIL'
        ) AS quality_failed_count
), provider_policy_metrics AS (
    SELECT
        (
            SELECT count(*)::integer
            FROM batch_provider_evidence
            WHERE provider_code = 'KRX'
              AND provider_status_code = 'PROVIDER_DONE'
              AND rows_collected > 0
              AND provider_detail_json->>'source_policy_code' = 'PYKRX_AUXILIARY_APPROVED'
        ) AS pykrx_auxiliary_policy_rows,
        (
            SELECT count(*)::integer
            FROM batch_provider_evidence
            WHERE provider_code = 'KRX'
              AND provider_status_code = 'PROVIDER_DONE'
              AND rows_collected > 0
              AND provider_detail_json->>'source_policy_code' = 'OFFICIAL_KRX_APPROVED'
        ) AS official_krx_policy_rows,
        (
            SELECT count(*)::integer
            FROM batch_provider_evidence
            WHERE provider_code = 'KRX'
              AND provider_status_code = 'PROVIDER_DONE'
              AND rows_collected > 0
              AND provider_detail_json->>'source_policy_code' = 'OFFICIAL_KRX_APPROVED'
        ) AS official_krx_provider_done
), dart_metrics AS (
    SELECT
        (
            SELECT count(*)::integer
            FROM document_chunks
            WHERE provider_code = 'DART'
              AND receipt_no IS NOT NULL
              AND parser_version = 'dart-xml-v1'
        ) AS dart_document_chunks,
        (
            SELECT count(*)::integer
            FROM document_chunks
            WHERE provider_code = 'DART'
              AND receipt_no IS NOT NULL
              AND parser_version = 'dart-xml-v1'
              AND is_embedded IS TRUE
        ) AS embedded_dart_document_chunks
)
SELECT
    (
        SELECT COUNT(*)::integer
        FROM nba_actions n
        JOIN scoped_customers c ON c.id = n.customer_id
        WHERE n.priority_code = 'URGENT'
          AND n.status_code IN ('PENDING', 'IN_PROGRESS', 'SNOOZED')
    ) AS urgent_nba_count,
    (
        SELECT COUNT(*)::integer
        FROM products p
        WHERE p.is_active IS TRUE
          AND p.maturity_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days'
    ) AS due_maturity_count,
    (
        SELECT COUNT(*)::integer
        FROM consultations co
        JOIN scoped_customers c ON c.id = co.customer_id
        WHERE co.consultation_at::date = CURRENT_DATE
    ) AS consultations_today,
    (SELECT payload FROM latest_house_view) AS latest_house_view,
    jsonb_build_object(
        'legacy_market_price_rows', (SELECT legacy_market_price_rows FROM legacy_market_metrics),
        'legacy_market_price_sources',
            (SELECT legacy_market_price_sources FROM legacy_market_metrics),
        'latest_legacy_source_code', (SELECT source_code FROM latest_legacy_market_price),
        'latest_legacy_market_price_date',
            (SELECT price_date::text FROM latest_legacy_market_price),
        'security_master_rows', (SELECT security_master_rows FROM market_price_metrics),
        'price_bar_rows', (SELECT price_bar_rows FROM market_price_metrics),
        'accepted_price_bar_rows', (SELECT accepted_price_bar_rows FROM market_price_metrics),
        'official_krx_price_bar_rows', (
            SELECT count(*)::integer FROM market_price_bars WHERE source_code = 'KRX'
        ),
        'latest_price_bar_source_as_of', (SELECT source_as_of::text FROM latest_price_bar),
        'latest_price_bar_provider_code', (SELECT source_code FROM latest_price_bar),
        'quality_check_count', (SELECT quality_check_count FROM market_price_metrics),
        'quality_failed_count', (SELECT quality_failed_count FROM market_price_metrics),
        'pykrx_auxiliary_policy_rows',
            (SELECT pykrx_auxiliary_policy_rows FROM provider_policy_metrics),
        'official_krx_policy_rows',
            (SELECT official_krx_policy_rows FROM provider_policy_metrics),
        'official_krx_provider_done',
            (SELECT official_krx_provider_done FROM provider_policy_metrics),
        'dart_document_chunks', (SELECT dart_document_chunks FROM dart_metrics),
        'embedded_dart_document_chunks', (SELECT embedded_dart_document_chunks FROM dart_metrics)
    ) AS domestic_market_metrics;
"""

# P2 ACTIVE/ACTIVATED 정합 follow-up: exclude test fixtures from latest_house_view
# (same predicate the house_views readers use, bare columns resolve against the
# single-table CTE) so a QA activation probe never surfaces as the banker's
# "latest house view". Injected via replace to avoid f-string brace escaping in the
# large jsonb_build_object SQL.
# Live-view status set is the house_views SoT (LIVE_HOUSE_VIEW_STATUS_IN). Derive the
# replace target/replacement from it so the dashboard CTE never drifts from the readers.
_LIVE_HOUSE_VIEW_WHERE = f"WHERE h.status_code IN {LIVE_HOUSE_VIEW_STATUS_IN}"
GET_DASHBOARD_SUMMARY_SQL = _GET_DASHBOARD_SUMMARY_SQL_BASE.replace(
    _LIVE_HOUSE_VIEW_WHERE,
    _LIVE_HOUSE_VIEW_WHERE + "\n      AND " + NON_FIXTURE_HOUSE_VIEW_PREDICATE,
)
if GET_DASHBOARD_SUMMARY_SQL == _GET_DASHBOARD_SUMMARY_SQL_BASE:  # pragma: no cover
    raise RuntimeError(
        "dashboard latest_house_view live-status predicate drifted from "
        "LIVE_HOUSE_VIEW_STATUS_IN (house_views SoT); update the CTE literal to match"
    )


def _actor_params(actor: ActorContext) -> tuple[str, str, str | None]:
    return actor.role_code, actor.employee_id, actor.branch_id


async def get_dashboard_summary(connection: Any, *, actor: ActorContext) -> dict[str, Any]:
    """Read role-scoped dashboard counters and the latest active house view."""

    row = await fetch_one(connection, GET_DASHBOARD_SUMMARY_SQL, *_actor_params(actor))
    result = row_to_dict(row)
    if result is None:
        return {
            "urgent_nba_count": 0,
            "due_maturity_count": 0,
            "consultations_today": 0,
            "latest_house_view": None,
            "domestic_market_status": build_domestic_market_payload({}),
            "synthetic_customer_notice": synthetic_customer_notice(),
        }
    domestic_market_metrics = result.pop("domestic_market_metrics") or {}
    if isinstance(domestic_market_metrics, str):
        domestic_market_metrics = json.loads(domestic_market_metrics)
    if not isinstance(domestic_market_metrics, dict):
        domestic_market_metrics = {}
    # asyncpg returns jsonb columns as raw JSON strings by default. Parse so
    # the web client can read `latest_house_view.summary` directly instead of
    # eternally falling through to the placeholder copy.
    latest_house_view = result.get("latest_house_view")
    if isinstance(latest_house_view, str):
        try:
            latest_house_view = json.loads(latest_house_view)
        except ValueError:
            latest_house_view = None
    if not isinstance(latest_house_view, dict):
        latest_house_view = None
    result["latest_house_view"] = latest_house_view
    result["domestic_market_status"] = build_domestic_market_payload(domestic_market_metrics)
    result["synthetic_customer_notice"] = synthetic_customer_notice()
    return result
