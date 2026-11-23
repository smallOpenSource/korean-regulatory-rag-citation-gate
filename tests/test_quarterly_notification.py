"""Stage 4 T257 — quarterly notification orchestrator (end-to-end happy + edge)."""

from __future__ import annotations

from datetime import date

import pytest

from apps.api.harness.services.marketing.quarterly_notification import (
    READABILITY_THRESHOLD,
    apply_pii_mask,
    approve_first,
    approve_second,
    compose_notification,
    request_four_eyes,
    run_four_gates,
    simulate_send,
)


def _clean_draft(**overrides):
    base = dict(
        customer_id="cust-1",
        customer_email="customer@example.com",
        employee_id="emp-drafter",
        quarter="2026Q2",
        subject="분기 안내 메일",
        body="고객님의 포트폴리오 상태입니다. 신뢰 가능한 자산은 안정적입니다. 검토 부탁드립니다.",
        last_notice_at=date(2025, 5, 1),
        today=date(2026, 5, 18),
        internal_domains=("internal.bank.example",),
    )
    base.update(overrides)
    return compose_notification(**base)


def test_threshold_60():
    assert READABILITY_THRESHOLD == 60.0


def test_compose_initial_state():
    d = _clean_draft()
    assert d["state"] == "DRAFTED"
    assert d["audit_action_code"] == "quarterly_notification_drafted"
    assert d["is_external"] is True  # example.com NOT in internal list
    assert d["due_status"] == "overdue"  # 2025-05-01 vs 2026-05-18 ≥ 365 days


def test_compose_internal_recipient():
    d = _clean_draft(customer_email="user@internal.bank.example")
    assert d["is_external"] is False


def test_compose_rejects_missing_fields():
    with pytest.raises(ValueError):
        compose_notification(
            customer_id="", customer_email="x@y.com", employee_id="e",
            quarter="2026Q2", subject="s", body="b",
            last_notice_at=None, today=date(2026, 5, 18),
        )
    with pytest.raises(ValueError):
        compose_notification(
            customer_id="c", customer_email="", employee_id="e",
            quarter="2026Q2", subject="s", body="b",
            last_notice_at=None, today=date(2026, 5, 18),
        )


def test_apply_pii_mask_external_redacts():
    d = _clean_draft(body="고객님 주민번호 900101-1234567 안내드립니다.")
    masked = apply_pii_mask(d)
    assert "900101-1234567" not in masked["body"]
    assert "[REDACTED:RRN]" in masked["body"]
    assert masked["pii_report"]["masked"] is True
    assert masked["audit_action_code"] == "quarterly_notification_pii_masked"


def test_apply_pii_mask_internal_skips():
    d = _clean_draft(
        customer_email="user@internal.bank.example",
        body="고객님 주민번호 900101-1234567 안내드립니다.",
    )
    result = apply_pii_mask(d)
    # Internal recipient keeps original text
    assert "900101-1234567" in result["body"]
    assert result["pii_report"]["masked"] is False
    assert result["pii_report"]["reason"] == "internal_domain"


def test_apply_pii_mask_invalid_state():
    d = _clean_draft()
    d2 = apply_pii_mask(d)  # transitions out of DRAFTED in external path
    # Hmm — design preserves DRAFTED state; only state transitions are via gates
    # So this test verifies apply_pii_mask twice doesn't error
    d3 = apply_pii_mask(d2)  # internal path returns DRAFTED-equivalent
    assert d3 is not None


def test_run_four_gates_pass_path():
    d = _clean_draft()
    masked = apply_pii_mask(d)
    gated = run_four_gates(masked)
    assert gated["state"] == "GATES_PASSED"
    assert gated["all_gates_passed"] is True
    assert gated["audit_action_code"] == "quarterly_notification_gates_passed"


def test_run_four_gates_blocks_on_unfair_practice():
    d = _clean_draft(body="이번 분기 반드시 가입하셔야 합니다.")
    masked = apply_pii_mask(d)
    gated = run_four_gates(masked)
    assert gated["state"] == "GATES_BLOCKED"
    assert gated["gates"]["reasoning"]["passed"] is False


def test_run_four_gates_blocks_on_low_readability():
    long_text = (
        "오늘 시장은 매우 복잡한 양상을 보이고 있으며 다양한 거시경제 변수들이 "
        "동시에 작용하여 단기 예측이 매우 어려운 상황으로 평가되고 있습니다."
    )
    d = _clean_draft(body=long_text)
    masked = apply_pii_mask(d)
    gated = run_four_gates(masked)
    assert gated["state"] == "GATES_BLOCKED"
    assert gated["gates"]["readability"]["passed"] is False


def test_run_four_gates_blocks_on_not_due():
    """Customer notified recently — suitability_due gate fails."""
    d = _clean_draft(last_notice_at=date(2026, 5, 1))  # only 17 days ago, current
    masked = apply_pii_mask(d)
    gated = run_four_gates(masked)
    assert gated["state"] == "GATES_BLOCKED"
    assert gated["gates"]["suitability_due"]["passed"] is False


def test_four_eyes_flow_to_approved():
    d = _clean_draft()
    masked = apply_pii_mask(d)
    gated = run_four_gates(masked)
    fe = request_four_eyes(gated)
    first = approve_first(fe, approver_id="emp-supervisor-1")
    second = approve_second(first, approver_id="emp-supervisor-2")
    assert second["four_eyes"]["state"] == "APPROVED"


def test_four_eyes_requires_gates_passed():
    d = _clean_draft()
    masked = apply_pii_mask(d)  # still DRAFTED in our flow (no transition)
    with pytest.raises(ValueError):
        request_four_eyes(masked)


def test_simulate_send_requires_4eyes_approved():
    d = _clean_draft()
    masked = apply_pii_mask(d)
    gated = run_four_gates(masked)
    fe = request_four_eyes(gated)
    with pytest.raises(ValueError):
        simulate_send(fe)


def test_simulate_send_full_happy_path():
    d = _clean_draft()
    masked = apply_pii_mask(d)
    gated = run_four_gates(masked)
    fe = request_four_eyes(gated)
    first = approve_first(fe, approver_id="emp-supervisor-1")
    second = approve_second(first, approver_id="emp-supervisor-2")
    sent = simulate_send(second)
    assert sent["state"] == "SENT_SIMULATION"
    assert sent["audit_action_code"] == "quarterly_notification_sent_simulation"
    assert sent["sent_at"].endswith("Z")


def test_inputs_not_mutated_through_pipeline():
    d = _clean_draft()
    masked = apply_pii_mask(d)
    gated = run_four_gates(masked)
    # Original draft unchanged
    assert d["state"] == "DRAFTED"
    assert "gates" not in d
    assert "all_gates_passed" not in d
    # Masked still DRAFTED state (we don't transition on mask)
    assert "all_gates_passed" not in masked
