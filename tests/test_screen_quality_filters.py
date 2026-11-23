"""Screen-quality filter invariants for house_views and email_drafts.

PB/WM staff lists must hide internal test fixtures and identifier-leaking rows.
ADMIN/AUDIT_VIEWER can opt in to see fixtures via the explicit query param.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from apps.api.harness.core.rbac import ActorContext
from apps.api.harness.repositories import email as email_repo
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
    except Exception as exc:
        pytest.skip(f"PostgreSQL integration database is unavailable: {exc}")


async def _prepare_connection() -> Any:
    load_env_file(PROJECT_ROOT / ".env")
    try:
        await run_migrations()
    except Exception as exc:
        pytest.skip(f"PostgreSQL migrations are unavailable: {exc}")
    connection = await _connect()
    try:
        await apply_profile(connection, "full-mvp")
    except Exception as exc:
        await connection.close()
        pytest.skip(f"full-mvp seed is unavailable: {exc}")
    return connection


def _has_test_fixture_token(text: str | None) -> bool:
    if not text:
        return False
    haystack = text.upper()
    for token in ("GOLDEN_TEST", "RALPH", "SYNTHETIC BOUNDARY", "GOLDEN REGRESSION"):
        if token in haystack:
            return True
    return False


async def _run_house_view_pb_filter_check() -> None:
    connection = await _prepare_connection()
    try:
        rows = await house_repo.list_house_views(
            connection,
            status_code=None,
            limit=200,
            offset=0,
            include_test_fixtures=False,
        )
    finally:
        await connection.close()

    for row in rows:
        status = str(row.get("status_code") or "")
        title = str(row.get("title") or "")
        summary = str(row.get("summary") or "")
        assert status not in {
            "GOLDEN_TEST",
            "GOLDEN",
            "RALPH",
            "RALPH-QA",
            "RALPH_QA",
            "SYNTHETIC_BOUNDARY",
            "TEST",
            "TEST_FIXTURE",
        }, f"PB list leaked test status_code: {status} ({row.get('id')})"
        assert not _has_test_fixture_token(title), (
            f"PB list leaked test title: {title!r}"
        )
        assert not _has_test_fixture_token(summary), (
            f"PB list leaked test summary: {summary!r}"
        )


async def _run_house_view_admin_opt_in_check() -> None:
    connection = await _prepare_connection()
    try:
        unfiltered = await house_repo.list_house_views(
            connection,
            status_code=None,
            limit=200,
            offset=0,
            include_test_fixtures=True,
        )
        filtered = await house_repo.list_house_views(
            connection,
            status_code=None,
            limit=200,
            offset=0,
            include_test_fixtures=False,
        )
    finally:
        await connection.close()

    assert len(unfiltered) >= len(filtered)


async def _run_email_draft_pb_filter_check() -> None:
    connection = await _prepare_connection()
    try:
        row = await connection.fetchrow(
            """/* sql_id: test_pick_synthetic_pb */
            SELECT id::text AS id, branch_id::text AS branch_id
            FROM employees
            WHERE role_code = 'PB'
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
        if row is None:
            pytest.skip("No synthetic PB employee available for the screen-quality filter test")
        actor = ActorContext(
            role_code="PB",
            employee_id=row["id"],
            branch_id=row["branch_id"],
        )
        drafts = await email_repo.list_email_drafts_for_actor(
            connection,
            actor=actor,
            status_code=None,
            limit=200,
            offset=0,
        )
    finally:
        await connection.close()

    for draft in drafts:
        subject = str(draft.get("subject") or "")
        body = str(draft.get("body") or "")
        assert not _has_test_fixture_token(subject), (
            f"PB email draft list leaked test subject: {subject!r}"
        )
        assert "REG-04" not in body, (
            f"PB email draft list leaked internal identifier in body: {body!r}"
        )
        assert "GOLDEN_TEST" not in body.upper(), (
            f"PB email draft list leaked test marker in body: {body!r}"
        )


def test_list_house_views_excludes_test_fixtures_for_pb() -> None:
    asyncio.run(_run_house_view_pb_filter_check())


def test_list_house_views_admin_opt_in_returns_fixtures() -> None:
    asyncio.run(_run_house_view_admin_opt_in_check())


def test_list_email_drafts_excludes_golden_test_subjects_for_pb() -> None:
    asyncio.run(_run_email_draft_pb_filter_check())


def test_format_module_smoke() -> None:
    """Sanity assertions for the JS-side format helpers contract (string match)."""
    src = (PROJECT_ROOT / "apps" / "web" / "src" / "lib" / "format.ts").read_text(
        encoding="utf-8"
    )
    assert "formatBankerTimestamp" in src, "formatBankerTimestamp helper is missing"
    assert "formatBankerNumber" in src, "formatBankerNumber helper is missing"
    assert "SEOUL_TZ_OFFSET_MIN" in src


def test_dev_reference_component_exists() -> None:
    """Stage 3 contract: DevReference component must guard internal identifiers."""
    src = (PROJECT_ROOT / "apps" / "web" / "src" / "components" / "DevReference.tsx").read_text(
        encoding="utf-8"
    )
    assert "ADMIN" in src and "AUDIT_VIEWER" in src
    assert "useAuthStore" in src
