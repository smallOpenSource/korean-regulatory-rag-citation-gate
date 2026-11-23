"""Data readiness repository queries."""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import fetch_one
from apps.api.harness.services.readiness import build_readiness_payload

from .common import row_to_dict

READINESS_METRICS_SQL = """
/* sql_id: get_data_readiness_metrics */
SELECT
    (SELECT count(*) FROM customers WHERE is_active = TRUE) AS active_customers,
    (SELECT count(*) FROM portfolios) AS portfolios,
    (SELECT count(*) FROM house_views WHERE status_code = 'ACTIVE') AS active_house_views,
    (SELECT count(*) FROM documents) AS documents,
    (SELECT count(*) FROM document_chunks WHERE is_embedded = TRUE) AS embedded_chunks,
    (SELECT count(*) FROM raw_documents WHERE is_processed = FALSE) AS pending_raw_documents,
    (SELECT count(*) FROM batch_job_logs WHERE status_code = 'RUNNING') AS running_batches,
    (
        SELECT count(*) FROM batch_job_logs
        WHERE status_code = 'DONE'
          AND created_at >= now() - interval '24 hours'
    ) AS done_recent_batches,
    (
        SELECT count(*) FROM batch_job_logs
        WHERE status_code = 'FAILED'
          AND created_at >= now() - interval '24 hours'
    ) AS failed_recent_batches,
    (
        SELECT count(*) FROM batch_job_logs
        WHERE status_code = 'SKIPPED'
          AND created_at >= now() - interval '24 hours'
    ) AS skipped_recent_batches,
    (
        SELECT count(*) FROM batch_provider_evidence
        WHERE provider_status_code <> 'PROVIDER_DONE'
          AND observed_at >= now() - interval '24 hours'
    ) AS provider_detail_problem_recent,
    (
        SELECT count(*) FROM batch_provider_evidence
        WHERE provider_code = 'KRX'
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
    ) AS krx_done_provider_rows,
    (
        SELECT count(*) FROM batch_provider_evidence
        WHERE provider_code = 'KRX'
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
          AND provider_detail_json->>'source_policy_code' = 'PYKRX_AUXILIARY_APPROVED'
    ) AS pykrx_auxiliary_policy_rows,
    (
        SELECT count(*) FROM batch_provider_evidence
        WHERE provider_code = 'KRX'
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
          AND provider_detail_json->>'source_policy_code' = 'OFFICIAL_KRX_APPROVED'
    ) AS official_krx_policy_rows,
    (
        SELECT count(*) FROM market_price_bars
        WHERE source_code = 'KRX'
          AND is_synthetic IS FALSE
    ) AS official_krx_price_bar_rows,
    (
        SELECT count(*) FROM market_universe_snapshots
        WHERE universe_code = 'DOMESTIC_TOP200_MARKET_CAP'
    ) AS top200_universe_snapshot_count,
    (
        SELECT selected_count FROM market_universe_snapshots
        WHERE universe_code = 'DOMESTIC_TOP200_MARKET_CAP'
        ORDER BY as_of_date DESC, resolved_trading_date DESC, created_at DESC
        LIMIT 1
    ) AS top200_selected_count,
    (
        SELECT target_size FROM market_universe_snapshots
        WHERE universe_code = 'DOMESTIC_TOP200_MARKET_CAP'
        ORDER BY as_of_date DESC, resolved_trading_date DESC, created_at DESC
        LIMIT 1
    ) AS top200_target_size,
    (
        SELECT count(*) FROM market_universe_coverage_daily daily
        JOIN market_universe_snapshots snapshot ON snapshot.id = daily.snapshot_id
        WHERE snapshot.universe_code = 'DOMESTIC_TOP200_MARKET_CAP'
          AND daily.is_expected_trading_day IS TRUE
    ) AS top200_expected_member_days,
    (
        SELECT count(*) FROM market_universe_coverage_daily daily
        JOIN market_universe_snapshots snapshot ON snapshot.id = daily.snapshot_id
        WHERE snapshot.universe_code = 'DOMESTIC_TOP200_MARKET_CAP'
          AND daily.is_expected_trading_day IS TRUE
          AND daily.has_valid_bar IS TRUE
    ) AS top200_valid_member_days,
    (
        SELECT count(*) FROM market_universe_coverage_daily daily
        JOIN market_universe_snapshots snapshot ON snapshot.id = daily.snapshot_id
        WHERE snapshot.universe_code = 'DOMESTIC_TOP200_MARKET_CAP'
          AND daily.is_expected_trading_day IS TRUE
          AND daily.has_valid_bar IS FALSE
    ) AS top200_missing_member_days,
    (
        SELECT count(*) FROM migration_versions
        WHERE version IN (12, 13, 14, 15, 16, 17, 18)
    ) AS required_provider_migrations_applied,
    (
        SELECT CASE WHEN to_regclass('public.batch_provider_evidence') IS NULL THEN 0 ELSE 1 END
    ) AS batch_provider_evidence_table_present,
    (
        SELECT count(*) FROM securities
        WHERE country_code = 'KR'
          AND security_type_code = 'EQUITY'
          AND currency = 'KRW'
          AND is_active IS TRUE
    ) AS security_master_rows,
    (
        SELECT count(*) FROM market_price_bars
        WHERE is_synthetic IS FALSE
    ) AS price_bar_rows,
    (
        SELECT count(*) FROM market_price_bars
        WHERE is_synthetic IS FALSE
          AND quality_status_code IN ('VALID', 'RECONCILED')
    ) AS accepted_price_bar_rows,
    (
        SELECT source_as_of FROM market_price_bars
        WHERE is_synthetic IS FALSE
        ORDER BY CASE WHEN source_code = 'KRX' THEN 0 ELSE 1 END,
                 price_date DESC, source_as_of DESC, created_at DESC
        LIMIT 1
    ) AS latest_price_bar_source_as_of,
    (
        SELECT source_code FROM market_price_bars
        WHERE is_synthetic IS FALSE
        ORDER BY CASE WHEN source_code = 'KRX' THEN 0 ELSE 1 END,
                 price_date DESC, source_as_of DESC, created_at DESC
        LIMIT 1
    ) AS latest_price_bar_provider_code,
    (
        SELECT count(*) FROM market_data_quality_checks
    ) AS quality_check_count,
    (
        SELECT count(*) FROM market_data_quality_checks
        WHERE status_code = 'FAIL'
    ) AS quality_failed_count,
    (
        SELECT count(*) FROM macro_indicators
        WHERE source_code = 'ECOS'
    ) AS ecos_parseable_rows,
    (
        SELECT count(*) FROM batch_provider_evidence
        WHERE provider_code = 'ECOS'
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
    ) AS ecos_provider_done,
    (
        SELECT max(reference_date) FROM macro_indicators
        WHERE source_code = 'ECOS'
    ) AS latest_ecos_reference_date,
    (
        SELECT count(*) FROM document_sources
        WHERE provider_code = 'DART'
    ) AS dart_document_sources,
    (
        SELECT count(*) FROM batch_provider_evidence
        WHERE provider_code IN ('DART', 'OPENDART')
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
    ) AS dart_provider_done,
    (
        SELECT count(*) FROM batch_provider_evidence
        WHERE provider_code = 'KRX'
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
    ) AS krx_provider_done,
    (
        SELECT count(*) FROM batch_provider_evidence
        WHERE provider_code = 'KRX'
          AND provider_status_code = 'PROVIDER_DONE'
          AND rows_collected > 0
          AND provider_detail_json->>'source_policy_code' = 'OFFICIAL_KRX_APPROVED'
    ) AS official_krx_provider_done,
    (
        SELECT count(*) FROM market_prices
    ) AS legacy_market_price_rows,
    (
        SELECT count(DISTINCT source_code) FROM market_prices
    ) AS legacy_market_price_sources,
    (
        SELECT source_code FROM market_prices
        ORDER BY price_date DESC, created_at DESC
        LIMIT 1
    ) AS latest_legacy_source_code,
    (
        SELECT price_date FROM market_prices
        ORDER BY price_date DESC, created_at DESC
        LIMIT 1
    ) AS latest_legacy_market_price_date,
    (
        SELECT count(*) FROM raw_documents
        WHERE source_type_code = 'DART'
    ) AS dart_raw_documents,
    (
        SELECT count(*)
        FROM document_chunks
        WHERE provider_code = 'DART'
          AND receipt_no IS NOT NULL
          AND parser_version = 'dart-xml-v1'
    ) AS dart_document_chunks,
    (
        SELECT count(*)
        FROM document_chunks
        WHERE provider_code = 'DART'
          AND receipt_no IS NOT NULL
          AND parser_version = 'dart-xml-v1'
          AND is_embedded IS TRUE
    ) AS dart_embedded_chunks,
    (
        SELECT count(*)
        FROM document_chunks
        WHERE provider_code = 'DART'
          AND receipt_no IS NOT NULL
          AND parser_version = 'dart-xml-v1'
          AND is_embedded IS TRUE
    ) AS embedded_dart_document_chunks;
"""


async def get_data_readiness(connection: Any) -> dict[str, Any]:
    """Return API/Web readiness from aggregate DB metrics."""

    row = row_to_dict(await fetch_one(connection, READINESS_METRICS_SQL))
    return build_readiness_payload(row or {})
