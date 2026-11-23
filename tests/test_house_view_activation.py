"""House-view activation invariants against the real PostgreSQL database."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from apps.api.harness.repositories import house_views as house_repo
from db.migrator import database_url_from_env, load_env_file
from db.migrator import run as run_migrations
from db.seed import apply_profile
from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def _connect() -> Any:
    asyncpg = pytest.importorskip("asyncpg")
    load_env_file(PROJECT_ROOT / ".env")
    try:
        return await connect_with_retry(asyncpg, database_url_from_env())
    except Exception as exc:  # pragma: no cover - environment-dependent skip path
        pytest.skip(f"PostgreSQL integration database is unavailable: {exc}")


async def _prepare_database() -> Any:
    load_env_file(PROJECT_ROOT / ".env")
    try:
        await run_migrations()
    except Exception as exc:  # pragma: no cover - environment-dependent skip path
        pytest.skip(f"PostgreSQL migrations are unavailable: {exc}")
    connection = await _connect()
    try:
        await apply_profile(connection, "full-mvp")
    except Exception as exc:  # pragma: no cover - environment-dependent skip path
        await connection.close()
        pytest.skip(f"full-mvp seed is unavailable: {exc}")
    return connection


async def _active_house_view_ids(connection: Any) -> list[str]:
    rows = await connection.fetch(
        """/* sql_id: test_active_house_view_ids */
        SELECT id::text AS id
        FROM house_views
        WHERE status_code = 'ACTIVE'
        ORDER BY activated_at DESC NULLS LAST, created_at DESC;
        """
    )
    return [str(row["id"]) for row in rows]


async def _partial_unique_index_count(connection: Any) -> int:
    return int(
        await connection.fetchval(
            """/* sql_id: test_house_view_active_index_count */
            SELECT count(*)::integer
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'house_views'
              AND indexname = 'idx_house_views_one_active'
              AND indexdef ILIKE '%WHERE ((status_code)::text = ''ACTIVE''::text)%';
            """
        )
        or 0
    )


async def _run_activation_invariant_check() -> None:
    connection = await _prepare_database()
    try:
        assert await _partial_unique_index_count(connection) == 1
        active_before = await _active_house_view_ids(connection)
        assert len(active_before) == 1

        missing = await house_repo.activate_house_view(
            connection, house_view_id="00000000-0000-0000-0000-000000000000"
        )
        assert missing is None
        assert await _active_house_view_ids(connection) == active_before

        draft = await house_repo.create_house_view(
            connection,
            period_code="RALPH-QA",
            title="Ralph QA activation probe",
            summary="Synthetic house-view activation invariant probe.",
            created_by_id="22222222-2222-2222-2222-222222222203",
        )
        activated = await house_repo.activate_house_view(connection, house_view_id=str(draft["id"]))
        assert activated is not None
        assert activated["status_code"] == "ACTIVE"

        active_after = await _active_house_view_ids(connection)
        assert active_after == [str(draft["id"])]
    finally:
        await connection.close()


def test_house_view_activation_preserves_single_active_invariant():
    asyncio.run(_run_activation_invariant_check())
