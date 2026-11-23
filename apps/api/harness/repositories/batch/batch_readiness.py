"""Market universe, calendar, coverage, and portfolio-valuation repository helpers.

sql_id namespace: harness.batch.repo.readiness.*
"""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import fetch_one

from ..common import row_to_dict

UPSERT_MARKET_UNIVERSE_SNAPSHOT_SQL = """
/* sql_id: upsert_market_universe_snapshot */
INSERT INTO market_universe_snapshots(
    universe_code, as_of_date, resolved_trading_date, source_code, source_policy_code,
    rank_method_code, target_size, selected_count, raw_candidate_count, excluded_count,
    coverage_status_code, provider_evidence_id
)
VALUES (
    $1::varchar, $2::date, $3::date, $4::varchar, $5::varchar, $6::varchar, $7::integer,
    $8::integer, $9::integer, $10::integer, $11::varchar, $12::uuid
)
ON CONFLICT (universe_code, as_of_date, source_code, source_policy_code) DO UPDATE SET
    resolved_trading_date = EXCLUDED.resolved_trading_date,
    rank_method_code = EXCLUDED.rank_method_code,
    target_size = EXCLUDED.target_size,
    selected_count = EXCLUDED.selected_count,
    raw_candidate_count = EXCLUDED.raw_candidate_count,
    excluded_count = EXCLUDED.excluded_count,
    coverage_status_code = EXCLUDED.coverage_status_code,
    provider_evidence_id = EXCLUDED.provider_evidence_id,
    updated_at = now()
RETURNING id, universe_code, as_of_date, resolved_trading_date, source_code,
          source_policy_code, rank_method_code, target_size, selected_count,
          raw_candidate_count, excluded_count, coverage_status_code, provider_evidence_id,
          created_at, updated_at;
"""

UPSERT_MARKET_UNIVERSE_CANDIDATE_SQL = """
/* sql_id: upsert_market_universe_candidate */
INSERT INTO market_universe_candidates(
    snapshot_id, security_id, ticker, isin, security_name_kr, market_code,
    rank_before_filter, rank_after_filter, market_cap_krw, listed_shares, close_price,
    section_type_name, company_key, company_key_source_code, raw_payload_hash, included,
    exclusion_reason_code, provider_evidence_id
)
VALUES (
    $1::uuid, $2::uuid, $3::varchar, $4::varchar, $5::varchar, $6::varchar,
    $7::integer, $8::integer, $9::numeric, $10::numeric, $11::numeric, $12::varchar,
    $13::varchar, $14::varchar, $15::varchar, $16::boolean, $17::varchar, $18::uuid
)
ON CONFLICT (snapshot_id, ticker) DO UPDATE SET
    security_id = EXCLUDED.security_id,
    isin = EXCLUDED.isin,
    security_name_kr = EXCLUDED.security_name_kr,
    market_code = EXCLUDED.market_code,
    rank_before_filter = EXCLUDED.rank_before_filter,
    rank_after_filter = EXCLUDED.rank_after_filter,
    market_cap_krw = EXCLUDED.market_cap_krw,
    listed_shares = EXCLUDED.listed_shares,
    close_price = EXCLUDED.close_price,
    section_type_name = EXCLUDED.section_type_name,
    company_key = EXCLUDED.company_key,
    company_key_source_code = EXCLUDED.company_key_source_code,
    raw_payload_hash = EXCLUDED.raw_payload_hash,
    included = EXCLUDED.included,
    exclusion_reason_code = EXCLUDED.exclusion_reason_code,
    provider_evidence_id = EXCLUDED.provider_evidence_id,
    updated_at = now()
RETURNING id, snapshot_id, security_id, ticker, isin, security_name_kr, market_code,
          rank_before_filter, rank_after_filter, market_cap_krw, listed_shares, close_price,
          section_type_name, company_key, company_key_source_code, raw_payload_hash, included,
          exclusion_reason_code, provider_evidence_id, created_at, updated_at;
"""

UPSERT_MARKET_UNIVERSE_MEMBER_SQL = """
/* sql_id: upsert_market_universe_member */
INSERT INTO market_universe_members(
    snapshot_id, security_id, ticker, company_key, rank_no, market_code, market_cap_krw,
    listed_shares, close_price, included_reason_code
)
VALUES (
    $1::uuid, $2::uuid, $3::varchar, $4::varchar, $5::integer, $6::varchar, $7::numeric,
    $8::numeric, $9::numeric, $10::varchar
)
ON CONFLICT (snapshot_id, ticker) DO UPDATE SET
    security_id = EXCLUDED.security_id,
    company_key = EXCLUDED.company_key,
    rank_no = EXCLUDED.rank_no,
    market_code = EXCLUDED.market_code,
    market_cap_krw = EXCLUDED.market_cap_krw,
    listed_shares = EXCLUDED.listed_shares,
    close_price = EXCLUDED.close_price,
    included_reason_code = EXCLUDED.included_reason_code,
    updated_at = now()
RETURNING id, snapshot_id, security_id, ticker, company_key, rank_no, market_code,
          market_cap_krw, listed_shares, close_price, included_reason_code, created_at,
          updated_at;
"""

UPSERT_MARKET_TRADING_CALENDAR_SQL = """
/* sql_id: upsert_market_trading_calendar */
INSERT INTO market_trading_calendar(
    calendar_date, market_code, source_code, source_policy_code, is_expected_trading_day,
    is_observed_trading_day, no_trading_reason_code, batch_provider_evidence_id
)
VALUES (
    $1::date, $2::varchar, $3::varchar, $4::varchar, $5::boolean, $6::boolean,
    $7::varchar, $8::uuid
)
ON CONFLICT (market_code, calendar_date, source_code, source_policy_code) DO UPDATE SET
    is_expected_trading_day = EXCLUDED.is_expected_trading_day,
    is_observed_trading_day = EXCLUDED.is_observed_trading_day,
    no_trading_reason_code = EXCLUDED.no_trading_reason_code,
    batch_provider_evidence_id = EXCLUDED.batch_provider_evidence_id,
    updated_at = now()
RETURNING calendar_date, market_code, source_code, source_policy_code, is_expected_trading_day,
          is_observed_trading_day, no_trading_reason_code, batch_provider_evidence_id,
          created_at, updated_at;
"""

UPSERT_MARKET_UNIVERSE_COVERAGE_DAILY_SQL = """
/* sql_id: upsert_market_universe_coverage_daily */
INSERT INTO market_universe_coverage_daily(
    snapshot_id, member_id, security_id, market_code, calendar_date, is_expected_trading_day,
    has_valid_bar, market_price_bar_id, missing_reason_code, quality_status_code,
    batch_provider_evidence_id
)
VALUES (
    $1::uuid, $2::uuid, $3::uuid, $4::varchar, $5::date, $6::boolean, $7::boolean,
    $8::uuid, $9::varchar, $10::varchar, $11::uuid
)
ON CONFLICT (snapshot_id, member_id, calendar_date) DO UPDATE SET
    security_id = EXCLUDED.security_id,
    market_code = EXCLUDED.market_code,
    is_expected_trading_day = EXCLUDED.is_expected_trading_day,
    has_valid_bar = EXCLUDED.has_valid_bar,
    market_price_bar_id = EXCLUDED.market_price_bar_id,
    missing_reason_code = EXCLUDED.missing_reason_code,
    quality_status_code = EXCLUDED.quality_status_code,
    batch_provider_evidence_id = EXCLUDED.batch_provider_evidence_id,
    updated_at = now()
RETURNING id, snapshot_id, member_id, security_id, market_code, calendar_date,
          is_expected_trading_day, has_valid_bar, market_price_bar_id, missing_reason_code,
          quality_status_code, batch_provider_evidence_id, created_at, updated_at;
"""

GET_MARKET_UNIVERSE_COVERAGE_READINESS_SQL = """
/* sql_id: get_market_universe_coverage_readiness */
WITH latest_snapshot AS (
    SELECT id, universe_code, as_of_date, resolved_trading_date, target_size, selected_count,
           raw_candidate_count, excluded_count, coverage_status_code
    FROM market_universe_snapshots
    WHERE universe_code = $1::varchar
    ORDER BY as_of_date DESC, resolved_trading_date DESC, created_at DESC
    LIMIT 1
), coverage AS (
    SELECT count(*) FILTER (WHERE is_expected_trading_day IS TRUE)::integer AS expected_member_days,
           count(*) FILTER (
               WHERE is_expected_trading_day IS TRUE AND has_valid_bar IS TRUE
           )::integer AS valid_member_days,
           count(*) FILTER (
               WHERE is_expected_trading_day IS TRUE AND has_valid_bar IS FALSE
           )::integer AS missing_member_days,
           count(DISTINCT calendar_date) FILTER (
               WHERE is_expected_trading_day IS TRUE
           )::integer AS expected_trading_days
    FROM market_universe_coverage_daily daily
    JOIN latest_snapshot ON latest_snapshot.id = daily.snapshot_id
)
SELECT latest_snapshot.id AS snapshot_id, latest_snapshot.universe_code,
       latest_snapshot.as_of_date, latest_snapshot.resolved_trading_date,
       latest_snapshot.target_size, latest_snapshot.selected_count,
       latest_snapshot.raw_candidate_count, latest_snapshot.excluded_count,
       latest_snapshot.coverage_status_code,
       COALESCE(coverage.expected_member_days, 0) AS expected_member_days,
       COALESCE(coverage.valid_member_days, 0) AS valid_member_days,
       COALESCE(coverage.missing_member_days, 0) AS missing_member_days,
       COALESCE(coverage.expected_trading_days, 0) AS expected_trading_days,
       CASE
           WHEN COALESCE(coverage.expected_member_days, 0) = 0 THEN 0::numeric
           ELSE COALESCE(coverage.valid_member_days, 0)::numeric
                / coverage.expected_member_days::numeric
       END AS coverage_ratio
FROM latest_snapshot
LEFT JOIN coverage ON TRUE;
"""

GET_PORTFOLIO_VALUATION_FROM_BARS_SQL = """
/* sql_id: get_portfolio_valuation_from_bars */
WITH latest_bars AS (
    SELECT DISTINCT ON (bar.security_id)
           bar.security_id, bar.close_price, bar.price_date, bar.source_code, bar.source_as_of
    FROM market_price_bars bar
    WHERE bar.quality_status_code IN ('VALID', 'RECONCILED')
    ORDER BY bar.security_id, bar.price_date DESC, bar.source_as_of DESC
), holding_values AS (
    SELECT h.portfolio_id,
           sum(
               h.quantity * latest_bars.close_price * COALESCE(pu.weight_pct, 100.0000)
               / 100.0000
           )::numeric(20,2) AS valued_market_value_krw,
           max(latest_bars.price_date) AS valuation_price_date,
           max(latest_bars.source_as_of) AS source_as_of,
           count(latest_bars.security_id)::integer AS priced_holding_count,
           count(h.id)::integer AS holding_count
    FROM portfolio_holdings h
    JOIN product_underlyings pu ON pu.product_id = h.product_id
    LEFT JOIN latest_bars ON latest_bars.security_id = pu.security_id
    WHERE h.portfolio_id = $1::uuid
    GROUP BY h.portfolio_id
)
SELECT portfolio_id, valued_market_value_krw, valuation_price_date, source_as_of,
       priced_holding_count, holding_count,
       (priced_holding_count = holding_count AND holding_count > 0) AS valuation_ready
FROM holding_values;
"""


async def upsert_market_universe_snapshot(
    connection: Any,
    *,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Insert or refresh one official KRX universe snapshot header."""

    result = row_to_dict(
        await fetch_one(
            connection,
            UPSERT_MARKET_UNIVERSE_SNAPSHOT_SQL,
            row["universe_code"],
            row["as_of_date"],
            row["resolved_trading_date"],
            row.get("source_code", "KRX"),
            row.get("source_policy_code", "OFFICIAL_KRX_APPROVED"),
            row.get("rank_method_code", "MARKET_CAP_DESC"),
            row["target_size"],
            row.get("selected_count", 0),
            row.get("raw_candidate_count", 0),
            row.get("excluded_count", 0),
            row.get("coverage_status_code", "PENDING"),
            row.get("provider_evidence_id"),
        )
    )
    if result is None:
        raise RuntimeError("market universe snapshot upsert returned no row")
    return result


async def upsert_market_universe_candidate(
    connection: Any,
    *,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Insert or refresh one official KRX top-universe candidate row."""

    result = row_to_dict(
        await fetch_one(
            connection,
            UPSERT_MARKET_UNIVERSE_CANDIDATE_SQL,
            row["snapshot_id"],
            row.get("security_id"),
            row["ticker"],
            row.get("isin"),
            row["security_name_kr"],
            row["market_code"],
            row["rank_before_filter"],
            row.get("rank_after_filter"),
            row["market_cap_krw"],
            row.get("listed_shares"),
            row.get("close_price"),
            row.get("section_type_name"),
            row["company_key"],
            row.get("company_key_source_code", "TICKER"),
            row["raw_payload_hash"],
            bool(row.get("included", False)),
            row.get("exclusion_reason_code"),
            row.get("provider_evidence_id"),
        )
    )
    if result is None:
        raise RuntimeError("market universe candidate upsert returned no row")
    return result


async def upsert_market_universe_member(
    connection: Any,
    *,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Insert or refresh one selected top-universe member row."""

    result = row_to_dict(
        await fetch_one(
            connection,
            UPSERT_MARKET_UNIVERSE_MEMBER_SQL,
            row["snapshot_id"],
            row["security_id"],
            row["ticker"],
            row["company_key"],
            row["rank_no"],
            row["market_code"],
            row["market_cap_krw"],
            row.get("listed_shares"),
            row.get("close_price"),
            row.get("included_reason_code", "TOP_MARKET_CAP_COMMON_EQUITY"),
        )
    )
    if result is None:
        raise RuntimeError("market universe member upsert returned no row")
    return result


async def upsert_market_trading_calendar_day(
    connection: Any,
    *,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Insert or refresh one official market-calendar denominator day."""

    result = row_to_dict(
        await fetch_one(
            connection,
            UPSERT_MARKET_TRADING_CALENDAR_SQL,
            row["calendar_date"],
            row["market_code"],
            row.get("source_code", "KRX"),
            row.get("source_policy_code", "OFFICIAL_KRX_APPROVED"),
            bool(row["is_expected_trading_day"]),
            bool(row.get("is_observed_trading_day", False)),
            row.get("no_trading_reason_code"),
            row.get("batch_provider_evidence_id"),
        )
    )
    if result is None:
        raise RuntimeError("market trading calendar upsert returned no row")
    return result


async def upsert_market_universe_coverage_daily(
    connection: Any,
    *,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Insert or refresh one selected-member daily coverage fact."""

    result = row_to_dict(
        await fetch_one(
            connection,
            UPSERT_MARKET_UNIVERSE_COVERAGE_DAILY_SQL,
            row["snapshot_id"],
            row["member_id"],
            row["security_id"],
            row["market_code"],
            row["calendar_date"],
            bool(row["is_expected_trading_day"]),
            bool(row.get("has_valid_bar", False)),
            row.get("market_price_bar_id"),
            row.get("missing_reason_code"),
            row.get("quality_status_code", "VALID" if row.get("has_valid_bar") else "MISSING"),
            row.get("batch_provider_evidence_id"),
        )
    )
    if result is None:
        raise RuntimeError("market universe coverage daily upsert returned no row")
    return result


async def get_market_universe_coverage_readiness(
    connection: Any,
    *,
    universe_code: str = "DOMESTIC_TOP200_MARKET_CAP",
) -> dict[str, Any] | None:
    """Return latest top-universe coverage metrics from persisted DB evidence."""

    return row_to_dict(
        await fetch_one(connection, GET_MARKET_UNIVERSE_COVERAGE_READINESS_SQL, universe_code)
    )


async def get_portfolio_valuation_from_bars(
    connection: Any, *, portfolio_id: str
) -> dict[str, Any] | None:
    """Value product-underlying holdings from latest usable ``market_price_bars`` only."""

    return row_to_dict(
        await fetch_one(connection, GET_PORTFOLIO_VALUATION_FROM_BARS_SQL, portfolio_id)
    )
