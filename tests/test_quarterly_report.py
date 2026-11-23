"""Stage 4 T246 — AI quarterly report compliance + approval gate."""

from __future__ import annotations

import pytest

from apps.api.harness.services.ai.quarterly_report import (
    READABILITY_THRESHOLD,
    VALID_STATES,
    compose_draft,
    mark_approved,
    mark_blocked,
    run_compliance_check,
)


def _clean_draft():
    """Short, clear Korean text expected to pass readability + lint."""
    return compose_draft(
        customer_id="cust-1",
        employee_id="emp-drafter",
        quarter="2026Q2",
        body="고객님의 포트폴리오는 안정적입니다. 위험 등급은 그대로입니다. 검토를 권고드립니다.",
    )


def test_states_set():
    assert VALID_STATES == {"DRAFTED", "COMPLIANCE_OK", "COMPLIANCE_BLOCKED", "APPROVED"}


def test_readability_threshold_is_60():
    assert READABILITY_THRESHOLD == 60.0


def test_compose_draft_initial_fields():
    d = _clean_draft()
    assert d["state"] == "DRAFTED"
    assert d["customer_id"] == "cust-1"
    assert d["quarter"] == "2026Q2"
    assert d["audit_action_code"] == "quarterly_report_drafted"
    assert d["compliance_result"] is None
    assert d["approved_by"] is None
    assert d["blocked_reason_codes"] == []


def test_compose_draft_rejects_missing_fields():
    with pytest.raises(ValueError):
        compose_draft(customer_id="", employee_id="e", quarter="2026Q1", body="x")
    with pytest.raises(ValueError):
        compose_draft(customer_id="c", employee_id="", quarter="2026Q1", body="x")
    with pytest.raises(ValueError):
        compose_draft(customer_id="c", employee_id="e", quarter="", body="x")
    with pytest.raises(ValueError):
        compose_draft(customer_id="c", employee_id="e", quarter="2026Q1", body="")


def test_compose_draft_rejects_bad_quarter_format():
    for bad in ("2026Q5", "2026Q0", "26Q1", "2026-Q1", "2026q2"):
        with pytest.raises(ValueError):
            compose_draft(customer_id="c", employee_id="e", quarter=bad, body="x")


def test_compose_draft_accepts_all_quarters():
    for q in ("2026Q1", "2026Q2", "2026Q3", "2026Q4"):
        d = compose_draft(customer_id="c", employee_id="e", quarter=q, body="안녕하세요. 짧은 문장.")
        assert d["quarter"] == q


def test_compliance_check_pass_path():
    d = _clean_draft()
    r = run_compliance_check(d)
    assert r["state"] == "COMPLIANCE_OK"
    assert r["audit_action_code"] == "quarterly_report_compliance_ok"
    assert r["blocked_reason_codes"] == []
    assert r["compliance_result"]["readability"]["passes"] is True
    assert r["compliance_result"]["reasoning"]["flagged"] is False


def test_compliance_check_blocks_on_unfair_practice():
    d = compose_draft(
        customer_id="cust-1",
        employee_id="emp-drafter",
        quarter="2026Q2",
        body="이 상품에 반드시 가입하셔야 합니다.",
    )
    r = run_compliance_check(d)
    assert r["state"] == "COMPLIANCE_BLOCKED"
    assert "UNFAIR_PRACTICE_DETECTED" in r["blocked_reason_codes"]
    assert r["audit_action_code"] == "quarterly_report_blocked"


def test_compliance_check_blocks_on_low_readability():
    long_dense = (
        "오늘 시장은 매우 복잡한 양상을 보이고 있으며 다양한 거시경제 변수들이 "
        "동시에 작용하여 단기 예측이 매우 어려운 상황으로 평가되고 있습니다."
    )
    d = compose_draft(
        customer_id="c", employee_id="e", quarter="2026Q2", body=long_dense,
    )
    r = run_compliance_check(d)
    assert "READABILITY_BELOW_THRESHOLD" in r["blocked_reason_codes"]
    assert r["state"] == "COMPLIANCE_BLOCKED"


def test_compliance_check_invalid_state():
    d = _clean_draft()
    r = run_compliance_check(d)
    with pytest.raises(ValueError):
        run_compliance_check(r)


def test_mark_approved_happy_path():
    d = _clean_draft()
    r = run_compliance_check(d)
    a = mark_approved(r, approver_id="emp-supervisor")
    assert a["state"] == "APPROVED"
    assert a["approved_by"] == "emp-supervisor"
    assert a["audit_action_code"] == "quarterly_report_approved"


def test_mark_approved_rejects_self_approval():
    d = _clean_draft()
    r = run_compliance_check(d)
    with pytest.raises(ValueError):
        mark_approved(r, approver_id="emp-drafter")  # same as employee_id


def test_mark_approved_invalid_state():
    d = _clean_draft()
    # Not compliance-checked
    with pytest.raises(ValueError):
        mark_approved(d, approver_id="emp-supervisor")


def test_mark_approved_requires_id():
    d = _clean_draft()
    r = run_compliance_check(d)
    with pytest.raises(ValueError):
        mark_approved(r, approver_id="")


def test_mark_blocked_manual_path():
    d = _clean_draft()
    r = run_compliance_check(d)
    b = mark_blocked(r, reason_codes=["SUPERVISOR_OVERRIDE"], blocker_id="emp-mgr")
    assert b["state"] == "COMPLIANCE_BLOCKED"
    assert "SUPERVISOR_OVERRIDE" in b["blocked_reason_codes"]
    assert b["audit_action_code"] == "quarterly_report_blocked"


def test_mark_blocked_rejects_approved_state():
    d = _clean_draft()
    r = run_compliance_check(d)
    a = mark_approved(r, approver_id="emp-supervisor")
    with pytest.raises(ValueError):
        mark_blocked(a, reason_codes=["TOO_LATE"], blocker_id="emp-mgr")


def test_mark_blocked_requires_reason_codes():
    d = _clean_draft()
    with pytest.raises(ValueError):
        mark_blocked(d, reason_codes=[], blocker_id="emp-mgr")


def test_input_record_not_mutated_by_transitions():
    d = _clean_draft()
    r = run_compliance_check(d)
    assert d["state"] == "DRAFTED"  # original untouched
    assert d["compliance_result"] is None
    a = mark_approved(r, approver_id="emp-supervisor")
    assert r["state"] == "COMPLIANCE_OK"
    assert r["approved_by"] is None
    assert a["approved_by"] == "emp-supervisor"
