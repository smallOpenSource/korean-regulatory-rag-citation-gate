"""Stage 3 T200 — PII detection + masking + external-domain check."""

from __future__ import annotations

from apps.api.harness.services.compliance.pii_masking import (
    detect_pii,
    is_external_domain,
    mask_pii,
)


def test_empty_text_is_clean():
    r = detect_pii("")
    assert r["flagged"] is False
    assert r["matches"] == []
    assert r["audit_action_code"] == ""


def test_neutral_text_is_clean():
    r = detect_pii("오늘 시장은 안정적입니다.")
    assert r["flagged"] is False


def test_rrn_detected():
    r = detect_pii("주민번호 900101-1234567 입니다.")
    assert r["flagged"] is True
    assert r["category_counts"]["rrn"] == 1
    assert r["audit_action_code"] == "info_leak_warning_shown"


def test_rrn_detected_adjacent_korean_no_space():
    """Architect 2026-05-18 fix: Korean Hangul adjacent to digits must NOT block detection."""
    r = detect_pii("주민번호900101-1234567입니다")
    assert r["flagged"] is True
    assert r["category_counts"]["rrn"] == 1


def test_card_detected_adjacent_korean_no_space():
    r = detect_pii("카드번호1234-5678-9012-3456입니다")
    assert r["flagged"] is True
    assert r["category_counts"]["card"] == 1


def test_arc_detected():
    r = detect_pii("외국인등록번호 900101-5234567 안내")
    assert r["flagged"] is True
    assert r["category_counts"]["arc"] == 1


def test_mobile_detected():
    r = detect_pii("연락처 010-1234-5678")
    assert r["flagged"] is True
    assert r["category_counts"]["mobile"] == 1


def test_email_detected():
    r = detect_pii("문의: customer@example.com")
    assert r["flagged"] is True
    assert r["category_counts"]["email"] == 1


def test_card_detected():
    r = detect_pii("카드 1234-5678-9012-3456")
    assert r["flagged"] is True
    assert r["category_counts"]["card"] == 1


def test_account_detected():
    r = detect_pii("계좌 110-222-1234567 입금 부탁드립니다.")
    assert r["flagged"] is True
    assert r["category_counts"]["account"] == 1


def test_mask_replaces_pii():
    text = "이메일 a@b.co 휴대폰 010-1234-5678"
    r = mask_pii(text)
    assert r["flagged"] is True
    assert "a@b.co" not in r["masked_text"]
    assert "010-1234-5678" not in r["masked_text"]
    assert "[REDACTED:EMAIL]" in r["masked_text"]
    assert "[REDACTED:MOBILE]" in r["masked_text"]


def test_mask_preserves_non_pii():
    text = "오늘 시장은 안정적입니다. 위험은 낮습니다."
    r = mask_pii(text)
    assert r["flagged"] is False
    assert r["masked_text"] == text


def test_match_positions_reference_original_text():
    text = "주민번호 900101-1234567 끝"
    r = detect_pii(text)
    match = r["matches"][0]
    pos = match["position"]
    length = match["length"]
    assert text[pos:pos + length] == match["value"]


def test_multiple_categories_in_one_text():
    text = "주민번호 900101-1234567, 카드 1234-5678-9012-3456, 메일 a@b.co"
    r = detect_pii(text)
    assert r["category_counts"]["rrn"] == 1
    assert r["category_counts"]["card"] == 1
    assert r["category_counts"]["email"] == 1


def test_deterministic_across_repeated_calls():
    text = "주민번호 900101-1234567 카드 1234-5678-9012-3456"
    runs = set()
    for _ in range(50):
        r = detect_pii(text)
        runs.add((r["flagged"], len(r["matches"])))
    assert len(runs) == 1


def test_external_domain_allowlist():
    allow = ("internal.bank.example", "harness.internal")
    assert is_external_domain("pb@internal.bank.example", allow) is False
    assert is_external_domain("svc@harness.internal", allow) is False
    assert is_external_domain("client@gmail.com", allow) is True
    assert is_external_domain("user@example.com", allow) is True


def test_external_domain_empty_allowlist_is_external():
    """Empty allowlist treats every recipient as external (safe default)."""
    assert is_external_domain("anyone@anywhere.com") is True


def test_external_domain_malformed_email_returns_false():
    assert is_external_domain("not-an-email") is False
    assert is_external_domain("") is False
    assert is_external_domain("name@") is False
