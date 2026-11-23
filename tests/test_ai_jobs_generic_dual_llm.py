"""Tests for the dual-LLM generic primitives (Wave 6.3 US-W63-1).

Verifies:

1. ``call_quarantined_generic`` and ``call_privileged_generic`` are present and
   accept the documented keyword-only signature.
2. With Azure credentials unset, both primitives return ``{"error": str}``
   without raising — the fail-closed contract that ``run_ai_job_runner.py``
   relies on for ``mark_failed``.
3. The legacy RAG-specific wrappers ``call_quarantined_llm`` and
   ``call_privileged_llm`` still produce the original return-shape contracts
   (positive assertion against the thin-wrapper refactor).

No mocks for Azure — these are interface/fail-closed tests, not provider
integration tests. The fail-closed path is the actually-load-bearing
behavior for production worker daemons.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from apps.api.harness.services.ai_jobs import (
    call_privileged_generic,
    call_privileged_llm,
    call_quarantined_generic,
    call_quarantined_llm,
)


@pytest.fixture(autouse=True)
def _disable_azure(monkeypatch):
    """Force fail-closed branch by clearing Azure credentials."""

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "")
    monkeypatch.setenv("AZURE_OPENAI_BASE_URL", "")
    yield


def test_call_quarantined_generic_signature_is_keyword_only():
    sig = inspect.signature(call_quarantined_generic)
    params = list(sig.parameters.values())
    assert all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in params), (
        f"call_quarantined_generic must be keyword-only; got {params}"
    )
    names = {p.name for p in params}
    assert {"agent_id", "system_prompt", "user_data_blocks"}.issubset(names)


def test_call_privileged_generic_signature_is_keyword_only():
    sig = inspect.signature(call_privileged_generic)
    params = list(sig.parameters.values())
    assert all(p.kind == inspect.Parameter.KEYWORD_ONLY for p in params)
    names = {p.name for p in params}
    assert {"agent_id", "system_prompt", "data_blocks"}.issubset(names)


def test_call_quarantined_generic_returns_error_when_azure_unset():
    result = asyncio.run(
        call_quarantined_generic(
            agent_id="test_agent",
            system_prompt="return JSON",
            user_data_blocks=["<USER_DATA>hello</USER_DATA>"],
        )
    )
    assert isinstance(result, dict)
    assert "error" in result
    assert "Azure credentials not configured" in result["error"]


def test_call_privileged_generic_returns_error_when_azure_unset():
    result = asyncio.run(
        call_privileged_generic(
            agent_id="test_agent",
            system_prompt="answer briefly",
            data_blocks=["question: ping"],
        )
    )
    assert isinstance(result, dict)
    assert "error" in result


def test_call_quarantined_generic_never_raises_on_payload_edge_cases():
    """Empty blocks list, very long block, non-ascii — must still fail closed cleanly."""

    long_block = "<USER_DATA>" + "한국어 테스트 데이터 " * 200 + "</USER_DATA>"
    for blocks in ([], ["<USER_DATA>x</USER_DATA>"], [long_block]):
        result = asyncio.run(
            call_quarantined_generic(
                agent_id="test_agent",
                system_prompt="",
                user_data_blocks=blocks,
            )
        )
        assert "error" in result


def test_rag_wrapper_quarantined_llm_returns_error_shape_on_fail_closed():
    """Thin wrapper must still emit error with the same shape as legacy contract."""

    result = asyncio.run(
        call_quarantined_llm(
            agent_id="rag_qa",
            chunks=[{"chunk_id": "c1", "chunk_text": "x"}],
            question="q?",
        )
    )
    assert isinstance(result, dict)
    assert "error" in result


def test_rag_wrapper_privileged_llm_returns_error_shape_on_fail_closed():
    result = asyncio.run(
        call_privileged_llm(
            agent_id="rag_qa",
            quarantine_output={"summary": "s", "extracted_claims": []},
            question="q?",
            citations=[],
        )
    )
    assert isinstance(result, dict)
    assert "error" in result


def test_rag_wrapper_privileged_signature_unchanged():
    """Positive guard: the legacy keyword-only contract for rag_qa is preserved.

    This is the regression breaker that would have flagged any accidental
    rename of `quarantine_output` / `citations` / `question` during the
    Wave 6.3 thin-wrapper refactor.
    """

    sig = inspect.signature(call_privileged_llm)
    names = {p.name for p in sig.parameters.values()}
    assert {"agent_id", "quarantine_output", "question", "citations"}.issubset(names)
