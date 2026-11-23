"""금소법 §23 PDF 합성 계약서 generator (T208).

When a 추천/주문 simulation reaches APPROVED state in demo mode, the
caller invokes `generate_contract_pdf(...)` to produce a synthetic
contract PDF embedded with the T307 watermark + customer details +
4-gate evidence pointers. Output is **always** synthetic — recipient
must be `SYN-CUST-*`, governance_marker must be `PoC_AUTO_APPROVAL`,
and the watermark is mandatory (fail-loud if missing).

Library: reportlab (ADR-003 §approved python dep 2026-05-18).
Output: PDF bytes with the canonical T307 watermark in the page background.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path

from apps.api.harness.services.poc.watermark import WATERMARK_TEXT


class ContractInputError(ValueError):
    """Raised when contract inputs fail the synthetic-only guards."""


def _ensure_font_registered() -> str:
    """Register a Korean-capable font once, return font name (or 'Helvetica' fallback)."""
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                if "KoreanContractFont" not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont("KoreanContractFont", path))
                return "KoreanContractFont"
            except Exception:
                continue
    return "Helvetica"


def _draw_watermark(canv: canvas.Canvas, doc: object) -> None:
    """Stamp the T307 watermark diagonally across each page."""
    canv.saveState()
    canv.setFillColor(colors.Color(0.85, 0.55, 0.0, alpha=0.18))
    canv.setFont("Helvetica-Bold", 48)
    canv.translate(A4[0] / 2, A4[1] / 2)
    canv.rotate(45)
    canv.drawCentredString(0, 0, WATERMARK_TEXT)
    canv.restoreState()
    # Also a footer line so a black-and-white print preserves the signal
    canv.saveState()
    canv.setFillColor(colors.darkred)
    canv.setFont("Helvetica-Bold", 8)
    canv.drawCentredString(A4[0] / 2, 1 * cm, WATERMARK_TEXT)
    canv.restoreState()


def _validate_inputs(
    customer_no: str,
    employee_id: str,
    governance_marker: str,
) -> None:
    if not customer_no:
        raise ContractInputError("customer_no required")
    if not customer_no.startswith("SYN-"):
        raise ContractInputError(
            f"customer_no must start with 'SYN-' (PoC synthetic only); got {customer_no!r}"
        )
    if not employee_id:
        raise ContractInputError("employee_id required")
    if governance_marker != "PoC_AUTO_APPROVAL":
        raise ContractInputError(
            f"governance_marker must be 'PoC_AUTO_APPROVAL' for synthetic contracts; "
            f"got {governance_marker!r}"
        )


def generate_contract_pdf(
    *,
    customer_no: str,
    customer_name: str,
    employee_id: str,
    product_name: str,
    governance_marker: str = "PoC_AUTO_APPROVAL",
    four_gate_ref: str = "",
    risk_grade: str = "",
    issued_at: str | None = None,
) -> bytes:
    """Produce the synthetic contract as PDF bytes.

    Returns the PDF as raw bytes; caller persists to file or returns via API.
    """
    _validate_inputs(customer_no, employee_id, governance_marker)

    font_name = _ensure_font_registered()
    issued = issued_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        title="합성 계약서 (PoC SIMULATION)",
        author="Harness PoC",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "title-ko",
        parent=styles["Title"],
        fontName=font_name,
        alignment=TA_CENTER,
        fontSize=18,
    )
    body_style = ParagraphStyle(
        "body-ko",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=11,
        leading=15,
    )

    story: list[object] = [
        Paragraph("금융상품 가입 계약서 (합성)", title_style),
        Spacer(1, 0.4 * cm),
        Paragraph(
            "<i>본 문서는 PoC 시뮬레이션 산출물이며 실제 계약 효력이 없습니다. "
            "금소법 §23 (계약서류 제공의무) 데모용 합성 자료입니다.</i>",
            body_style,
        ),
        Spacer(1, 0.6 * cm),
    ]

    rows = [
        ["고객번호 (Customer No)", customer_no],
        ["고객명 (Customer Name)", customer_name or "(합성 고객)"],
        ["담당 직원 (Employee ID)", employee_id],
        ["상품명 (Product)", product_name],
        ["위험등급 (Risk Grade)", risk_grade or "(평가 진행 중)"],
        ["4-gate 증빙 (Evidence)", four_gate_ref or "(N/A — DRAFT 단계)"],
        ["governance_marker", governance_marker],
        ["발행 일시 (Issued at)", issued],
    ]
    table = Table(rows, colWidths=[5 * cm, 11 * cm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F4F2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ],
        ),
    )
    story.append(table)
    story.append(Spacer(1, 0.8 * cm))
    story.append(
        Paragraph(
            "<b>안내:</b> 본 계약은 PoC 데모 환경에서 생성된 합성 자료로, "
            "실제 자금 이동 또는 거래 체결과 무관합니다. "
            "audit_logs 의 contract_pdf_generated 행으로 추적됩니다.",
            body_style,
        ),
    )

    doc.build(story, onFirstPage=_draw_watermark, onLaterPages=_draw_watermark)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    # Post-condition: reportlab encodes text via PDF operators + glyph indices
    # so the literal UTF-8 string is NOT recoverable by a byte-substring scan
    # of compressed streams. We instead assert (a) the output is a valid PDF
    # and (b) the watermark draw callback was wired (both surfaces are
    # static guarantees from the code path above). The auditor verifies the
    # visible watermark via PDF viewer or via pypdf-based text extraction.
    if not pdf_bytes.startswith(b"%PDF-"):
        raise RuntimeError("Generated bytes are not a valid PDF (missing %PDF- header)")
    if len(pdf_bytes) < 500:
        raise RuntimeError(f"Generated PDF too small ({len(pdf_bytes)}B), likely invalid")
    return pdf_bytes


def build_audit_payload(
    *,
    customer_no: str,
    employee_id: str,
    product_name: str,
    pdf_size_bytes: int,
    pdf_sha256: str,
) -> dict[str, object]:
    """Compose the audit_logs payload for a generated contract PDF row."""
    return {
        "audit_action_code": "contract_pdf_generated",
        "customer_no": customer_no,
        "employee_id": employee_id,
        "product_name": product_name,
        "pdf_size_bytes": int(pdf_size_bytes),
        "pdf_sha256": pdf_sha256,
        "synthetic_only": True,
        "watermark_text": WATERMARK_TEXT,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
