"""Stage 4 T258 — 4-eyes approval state machine."""

from __future__ import annotations

import pytest

from apps.api.harness.services.compliance.four_eyes import (
    TERMINAL_STATES,
    VALID_SCOPES,
    VALID_STATES,
    finalize,
    first_approve,
    reject,
    request_approval,
    second_approve,
)


def _draft():
    return request_approval(
        scope="consultation_complete",
        originator_id="emp-originator",
        subject_ref="cons-123",
    )


def test_states_set_complete():
    assert VALID_STATES == {
        "DRAFTED",
        "FIRST_APPROVED",
        "SECOND_APPROVED",
        "APPROVED",
        "REJECTED",
    }


def test_terminal_states():
    assert TERMINAL_STATES == {"APPROVED", "REJECTED"}


def test_valid_scopes():
    assert VALID_SCOPES == {
        "consultation_complete",
        "email_send",
        "high_risk_transaction",
    }


def test_request_approval_returns_drafted():
    r = _draft()
    assert r["state"] == "DRAFTED"
    assert r["audit_action_code"] == "four_eyes_drafted"
    assert r["first_approver_id"] is None
    assert r["second_approver_id"] is None
    assert len(r["history"]) == 1


def test_request_approval_rejects_unknown_scope():
    with pytest.raises(ValueError):
        request_approval(scope="invalid", originator_id="o", subject_ref="s")


def test_request_approval_requires_originator_and_subject():
    with pytest.raises(ValueError):
        request_approval(scope="email_send", originator_id="", subject_ref="s")
    with pytest.raises(ValueError):
        request_approval(scope="email_send", originator_id="o", subject_ref="")


def test_first_approve_happy_path():
    r = _draft()
    r2 = first_approve(r, approver_id="emp-first")
    assert r2["state"] == "FIRST_APPROVED"
    assert r2["first_approver_id"] == "emp-first"
    assert r2["audit_action_code"] == "four_eyes_first_approved"
    # Immutability: original record unchanged
    assert r["state"] == "DRAFTED"
    assert r["first_approver_id"] is None


def test_first_approve_rejects_originator():
    r = _draft()
    with pytest.raises(ValueError):
        first_approve(r, approver_id="emp-originator")


def test_first_approve_rejects_invalid_state():
    r = _draft()
    r2 = first_approve(r, approver_id="emp-first")
    with pytest.raises(ValueError):
        first_approve(r2, approver_id="emp-second")


def test_second_approve_happy_path():
    r = _draft()
    r1 = first_approve(r, approver_id="emp-first")
    r2 = second_approve(r1, approver_id="emp-second")
    assert r2["state"] == "SECOND_APPROVED"
    assert r2["second_approver_id"] == "emp-second"
    assert r2["audit_action_code"] == "four_eyes_second_approved"


def test_second_approve_rejects_same_as_first():
    r = _draft()
    r1 = first_approve(r, approver_id="emp-first")
    with pytest.raises(ValueError):
        second_approve(r1, approver_id="emp-first")


def test_second_approve_rejects_originator():
    r = _draft()
    r1 = first_approve(r, approver_id="emp-first")
    with pytest.raises(ValueError):
        second_approve(r1, approver_id="emp-originator")


def test_finalize_only_from_second_approved():
    r = _draft()
    with pytest.raises(ValueError):
        finalize(r)
    r1 = first_approve(r, approver_id="emp-first")
    with pytest.raises(ValueError):
        finalize(r1)


def test_full_happy_path_to_approved():
    r = _draft()
    r1 = first_approve(r, approver_id="emp-first")
    r2 = second_approve(r1, approver_id="emp-second")
    r3 = finalize(r2)
    assert r3["state"] == "APPROVED"
    assert r3["audit_action_code"] == "four_eyes_approved"
    history_events = [h["event"] for h in r3["history"]]
    assert history_events == ["drafted", "first_approved", "second_approved", "approved"]


def test_reject_from_drafted():
    r = _draft()
    rr = reject(r, rejector_id="emp-mgr", reason="insufficient disclosure")
    assert rr["state"] == "REJECTED"
    assert rr["rejection_reason"] == "insufficient disclosure"
    assert rr["audit_action_code"] == "four_eyes_rejected"


def test_reject_from_first_approved():
    r = _draft()
    r1 = first_approve(r, approver_id="emp-first")
    rr = reject(r1, rejector_id="emp-mgr", reason="reverted on review")
    assert rr["state"] == "REJECTED"


def test_reject_rejects_from_terminal_state():
    r = _draft()
    r1 = first_approve(r, approver_id="emp-first")
    r2 = second_approve(r1, approver_id="emp-second")
    r3 = finalize(r2)
    with pytest.raises(ValueError):
        reject(r3, rejector_id="emp-mgr", reason="too late")


def test_reject_requires_reason():
    r = _draft()
    with pytest.raises(ValueError):
        reject(r, rejector_id="emp-mgr", reason="")
    with pytest.raises(ValueError):
        reject(r, rejector_id="", reason="x")


def test_history_records_each_transition():
    r = _draft()
    r1 = first_approve(r, approver_id="emp-first")
    r2 = second_approve(r1, approver_id="emp-second")
    r3 = finalize(r2)
    assert len(r3["history"]) == 4
    for entry in r3["history"]:
        assert "event" in entry
        assert "actor_id" in entry
        assert "at" in entry
        assert entry["at"].endswith("Z")


def test_immutability_of_input_history_list():
    """Each transition returns a new list; modifying the original must not
    leak into the updated copy."""
    r = _draft()
    r1 = first_approve(r, approver_id="emp-first")
    r["history"].append({"event": "spurious"})
    assert any(h["event"] == "spurious" for h in r["history"])
    assert not any(h["event"] == "spurious" for h in r1["history"])
