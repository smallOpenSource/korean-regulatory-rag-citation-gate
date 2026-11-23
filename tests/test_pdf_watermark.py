"""Stage 7 T307 PDF portion — apply_pdf_watermark on existing PDFs."""

from __future__ import annotations

import io

import pytest

from apps.api.harness.services.poc.watermark import (
    WATERMARK_TEXT,
    WatermarkBackendMissing,
    apply_pdf_watermark,
)


def _build_plain_pdf(message: str = "Test contract") -> bytes:
    """Generate a watermark-free PDF for the test fixture."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4

    buf = io.BytesIO()
    canv = canvas.Canvas(buf, pagesize=A4)
    canv.drawString(100, 700, message)
    canv.showPage()
    canv.save()
    return buf.getvalue()


def test_rejects_non_bytes():
    with pytest.raises(TypeError):
        apply_pdf_watermark("not bytes")  # type: ignore[arg-type]


def test_rejects_empty_bytes():
    with pytest.raises(WatermarkBackendMissing):
        apply_pdf_watermark(b"")


def test_returns_pdf_bytes():
    plain = _build_plain_pdf()
    stamped = apply_pdf_watermark(plain)
    assert isinstance(stamped, bytes)
    assert stamped.startswith(b"%PDF-")


def test_stamped_pdf_contains_watermark_text():
    plain = _build_plain_pdf("관계자 외 비공개")
    stamped = apply_pdf_watermark(plain)
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(stamped))
    extracted = "".join(page.extract_text() or "" for page in reader.pages)
    assert WATERMARK_TEXT in extracted


def test_stamped_pdf_preserves_original_content():
    plain = _build_plain_pdf("Original content marker")
    stamped = apply_pdf_watermark(plain)
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(stamped))
    extracted = "".join(page.extract_text() or "" for page in reader.pages)
    assert "Original content marker" in extracted


def test_stamped_pdf_page_count_unchanged():
    plain = _build_plain_pdf()
    stamped = apply_pdf_watermark(plain)
    from pypdf import PdfReader

    plain_reader = PdfReader(io.BytesIO(plain))
    stamped_reader = PdfReader(io.BytesIO(stamped))
    assert len(plain_reader.pages) == len(stamped_reader.pages) == 1
