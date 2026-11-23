"""test_v048_visual_audit_fixture.py — V048 AUDIT-NEG/POS fixture 검증.

AC3a: AUDIT-NEG-001 → 금지 패턴 match ≥ 1 (dead-detection: 결함 감지 증명)
AC3b: AUDIT-POS-001 → 금지 패턴 match = 0 (정상 fixture는 오탐 없음)
결정성: 50× 동일 결과 (UUID 상수 + ON CONFLICT DO UPDATE)

Dead-detection 원리 (PRD §5 S5):
  AUDIT-NEG-001은 asset_views_json = 'null'::jsonb (sentinel) + {} 2건.
  frontend가 null/empty JSONB 필드를 올바른 empty-state 처리 없이 렌더링하면
  MetadataBlock에서 standalone ' — ' dash 9건 노출 → BANNED_DASH 검출.
  Python 테스트는 DB 값에서 렌더링 시뮬레이션 텍스트를 구성해 패턴 적용.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest

from db.migrator import database_url_from_env, load_env_file
from tests._pg_retry import connect_with_retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── fixture UUID 상수 ────────────────────────────────────────────────────────
NEG_UUID = "a0000048-0000-0000-0000-000000000001"
POS_UUID = "a0000048-0000-0000-0000-000000000002"

# ── Python-equivalent banned patterns (banned-patterns.ts 대응) ───────────────
# BANNED_ENGLISH
_BANNED_ENGLISH = re.compile(
    r"\b(evidence|persisted|snapshot|universe|denominator|staff display)\b",
    re.IGNORECASE,
)
# BANNED_INTERNAL_ID
_BANNED_INTERNAL_ID = re.compile(r"\b(ADR-\d+|W\d-T\d+|REG-0\d)\b")
# BANNED_TEST_FIXTURE
_BANNED_TEST_FIXTURE = re.compile(
    r"(GOLDEN_TEST|RALPH(?:-?QA)?|Synthetic boundary|golden regression test)"
)
# BANNED_ISO_MICRO
_BANNED_ISO_MICRO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+")
# BANNED_PG_MICRO_TIMESTAMP
_BANNED_PG_MICRO_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+")
# BANNED_PG_SHORT_TZ
_BANNED_PG_SHORT_TZ = re.compile(r"\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?[+-]\d{2}(?!:)")
# BANNED_PLACEHOLDER
_BANNED_PLACEHOLDER = re.compile(
    r"응답을 기다리는 중|정보를 불러오는 중|최신 생성 정보 준비 중|생성 대기|모델 대기"
)
# BANNED_RAW_DB_FIELD
_BANNED_RAW_DB_FIELD = re.compile(
    r"\b(source_as_of|created_at|generated_at|observed_at)\b"
)
# BANNED_AUDIT_PREFIX
_BANNED_AUDIT_PREFIX = re.compile(r"^AUDIT-(NEG|POS)-\d+", re.MULTILINE)
# BANNED_DASH: standalone dash (U+002D or U+2014) surrounded by whitespace/quotes
_BANNED_DASH = re.compile(r'(?:^|\s|["\'])[-—](?:\s|["\']|$)')

ALL_BANNED = [
    ("BANNED_ENGLISH", _BANNED_ENGLISH),
    ("BANNED_INTERNAL_ID", _BANNED_INTERNAL_ID),
    ("BANNED_TEST_FIXTURE", _BANNED_TEST_FIXTURE),
    ("BANNED_ISO_MICRO", _BANNED_ISO_MICRO),
    ("BANNED_PG_MICRO_TIMESTAMP", _BANNED_PG_MICRO_TIMESTAMP),
    ("BANNED_PG_SHORT_TZ", _BANNED_PG_SHORT_TZ),
    ("BANNED_PLACEHOLDER", _BANNED_PLACEHOLDER),
    ("BANNED_RAW_DB_FIELD", _BANNED_RAW_DB_FIELD),
    ("BANNED_AUDIT_PREFIX", _BANNED_AUDIT_PREFIX),
    ("BANNED_DASH", _BANNED_DASH),
]


# ── 공통 연결 헬퍼 ────────────────────────────────────────────────────────────

async def _connect() -> Any:
    asyncpg = pytest.importorskip("asyncpg")
    load_env_file(PROJECT_ROOT / ".env")
    try:
        return await connect_with_retry(asyncpg, database_url_from_env())
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL integration database unavailable: {exc}")


# ── DB 조회 헬퍼 ──────────────────────────────────────────────────────────────

_FETCH_SQL = """
/* sql_id: test_v048_fetch_fixture */
SELECT
    id::text,
    title,
    status_code,
    empty_intent,
    asset_views_json,
    model_portfolios_json,
    risks_json,
    jsonb_typeof(asset_views_json)      AS asset_typeof,
    jsonb_typeof(model_portfolios_json) AS mp_typeof,
    jsonb_typeof(risks_json)            AS risks_typeof
FROM house_views
WHERE id = $1::uuid
"""


async def _fetch_fixture(conn: Any, fixture_uuid: str) -> dict[str, Any]:
    row = await conn.fetchrow(_FETCH_SQL, fixture_uuid)
    if row is None:
        pytest.skip(
            f"V048 fixture {fixture_uuid} 미존재 — V048 migration 미적용 또는 DB 불가"
        )
    return dict(row)


# ── 렌더링 시뮬레이션 ─────────────────────────────────────────────────────────

def _simulate_rendered_text(row: dict[str, Any]) -> str:
    """DB 값 → frontend 렌더링 시뮬레이션 텍스트 구성.

    PRD §18 C1 mechanism + jsonb_typeof SoT:
      jsonb_typeof = 'null'   → frontend shows ' — ' (null sentinel, BANNED_DASH 트리거)
      jsonb_typeof = 'object' AND val == {} → frontend shows ' — ' (empty-state dash)
      jsonb_typeof = 'object' AND val != {} → frontend shows JSON string (no ban)
    """
    # (json_col, typeof_col) pairs — typeof is the authoritative DB-side type
    pairs = [
        ("asset_views_json", "asset_typeof"),
        ("model_portfolios_json", "mp_typeof"),
        ("risks_json", "risks_typeof"),
    ]
    parts: list[str] = []
    for col, typeof_col in pairs:
        val = row.get(col)
        val_type = row.get(typeof_col, "")
        if (
            val_type == "null"
            or val is None
            or val == "null"  # asyncpg string repr of JSON null
            or val == {}
            or val == "{}"
        ):
            # null sentinel or empty object → MetadataBlock placeholder dash
            parts.append(" — ")
        else:
            # valid json object → rendered as string content
            parts.append(str(val))
    return " ".join(parts)


# ── 메인 검증 로직 ────────────────────────────────────────────────────────────

async def _run_v048_checks() -> None:
    conn = await _connect()
    try:
        neg = await _fetch_fixture(conn, NEG_UUID)
        pos = await _fetch_fixture(conn, POS_UUID)

        # ── AUDIT-NEG-001 구조 검증 ────────────────────────────────────────
        assert neg["title"] == "AUDIT-NEG-001", f"NEG title mismatch: {neg['title']!r}"
        assert neg["status_code"] == "DRAFT", f"NEG status_code={neg['status_code']!r}"
        assert neg["empty_intent"] == "failure", f"NEG empty_intent={neg['empty_intent']!r}"

        # C1 sentinel: asset_views_json = 'null'::jsonb
        #   jsonb_typeof = 'null'  → db_null 의도 보존
        #   asyncpg는 JSON null을 문자열 'null' 또는 Python None으로 반환 (구현 의존)
        #   → asset_typeof 로 판정 (DB-side, 구현 독립)
        assert neg["asset_typeof"] == "null", (
            f"NEG asset_typeof should be 'null' (C1 sentinel), got {neg['asset_typeof']!r}"
        )
        assert neg["mp_typeof"] == "object", (
            f"NEG mp_typeof should be 'object' (empty object), got {neg['mp_typeof']!r}"
        )
        assert neg["risks_typeof"] == "object", (
            f"NEG risks_typeof should be 'object' (empty object), got {neg['risks_typeof']!r}"
        )

        # ── AUDIT-POS-001 구조 검증 ────────────────────────────────────────
        assert pos["title"] == "AUDIT-POS-001", f"POS title mismatch: {pos['title']!r}"
        assert pos["status_code"] == "GENERATED", f"POS status_code={pos['status_code']!r}"
        assert pos["empty_intent"] == "by_design", f"POS empty_intent={pos['empty_intent']!r}"

        # valid object (not null, not empty) — typeof로 판정 (asyncpg 반환 형식 독립)
        for type_col in ("asset_typeof", "mp_typeof", "risks_typeof"):
            assert pos[type_col] == "object", (
                f"POS {type_col} should be 'object' (db_valid), got {pos[type_col]!r}"
            )
        # empty object 여부 추가 검증
        for col_key in ("asset_views_json", "model_portfolios_json", "risks_json"):
            val = pos[col_key]
            assert val not in (None, "null", {}, "{}"), (
                f"POS {col_key} must be non-empty valid JSON, got {val!r}"
            )

        # ── AC3a: NEG fixture → 금지 패턴 match ≥ 1 (dead-detection) ──────
        neg_text = _simulate_rendered_text(neg)
        neg_matches = [(name, pat.search(neg_text)) for name, pat in ALL_BANNED]
        neg_hits = [(name, m.group()) for name, m in neg_matches if m]
        assert len(neg_hits) >= 1, (
            f"AC3a FAIL: NEG-001 시뮬레이션 텍스트 {neg_text!r}에서 "
            f"금지 패턴 match 0건 (BANNED_DASH 비감지 → 패턴 파손 의심)"
        )

        # ── AC3b: POS fixture → 금지 패턴 match = 0 ──────────────────────
        pos_text = _simulate_rendered_text(pos)
        pos_matches = [(name, pat.search(pos_text)) for name, pat in ALL_BANNED]
        pos_hits = [(name, m.group()) for name, m in pos_matches if m]
        assert len(pos_hits) == 0, (
            f"AC3b FAIL: POS-001 시뮬레이션 텍스트 {pos_text!r}에서 "
            f"금지 패턴 오탐 {len(pos_hits)}건: {pos_hits}"
        )

    finally:
        await conn.close()


async def _run_determinism_check(n: int = 50) -> None:
    """50× 결정성: 동일 UUID로 n번 조회 → 동일 결과 보장."""
    conn = await _connect()
    try:
        baseline_neg = await _fetch_fixture(conn, NEG_UUID)
        baseline_pos = await _fetch_fixture(conn, POS_UUID)

        check_cols = (
            "id", "title", "status_code", "empty_intent",
            "asset_typeof", "mp_typeof", "risks_typeof",
        )

        for i in range(n - 1):
            neg = await _fetch_fixture(conn, NEG_UUID)
            pos = await _fetch_fixture(conn, POS_UUID)
            for col in check_cols:
                assert neg[col] == baseline_neg[col], (
                    f"결정성 실패 (iter {i+2}): NEG.{col} "
                    f"{neg[col]!r} ≠ baseline {baseline_neg[col]!r}"
                )
                assert pos[col] == baseline_pos[col], (
                    f"결정성 실패 (iter {i+2}): POS.{col} "
                    f"{pos[col]!r} ≠ baseline {baseline_pos[col]!r}"
                )
    finally:
        await conn.close()


# ── pytest test functions ─────────────────────────────────────────────────────

def test_v048_neg_structure_and_ac3a():
    """AC3a + NEG-001 DB 구조 검증 (empty_intent=failure, sentinel null)."""
    asyncio.run(_run_v048_checks())


def test_v048_determinism_50x():
    """50× 결정성: 동일 UUID 조회 50회 → 동일 결과 (ON CONFLICT DO UPDATE 보장)."""
    asyncio.run(_run_determinism_check(50))
