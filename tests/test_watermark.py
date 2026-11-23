"""Stage 6 T307 — POC SIMULATION 워터마크 + 메타데이터 검증 (CSV/email portion)."""

from __future__ import annotations

import pytest

from apps.api.harness.services.poc.watermark import (
    EMAIL_HTML_BANNER,
    EMAIL_TEXT_BANNER,
    WATERMARK_TEXT,
    WatermarkBackendMissing,
    apply_csv_watermark,
    apply_email_html_watermark,
    apply_email_text_watermark,
    apply_pdf_watermark,
    verify_csv_watermark,
    verify_email_watermark,
    verify_metadata,
)


def test_watermark_text_exact_string():
    """Audit reviewers grep this string verbatim — must not drift."""
    assert WATERMARK_TEXT == "POC SIMULATION — NOT A REAL ORDER"


def test_apply_csv_watermark_prepends_comment():
    csv = "id,name\n1,Alice\n2,Bob\n"
    out = apply_csv_watermark(csv)
    assert out.startswith("# POC SIMULATION — NOT A REAL ORDER\n")
    assert "id,name\n1,Alice\n2,Bob\n" in out


def test_apply_csv_watermark_idempotent():
    csv = "id,name\n1,Alice\n"
    once = apply_csv_watermark(csv)
    twice = apply_csv_watermark(once)
    assert once == twice


def test_apply_csv_watermark_rejects_non_string():
    with pytest.raises(TypeError):
        apply_csv_watermark(123)  # type: ignore[arg-type]


def test_apply_email_text_watermark_prepends_banner():
    body = "Dear customer,\n\nYour quarterly report is attached.\n"
    out = apply_email_text_watermark(body)
    assert "*** POC SIMULATION — NOT A REAL ORDER ***" in out
    assert "Dear customer" in out


def test_apply_email_text_watermark_idempotent():
    body = "hello"
    once = apply_email_text_watermark(body)
    twice = apply_email_text_watermark(once)
    assert once == twice


def test_apply_email_html_watermark_inserts_after_body_tag():
    html = "<html><head></head><body><p>Hello</p></body></html>"
    out = apply_email_html_watermark(html)
    assert EMAIL_HTML_BANNER in out
    body_pos = out.find("<body>")
    banner_pos = out.find(EMAIL_HTML_BANNER)
    assert banner_pos > body_pos


def test_apply_email_html_watermark_prepends_when_no_body_tag():
    html = "<p>Bare html fragment</p>"
    out = apply_email_html_watermark(html)
    assert out.startswith(EMAIL_HTML_BANNER)


def test_apply_email_html_watermark_idempotent():
    html = "<body><p>hi</p></body>"
    once = apply_email_html_watermark(html)
    twice = apply_email_html_watermark(once)
    assert once == twice


def test_apply_pdf_watermark_implemented_post_adr003_amendment():
    """ADR-003 §3 reportlab approval (2026-05-18) — apply_pdf_watermark now
    stamps the watermark onto valid input PDFs. Empty/invalid input still
    raises WatermarkBackendMissing per the fail-loud guarantee.
    """
    # Empty input remains a fail-loud condition.
    with pytest.raises(WatermarkBackendMissing):
        apply_pdf_watermark(b"")
    # Non-bytes raises TypeError, not WatermarkBackendMissing.
    with pytest.raises(TypeError):
        apply_pdf_watermark("not bytes")  # type: ignore[arg-type]


def test_verify_csv_watermark_present():
    csv = apply_csv_watermark("id,name\n")
    r = verify_csv_watermark(csv)
    assert r["present"] is True
    assert r["line_number"] == 0
    assert r["audit_action_code"] == "poc_watermark_present"


def test_verify_csv_watermark_missing():
    r = verify_csv_watermark("id,name\n1,Alice\n")
    assert r["present"] is False
    assert r["line_number"] is None
    assert r["audit_action_code"] == "poc_watermark_missing"


def test_verify_email_watermark_text():
    body = apply_email_text_watermark("hello")
    r = verify_email_watermark(body)
    assert r["present"] is True
    assert r["text_banner"] is True
    assert r["html_banner"] is False


def test_verify_email_watermark_html():
    body = apply_email_html_watermark("<body><p>hello</p></body>")
    r = verify_email_watermark(body)
    assert r["present"] is True
    assert r["html_banner"] is True
    assert r["text_banner"] is False


def test_verify_email_watermark_missing():
    r = verify_email_watermark("plain message no banner")
    assert r["present"] is False
    assert r["audit_action_code"] == "poc_watermark_missing"


def test_verify_metadata_compliant():
    md = {
        "governance_marker": "PoC_AUTO_APPROVAL",
        "watermark_text": WATERMARK_TEXT,
    }
    r = verify_metadata(md)
    assert r["fully_compliant"] is True
    assert r["audit_action_code"] == "poc_metadata_compliant"


def test_verify_metadata_missing_marker():
    md = {"watermark_text": WATERMARK_TEXT}
    r = verify_metadata(md)
    assert r["is_demo_marker_present"] is False
    assert r["fully_compliant"] is False
    assert r["audit_action_code"] == "poc_metadata_noncompliant"


def test_verify_metadata_mismatched_text():
    md = {
        "governance_marker": "PoC_AUTO_APPROVAL",
        "watermark_text": "wrong text",
    }
    r = verify_metadata(md)
    assert r["watermark_text_matches"] is False
    assert r["fully_compliant"] is False


def test_verify_metadata_rejects_non_dict():
    with pytest.raises(TypeError):
        verify_metadata("not a dict")  # type: ignore[arg-type]


def test_banner_constants_contain_watermark_text():
    assert WATERMARK_TEXT in EMAIL_TEXT_BANNER
    assert WATERMARK_TEXT in EMAIL_HTML_BANNER
