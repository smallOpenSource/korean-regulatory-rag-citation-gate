"""Stage 5 T269 — ai_output_feedback backend service."""

from __future__ import annotations

import pytest

from apps.api.harness.services.ai.feedback import (
    VALID_POLARITIES,
    VALID_REASON_CODES,
    aggregate_by_agent,
    is_feedback_actionable,
    record_feedback,
)


def test_polarities():
    assert VALID_POLARITIES == {"positive", "negative"}


def test_reason_codes_include_positive_and_negative_buckets():
    assert "HALLUCINATED" in VALID_REASON_CODES
    assert "MISSING_CITATION" in VALID_REASON_CODES
    assert "REGULATORY_RISK" in VALID_REASON_CODES
    assert "ACCURATE" in VALID_REASON_CODES
    assert "WELL_CITED" in VALID_REASON_CODES


def test_record_feedback_positive():
    rec = record_feedback(
        ai_output_id="ai-1",
        employee_id="emp-1",
        polarity="positive",
        reason_code="ACCURATE",
    )
    assert rec["polarity"] == "positive"
    assert rec["reason_code"] == "ACCURATE"
    assert rec["audit_action_code"] == "ai_output_feedback_recorded"
    assert rec["recorded_at"].endswith("Z")


def test_record_feedback_minimal_negative():
    rec = record_feedback(
        ai_output_id="ai-1",
        employee_id="emp-1",
        polarity="negative",
    )
    assert rec["polarity"] == "negative"
    assert rec["reason_code"] == ""
    assert rec["comment"] == ""


def test_record_feedback_rejects_unknown_polarity():
    with pytest.raises(ValueError):
        record_feedback(
            ai_output_id="ai-1",
            employee_id="emp-1",
            polarity="neutral",
        )


def test_record_feedback_rejects_unknown_reason_code():
    with pytest.raises(ValueError):
        record_feedback(
            ai_output_id="ai-1",
            employee_id="emp-1",
            polarity="positive",
            reason_code="MY_INVENTED_REASON",
        )


def test_record_feedback_requires_ids():
    with pytest.raises(ValueError):
        record_feedback(
            ai_output_id="",
            employee_id="emp-1",
            polarity="positive",
        )
    with pytest.raises(ValueError):
        record_feedback(
            ai_output_id="ai-1",
            employee_id="",
            polarity="positive",
        )


def test_aggregate_by_agent_simple():
    records = [
        record_feedback(ai_output_id="ai-1", employee_id="e", polarity="positive", reason_code="ACCURATE"),
        record_feedback(ai_output_id="ai-2", employee_id="e", polarity="negative", reason_code="HALLUCINATED"),
        record_feedback(ai_output_id="ai-1", employee_id="e", polarity="positive", reason_code="WELL_CITED"),
    ]
    lookup = {"ai-1": "rag_qa", "ai-2": "rag_qa"}
    agg = aggregate_by_agent(records, lookup)
    assert agg["rag_qa"]["positive"] == 2
    assert agg["rag_qa"]["negative"] == 1
    assert agg["rag_qa"]["total"] == 3
    assert abs(agg["rag_qa"]["positive_ratio"] - 2 / 3) < 1e-9
    reasons = agg["rag_qa"]["reasons"]
    assert reasons["ACCURATE"] == 1
    assert reasons["WELL_CITED"] == 1
    assert reasons["HALLUCINATED"] == 1


def test_aggregate_by_agent_multi_agent():
    records = [
        record_feedback(ai_output_id="r1", employee_id="e", polarity="positive"),
        record_feedback(ai_output_id="e1", employee_id="e", polarity="negative"),
    ]
    lookup = {"r1": "rag_qa", "e1": "email_draft"}
    agg = aggregate_by_agent(records, lookup)
    assert set(agg.keys()) == {"rag_qa", "email_draft"}
    assert agg["rag_qa"]["positive"] == 1
    assert agg["email_draft"]["negative"] == 1


def test_aggregate_ignores_records_with_unknown_ai_output_id():
    records = [
        record_feedback(ai_output_id="orphan", employee_id="e", polarity="positive"),
    ]
    agg = aggregate_by_agent(records, agent_lookup={})
    assert agg == {}


def test_aggregate_rejects_non_list_or_non_dict():
    with pytest.raises(TypeError):
        aggregate_by_agent("not-a-list", {})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        aggregate_by_agent([], "not-a-dict")  # type: ignore[arg-type]


def test_is_feedback_actionable_positive_never_actionable():
    rec = record_feedback(
        ai_output_id="ai-1", employee_id="e", polarity="positive", reason_code="ACCURATE",
    )
    assert is_feedback_actionable(rec) is False


def test_is_feedback_actionable_negative_regulatory():
    rec = record_feedback(
        ai_output_id="ai-1", employee_id="e", polarity="negative", reason_code="REGULATORY_RISK",
    )
    assert is_feedback_actionable(rec) is True


def test_is_feedback_actionable_negative_hallucination():
    rec = record_feedback(
        ai_output_id="ai-1", employee_id="e", polarity="negative", reason_code="HALLUCINATED",
    )
    assert is_feedback_actionable(rec) is True


def test_is_feedback_actionable_negative_off_topic_not_actionable():
    """OFF_TOPIC is annoying but not the kind of issue that pages oncall."""
    rec = record_feedback(
        ai_output_id="ai-1", employee_id="e", polarity="negative", reason_code="OFF_TOPIC",
    )
    assert is_feedback_actionable(rec) is False
