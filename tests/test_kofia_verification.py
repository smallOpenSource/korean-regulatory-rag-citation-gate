"""Stage 3 T236 — KOFIA digital-solicitation identity + chat-log metadata."""

from __future__ import annotations

import hashlib

import pytest

from apps.api.harness.services.marketing.kofia_verification import (
    CHANNEL_KINDS,
    VERIFICATION_METHODS,
    build_chat_log_meta,
    build_verification_step,
    compose_kofia_record,
)


_VALID_SHA = hashlib.sha256(b"sample transcript").hexdigest()


def test_verification_methods_set_has_five_canonical_methods():
    assert VERIFICATION_METHODS == frozenset({
        "id_document",
        "mobile_otp",
        "bank_account",
        "facial_match",
        "signature",
    })


def test_channel_kinds_set_has_three_canonical_kinds():
    assert CHANNEL_KINDS == frozenset({"chat", "voice", "video"})


def test_build_verification_step_success():
    step = build_verification_step(
        "mobile_otp",
        employee_id="emp-1",
        customer_id="cust-1",
        succeeded=True,
        evidence_ref="audit:abc",
    )
    assert step["method"] == "mobile_otp"
    assert step["succeeded"] is True
    assert step["failure_reason"] == ""
    assert step["audit_action_code"] == "kofia_identity_verified"
    assert step["captured_at"].endswith("Z")


def test_build_verification_step_failure():
    step = build_verification_step(
        "id_document",
        employee_id="emp-1",
        customer_id="cust-1",
        succeeded=False,
        failure_reason="OCR_LOW_CONFIDENCE",
    )
    assert step["succeeded"] is False
    assert step["failure_reason"] == "OCR_LOW_CONFIDENCE"
    assert step["audit_action_code"] == "kofia_identity_verification_failed"


def test_build_verification_step_rejects_unknown_method():
    with pytest.raises(ValueError):
        build_verification_step(
            "biometric_fingerprint",
            employee_id="emp-1",
            customer_id="cust-1",
            succeeded=True,
        )


def test_build_verification_step_requires_ids():
    with pytest.raises(ValueError):
        build_verification_step(
            "id_document",
            employee_id="",
            customer_id="cust-1",
            succeeded=True,
        )


def test_build_chat_log_meta_ok():
    meta = build_chat_log_meta(
        consultation_id="cons-1",
        channel_kind="chat",
        transport="internal_chat",
        turn_count=24,
        transcript_sha256=_VALID_SHA,
        duration_seconds=600,
    )
    assert meta["channel_kind"] == "chat"
    assert meta["turn_count"] == 24
    assert meta["transcript_sha256"] == _VALID_SHA
    assert meta["audit_action_code"] == "kofia_chat_log_recorded"


def test_build_chat_log_rejects_invalid_channel():
    with pytest.raises(ValueError):
        build_chat_log_meta(
            consultation_id="cons-1",
            channel_kind="email",
            transport="internal_chat",
            turn_count=1,
            transcript_sha256=_VALID_SHA,
        )


def test_build_chat_log_rejects_bad_sha():
    with pytest.raises(ValueError):
        build_chat_log_meta(
            consultation_id="cons-1",
            channel_kind="chat",
            transport="internal_chat",
            turn_count=1,
            transcript_sha256="not-a-hex-sha",
        )


def test_build_chat_log_rejects_negative_counts():
    with pytest.raises(ValueError):
        build_chat_log_meta(
            consultation_id="cons-1",
            channel_kind="chat",
            transport="internal_chat",
            turn_count=-1,
            transcript_sha256=_VALID_SHA,
        )


def test_compose_kofia_record_compliant():
    v = [build_verification_step("mobile_otp", employee_id="e", customer_id="c", succeeded=True)]
    c = [build_chat_log_meta(
        consultation_id="cons-1",
        channel_kind="chat",
        transport="internal_chat",
        turn_count=10,
        transcript_sha256=_VALID_SHA,
    )]
    rec = compose_kofia_record(v, c)
    assert rec["compliant"] is True
    assert rec["verifications_passed"] == 1
    assert rec["verifications_failed"] == 0
    assert rec["chat_log_count"] == 1


def test_compose_kofia_record_not_compliant_without_chat_log():
    v = [build_verification_step("mobile_otp", employee_id="e", customer_id="c", succeeded=True)]
    rec = compose_kofia_record(v, [])
    assert rec["compliant"] is False
    assert rec["chat_log_count"] == 0


def test_compose_kofia_record_not_compliant_with_only_failed_verifications():
    v = [build_verification_step(
        "id_document",
        employee_id="e",
        customer_id="c",
        succeeded=False,
        failure_reason="OCR_LOW_CONFIDENCE",
    )]
    c = [build_chat_log_meta(
        consultation_id="cons-1",
        channel_kind="chat",
        transport="internal_chat",
        turn_count=10,
        transcript_sha256=_VALID_SHA,
    )]
    rec = compose_kofia_record(v, c)
    assert rec["compliant"] is False
    assert rec["verifications_passed"] == 0
    assert rec["verifications_failed"] == 1


def test_compose_kofia_record_rejects_non_lists():
    with pytest.raises(TypeError):
        compose_kofia_record({}, [])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        compose_kofia_record([], "notalist")  # type: ignore[arg-type]


def test_captured_at_iso_z_format():
    step = build_verification_step(
        "signature",
        employee_id="e",
        customer_id="c",
        succeeded=True,
    )
    ts = step["captured_at"]
    assert isinstance(ts, str)
    assert ts.endswith("Z")
    assert "T" in ts
