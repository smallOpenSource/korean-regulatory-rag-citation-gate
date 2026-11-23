"""DB integration checks for the deterministic full-MVP seed profile."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from db.migrator import database_url_from_env, load_env_file
from db.migrator import run as run_migrations
from db.seed import apply_profile
from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STABLE_COUNT_TABLES = (
    "customers",
    "products",
    "portfolios",
    "portfolio_holdings",
    "nba_actions",
    "aftercare_events",
    "documents",
    "document_chunks",
    "batch_job_logs",
)
PROVIDER_TABLES = (
    "market_price_bars",
    "market_prices",
    "financial_ratios",
    "investor_flows",
    "macro_indicators",
)


async def _connect() -> Any:
    asyncpg = pytest.importorskip("asyncpg")
    load_env_file(PROJECT_ROOT / ".env")
    try:
        return await connect_with_retry(asyncpg, database_url_from_env())
    except Exception as exc:  # pragma: no cover - environment-dependent skip path
        pytest.skip(f"PostgreSQL integration database is unavailable: {exc}")


async def _count_rows(connection: Any, table_name: str) -> int:
    sql = (
        f"/* sql_id: test_seed_count_{table_name} */\n"
        f"SELECT count(*)::integer AS row_count FROM {table_name};"
    )
    return int(await connection.fetchval(sql) or 0)


async def _table_counts(connection: Any, table_names: tuple[str, ...]) -> dict[str, int]:
    return {table_name: await _count_rows(connection, table_name) for table_name in table_names}


async def _provider_doc_counts(connection: Any) -> dict[str, int]:
    row = await connection.fetchrow(
        """/* sql_id: test_seed_provider_doc_counts */
        SELECT
            (
                SELECT count(*)::integer
                FROM raw_documents
                WHERE source_type_code <> 'MANUAL'
            ) AS raw_count,
            (
                SELECT count(*)::integer
                FROM documents
                WHERE source_type_code <> 'MANUAL'
            ) AS doc_count,
            (
                SELECT count(*)::integer
                FROM document_chunks dc
                JOIN documents d ON d.id = dc.document_id
                WHERE d.source_type_code <> 'MANUAL'
                  AND (dc.embedding IS NOT NULL OR dc.is_embedded IS TRUE)
            ) AS embedded_count;
        """
    )
    return dict(row)


async def _run_seed_idempotency_check() -> None:
    load_env_file(PROJECT_ROOT / ".env")
    try:
        await run_migrations()
    except Exception as exc:  # pragma: no cover - environment-dependent skip path
        pytest.skip(f"PostgreSQL integration database is unavailable: {exc}")
    connection = await _connect()
    try:
        provider_counts_before = await _table_counts(connection, PROVIDER_TABLES)
        provider_doc_counts_before = await _provider_doc_counts(connection)
        first_result = await apply_profile(connection, "full-mvp")
        first_counts = await _table_counts(connection, STABLE_COUNT_TABLES)
        second_result = await apply_profile(connection, "full-mvp")
        second_counts = await _table_counts(connection, STABLE_COUNT_TABLES)
        provider_counts_after = await _table_counts(connection, PROVIDER_TABLES)
        provider_doc_counts_after = await _provider_doc_counts(connection)
        display_placeholder_count = await connection.fetchval(
            """/* sql_id: test_seed_display_placeholder_count */
            SELECT count(*)::integer
            FROM customers c
            JOIN portfolios pf ON pf.customer_id = c.id
            JOIN portfolio_holdings ph ON ph.portfolio_id = pf.id
            JOIN products pr ON pr.id = ph.product_id
            WHERE c.customer_name ~* '(SYN-CUST|Synthetic|고객\\s*[0-9]+$)'
               OR pf.portfolio_name ~* '(Synthetic Portfolio|SYN-|고객\\s*[0-9]+$)'
               OR pr.product_name ~* '(Synthetic|SYN-)'
               OR c.customer_name ~ '[0-9]{2,3}-[0-9]{3,4}-[0-9]{4}'
               OR c.customer_name ~ '[0-9]{6}-[1-4][0-9]{6}'
               OR c.customer_name ~* '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+'
               OR pf.portfolio_name ~ '[0-9]{2,3}-[0-9]{3,4}-[0-9]{4}'
               OR pf.portfolio_name ~ '[0-9]{6}-[1-4][0-9]{6}'
               OR pf.portfolio_name ~* '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+'
               OR pr.product_name ~ '[0-9]{2,3}-[0-9]{3,4}-[0-9]{4}'
               OR pr.product_name ~ '[0-9]{6}-[1-4][0-9]{6}'
               OR pr.product_name ~* '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+';
            """
        )
        incoherent_weight_count = await connection.fetchval(
            """/* sql_id: test_seed_incoherent_weight_count */
            SELECT count(*)::integer
            FROM (
                SELECT portfolio_id, sum(weight_pct) AS total_weight
                FROM portfolio_holdings
                GROUP BY portfolio_id
            ) weights
            WHERE abs(total_weight - 100.0000) > 0.0100;
            """
        )
        incoherent_asset_count = await connection.fetchval(
            """/* sql_id: test_seed_incoherent_asset_count */
            SELECT count(*)::integer
            FROM (
                SELECT c.id, c.total_assets_krw, sum(ph.market_value_krw) AS holding_value
                FROM customers c
                JOIN portfolios pf ON pf.customer_id = c.id
                JOIN portfolio_holdings ph ON ph.portfolio_id = pf.id
                GROUP BY c.id, c.total_assets_krw
            ) totals
            WHERE abs(holding_value - total_assets_krw) > 1.00;
            """
        )
        risk_mismatch_count = await connection.fetchval(
            """/* sql_id: test_seed_risk_mismatch_count */
            SELECT count(*)::integer
            FROM customers c
            JOIN portfolios pf ON pf.customer_id = c.id
            JOIN portfolio_holdings ph ON ph.portfolio_id = pf.id
            JOIN products pr ON pr.id = ph.product_id
            WHERE pr.risk_level_code::integer > c.risk_grade_code::integer;
            """
        )
        simulation_id_counts = await connection.fetchrow(
            """/* sql_id: test_seed_simulation_id_stability */
            WITH seed_customers AS (
                SELECT (
                    '33333333-3333-3333-3333-'
                    || lpad((333333333300 + customer_no)::text, 12, '0')
                )::uuid AS id
                FROM generate_series(1, 20) AS customer(customer_no)
            ), recommendation_counts AS (
                SELECT
                    count(*) FILTER (
                        WHERE r.id::text LIKE 'bbbbbbbb-bbbb-bbbb-bbbb-000000003%'
                    )::integer AS expected_recommendations,
                    count(*) FILTER (
                        WHERE r.id::text NOT LIKE 'bbbbbbbb-bbbb-bbbb-bbbb-000000003%'
                    )::integer AS unexpected_recommendations
                FROM recommendation_simulations r
                JOIN seed_customers sc ON sc.id = r.customer_id
            ), order_counts AS (
                SELECT
                    count(*) FILTER (
                        WHERE o.id::text LIKE 'cccccccc-cccc-cccc-cccc-000000003%'
                    )::integer AS expected_orders,
                    count(*) FILTER (
                        WHERE o.id::text NOT LIKE 'cccccccc-cccc-cccc-cccc-000000003%'
                    )::integer AS unexpected_orders
                FROM order_simulations o
                JOIN seed_customers sc ON sc.id = o.customer_id
            )
            SELECT *
            FROM recommendation_counts
            CROSS JOIN order_counts;
            """
        )
    finally:
        await connection.close()

    assert first_result["readiness"]["ready"] is True
    assert second_result["readiness"]["ready"] is True
    assert first_counts == second_counts
    assert provider_counts_before == provider_counts_after
    assert provider_doc_counts_before == provider_doc_counts_after
    assert display_placeholder_count == 0
    assert incoherent_weight_count == 0
    assert incoherent_asset_count == 0
    assert risk_mismatch_count == 0
    assert dict(simulation_id_counts) == {
        "expected_recommendations": 12,
        "unexpected_recommendations": 0,
        "expected_orders": 12,
        "unexpected_orders": 0,
    }


def test_full_mvp_seed_profile_runs_against_postgres_and_is_idempotent():
    asyncio.run(_run_seed_idempotency_check())
