"""OpenDART batch provider helpers."""

from __future__ import annotations

import json
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, time
from io import BytesIO
from typing import Any
from xml.etree import ElementTree

from apps.api.harness.batch.collectors import store_raw_document_with_source
from apps.api.harness.external.http import ExternalProviderError, build_url
from apps.api.harness.external.public_data import DartClient

from apps.api.harness.batch.providers import (  # noqa: E402
    ProviderEvidence,
    _date,
    _require_text,
)


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DartFilingTarget:
    corp_code: str | None
    begin_date: str
    end_date: str
    stock_code: str | None = None
    report_type: str | None = None
    page_count: int = 100


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DART_XML_PARSER_VERSION = "dart-xml-v1"
DART_STATUS_SUCCESS = "000"
DART_STATUS_NO_DATA = "013"
DART_DOCUMENT_NO_DATA_STATUS_CODES = {DART_STATUS_NO_DATA, "014"}
DART_AUTH_FAILURE_STATUS_CODES = frozenset({"010", "011", "012"})
DART_RATE_LIMIT_STATUS_CODES = frozenset({"020", "021"})


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def dart_target_ref(target: DartFilingTarget, *, corp_code: str | None = None) -> str:
    """Build a deterministic non-secret DART target reference for provider evidence."""

    resolved_corp_code = corp_code or target.corp_code or "stock"
    scope = target.report_type or "all"
    return f"DART:{resolved_corp_code}:{target.begin_date}-{target.end_date}:{scope}"


def _dart_payload_status(payload: dict[str, Any]) -> tuple[str | None, str]:
    status = str(payload.get("status") or "").strip() or None
    message = str(payload.get("message") or payload.get("msg") or "").strip()
    return status, message


def dart_provider_status_code(*, status: str | None, has_rows: bool) -> str:
    """Map OpenDART status metadata into the provider-detail taxonomy."""

    if status in (None, "", DART_STATUS_SUCCESS):
        return "PROVIDER_DONE" if has_rows else "PROVIDER_FAILED_SCHEMA"
    if status == DART_STATUS_NO_DATA:
        return "PROVIDER_NO_DATA"
    if status in DART_AUTH_FAILURE_STATUS_CODES:
        return "PROVIDER_FAILED_AUTH"
    if status in DART_RATE_LIMIT_STATUS_CODES:
        return "PROVIDER_FAILED_RATE_LIMIT"
    return "PROVIDER_FAILED_SCHEMA"


def dart_list_evidence(
    *,
    payload: dict[str, Any],
    target: DartFilingTarget,
    corp_code: str,
    rows_collected: int = 0,
    rows_skipped: int = 0,
    rows_failed: int = 0,
) -> ProviderEvidence:
    """Classify one OpenDART listing response without leaking credentials."""

    filings = payload.get("list")
    if isinstance(filings, dict):
        has_rows = True
    elif isinstance(filings, list):
        has_rows = bool(filings)
    else:
        has_rows = False
    status, message = _dart_payload_status(payload)
    provider_status_code = dart_provider_status_code(status=status, has_rows=has_rows)
    return ProviderEvidence(
        provider_code="DART",
        provider_status_code=provider_status_code,
        target_ref=dart_target_ref(target, corp_code=corp_code),
        rows_collected=rows_collected,
        rows_skipped=rows_skipped,
        rows_failed=rows_failed,
        reason_message=message or None,
        provider_detail_json={
            "dart_status": status,
            "page_no": payload.get("page_no"),
            "total_page": payload.get("total_page"),
            "total_count": payload.get("total_count"),
            "stock_code": target.stock_code,
            "report_type": target.report_type,
        },
    )


def dart_document_body_evidence(
    *,
    target: DartFilingTarget,
    corp_code: str,
    filing_rows: int,
    document_xml_bodies: int,
    rows_collected: int = 0,
    rows_skipped: int = 0,
    rows_failed: int = 0,
    reason_message: str | None = None,
) -> ProviderEvidence:
    """Classify DART target evidence after the required document.xml body gate.

    A successful filing-list row alone is not sufficient for OpenDART readiness:
    T55 requires at least one official ``document.xml`` body to be accepted for
    persistence/transform.  This helper keeps list-only discoveries as honest
    no-data evidence instead of greenwashing them as ``PROVIDER_DONE``.
    """

    has_body = document_xml_bodies > 0
    return ProviderEvidence(
        provider_code="DART",
        provider_status_code="PROVIDER_DONE" if has_body else "PROVIDER_NO_DATA",
        target_ref=dart_target_ref(target, corp_code=corp_code),
        rows_collected=rows_collected,
        rows_skipped=rows_skipped,
        rows_failed=rows_failed,
        reason_message=(
            None
            if has_body
            else reason_message
            or (
                "OpenDART list rows were found but document.xml bodies were unavailable"
                if filing_rows
                else "OpenDART returned no filing rows"
            )
        ),
        provider_detail_json={
            "stock_code": target.stock_code,
            "corp_code": corp_code,
            "begin_date": target.begin_date,
            "end_date": target.end_date,
            "report_type": target.report_type,
            "page_count": target.page_count,
            "filing_rows": filing_rows,
            "document_xml_bodies": document_xml_bodies,
        },
    )


def ensure_dart_success_or_no_data(
    *, payload: dict[str, Any], target: DartFilingTarget, corp_code: str
) -> ProviderEvidence:
    """Return DART evidence or raise a taxonomy-coded provider error for failures."""

    evidence = dart_list_evidence(payload=payload, target=target, corp_code=corp_code)
    if evidence.provider_status_code in {"PROVIDER_DONE", "PROVIDER_NO_DATA"}:
        return evidence
    status, message = _dart_payload_status(payload)
    reason = message or "OpenDART returned non-success status"
    raise ExternalProviderError(
        f"{evidence.provider_status_code}: DART list status={status or 'missing'} {reason}"
    )


def dart_total_pages(payload: dict[str, Any]) -> int:
    """Read the OpenDART total_page field, defaulting to one page."""

    raw_total_pages = payload.get("total_page") or 1
    try:
        total_pages = int(raw_total_pages)
    except (TypeError, ValueError) as exc:
        raise ExternalProviderError("PROVIDER_FAILED_SCHEMA: DART total_page is invalid") from exc
    return max(total_pages, 1)


def parse_dart_filing_documents(
    *, payload: dict[str, Any], api_base_url: str
) -> list[dict[str, Any]]:
    """Convert DART listing rows into provider-lineage document.xml targets."""

    status, message = _dart_payload_status(payload)
    if status == DART_STATUS_NO_DATA:
        return []
    if status not in (None, "", DART_STATUS_SUCCESS):
        provider_status = dart_provider_status_code(status=status, has_rows=False)
        raise ExternalProviderError(
            f"{provider_status}: DART list status={status} "
            f"{message or 'OpenDART returned non-success status'}"
        )
    filings = payload.get("list")
    if isinstance(filings, dict):
        filings = [filings]
    if not isinstance(filings, list):
        raise ExternalProviderError("DART response missing filing list")
    documents: list[dict[str, Any]] = []
    for filing in filings:
        if not isinstance(filing, dict):
            raise ExternalProviderError("DART filing row is not an object")
        receipt_no = _require_text(filing.get("rcept_no"), field_name="rcept_no")
        corp_code = _require_text(filing.get("corp_code"), field_name="corp_code")
        published_at = None
        if filing.get("rcept_dt"):
            published_date = _date(filing.get("rcept_dt"), field_name="rcept_dt")
            published_at = datetime.combine(published_date, time.min, tzinfo=UTC)
        documents.append(
            {
                "source_type_code": "DART",
                "source_url": build_url(
                    api_base_url, "/api/document.xml", {"rcept_no": receipt_no}
                ),
                "raw_text": json.dumps(filing, ensure_ascii=False, sort_keys=True),
                "source_document_id": receipt_no,
                "receipt_no": receipt_no,
                "corp_code": corp_code,
                "published_at": published_at,
                "parser_version": DART_XML_PARSER_VERSION,
                "source_payload": {
                    "corp_code": corp_code,
                    "receipt_no": receipt_no,
                    "report_name": str(filing.get("report_nm") or "").strip(),
                    "receipt_date": str(filing.get("rcept_dt") or "").strip(),
                },
            }
        )
    return documents


def parse_dart_corp_code_zip(content: bytes) -> dict[str, str]:
    """Return stock_code -> corp_code mappings from OpenDART corpCode.xml ZIP bytes."""

    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            xml_name = next(name for name in archive.namelist() if name.lower().endswith(".xml"))
            xml_bytes = archive.read(xml_name)
    except (StopIteration, zipfile.BadZipFile, KeyError) as exc:
        raise ExternalProviderError(
            "PROVIDER_FAILED_SCHEMA: DART corpCode.zip is invalid"
        ) from exc
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise ExternalProviderError(
            "PROVIDER_FAILED_SCHEMA: DART corpCode.xml is invalid"
        ) from exc
    mapping: dict[str, str] = {}
    for item in root.findall(".//list"):
        corp_code = (item.findtext("corp_code") or "").strip()
        stock_code = (item.findtext("stock_code") or "").strip()
        if corp_code and stock_code and stock_code.isdigit() and len(stock_code) == 6:
            mapping[stock_code] = corp_code
    if not mapping:
        raise ExternalProviderError(
            "PROVIDER_FAILED_SCHEMA: DART corpCode.xml has no stock rows"
        )
    return mapping


def _extract_dart_document_status(xml_text: str) -> tuple[str | None, str]:
    stripped = xml_text.strip()
    if not stripped.startswith("<"):
        return None, ""
    try:
        root = ElementTree.fromstring(stripped)
    except ElementTree.ParseError:
        return None, ""
    if root.tag.lower() not in {"result", "response"}:
        return None, ""
    status = root.findtext(".//status") or root.findtext(".//STATUS")
    message = (
        root.findtext(".//message")
        or root.findtext(".//MESSAGE")
        or root.findtext(".//msg")
        or root.findtext(".//MSG")
        or ""
    )
    return (status or "").strip() or None, message.strip()


def ensure_dart_document_xml_success(xml_text: str, *, receipt_no: str) -> bool:
    """Return False for official document no-data; raise for auth/rate/schema failures."""

    if not xml_text.strip():
        return False
    status, message = _extract_dart_document_status(xml_text)
    if status in (None, "", DART_STATUS_SUCCESS):
        return True
    provider_status = dart_provider_status_code(status=status, has_rows=False)
    if status in DART_DOCUMENT_NO_DATA_STATUS_CODES or provider_status == "PROVIDER_NO_DATA":
        return False
    raise ExternalProviderError(
        f"{provider_status}: DART document.xml status={status} "
        f"receipt_no={receipt_no} {message or 'OpenDART returned non-success status'}"
    )


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


async def collect_dart_raw_documents(
    *,
    connection: Any,
    client: DartClient,
    targets: Iterable[DartFilingTarget],
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, int]:
    counters = {"rows_collected": 0, "rows_skipped": 0, "rows_failed": 0}
    corp_code_by_stock: dict[str, str] | None = None
    for target in targets:
        corp_code = target.corp_code
        if not corp_code:
            if not target.stock_code:
                raise ExternalProviderError("PROVIDER_FAILED_SCHEMA: DART target lacks corp_code")
            if corp_code_by_stock is None:
                corp_code_by_stock = parse_dart_corp_code_zip(client.corp_code_zip())
            corp_code = corp_code_by_stock.get(target.stock_code)
            if not corp_code:
                raise ExternalProviderError(
                    "PROVIDER_FAILED_SCHEMA: DART corpCode discovery "
                    f"has no stock_code={target.stock_code}"
                )

        page_no = 1
        total_pages = 1
        target_collected = 0
        target_skipped = 0
        target_failed = 0
        target_documents = 0
        target_document_bodies = 0
        target_reason: str | None = None
        while page_no <= total_pages:
            payload = client.list_filings(
                corp_code=corp_code,
                begin_date=target.begin_date,
                end_date=target.end_date,
                page_no=page_no,
                page_count=target.page_count,
                report_type=target.report_type,
            )
            list_evidence = ensure_dart_success_or_no_data(
                payload=payload, target=target, corp_code=corp_code
            )
            if list_evidence.provider_status_code == "PROVIDER_NO_DATA":
                counters["rows_skipped"] += 1
                target_skipped += 1
                target_reason = list_evidence.reason_message or "OpenDART returned no filing rows"
                break
            total_pages = dart_total_pages(payload)
            for document in parse_dart_filing_documents(
                payload=payload, api_base_url=client.config.base_url
            ):
                target_documents += 1
                xml_text = client.document_xml(receipt_no=str(document["receipt_no"]))
                if not ensure_dart_document_xml_success(
                    xml_text, receipt_no=str(document["receipt_no"])
                ):
                    counters["rows_skipped"] += 1
                    target_skipped += 1
                    target_reason = (
                        target_reason or "OpenDART document.xml returned official no-data"
                    )
                    continue
                target_document_bodies += 1
                inserted = await store_raw_document_with_source(
                    connection,
                    source_type_code=str(document["source_type_code"]),
                    source_url=str(document["source_url"]),
                    raw_text=xml_text,
                    provider_code="DART",
                    source_document_id=str(document["source_document_id"]),
                    receipt_no=str(document["receipt_no"]),
                    corp_code=str(document["corp_code"]),
                    published_at=document.get("published_at"),
                    parser_version=str(document["parser_version"]),
                    source_payload=document.get("source_payload"),
                )
                if inserted:
                    counters["rows_collected"] += 1
                    target_collected += 1
                else:
                    counters["rows_skipped"] += 1
                    target_skipped += 1
            page_no += 1

        if evidence is not None and target_collected + target_skipped + target_failed > 0:
            evidence.append(
                dart_document_body_evidence(
                    target=target,
                    corp_code=corp_code,
                    filing_rows=target_documents,
                    document_xml_bodies=target_document_bodies,
                    rows_collected=target_collected,
                    rows_skipped=target_skipped,
                    rows_failed=target_failed,
                    reason_message=target_reason,
                ).as_report_detail()
            )
    return counters
