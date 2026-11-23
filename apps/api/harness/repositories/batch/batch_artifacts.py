"""Market data artifact repository: raw docs, price bars, KRX securities, quality checks.

sql_id namespace: harness.batch.repo.artifacts.*
"""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import execute, fetch_all, fetch_one

from ..common import row_to_dict, rows_to_dicts

INSERT_RAW_DOCUMENT_SQL = """
/* sql_id: insert_raw_document */
INSERT INTO raw_documents(source_type_code, source_url, content_hash, raw_text, is_processed)
VALUES ($1, $2, $3, $4, FALSE)
ON CONFLICT (content_hash, source_url) DO NOTHING
RETURNING id, source_type_code, source_url, content_hash, collected_at, is_processed, processed_at;
"""

GET_RAW_DOCUMENT_BY_HASH_URL_SQL = """
/* sql_id: get_raw_document_by_hash_url */
SELECT id, source_type_code, source_url, content_hash, collected_at, is_processed, processed_at
FROM raw_documents
WHERE content_hash = $1
  AND source_url = $2
LIMIT 1;
"""

UPSERT_MARKET_PRICE_SQL = """
/* sql_id: upsert_market_price_bar */
WITH candidate_security AS (
    SELECT s.id, s.ticker, s.isin, s.security_name_kr, s.market_code
    FROM securities s
    LEFT JOIN security_identifiers si ON si.security_id = s.id
    WHERE s.country_code = 'KR'
      AND s.security_type_code = 'EQUITY'
      AND s.currency = 'KRW'
      AND s.is_active IS TRUE
      AND (
          s.ticker = $1::varchar
          OR s.isin = $1::varchar
          OR si.identifier_value = $1::varchar
      )
    ORDER BY CASE
        WHEN s.ticker = $1::varchar THEN 0
        WHEN s.isin = $1::varchar THEN 1
        ELSE 2
    END
    LIMIT 1
), upserted AS (
    INSERT INTO market_price_bars(
        security_id, source_code, price_date, open_price, high_price, low_price, close_price,
        adjusted_close_price, volume, source_as_of, quality_status_code, quality_message,
        trading_value_krw, market_cap_krw, listed_shares, change_price, change_rate_pct
    )
    SELECT candidate_security.id, $2::varchar, $3::date, $4::numeric, $5::numeric,
           $6::numeric, $7::numeric, COALESCE($8::numeric, $7::numeric),
           $9::numeric, COALESCE($10::timestamptz, now()), 'RAW', NULL,
           $11::numeric, $12::numeric, $13::numeric, $14::numeric, $15::numeric
    FROM candidate_security
    ON CONFLICT (security_id, price_date, source_code, timeframe_code) DO UPDATE SET
        open_price = EXCLUDED.open_price,
        high_price = EXCLUDED.high_price,
        low_price = EXCLUDED.low_price,
        close_price = EXCLUDED.close_price,
        adjusted_close_price = EXCLUDED.adjusted_close_price,
        volume = EXCLUDED.volume,
        source_as_of = EXCLUDED.source_as_of,
        trading_value_krw = EXCLUDED.trading_value_krw,
        market_cap_krw = EXCLUDED.market_cap_krw,
        listed_shares = EXCLUDED.listed_shares,
        change_price = EXCLUDED.change_price,
        change_rate_pct = EXCLUDED.change_rate_pct,
        quality_status_code = 'RAW',
        quality_message = NULL,
        updated_at = now()
    RETURNING id, security_id, source_code, price_date, timeframe_code, open_price, high_price,
              low_price, close_price, adjusted_close_price, volume, trading_value_krw,
              market_cap_krw, listed_shares, change_price, change_rate_pct, source_as_of,
              quality_status_code, quality_message, created_at, updated_at
)
SELECT upserted.id, candidate_security.ticker, candidate_security.isin,
       candidate_security.security_name_kr, candidate_security.market_code,
       upserted.security_id, upserted.source_code, upserted.price_date,
       upserted.timeframe_code, upserted.open_price, upserted.high_price,
       upserted.low_price, upserted.close_price, upserted.adjusted_close_price,
       upserted.volume, upserted.trading_value_krw, upserted.market_cap_krw,
       upserted.listed_shares, upserted.change_price, upserted.change_rate_pct,
       upserted.source_as_of, upserted.quality_status_code, upserted.quality_message,
       upserted.created_at, upserted.updated_at
FROM upserted
JOIN candidate_security ON candidate_security.id = upserted.security_id;
"""

UPSERT_KRX_SECURITY_SQL = """
/* sql_id: upsert_krx_official_security */
INSERT INTO securities(ticker, isin, security_name_kr, market_code, listed_at)
VALUES ($1::varchar, $2::varchar, $3::varchar, $4::varchar, $5::date)
ON CONFLICT (ticker) DO UPDATE SET
    isin = EXCLUDED.isin,
    security_name_kr = EXCLUDED.security_name_kr,
    market_code = EXCLUDED.market_code,
    country_code = 'KR',
    security_type_code = 'EQUITY',
    currency = 'KRW',
    is_active = TRUE,
    listed_at = COALESCE(EXCLUDED.listed_at, securities.listed_at),
    updated_at = now()
RETURNING id, ticker, isin, security_name_kr, market_code, listed_at, created_at, updated_at;
"""

UPSERT_KRX_SECURITY_IDENTIFIERS_SQL = """
/* sql_id: upsert_krx_official_security_identifiers */
WITH target_security AS (
    SELECT id, ticker, isin
    FROM securities
    WHERE ticker = $1::varchar
), identifier_seed AS (
    SELECT id AS security_id,
           'TICKER'::varchar AS identifier_type_code,
           ticker AS identifier_value,
           TRUE AS is_primary
    FROM target_security
    UNION ALL
    SELECT id AS security_id,
           'KRX_SHORT_CODE'::varchar AS identifier_type_code,
           ticker AS identifier_value,
           FALSE AS is_primary
    FROM target_security
    UNION ALL
    SELECT id AS security_id,
           'ISIN'::varchar AS identifier_type_code,
           isin AS identifier_value,
           TRUE AS is_primary
    FROM target_security
)
INSERT INTO security_identifiers(
    security_id, identifier_type_code, identifier_value, source_code, is_primary
)
SELECT security_id, identifier_type_code, identifier_value, 'KRX', is_primary
FROM identifier_seed
ON CONFLICT (identifier_type_code, identifier_value, source_code) DO UPDATE SET
    security_id = EXCLUDED.security_id,
    is_primary = EXCLUDED.is_primary
RETURNING security_id, identifier_type_code, identifier_value, source_code, is_primary;
"""

INSERT_MARKET_DATA_EVIDENCE_SQL = """
/* sql_id: insert_market_data_evidence */
INSERT INTO market_data_evidence(source_code, evidence_type_code, provider_reference,
                                 payload_hash, source_as_of, evidence_json)
VALUES ($1, $2, $3, $4, $5::timestamptz, $6::jsonb)
ON CONFLICT (source_code, evidence_type_code, payload_hash) DO UPDATE SET
    provider_reference = EXCLUDED.provider_reference,
    source_as_of = EXCLUDED.source_as_of,
    evidence_json = EXCLUDED.evidence_json
RETURNING id, source_code, evidence_type_code, provider_reference, payload_hash,
          source_as_of, collected_at, evidence_json;
"""

INSERT_MARKET_QUALITY_CHECK_SQL = """
/* sql_id: insert_market_quality_check */
INSERT INTO market_data_quality_checks(check_code, security_id, source_code, price_date,
                                       status_code, severity_code, observed_json, evidence_id)
VALUES ($1, $2::uuid, $3, $4::date, $5, $6, $7::jsonb, $8::uuid)
RETURNING id, check_code, security_id, source_code, price_date, status_code, severity_code,
          observed_json, evidence_id, created_at;
"""

MARK_PRICE_BARS_VALID_SQL = """
/* sql_id: mark_price_bars_valid */
UPDATE market_price_bars
SET quality_status_code = 'VALID',
    quality_message = NULL,
    updated_at = now()
WHERE quality_status_code IN ('RAW', 'WARN')
  AND open_price IS NOT NULL
  AND high_price IS NOT NULL
  AND low_price IS NOT NULL
  AND high_price >= low_price
  AND close_price BETWEEN low_price AND high_price
  AND (volume IS NULL OR volume >= 0);
"""

LIST_PRICE_BAR_RECONCILIATION_SQL = """
/* sql_id: list_price_bar_reconciliation */
WITH source_pairs AS (
    SELECT left_bar.security_id, left_bar.price_date,
           left_bar.source_code AS left_source_code,
           right_bar.source_code AS right_source_code,
           left_bar.close_price AS left_close_price,
           right_bar.close_price AS right_close_price,
           abs(left_bar.close_price - right_bar.close_price) AS close_diff
    FROM market_price_bars left_bar
    JOIN market_price_bars right_bar
      ON right_bar.security_id = left_bar.security_id
     AND right_bar.price_date = left_bar.price_date
     AND right_bar.source_code > left_bar.source_code
    WHERE left_bar.price_date BETWEEN $1::date AND $2::date
)
SELECT s.ticker, s.isin, source_pairs.price_date, source_pairs.left_source_code,
       source_pairs.right_source_code, source_pairs.left_close_price,
       source_pairs.right_close_price, source_pairs.close_diff
FROM source_pairs
JOIN securities s ON s.id = source_pairs.security_id
WHERE source_pairs.close_diff > $3::numeric
ORDER BY source_pairs.price_date DESC, s.ticker, source_pairs.left_source_code;
"""

GET_MARKET_PRICE_BAR_READINESS_SQL = """
/* sql_id: get_market_price_bar_readiness */
SELECT
    (
        SELECT count(*)::integer
        FROM securities
        WHERE is_active IS TRUE
    ) AS active_domestic_securities,
    (SELECT count(*)::integer FROM market_price_bars) AS price_bar_count,
    (SELECT max(price_date) FROM market_price_bars) AS latest_price_date,
    (SELECT max(source_as_of) FROM market_price_bars) AS latest_source_as_of,
    (
        SELECT count(*)::integer
        FROM market_price_bars
        WHERE quality_status_code IN ('VALID', 'RECONCILED')
    ) AS usable_price_bar_count,
    (
        SELECT count(*)::integer
        FROM market_data_quality_checks
        WHERE status_code IN ('WARN', 'FAIL')
          AND created_at >= now() - interval '24 hours'
    ) AS recent_quality_issue_count;
"""

UPSERT_MACRO_INDICATOR_SQL = """
/* sql_id: upsert_macro_indicator */
INSERT INTO macro_indicators(indicator_code, indicator_name, reference_date,
                             value, unit, source_code)
VALUES ($1, $2, $3::date, $4, $5, $6)
ON CONFLICT (indicator_code, reference_date, source_code) DO NOTHING
RETURNING id, indicator_code, indicator_name, reference_date, value, unit, source_code, created_at;
"""


async def insert_raw_document(
    connection: Any, *, source_type_code: str, source_url: str, content_hash: str, raw_text: str
) -> dict[str, Any] | None:
    """Insert raw document if not duplicate."""

    return row_to_dict(
        await fetch_one(
            connection,
            INSERT_RAW_DOCUMENT_SQL,
            source_type_code,
            source_url,
            content_hash,
            raw_text,
        )
    )


async def get_raw_document_by_hash_url(
    connection: Any, *, content_hash: str, source_url: str
) -> dict[str, Any] | None:
    """Return a raw document by its provider dedupe key."""

    return row_to_dict(
        await fetch_one(connection, GET_RAW_DOCUMENT_BY_HASH_URL_SQL, content_hash, source_url)
    )


async def upsert_market_price(connection: Any, *, row: dict[str, Any]) -> dict[str, Any] | None:
    """Upsert one domestic Korea equity daily bar into ``market_price_bars``."""

    return row_to_dict(
        await fetch_one(
            connection,
            UPSERT_MARKET_PRICE_SQL,
            row["ticker"],
            row["source_code"],
            row["price_date"],
            row.get("open_price"),
            row.get("high_price"),
            row.get("low_price"),
            row["close_price"],
            row.get("adjusted_close_price"),
            row.get("volume"),
            row.get("source_as_of"),
            row.get("trading_value_krw"),
            row.get("market_cap_krw"),
            row.get("listed_shares"),
            row.get("change_price"),
            row.get("change_rate_pct"),
        )
    )


async def upsert_krx_official_security(
    connection: Any,
    *,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Upsert a KRX official security-master row and source identifiers."""

    security = row_to_dict(
        await fetch_one(
            connection,
            UPSERT_KRX_SECURITY_SQL,
            row["ticker"],
            row["isin"],
            row["security_name_kr"],
            row["market_code"],
            row.get("listed_at"),
        )
    )
    if security is None:
        raise RuntimeError("KRX official security upsert returned no row")
    await fetch_all(connection, UPSERT_KRX_SECURITY_IDENTIFIERS_SQL, row["ticker"])
    return security


async def insert_market_data_evidence(
    connection: Any,
    *,
    source_code: str,
    evidence_type_code: str,
    provider_reference: str | None,
    payload_hash: str,
    source_as_of: Any,
    evidence_json: str,
) -> dict[str, Any]:
    """Insert or refresh immutable-source market data evidence metadata."""

    row = await fetch_one(
        connection,
        INSERT_MARKET_DATA_EVIDENCE_SQL,
        source_code,
        evidence_type_code,
        provider_reference,
        payload_hash,
        source_as_of,
        evidence_json,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("market data evidence insert returned no row")
    return result


async def insert_market_quality_check(
    connection: Any,
    *,
    check_code: str,
    security_id: str | None,
    source_code: str | None,
    price_date: Any | None,
    status_code: str,
    severity_code: str,
    observed_json: str,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    """Persist one market-data quality/evidence check result."""

    row = await fetch_one(
        connection,
        INSERT_MARKET_QUALITY_CHECK_SQL,
        check_code,
        security_id,
        source_code,
        price_date,
        status_code,
        severity_code,
        observed_json,
        evidence_id,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("market quality check insert returned no row")
    return result


async def mark_price_bars_valid(connection: Any) -> str:
    """Mark raw price bars valid when basic OHLC checks pass."""

    return await execute(connection, MARK_PRICE_BARS_VALID_SQL)


async def list_price_bar_reconciliation(
    connection: Any, *, start_date: Any, end_date: Any, tolerance: Any
) -> list[dict[str, Any]]:
    """Return cross-source close-price differences above tolerance."""

    rows = await fetch_all(
        connection,
        LIST_PRICE_BAR_RECONCILIATION_SQL,
        start_date,
        end_date,
        tolerance,
    )
    return rows_to_dicts(rows)


async def get_market_price_bar_readiness(connection: Any) -> dict[str, Any]:
    """Return readiness metrics sourced only from ``market_price_bars``."""

    row = await fetch_one(connection, GET_MARKET_PRICE_BAR_READINESS_SQL)
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("market price bar readiness query returned no row")
    return result


async def upsert_macro_indicator(connection: Any, *, row: dict[str, Any]) -> dict[str, Any] | None:
    """Insert one macro indicator row, skipping duplicates."""

    return row_to_dict(
        await fetch_one(
            connection,
            UPSERT_MACRO_INDICATOR_SQL,
            row["indicator_code"],
            row["indicator_name"],
            row["reference_date"],
            row["value"],
            row["unit"],
            row["source_code"],
        )
    )
