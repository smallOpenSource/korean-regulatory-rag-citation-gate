"""Stage 5 T279 — RAG quarantine metrics aggregator."""

from __future__ import annotations

import pytest

from apps.api.harness.services.ai.quarantine_metrics import (
    KNOWN_REASON_CODES,
    compute_metrics,
    is_block_ratio_alarming,
    top_reason_codes,
)


def test_known_reason_codes_has_eight_per_t262():
    assert len(KNOWN_REASON_CODES) == 8


def test_compute_metrics_empty_window():
    m = compute_metrics([])
    assert m["total_answers"] == 0
    assert m["blocked_count"] == 0
    assert m["block_ratio"] == 0.0
    assert m["unknown_codes"] == []
    assert m["audit_action_code"] == "rag_quarantine_metrics_computed"


def test_compute_metrics_all_pass():
    rows = [
        {"agent": "rag_qa", "fail_closed": False},
        {"agent": "rag_qa", "fail_closed": False},
    ]
    m = compute_metrics(rows)
    assert m["total_answers"] == 2
    assert m["blocked_count"] == 0
    assert m["block_ratio"] == 0.0


def test_compute_metrics_one_blocked():
    rows = [
        {"agent": "rag_qa", "fail_closed": False},
        {"agent": "rag_qa", "fail_closed": True, "fail_closed_reason_code": "NO_CITATION"},
    ]
    m = compute_metrics(rows)
    assert m["total_answers"] == 2
    assert m["blocked_count"] == 1
    assert m["block_ratio"] == 0.5
    assert m["by_reason_code"]["NO_CITATION"] == 1


def test_compute_metrics_unknown_reason_bucketed():
    rows = [
        {"agent": "rag_qa", "fail_closed": True, "fail_closed_reason_code": "NEW_REASON_NOT_IN_SCHEMA"},
    ]
    m = compute_metrics(rows)
    assert m["blocked_count"] == 1
    assert m["by_reason_code"]["UNKNOWN"] == 1
    assert "NEW_REASON_NOT_IN_SCHEMA" in m["unknown_codes"]


def test_compute_metrics_by_agent_slicing():
    rows = [
        {"agent": "rag_qa", "fail_closed": False},
        {"agent": "rag_qa", "fail_closed": True, "fail_closed_reason_code": "TIMEOUT"},
        {"agent": "email_draft", "fail_closed": False},
    ]
    m = compute_metrics(rows)
    assert m["by_agent"]["rag_qa"]["total"] == 2
    assert m["by_agent"]["rag_qa"]["blocked"] == 1
    assert m["by_agent"]["email_draft"]["total"] == 1
    assert m["by_agent"]["email_draft"]["blocked"] == 0


def test_compute_metrics_missing_agent_field():
    rows = [{"fail_closed": True, "fail_closed_reason_code": "TIMEOUT"}]
    m = compute_metrics(rows)
    assert "_unknown" in m["by_agent"]


def test_compute_metrics_rejects_non_list():
    with pytest.raises(TypeError):
        compute_metrics({"not": "a list"})  # type: ignore[arg-type]


def test_compute_metrics_ignores_non_dict_rows():
    rows = [
        {"agent": "rag_qa", "fail_closed": True, "fail_closed_reason_code": "NO_CITATION"},
        "not a dict",  # type: ignore[list-item]
        42,  # type: ignore[list-item]
    ]
    m = compute_metrics(rows)
    assert m["total_answers"] == 1


def test_is_block_ratio_alarming_above_threshold():
    metrics = {"block_ratio": 0.35}
    assert is_block_ratio_alarming(metrics) is True


def test_is_block_ratio_alarming_at_threshold():
    """Default threshold is strict-greater-than (> not >=) per REG-06 §5."""
    metrics = {"block_ratio": 0.30}
    assert is_block_ratio_alarming(metrics) is False


def test_is_block_ratio_alarming_custom_threshold():
    metrics = {"block_ratio": 0.06}
    assert is_block_ratio_alarming(metrics, threshold=0.05) is True
    assert is_block_ratio_alarming(metrics, threshold=0.10) is False


def test_is_block_ratio_alarming_missing_field():
    assert is_block_ratio_alarming({}) is False


def test_top_reason_codes_returns_descending():
    rows = [
        {"agent": "rag_qa", "fail_closed": True, "fail_closed_reason_code": "NO_CITATION"},
        {"agent": "rag_qa", "fail_closed": True, "fail_closed_reason_code": "NO_CITATION"},
        {"agent": "rag_qa", "fail_closed": True, "fail_closed_reason_code": "TIMEOUT"},
        {"agent": "rag_qa", "fail_closed": True, "fail_closed_reason_code": "RATE_LIMIT_EXCEEDED"},
    ]
    m = compute_metrics(rows)
    top = top_reason_codes(m, k=3)
    assert len(top) == 3
    assert top[0] == ("NO_CITATION", 2)
    # TIMEOUT vs RATE_LIMIT_EXCEEDED both have count 1; tie-break alphabetical
    counts = [t[1] for t in top]
    assert counts == sorted(counts, reverse=True)


def test_top_reason_codes_excludes_zero_buckets():
    m = compute_metrics([])
    top = top_reason_codes(m)
    assert top == []


def test_top_reason_codes_rejects_invalid_k():
    m = compute_metrics([])
    with pytest.raises(ValueError):
        top_reason_codes(m, k=0)
