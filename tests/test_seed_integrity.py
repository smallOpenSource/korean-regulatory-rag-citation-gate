"""Full-MVP seed data integrity checks against real PostgreSQL."""

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


async def _prepare_seeded_database() -> None:
    asyncpg = pytest.importorskip("asyncpg")
    load_env_file(PROJECT_ROOT / ".env")
    try:
        await run_migrations()
        connection = await connect_with_retry(asyncpg, database_url_from_env())
    except Exception as exc:  # pragma: no cover - environment-dependent skip path
        pytest.skip(f"PostgreSQL integration database is unavailable: {exc}")
    try:
        await apply_profile(connection, "full-mvp")
    finally:
        await connection.close()


@pytest.fixture(scope="module")
def seeded_database() -> None:
    asyncio.run(_prepare_seeded_database())


async def _fetch(sql: str) -> list[dict[str, Any]]:
    asyncpg = pytest.importorskip("asyncpg")
    connection = await connect_with_retry(asyncpg, database_url_from_env())
    try:
        return [dict(row) for row in await connection.fetch(sql)]
    finally:
        await connection.close()


def test_seed_portfolio_weights_and_valuation_ranges(seeded_database: None):
    weight_violations = asyncio.run(
        _fetch(
            """
            /* sql_id: test_seed_portfolio_weight_integrity */
            SELECT portfolio_id, sum(weight_pct)::numeric(8,4) AS weight_sum
            FROM portfolio_holdings
            GROUP BY portfolio_id
            HAVING abs(sum(weight_pct) - 100.0000) > 0.0100;
            """
        )
    )
    valuation_violations = asyncio.run(
        _fetch(
            """
            /* sql_id: test_seed_portfolio_valuation_integrity */
            WITH portfolio_values AS (
                SELECT p.customer_id, sum(h.market_value_krw) AS holding_value
                FROM portfolios p
                JOIN portfolio_holdings h ON h.portfolio_id = p.id
                GROUP BY p.customer_id
            )
            SELECT c.customer_no, c.customer_name, c.total_assets_krw, pv.holding_value
            FROM customers c
            JOIN portfolio_values pv ON pv.customer_id = c.id
            WHERE pv.holding_value < c.total_assets_krw * 0.20
               OR pv.holding_value > c.total_assets_krw * 1.50;
            """
        )
    )

    assert weight_violations == []
    assert valuation_violations == []


def test_seed_recommendation_suitability_warnings_are_consistent(seeded_database: None):
    recommendation_violations = asyncio.run(
        _fetch(
            """
            /* sql_id: test_seed_recommendation_suitability_integrity */
            SELECT r.id, c.customer_name, c.risk_grade_code, p.product_name, p.risk_level_code,
                   r.status_code, r.suitability_passed, r.gate_detail_json
            FROM recommendation_simulations r
            JOIN customers c ON c.id = r.customer_id
            JOIN products p ON p.id = r.product_id
            WHERE r.id::text LIKE 'bbbbbbbb-bbbb-bbbb-bbbb-000000003%'
              AND (
                    (
                        p.risk_level_code::integer > c.risk_grade_code::integer
                        AND (
                            r.status_code <> 'BLOCKED'
                            OR r.suitability_passed IS TRUE
                            OR NOT (r.gate_detail_json -> 'failed' ? 'suitability_passed')
                        )
                    )
                    OR (
                        p.risk_level_code::integer <= c.risk_grade_code::integer
                        AND r.suitability_passed IS FALSE
                    )
                  );
            """
        )
    )
    order_violations = asyncio.run(
        _fetch(
            """
            /* sql_id: test_seed_order_recommendation_integrity */
            SELECT o.id, o.status_code AS order_status, r.status_code AS recommendation_status
            FROM order_simulations o
            JOIN recommendation_simulations r ON r.id = o.recommendation_simulation_id
            WHERE o.id::text LIKE 'cccccccc-cccc-cccc-cccc-000000003%'
              AND o.status_code = 'SIMULATED_EXECUTED'
              AND r.status_code <> 'APPROVED';
            """
        )
    )

    assert recommendation_violations == []
    assert order_violations == []


def test_seed_user_facing_fields_do_not_expose_placeholder_copy(seeded_database: None):
    placeholder_rows = asyncio.run(
        _fetch(
            """
            /* sql_id: test_seed_user_facing_placeholder_integrity */
            SELECT 'employees.name' AS field_name, name AS field_value
            FROM employees
            WHERE name ~* '(Synthetic|SYN-)'
            UNION ALL
            SELECT 'customers.customer_name' AS field_name, customer_name AS field_value
            FROM customers
            WHERE customer_name ~* '(Synthetic|SYN-CUST|고객\\s*[0-9]+$)'
               OR customer_name ~ '[0-9]{2,3}-[0-9]{3,4}-[0-9]{4}'
               OR customer_name ~ '[0-9]{6}-[1-4][0-9]{6}'
               OR customer_name ~* '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+'
            UNION ALL
            SELECT 'products.product_name' AS field_name, product_name AS field_value
            FROM products
            WHERE product_name ~* '(Synthetic|SYN-)'
               OR product_name ~ '[0-9]{2,3}-[0-9]{3,4}-[0-9]{4}'
               OR product_name ~ '[0-9]{6}-[1-4][0-9]{6}'
               OR product_name ~* '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+'
            UNION ALL
            SELECT 'portfolios.portfolio_name' AS field_name, portfolio_name AS field_value
            FROM portfolios
            WHERE portfolio_name ~* '(Synthetic|SYN-|고객\\s*[0-9]+$)'
               OR portfolio_name ~ '[0-9]{2,3}-[0-9]{3,4}-[0-9]{4}'
               OR portfolio_name ~ '[0-9]{6}-[1-4][0-9]{6}'
               OR portfolio_name ~* '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+';
            """
        )
    )

    assert placeholder_rows == []
