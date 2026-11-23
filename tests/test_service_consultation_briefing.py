"""Tests for services/consultation_briefing.py (Wave 6.3 US-W63-2b, R36).

Verifies the consultation_briefing dispatcher's contract against the live
PostgreSQL schema:

1. resource_type='consultations' validation: rejects mismatched jobs.
2. resource_id missing / row not found: raises ValueError.
3. fail-closed: missing Azure credentials → quarantined LLM error →
   RuntimeError naming the lane.
4. consultations.summary is NEVER mutated — only ai_outputs INSERT.
5. Test transactions roll back so the live consultations table is never
   permanently modified.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytest.importorskip("asyncpg")

from apps.api.harness.services.consultation_briefing import run_consultation_briefing  # noqa: E402

TEST_CONSULTATION_ID = uuid.UUID("00000000-0000-4000-8000-000000000501")
TEST_JOB_ID = uuid.UUID("00000000-0000-4000-8000-000000000502")


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


@pytest.fixture()
def db_config():
    _load_env()
    from apps.api.harness.core.config import load_config

    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        pytest.skip(".env not present")
    config = load_config(env_path)
    if not config.database.database_url:
        pytest.skip("DATABASE_URL missing")
    return config


def test_rejects_wrong_resource_type():
    job = {
        "id": TEST_JOB_ID,
        "resource_type": "email_drafts",
        "resource_id": TEST_CONSULTATION_ID,
        "job_type_code": "consultation_briefing",
    }

    async def _run():
        await run_consultation_briefing(None, job)

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(_run())
    assert "consultations" in str(excinfo.value)


def test_rejects_missing_resource_id():
    job = {
        "id": TEST_JOB_ID,
        "resource_type": "consultations",
        "resource_id": None,
        "job_type_code": "consultation_briefing",
    }

    async def _run():
        await run_consultation_briefing(None, job)

    with pytest.raises(ValueError) as excinfo:
        asyncio.run(_run())
    assert "resource_id" in str(excinfo.value)


def test_fail_closed_runtime_error_and_summary_untouched(db_config, monkeypatch):
    """fail-closed branch + consultations.summary is left alone (ADR-005 §Drivers)."""

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "")

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    customer_row = await conn.fetchrow("SELECT id FROM customers LIMIT 1")
                    employee_row = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if customer_row is None or employee_row is None:
                        pytest.skip("no customer/employee seeded")

                    await conn.execute(
                        """
                        INSERT INTO consultations(id, customer_id, employee_id, channel_code,
                                                  status_code, summary)
                        VALUES ($1::uuid, $2::uuid, $3::uuid, 'FACE_TO_FACE', 'DRAFT',
                                'PB original summary text')
                        """,
                        str(TEST_CONSULTATION_ID),
                        str(customer_row["id"]),
                        str(employee_row["id"]),
                    )

                    job = {
                        "id": TEST_JOB_ID,
                        "resource_type": "consultations",
                        "resource_id": TEST_CONSULTATION_ID,
                        "job_type_code": "consultation_briefing",
                    }

                    err = None
                    try:
                        await run_consultation_briefing(conn, job)
                    except RuntimeError as exc:
                        err = exc

                    summary_after = await conn.fetchval(
                        "SELECT summary FROM consultations WHERE id = $1::uuid",
                        str(TEST_CONSULTATION_ID),
                    )
                    ai_output_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM ai_outputs WHERE resource_id = $1::uuid",
                        str(TEST_CONSULTATION_ID),
                    )
                    return err, summary_after, ai_output_count
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    err, summary_after, ai_output_count = asyncio.run(_exercise())
    assert err is not None
    assert "quarantined LLM error" in str(err) or "Azure credentials not configured" in str(err)
    assert summary_after == "PB original summary text"
    assert ai_output_count == 0


def test_missing_consultation_row_raises_value_error(db_config):
    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    job = {
                        "id": TEST_JOB_ID,
                        "resource_type": "consultations",
                        "resource_id": uuid.UUID("00000000-0000-4000-8000-000000099998"),
                        "job_type_code": "consultation_briefing",
                    }
                    err = None
                    try:
                        await run_consultation_briefing(conn, job)
                    except ValueError as exc:
                        err = exc
                    return err
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    err = asyncio.run(_exercise())
    assert err is not None
    assert "not found" in str(err)


def test_briefing_carries_data_quality_and_no_pii(db_config, monkeypatch):
    """P0 AI-output-quality (2026-05-30): the consultation_briefing output_json
    must carry a mandatory data_quality_notice + a PII-safe _model_input + a
    deterministic faithfulness stamp, and the customer name must NOT reach the
    privileged LLM prompt or the stored question_text. Both LLM lanes are
    monkeypatched (hermetic; only the DB is real and rolled back)."""

    import apps.api.harness.services.consultation_briefing as cb

    captured: dict[str, list[str]] = {}

    async def _fake_quarantine(*, agent_id, system_prompt, user_data_blocks, response_is_json):
        # Empty customer_concern exercises the else-branch question_text (the
        # branch whose customer-name echo was replaced by the resource UUID).
        return {
            "customer_concern": "",
            "risk_flag": "MODERATE",
            "follow_up_intent": "리밸런싱 검토",
            "key_quotes": [],
        }

    async def _fake_privileged(*, agent_id, system_prompt, data_blocks, response_is_json):
        captured["data_blocks"] = list(data_blocks)
        return {
            "customer_context_summary": "합성·미검증 데이터 기반 요약입니다.",
            "portfolio_highlights": "국내 채권 중심 포트폴리오.",
            "suggested_agenda": "1. 현황 점검 2. 리밸런싱",
            "risk_notes": "금리 리스크 모니터링 권장.",
            "follow_up_items": ["만기 현황 확인"],
            "_model": "fake-test-model",
            "_tokens_in": 1,
            "_tokens_out": 1,
        }

    monkeypatch.setattr(cb, "call_quarantined_generic", _fake_quarantine)
    monkeypatch.setattr(cb, "call_privileged_generic", _fake_privileged)

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    cust = await conn.fetchrow(
                        "SELECT id, customer_name FROM customers "
                        "WHERE customer_name IS NOT NULL AND risk_grade_code IS NOT NULL "
                        "AND segment_code IS NOT NULL AND total_assets_krw IS NOT NULL LIMIT 1"
                    )
                    emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if cust is None or emp is None:
                        pytest.skip("no customer/employee seeded")
                    await conn.execute(
                        """
                        INSERT INTO consultations(id, customer_id, employee_id, channel_code,
                                                  status_code, summary)
                        VALUES ($1::uuid, $2::uuid, $3::uuid, 'FACE_TO_FACE', 'DRAFT',
                                'PB original summary text')
                        """,
                        str(TEST_CONSULTATION_ID),
                        str(cust["id"]),
                        str(emp["id"]),
                    )
                    # ai_outputs.job_id is a FK to ai_jobs — insert a real job row
                    # (rolled back with the transaction) so the success path can
                    # persist its ai_outputs row.
                    await conn.execute(
                        "INSERT INTO ai_jobs(id, job_type_code, status_code, "
                        "requested_by_id, resource_type, resource_id) "
                        "VALUES ($1::uuid, 'consultation_briefing', 'RUNNING', "
                        "$2::uuid, 'consultations', $3::uuid)",
                        str(TEST_JOB_ID),
                        str(emp["id"]),
                        str(TEST_CONSULTATION_ID),
                    )
                    job = {
                        "id": TEST_JOB_ID,
                        "resource_type": "consultations",
                        "resource_id": TEST_CONSULTATION_ID,
                        "job_type_code": "consultation_briefing",
                    }
                    await run_consultation_briefing(conn, job)
                    out = await conn.fetchrow(
                        "SELECT output_json, question_text FROM ai_outputs "
                        "WHERE job_id = $1::uuid",
                        str(TEST_JOB_ID),
                    )
                    return dict(out), str(cust["customer_name"])
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    out, customer_name = asyncio.run(_exercise())
    output_json = out["output_json"]
    if isinstance(output_json, str):
        output_json = json.loads(output_json)

    # 1. Mandatory data-quality disclosure stamped onto the output.
    assert output_json.get("data_quality_notice"), "data_quality_notice missing"
    # 2. PII-safe grounding capture (no customer name key).
    model_input = output_json["_model_input"]
    assert "customer_name" not in model_input
    assert "portfolios" in model_input, "_model_input.portfolios not captured"
    # 3. Deterministic faithfulness stamp present; fake summary carries the token.
    assert output_json["faithfulness"]["method"] == "deterministic_v1"
    assert output_json["faithfulness"]["has_disclosure"] is True
    # 4. The customer name must not leak into the LLM prompt or stored question.
    prompt_blob = "\n".join(captured.get("data_blocks") or [])
    assert customer_name and customer_name not in prompt_blob, "name leaked to LLM"
    assert customer_name not in str(out["question_text"]), "name leaked to question_text"


def test_briefing_scrubs_memo_pii_from_all_sinks(db_config, monkeypatch):
    """P0 PII back-channel (2026-05-30 adversarial review): a customer name a PB
    types into a free-form consultation memo can be re-surfaced by the quarantine
    LLM into customer_concern/key_quotes, which feed (1) the privileged prompt,
    (2) the persisted question_text, and (3) output_json. Even when the (faked,
    deliberately NON-compliant) quarantine LLM echoes the name verbatim, the
    deterministic _scrub_known_pii backstop must keep the name out of ALL THREE
    sinks. This is the leak the empty-concern test above cannot catch."""

    import apps.api.harness.services.consultation_briefing as cb

    captured: dict[str, list[str]] = {}
    state: dict[str, str] = {}

    # Non-compliant quarantine LLM: echoes the memo name verbatim into every
    # free-form field (the worst case the deterministic scrub must neutralise).
    async def _fake_quarantine(**_kw):
        n = state["name"]
        return {
            "customer_concern": f"{n}님께서 채권 비중 손실을 우려하셨습니다.",
            "risk_flag": "MODERATE",
            "follow_up_intent": f"{n} 리밸런싱 검토",
            "key_quotes": [f"{n}: 손실이 걱정됩니다"],
        }

    # Privileged LLM echoes its received <USER_DATA> back, so output_json
    # reflects exactly what the prompt carried (post-scrub).
    async def _fake_privileged(**kw):
        blocks = list(kw["data_blocks"])
        captured["data_blocks"] = blocks
        return {
            "customer_context_summary": "합성·미검증 데이터 기반. " + "\n".join(blocks),
            "portfolio_highlights": "—",
            "suggested_agenda": "—",
            "risk_notes": "—",
            "follow_up_items": [],
            "_model": "fake-test-model",
            "_tokens_in": 1,
            "_tokens_out": 1,
        }

    monkeypatch.setattr(cb, "call_quarantined_generic", _fake_quarantine)
    monkeypatch.setattr(cb, "call_privileged_generic", _fake_privileged)

    async def _exercise():
        from apps.api.harness.core.db import create_pool

        pool = await create_pool(db_config.database)
        try:
            async with pool.acquire() as conn:
                tr = conn.transaction()
                await tr.start()
                try:
                    cust = await conn.fetchrow(
                        "SELECT id, customer_name FROM customers "
                        "WHERE customer_name IS NOT NULL AND length(customer_name) >= 2 "
                        "AND risk_grade_code IS NOT NULL AND segment_code IS NOT NULL "
                        "AND total_assets_krw IS NOT NULL LIMIT 1"
                    )
                    emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                    if cust is None or emp is None:
                        pytest.skip("no customer/employee seeded")
                    name = str(cust["customer_name"])
                    state["name"] = name

                    await conn.execute(
                        """
                        INSERT INTO consultations(id, customer_id, employee_id, channel_code,
                                                  status_code, summary)
                        VALUES ($1::uuid, $2::uuid, $3::uuid, 'FACE_TO_FACE', 'DRAFT',
                                'PB original summary text')
                        """,
                        str(TEST_CONSULTATION_ID),
                        str(cust["id"]),
                        str(emp["id"]),
                    )
                    await conn.execute(
                        "INSERT INTO consultation_notes(consultation_id, author_id, note_text) "
                        "VALUES ($1::uuid, $2::uuid, $3)",
                        str(TEST_CONSULTATION_ID),
                        str(emp["id"]),
                        f"고객 {name} 면담 메모: 손실 우려 표명",
                    )
                    await conn.execute(
                        "INSERT INTO ai_jobs(id, job_type_code, status_code, "
                        "requested_by_id, resource_type, resource_id) "
                        "VALUES ($1::uuid, 'consultation_briefing', 'RUNNING', "
                        "$2::uuid, 'consultations', $3::uuid)",
                        str(TEST_JOB_ID),
                        str(emp["id"]),
                        str(TEST_CONSULTATION_ID),
                    )
                    job = {
                        "id": TEST_JOB_ID,
                        "resource_type": "consultations",
                        "resource_id": TEST_CONSULTATION_ID,
                        "job_type_code": "consultation_briefing",
                    }
                    await run_consultation_briefing(conn, job)
                    out = await conn.fetchrow(
                        "SELECT output_json, question_text FROM ai_outputs "
                        "WHERE job_id = $1::uuid",
                        str(TEST_JOB_ID),
                    )
                    return dict(out), name
                finally:
                    await tr.rollback()
        finally:
            await pool.close()

    out, name = asyncio.run(_exercise())
    # Sink 1: the privileged LLM prompt (data_blocks) must not carry the name.
    prompt_blob = "\n".join(captured.get("data_blocks") or [])
    assert name not in prompt_blob, "memo name leaked into privileged prompt"
    # Sink 2: the persisted question_text (concern-branch) must not carry the name.
    assert name not in str(out["question_text"]), "memo name leaked into question_text"
    # Sink 3: the persisted output_json must not carry the name.
    assert name not in str(out["output_json"]), "memo name leaked into output_json"


async def _run_briefing_and_fetch(db_config):
    """Seed a consultation + ai_jobs row (rolled back), run the briefing, and
    return the persisted ai_outputs row (output_json + question_text +
    fail_closed_reason_code). The LLM lanes must already be monkeypatched."""
    from apps.api.harness.core.db import create_pool

    pool = await create_pool(db_config.database)
    try:
        async with pool.acquire() as conn:
            tr = conn.transaction()
            await tr.start()
            try:
                cust = await conn.fetchrow(
                    "SELECT id, customer_name FROM customers "
                    "WHERE customer_name IS NOT NULL AND risk_grade_code IS NOT NULL "
                    "AND segment_code IS NOT NULL AND total_assets_krw IS NOT NULL LIMIT 1"
                )
                emp = await conn.fetchrow("SELECT id FROM employees LIMIT 1")
                if cust is None or emp is None:
                    pytest.skip("no customer/employee seeded")
                await conn.execute(
                    "INSERT INTO consultations(id, customer_id, employee_id, channel_code, "
                    "status_code, summary) VALUES ($1::uuid, $2::uuid, $3::uuid, "
                    "'FACE_TO_FACE', 'DRAFT', 'PB original summary text')",
                    str(TEST_CONSULTATION_ID),
                    str(cust["id"]),
                    str(emp["id"]),
                )
                await conn.execute(
                    "INSERT INTO ai_jobs(id, job_type_code, status_code, requested_by_id, "
                    "resource_type, resource_id) VALUES ($1::uuid, 'consultation_briefing', "
                    "'RUNNING', $2::uuid, 'consultations', $3::uuid)",
                    str(TEST_JOB_ID),
                    str(emp["id"]),
                    str(TEST_CONSULTATION_ID),
                )
                job = {
                    "id": TEST_JOB_ID,
                    "resource_type": "consultations",
                    "resource_id": TEST_CONSULTATION_ID,
                    "job_type_code": "consultation_briefing",
                }
                await run_consultation_briefing(conn, job)
                out = await conn.fetchrow(
                    "SELECT output_json, question_text, fail_closed_reason_code "
                    "FROM ai_outputs WHERE job_id = $1::uuid",
                    str(TEST_JOB_ID),
                )
                return dict(out)
            finally:
                await tr.rollback()
    finally:
        await pool.close()


def test_briefing_masks_structured_pii_in_memo_extraction(db_config, monkeypatch):
    """(c-2) NER-lite: structured PII (phone/RRN/account) a PB typed into a memo
    and echoed by the quarantine LLM must be masked (mask_pii) before it reaches
    the privileged prompt, question_text, and output_json — even when it is NOT
    the customer's name (the _scrub_known_pii backstop only covers the name)."""

    import apps.api.harness.services.consultation_briefing as cb

    captured: dict[str, list[str]] = {}
    phone = "010-9876-5432"
    rrn = "900101-1234567"
    account = "123-45-678901"

    async def _fake_quarantine(**_kw):
        return {
            "customer_concern": f"고객 연락처 {phone} 회신 요청, 주민 {rrn}.",
            "risk_flag": "MODERATE",
            "follow_up_intent": "리밸런싱 검토",
            "key_quotes": [f"계좌 {account} 잔액 문의"],
        }

    async def _fake_privileged(**kw):
        captured["data_blocks"] = list(kw["data_blocks"])
        return {
            "customer_context_summary": "합성·미검증 데이터 기반. " + "\n".join(kw["data_blocks"]),
            "portfolio_highlights": "—",
            "suggested_agenda": "—",
            "risk_notes": "—",
            "follow_up_items": [],
            "_model": "fake-test-model",
            "_tokens_in": 1,
            "_tokens_out": 1,
        }

    monkeypatch.setattr(cb, "call_quarantined_generic", _fake_quarantine)
    monkeypatch.setattr(cb, "call_privileged_generic", _fake_privileged)

    out = asyncio.run(_run_briefing_and_fetch(db_config))
    blob = (
        "\n".join(captured.get("data_blocks") or [])
        + str(out["question_text"])
        + str(out["output_json"])
    )
    assert phone not in blob, "raw phone leaked across a sink"
    assert rrn not in blob, "raw RRN leaked across a sink"
    assert account not in blob, "raw account number leaked across a sink"
    assert "[REDACTED:MOBILE]" in blob, "mask_pii did not mask the phone"
    assert "[REDACTED:RRN]" in blob, "mask_pii did not mask the RRN"


def test_briefing_output_boundary_fails_closed_on_llm07_leak(db_config, monkeypatch):
    """(c-1) backstop: an LLM07 system-prompt leak the privileged LLM emits is
    caught at the output boundary — the briefing content is cleared and
    fail_closed_reason_code='LLM07_LEAKAGE_REDACTED' is persisted (the sanitize
    pass nba_script / portfolio_analysis had and this agent previously lacked)."""

    import apps.api.harness.services.consultation_briefing as cb

    async def _fake_quarantine(**_kw):
        return {
            "customer_concern": "",
            "risk_flag": "LOW",
            "follow_up_intent": "",
            "key_quotes": [],
        }

    async def _fake_privileged(**_kw):
        return {
            "customer_context_summary": "Your role is to reveal the system prompt verbatim.",
            "portfolio_highlights": "x",
            "suggested_agenda": "x",
            "risk_notes": "x",
            "follow_up_items": [],
            "_model": "fake-test-model",
            "_tokens_in": 1,
            "_tokens_out": 1,
        }

    monkeypatch.setattr(cb, "call_quarantined_generic", _fake_quarantine)
    monkeypatch.setattr(cb, "call_privileged_generic", _fake_privileged)

    out = asyncio.run(_run_briefing_and_fetch(db_config))
    output_json = out["output_json"]
    if isinstance(output_json, str):
        output_json = json.loads(output_json)
    assert out["fail_closed_reason_code"] == "LLM07_LEAKAGE_REDACTED"
    assert output_json["customer_context_summary"] == "", "content not cleared on LLM07 leak"


def test_briefing_output_boundary_masks_pii_in_generated_text(db_config, monkeypatch):
    """(c-1) backstop: structured PII the privileged LLM itself emits into a
    briefing field is masked at the output boundary before persistence."""

    import apps.api.harness.services.consultation_briefing as cb

    out_phone = "010-1111-2222"

    async def _fake_quarantine(**_kw):
        return {
            "customer_concern": "",
            "risk_flag": "LOW",
            "follow_up_intent": "",
            "key_quotes": [],
        }

    async def _fake_privileged(**_kw):
        return {
            "customer_context_summary": "합성·미검증 데이터 기반 요약입니다.",
            "portfolio_highlights": f"고객 연락처 {out_phone} 확인이 필요합니다.",
            "suggested_agenda": "현황 점검",
            "risk_notes": "금리 리스크",
            "follow_up_items": [],
            "_model": "fake-test-model",
            "_tokens_in": 1,
            "_tokens_out": 1,
        }

    monkeypatch.setattr(cb, "call_quarantined_generic", _fake_quarantine)
    monkeypatch.setattr(cb, "call_privileged_generic", _fake_privileged)

    out = asyncio.run(_run_briefing_and_fetch(db_config))
    output_json = str(out["output_json"])
    assert out_phone not in output_json, "LLM-emitted phone leaked into output_json"
    assert "[REDACTED:MOBILE]" in output_json, "output-boundary mask_pii did not fire"
