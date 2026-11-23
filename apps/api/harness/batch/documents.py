"""Document transform, RAG readiness, and derived workflow refresh helpers."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from apps.api.harness.repositories import documents as document_repo

DEFAULT_CHUNK_TOKENS = 512
DEFAULT_CHUNK_OVERLAP_TOKENS = 64
DEFAULT_MIN_CHARS = 50
DART_XML_PARSER_VERSION = "dart-xml-v1"
PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s+prompt|developer\s+message|assistant\s+message", re.IGNORECASE),
    re.compile(r"override\s+(the\s+)?(policy|compliance|instructions)", re.IGNORECASE),
    re.compile(r"이전\s*지시.*무시|시스템\s*프롬프트|정책.*무시"),
)


@dataclass(frozen=True)
class SanitizedText:
    """Document text after quarantining prompt-like instructions."""

    text: str
    quarantined_lines: int


@dataclass(frozen=True)
class SectionDraft:
    """Parser-versioned document section prepared for chunking."""

    path: str
    text: str
    quarantined_lines: int


@dataclass(frozen=True)
class ChunkDraft:
    """Prepared chunk text plus the token count stored with document_chunks."""

    text: str
    token_count: int


def normalize_text(raw_text: str) -> str:
    """Normalize whitespace without changing document meaning."""

    return " ".join(raw_text.split())


def sanitize_untrusted_document_text(raw_text: str) -> SanitizedText:
    """Remove prompt-like instructions from untrusted provider text before retrieval."""

    kept_lines: list[str] = []
    quarantined = 0
    for line in raw_text.splitlines() or [raw_text]:
        if any(pattern.search(line) for pattern in PROMPT_INJECTION_PATTERNS):
            quarantined += 1
            continue
        kept_lines.append(line)
    return SanitizedText(text=normalize_text("\n".join(kept_lines)), quarantined_lines=quarantined)


def _tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].strip() or "node"


def _element_label(element: ET.Element) -> str:
    tag = _tag_name(element.tag)
    for key in ("A_NAME", "NAME", "name", "title", "TITLE"):
        value = element.attrib.get(key)
        if value:
            return f"{tag}:{normalize_text(value)[:80]}"
    return tag


def _direct_element_text(element: ET.Element) -> str:
    parts: list[str] = []
    if element.text and element.text.strip():
        parts.append(element.text)
    for child in list(element):
        if child.tail and child.tail.strip():
            parts.append(child.tail)
    return normalize_text(" ".join(parts))


def extract_dart_xml_sections(
    raw_text: str, *, min_chars: int = DEFAULT_MIN_CHARS
) -> list[SectionDraft]:
    """Parse OpenDART document.xml into sanitized, parser-versioned sections."""

    try:
        root = ET.fromstring(raw_text)
    except ET.ParseError:
        sanitized = sanitize_untrusted_document_text(raw_text)
        return (
            [
                SectionDraft(
                    path="raw",
                    text=sanitized.text,
                    quarantined_lines=sanitized.quarantined_lines,
                )
            ]
            if len(sanitized.text) >= min_chars
            else []
        )

    sections: list[SectionDraft] = []

    def walk(element: ET.Element, path: list[str]) -> tuple[int, int]:
        current_path = [*path, _element_label(element)]
        child_sections = 0
        child_quarantined = 0
        for child in list(element):
            section_count, quarantined_count = walk(child, current_path)
            child_sections += section_count
            child_quarantined += quarantined_count

        direct_text = _direct_element_text(element)
        candidate = direct_text
        if child_sections == 0 and len(candidate) < min_chars:
            candidate = normalize_text(" ".join(element.itertext()))
        sanitized = sanitize_untrusted_document_text(candidate)
        total_quarantined = child_quarantined + sanitized.quarantined_lines
        if len(sanitized.text) >= min_chars:
            sections.append(
                SectionDraft(
                    path="/".join(current_path[-6:]),
                    text=sanitized.text,
                    quarantined_lines=total_quarantined,
                )
            )
            return child_sections + 1, total_quarantined
        return child_sections, total_quarantined

    _, total_quarantined = walk(root, [])
    if sections:
        if total_quarantined and not any(section.quarantined_lines for section in sections):
            first = sections[0]
            sections[0] = SectionDraft(
                path=first.path,
                text=first.text,
                quarantined_lines=total_quarantined,
            )
        return sections
    sanitized = sanitize_untrusted_document_text(" ".join(root.itertext()))
    if len(sanitized.text) < min_chars:
        return []
    return [
        SectionDraft(
            path=_tag_name(root.tag),
            text=sanitized.text,
            quarantined_lines=sanitized.quarantined_lines,
        )
    ]


def sections_from_raw_document(
    row: dict[str, Any], *, min_chars: int = DEFAULT_MIN_CHARS
) -> list[SectionDraft]:
    """Return parser sections for DART XML or a sanitized single-section fallback."""

    raw_text = str(row.get("raw_text") or "")
    if str(row.get("source_type_code") or "") == "DART" and raw_text.lstrip().startswith("<"):
        return extract_dart_xml_sections(raw_text, min_chars=min_chars)
    sanitized = sanitize_untrusted_document_text(raw_text)
    if len(sanitized.text) < min_chars:
        return []
    return [
        SectionDraft(
            path="document",
            text=sanitized.text,
            quarantined_lines=sanitized.quarantined_lines,
        )
    ]


def chunk_text(
    text: str,
    *,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> list[ChunkDraft]:
    """Split normalized text into overlapping word-token chunks."""

    if chunk_tokens <= 0:
        raise ValueError("chunk_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= chunk_tokens:
        raise ValueError("overlap_tokens must be non-negative and smaller than chunk_tokens")

    tokens = normalize_text(text).split()
    if not tokens:
        return []

    chunks: list[ChunkDraft] = []
    step = chunk_tokens - overlap_tokens
    for start in range(0, len(tokens), step):
        window = tokens[start : start + chunk_tokens]
        chunk = " ".join(window)
        if len(chunk) >= min_chars:
            chunks.append(ChunkDraft(text=chunk, token_count=len(window)))
        if start + chunk_tokens >= len(tokens):
            break
    return chunks


def title_from_raw_document(*, source_type_code: str, content_hash: str) -> str:
    """Build a deterministic title that avoids leaking provider URL query secrets."""

    return f"{source_type_code} document {content_hash[:12]}"


def rag_readiness_status(counts: dict[str, Any]) -> str:
    """Classify RAG readiness without inventing model/provider success."""

    embedded = int(counts.get("embedded_chunks_count") or 0)
    chunks = int(counts.get("chunks_count") or 0)
    blocked = int(counts.get("blocked_batch_logs_count") or 0)
    if embedded > 0:
        return "READY"
    if chunks > 0:
        return "PENDING_EMBEDDING"
    if blocked > 0:
        return "PROVIDER_BLOCKED"
    return "EMPTY"


async def transform_raw_documents(
    *,
    connection: Any,
    limit: int = 100,
    chunk_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> dict[str, int]:
    """Transform raw_documents into documents and document_chunks."""

    rows = await document_repo.list_unprocessed_raw_documents(connection, limit=limit)
    counters = {"rows_collected": 0, "rows_skipped": 0, "rows_failed": 0}
    for row in rows:
        raw_document_id = str(row["id"])
        sections = sections_from_raw_document(row, min_chars=min_chars)
        chunks_by_section: list[tuple[SectionDraft, ChunkDraft]] = []
        for section in sections:
            chunks_by_section.extend(
                (section, chunk)
                for chunk in chunk_text(
                    section.text,
                    chunk_tokens=chunk_tokens,
                    overlap_tokens=overlap_tokens,
                    min_chars=min_chars,
                )
            )
        if not chunks_by_section:
            await document_repo.mark_raw_document_processed(
                connection, raw_document_id=raw_document_id
            )
            counters["rows_skipped"] += 1
            continue

        source_url = str(row.get("canonical_url") or row["source_url"])
        source_id = str(row.get("source_document_id") or row.get("receipt_no") or raw_document_id)
        raw_content = "\n\n".join(section.text for section in sections)
        document = await document_repo.upsert_document_from_raw(
            connection,
            source_type_code=str(row["source_type_code"]),
            source_id=source_id,
            title=title_from_raw_document(
                source_type_code=str(row["source_type_code"]),
                content_hash=str(row["content_hash"]),
            ),
            content_hash=str(row["content_hash"]),
            raw_content=raw_content,
            source_url=source_url,
            published_at=row.get("published_at"),
        )
        await document_repo.link_document_source(
            connection, raw_document_id=raw_document_id, document_id=str(document["id"])
        )
        for chunk_no, (section, chunk) in enumerate(chunks_by_section):
            await document_repo.upsert_document_chunk(
                connection,
                document_id=str(document["id"]),
                chunk_no=chunk_no,
                chunk_text=chunk.text,
                token_count=chunk.token_count,
                provider_code=str(row.get("provider_code") or row["source_type_code"]),
                corp_code=row.get("corp_code"),
                receipt_no=row.get("receipt_no"),
                source_url=source_url,
                published_at=row.get("published_at"),
                section_path=section.path,
                parser_version=str(row.get("parser_version") or DART_XML_PARSER_VERSION),
                metadata={"quarantined_prompt_lines": section.quarantined_lines},
            )
        await document_repo.mark_raw_document_processed(connection, raw_document_id=raw_document_id)
        counters["rows_collected"] += 1
    return counters


async def rag_readiness_snapshot(*, connection: Any) -> dict[str, Any]:
    """Return RAG readiness counters with a derived status field."""

    counts = await document_repo.get_rag_readiness_counts(connection)
    return {**counts, "status_code": rag_readiness_status(counts)}


async def refresh_aftercare_and_nba(
    *,
    connection: Any,
    maturity_horizon_days: int = 45,
    no_contact_days: int = 30,
) -> dict[str, int]:
    """Refresh derived aftercare events and pending NBA rows from persisted state."""

    maturity_events = await document_repo.insert_maturity_aftercare(
        connection, horizon_days=maturity_horizon_days
    )
    no_contact_events = await document_repo.insert_no_contact_aftercare(
        connection, no_contact_days=no_contact_days
    )
    nba_actions = await document_repo.insert_nba_from_open_aftercare(connection)
    return {
        "rows_collected": len(maturity_events) + len(no_contact_events) + len(nba_actions),
        "rows_skipped": 0,
        "rows_failed": 0,
    }
