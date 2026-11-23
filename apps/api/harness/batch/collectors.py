"""Batch collector helpers for provider documents, market prices, and macro data."""

from __future__ import annotations

from typing import Any

from apps.api.harness.external.public_data import content_hash
from apps.api.harness.repositories import batch as batch_repo
from apps.api.harness.repositories import documents as document_repo


def sanitize_provider_text(raw_text: str) -> str:
    """Return provider text acceptable for PostgreSQL text columns."""

    return raw_text.replace("\x00", "")


async def store_raw_document(
    connection: Any,
    *,
    source_type_code: str,
    source_url: str,
    raw_text: str,
) -> bool:
    """Store raw text with SHA-256 deduplication; return True if inserted."""

    stored_text = sanitize_provider_text(raw_text)
    inserted = await batch_repo.insert_raw_document(
        connection,
        source_type_code=source_type_code,
        source_url=source_url,
        content_hash=content_hash(stored_text),
        raw_text=stored_text,
    )
    return inserted is not None


async def store_market_prices(connection: Any, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Persist domestic Korea equity price bars using raw-SQL upsert semantics."""

    counters = {"rows_collected": 0, "rows_skipped": 0, "rows_failed": 0}
    for row in rows:
        try:
            inserted = await batch_repo.upsert_market_price(connection, row=row)
        except Exception:  # noqa: BLE001 - per-row batch policy counts failures
            counters["rows_failed"] += 1
            continue
        if inserted is None:
            counters["rows_skipped"] += 1
        else:
            counters["rows_collected"] += 1
    if counters["rows_collected"] > 0:
        await batch_repo.mark_price_bars_valid(connection)
    return counters


async def store_macro_indicators(connection: Any, rows: list[dict[str, Any]]) -> dict[str, int]:
    """Persist macro indicators using ON CONFLICT DO NOTHING semantics."""

    counters = {"rows_collected": 0, "rows_skipped": 0, "rows_failed": 0}
    for row in rows:
        try:
            inserted = await batch_repo.upsert_macro_indicator(connection, row=row)
        except Exception:  # noqa: BLE001 - per-row batch policy counts failures
            counters["rows_failed"] += 1
            continue
        if inserted is None:
            counters["rows_skipped"] += 1
        else:
            counters["rows_collected"] += 1
    return counters


async def store_raw_document_with_source(
    connection: Any,
    *,
    source_type_code: str,
    source_url: str,
    raw_text: str,
    provider_code: str,
    source_document_id: str,
    receipt_no: str | None,
    corp_code: str | None,
    published_at: Any | None,
    parser_version: str,
    source_payload: dict[str, Any] | None = None,
) -> bool:
    """Store raw document plus provider source metadata; return True only for new raw rows."""

    stored_text = sanitize_provider_text(raw_text)
    digest = content_hash(stored_text)
    inserted = await batch_repo.insert_raw_document(
        connection,
        source_type_code=source_type_code,
        source_url=source_url,
        content_hash=digest,
        raw_text=stored_text,
    )
    raw_row = inserted or await batch_repo.get_raw_document_by_hash_url(
        connection, content_hash=digest, source_url=source_url
    )
    if raw_row is None:
        raise RuntimeError("raw document insert/read returned no row")
    await document_repo.upsert_document_source(
        connection,
        raw_document_id=str(raw_row["id"]),
        provider_code=provider_code,
        source_document_id=source_document_id,
        receipt_no=receipt_no,
        corp_code=corp_code,
        canonical_url=source_url,
        published_at=published_at,
        content_hash=digest,
        parser_version=parser_version,
        source_payload=source_payload,
    )
    return inserted is not None
