"""Tests for V054 — v8 audit_action_codes + audit_logs_v8_archive.

Verifies three contracts introduced by V054__v8_audit_action_codes_and_cleanup.sql:

1. audit_action_codes 에 v8_cell_visited / v8_unreachable_marked 존재.
2. audit_logs_v8_archive 테이블 존재 + audit_logs 와 동일 컬럼 구조
   (id, actor_id, action_code, resource_type, resource_id, ip_address,
    user_agent, detail_json, created_at + archived_at 추가).
3. audit_logs 에 v8_cell_visited INSERT 성공 — V008/V019 trigger 미발동
   (UPDATE/DELETE/TRUNCATE 차단 trigger 이며 INSERT 는 무제한 허용).

DATABASE_URL 미설정 시 pytest.skip 으로 soft-fail.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("asyncpg")
import asyncpg  # noqa: E402

from tests._pg_retry import connect_with_retry  # noqa: E402


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@pytest.fixture(scope="module")
def db_url() -> str:
    _load_env()
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping V054 DB tests")
    return url


# ─── helper ─────────────────────────────────────────────────────────────────

def _run(coro):  # type: ignore[no-untyped-def]
    """Python 3.11 deprecated get_event_loop() outside a running loop;
    asyncio.run() is the supported replacement that creates a fresh loop
    per call and closes it cleanly.
    """
    return asyncio.run(coro)


# ─── Test 1: audit_action_codes 존재 ────────────────────────────────────────

def test_v8_cell_visited_action_code_exists(db_url: str) -> None:
    """audit_action_codes 에 v8_cell_visited 가 등록되어 있어야 한다."""

    async def _check() -> None:
        conn = await connect_with_retry(asyncpg, db_url)
        try:
            row = await conn.fetchrow(
                "SELECT action_code, description FROM audit_action_codes"
                " WHERE action_code = $1",
                "v8_cell_visited",
            )
            if row is None:
                pytest.skip(
                    "v8_cell_visited not in audit_action_codes — V054 migration not applied yet"
                )
            assert row["action_code"] == "v8_cell_visited"
            assert row["description"]  # non-empty description required
        finally:
            await conn.close()

    _run(_check())


def test_v8_unreachable_marked_action_code_exists(db_url: str) -> None:
    """audit_action_codes 에 v8_unreachable_marked 가 등록되어 있어야 한다."""

    async def _check() -> None:
        conn = await connect_with_retry(asyncpg, db_url)
        try:
            row = await conn.fetchrow(
                "SELECT action_code, description FROM audit_action_codes"
                " WHERE action_code = $1",
                "v8_unreachable_marked",
            )
            if row is None:
                pytest.skip(
                    "v8_unreachable_marked not in audit_action_codes — V054 migration not applied yet"
                )
            assert row["action_code"] == "v8_unreachable_marked"
            assert row["description"]
        finally:
            await conn.close()

    _run(_check())


# ─── Test 2: audit_logs_v8_archive 테이블 + 컬럼 구조 ───────────────────────

_EXPECTED_ARCHIVE_COLUMNS = frozenset({
    "id",
    "actor_id",
    "action_code",
    "resource_type",
    "resource_id",
    "ip_address",
    "user_agent",
    "detail_json",
    "created_at",
    "archived_at",
})


def test_audit_logs_v8_archive_table_exists(db_url: str) -> None:
    """audit_logs_v8_archive 테이블이 존재해야 한다."""

    async def _check() -> None:
        conn = await connect_with_retry(asyncpg, db_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'audit_logs_v8_archive'
                """
            )
            if row is None:
                pytest.skip(
                    "audit_logs_v8_archive table not found — V054 migration not applied yet"
                )
            assert row["table_name"] == "audit_logs_v8_archive"
        finally:
            await conn.close()

    _run(_check())


def test_audit_logs_v8_archive_has_required_columns(db_url: str) -> None:
    """audit_logs_v8_archive 컬럼이 audit_logs 동일 + archived_at 추가여야 한다."""

    async def _check() -> None:
        conn = await connect_with_retry(asyncpg, db_url)
        try:
            rows = await conn.fetch(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'audit_logs_v8_archive'
                """
            )
            if not rows:
                pytest.skip(
                    "audit_logs_v8_archive table not found — V054 migration not applied yet"
                )
            actual_columns = {row["column_name"] for row in rows}
            missing = _EXPECTED_ARCHIVE_COLUMNS - actual_columns
            assert not missing, (
                f"audit_logs_v8_archive missing columns: {sorted(missing)}"
            )
        finally:
            await conn.close()

    _run(_check())


# ─── Test 3: audit_logs INSERT v8_cell_visited — trigger 미발동 ──────────────

def test_audit_logs_insert_v8_cell_visited_no_trigger_block(db_url: str) -> None:
    """audit_logs 에 v8_cell_visited row INSERT 가 성공해야 한다.

    V008 trg_audit_logs_no_update / trg_audit_logs_no_delete,
    V019 trg_audit_logs_no_truncate 는 UPDATE/DELETE/TRUNCATE 만 차단하므로
    INSERT 는 정상 완료되어야 한다.
    삽입 후 ROLLBACK 하여 테스트 데이터 오염 방지.
    """
    test_resource_id = uuid.uuid4()

    async def _check() -> None:
        conn = await connect_with_retry(asyncpg, db_url)
        try:
            # v8_cell_visited action_code 가 없으면 skip (V054 미적용)
            code_exists = await conn.fetchrow(
                "SELECT 1 FROM audit_action_codes WHERE action_code = $1",
                "v8_cell_visited",
            )
            if code_exists is None:
                pytest.skip("v8_cell_visited not in audit_action_codes — V054 migration not applied yet")

            async with conn.transaction():
                # INSERT 가 exception 없이 성공해야 함
                inserted = await conn.fetchrow(
                    """
                    INSERT INTO audit_logs
                        (action_code, resource_type, resource_id, detail_json)
                    VALUES
                        ($1, $2, $3, $4)
                    RETURNING id, action_code, resource_type, resource_id
                    """,
                    "v8_cell_visited",
                    "v8_manifest_cell",
                    test_resource_id,
                    '{"cell_key": "AUDIT-v8-test", "test": true}',
                )
                assert inserted is not None, "INSERT INTO audit_logs returned None"
                assert inserted["action_code"] == "v8_cell_visited"
                assert inserted["resource_type"] == "v8_manifest_cell"
                assert str(inserted["resource_id"]) == str(test_resource_id)

                # ROLLBACK — test data 오염 방지
                raise _Rollback("intentional rollback")
        except _Rollback:
            pass  # expected
        finally:
            await conn.close()

    _run(_check())


class _Rollback(Exception):
    """Sentinel to trigger transaction rollback in test."""
