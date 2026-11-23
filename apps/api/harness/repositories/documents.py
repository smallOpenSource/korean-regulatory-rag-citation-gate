"""Raw document transform and derived refresh repositories."""

from __future__ import annotations

import json
from typing import Any

from apps.api.harness.core.db import execute, fetch_all, fetch_one

from .common import row_to_dict, rows_to_dicts

LIST_UNPROCESSED_RAW_DOCUMENTS_SQL = """
/* sql_id: list_unprocessed_raw_documents */
SELECT rd.id, rd.source_type_code, rd.source_url, rd.content_hash, rd.raw_text,
       rd.collected_at, ds.provider_code, ds.source_document_id, ds.receipt_no,
       ds.corp_code, ds.canonical_url, ds.published_at, ds.parser_version
FROM raw_documents rd
LEFT JOIN LATERAL (
    SELECT source.provider_code, source.source_document_id, source.receipt_no,
           source.corp_code, source.canonical_url, source.published_at, source.parser_version
    FROM document_sources source
    WHERE source.raw_document_id = rd.id
    ORDER BY source.created_at DESC
    LIMIT 1
) ds ON TRUE
WHERE rd.is_processed IS FALSE
ORDER BY rd.collected_at
LIMIT $1;
"""

UPSERT_DOCUMENT_FROM_RAW_SQL = """
/* sql_id: upsert_document_from_raw */
WITH inserted AS (
    INSERT INTO documents(source_type_code, source_id, title, content_hash, raw_content,
                          source_url, published_at)
    SELECT $1::varchar, $2::varchar, $3::varchar, $4::varchar, $5::text, $6::text, $7::timestamptz
    WHERE NOT EXISTS (
        SELECT 1
        FROM documents
        WHERE content_hash = $4::varchar
          AND source_url = $6::text
    )
    RETURNING id, source_type_code, source_id, title, content_hash, source_url,
              published_at, created_at
)
SELECT id, source_type_code, source_id, title, content_hash, source_url, published_at, created_at
FROM inserted
UNION ALL
SELECT id, source_type_code, source_id, title, content_hash, source_url, published_at, created_at
FROM documents
WHERE content_hash = $4::varchar
  AND source_url = $6::text
LIMIT 1;
"""

UPSERT_DOCUMENT_CHUNK_SQL = """
/* sql_id: upsert_document_chunk */
INSERT INTO document_chunks(document_id, chunk_no, chunk_text, token_count, provider_code,
                            corp_code, receipt_no, source_url, published_at, section_path,
                            parser_version, metadata_json)
VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9::timestamptz, $10, $11, $12::jsonb)
ON CONFLICT (document_id, chunk_no) DO UPDATE
SET chunk_text = EXCLUDED.chunk_text,
    token_count = EXCLUDED.token_count,
    provider_code = EXCLUDED.provider_code,
    corp_code = EXCLUDED.corp_code,
    receipt_no = EXCLUDED.receipt_no,
    source_url = EXCLUDED.source_url,
    published_at = EXCLUDED.published_at,
    section_path = EXCLUDED.section_path,
    parser_version = EXCLUDED.parser_version,
    metadata_json = EXCLUDED.metadata_json,
    embedding = CASE
        WHEN document_chunks.chunk_text IS DISTINCT FROM EXCLUDED.chunk_text THEN NULL
        ELSE document_chunks.embedding
    END,
    is_embedded = CASE
        WHEN document_chunks.chunk_text IS DISTINCT FROM EXCLUDED.chunk_text THEN FALSE
        ELSE document_chunks.is_embedded
    END
RETURNING id, document_id, chunk_no, token_count, is_embedded, provider_code, corp_code,
          receipt_no, section_path, parser_version, created_at;
"""

MARK_RAW_DOCUMENT_PROCESSED_SQL = """
/* sql_id: mark_raw_document_processed */
UPDATE raw_documents
SET is_processed = TRUE, processed_at = now()
WHERE id = $1::uuid;
"""

UPSERT_DOCUMENT_SOURCE_SQL = """
/* sql_id: upsert_document_source */
INSERT INTO document_sources(raw_document_id, provider_code, source_document_id, receipt_no,
                             corp_code, canonical_url, published_at, content_hash,
                             parser_version, source_payload_json)
VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::timestamptz, $8, $9, $10::jsonb)
ON CONFLICT (provider_code, source_document_id, parser_version, content_hash) DO UPDATE
SET raw_document_id = EXCLUDED.raw_document_id,
    receipt_no = EXCLUDED.receipt_no,
    corp_code = EXCLUDED.corp_code,
    canonical_url = EXCLUDED.canonical_url,
    published_at = EXCLUDED.published_at,
    source_payload_json = EXCLUDED.source_payload_json
RETURNING id, raw_document_id, document_id, provider_code, source_document_id, receipt_no,
          corp_code, canonical_url, published_at, content_hash, parser_version,
          source_payload_json, created_at;
"""

LINK_DOCUMENT_SOURCE_SQL = """
/* sql_id: link_document_source */
UPDATE document_sources
SET document_id = $2::uuid
WHERE raw_document_id = $1::uuid
RETURNING id, raw_document_id, document_id, provider_code, source_document_id, receipt_no,
          corp_code, canonical_url, published_at, content_hash, parser_version, created_at;
"""

SEARCH_RAG_CHUNKS_SQL = """
/* sql_id: search_rag_chunks */
SELECT dc.id AS chunk_id, dc.document_id, dc.chunk_no, dc.chunk_text, dc.token_count,
       dc.provider_code, dc.corp_code, dc.receipt_no, dc.source_url, dc.published_at,
       dc.section_path, dc.parser_version, d.source_type_code, d.title AS document_title,
       d.source_id AS document_source_id, d.source_url AS document_source_url,
       d.published_at AS document_published_at,
       CASE
           WHEN $1 = '' THEN 0::real
           ELSE ts_rank_cd(dc.fts, plainto_tsquery('simple', $1))
       END AS retrieval_score
FROM document_chunks dc
JOIN documents d ON d.id = dc.document_id
WHERE dc.is_embedded IS TRUE
  AND ($2::varchar[] IS NULL OR d.source_type_code = ANY($2::varchar[]))
  AND ($3::varchar IS NULL OR dc.corp_code = $3::varchar)
  AND ($4::varchar IS NULL OR dc.receipt_no = $4::varchar)
  AND ($5::varchar IS NULL OR dc.provider_code = $5::varchar)
  AND ($6::timestamptz IS NULL OR COALESCE(dc.published_at, d.published_at) >= $6::timestamptz)
  AND ($7::timestamptz IS NULL OR COALESCE(dc.published_at, d.published_at) <= $7::timestamptz)
  AND (
      $1 = ''
      OR dc.fts @@ plainto_tsquery('simple', $1)
      OR dc.chunk_text ILIKE ('%' || $1 || '%')
  )
ORDER BY retrieval_score DESC, dc.created_at DESC
LIMIT $8;
"""

INSERT_RAG_ANSWER_EVIDENCE_SQL = """
/* sql_id: insert_rag_answer_evidence */
INSERT INTO rag_answer_evidence(ai_output_id, chunk_id, source_document_id, quote_span_json,
                                retrieval_score, rerank_score, confidence)
VALUES ($1::uuid, $2::uuid, $3, $4::jsonb, $5, $6, $7)
ON CONFLICT (ai_output_id, chunk_id) DO UPDATE
SET quote_span_json = EXCLUDED.quote_span_json,
    retrieval_score = EXCLUDED.retrieval_score,
    rerank_score = EXCLUDED.rerank_score,
    confidence = EXCLUDED.confidence
RETURNING id, ai_output_id, chunk_id, source_document_id, quote_span_json,
          retrieval_score, rerank_score, confidence, created_at;
"""

GET_RAG_READINESS_COUNTS_SQL = """
/* sql_id: get_rag_readiness_counts */
SELECT
    (SELECT count(*) FROM documents) AS documents_count,
    (SELECT count(*) FROM document_chunks) AS chunks_count,
    (SELECT count(*) FROM document_chunks WHERE is_embedded IS TRUE) AS embedded_chunks_count,
    (SELECT count(*) FROM document_chunks WHERE is_embedded IS FALSE) AS pending_chunks_count,
    (
        SELECT count(*)
        FROM batch_job_logs
        WHERE job_type_code IN ('DOCUMENT_TRANSFORM', 'EMBEDDING_REFRESH', 'RAG_REFRESH')
          AND status_code IN ('FAILED', 'SKIPPED')
    ) AS blocked_batch_logs_count,
    (SELECT count(*) FROM house_views WHERE status_code = 'ACTIVE') AS active_house_views_count,
    (SELECT count(*) FROM nba_actions WHERE status_code = 'PENDING') AS pending_nba_count,
    (SELECT count(*) FROM aftercare_events WHERE status_code = 'OPEN') AS open_aftercare_count;
"""

INSERT_MATURITY_AFTERCARE_SQL = """
/* sql_id: insert_maturity_aftercare */
INSERT INTO aftercare_events(customer_id, product_id, employee_id, event_type_code, event_date,
                             status_code, notes)
SELECT DISTINCT c.id, p.id, c.assigned_pb_id, 'MATURITY_DUE', p.maturity_date, 'OPEN',
       'Derived from portfolio holding maturity date'
FROM portfolio_holdings ph
JOIN portfolios pf ON pf.id = ph.portfolio_id
JOIN customers c ON c.id = pf.customer_id
JOIN products p ON p.id = ph.product_id
WHERE c.is_active IS TRUE
  AND p.is_active IS TRUE
  AND p.maturity_date IS NOT NULL
  AND p.maturity_date BETWEEN current_date AND current_date + ($1::int * interval '1 day')
  AND NOT EXISTS (
      SELECT 1
      FROM aftercare_events existing
      WHERE existing.customer_id = c.id
        AND existing.product_id = p.id
        AND existing.event_type_code = 'MATURITY_DUE'
        AND existing.status_code IN ('OPEN', 'IN_PROGRESS')
  )
RETURNING id, customer_id, product_id, employee_id, event_type_code, status_code;
"""

INSERT_NO_CONTACT_AFTERCARE_SQL = """
/* sql_id: insert_no_contact_aftercare */
INSERT INTO aftercare_events(customer_id, product_id, employee_id, event_type_code, event_date,
                             status_code, notes)
SELECT c.id, NULL, c.assigned_pb_id, 'NO_CONTACT', current_date, 'OPEN',
       'Derived from customer last_contacted_at threshold'
FROM customers c
WHERE c.is_active IS TRUE
  AND (c.last_contacted_at IS NULL OR c.last_contacted_at < now() - ($1::int * interval '1 day'))
  AND NOT EXISTS (
      SELECT 1
      FROM aftercare_events existing
      WHERE existing.customer_id = c.id
        AND existing.product_id IS NULL
        AND existing.event_type_code = 'NO_CONTACT'
        AND existing.status_code IN ('OPEN', 'IN_PROGRESS')
  )
RETURNING id, customer_id, product_id, employee_id, event_type_code, status_code;
"""

INSERT_NBA_FROM_AFTERCARE_SQL = """
/* sql_id: insert_nba_from_aftercare */
INSERT INTO nba_actions(customer_id, employee_id, action_type_code, priority_code, status_code,
                        trigger_code, script_text, script_generated_at, script_model_name,
                        due_date)
SELECT a.customer_id,
       a.employee_id,
       CASE a.event_type_code
           WHEN 'KI_TRIGGERED' THEN 'KI_FOLLOW_UP'
           WHEN 'MATURITY_DUE' THEN 'MATURITY_FOLLOW_UP'
           WHEN 'DRAWDOWN_BREACH' THEN 'DRAWDOWN_FOLLOW_UP'
           WHEN 'NO_CONTACT' THEN 'NO_CONTACT_FOLLOW_UP'
           ELSE 'REVIEW_FOLLOW_UP'
       END,
       CASE a.event_type_code
           WHEN 'KI_TRIGGERED' THEN 'URGENT'
           WHEN 'DRAWDOWN_BREACH' THEN 'HIGH'
           WHEN 'MATURITY_DUE' THEN 'HIGH'
           ELSE 'MEDIUM'
       END,
       'PENDING',
       a.event_type_code,
       NULL,
       NULL,
       NULL,
       current_date
FROM aftercare_events a
WHERE a.status_code = 'OPEN'
  AND NOT EXISTS (
      SELECT 1
      FROM nba_actions existing
      WHERE existing.customer_id = a.customer_id
        AND existing.trigger_code = a.event_type_code
        AND existing.status_code IN ('PENDING', 'IN_PROGRESS', 'SNOOZED')
  )
RETURNING id, customer_id, employee_id, action_type_code, priority_code, status_code,
          trigger_code;
"""


async def list_unprocessed_raw_documents(
    connection: Any, *, limit: int
) -> list[dict[str, Any]]:
    """Return unprocessed raw documents in deterministic collection order."""

    rows = await fetch_all(connection, LIST_UNPROCESSED_RAW_DOCUMENTS_SQL, limit)
    return rows_to_dicts(rows)


async def upsert_document_from_raw(
    connection: Any,
    *,
    source_type_code: str,
    source_id: str,
    title: str,
    content_hash: str,
    raw_content: str,
    source_url: str,
    published_at: Any | None = None,
) -> dict[str, Any]:
    """Create or read the canonical document row for a raw document."""

    row = await fetch_one(
        connection,
        UPSERT_DOCUMENT_FROM_RAW_SQL,
        source_type_code,
        source_id,
        title,
        content_hash,
        raw_content,
        source_url,
        published_at,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("document upsert returned no row")
    return result


async def upsert_document_chunk(
    connection: Any,
    *,
    document_id: str,
    chunk_no: int,
    chunk_text: str,
    token_count: int,
    provider_code: str | None = None,
    corp_code: str | None = None,
    receipt_no: str | None = None,
    source_url: str | None = None,
    published_at: Any | None = None,
    section_path: str | None = None,
    parser_version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert or refresh one document chunk while preserving valid embeddings."""

    row = await fetch_one(
        connection,
        UPSERT_DOCUMENT_CHUNK_SQL,
        document_id,
        chunk_no,
        chunk_text,
        token_count,
        provider_code,
        corp_code,
        receipt_no,
        source_url,
        published_at,
        section_path,
        parser_version,
        json.dumps(metadata or {}, ensure_ascii=False),
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("document chunk upsert returned no row")
    return result


async def mark_raw_document_processed(connection: Any, *, raw_document_id: str) -> None:
    """Mark one raw document processed after transform/chunk handling."""

    await execute(connection, MARK_RAW_DOCUMENT_PROCESSED_SQL, raw_document_id)


async def upsert_document_source(
    connection: Any,
    *,
    raw_document_id: str,
    provider_code: str,
    source_document_id: str,
    receipt_no: str | None,
    corp_code: str | None,
    canonical_url: str,
    published_at: Any | None,
    content_hash: str,
    parser_version: str,
    source_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or refresh provider source metadata for one raw document."""

    row = await fetch_one(
        connection,
        UPSERT_DOCUMENT_SOURCE_SQL,
        raw_document_id,
        provider_code,
        source_document_id,
        receipt_no,
        corp_code,
        canonical_url,
        published_at,
        content_hash,
        parser_version,
        json.dumps(source_payload or {}, ensure_ascii=False),
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("document source upsert returned no row")
    return result


async def link_document_source(
    connection: Any, *, raw_document_id: str, document_id: str
) -> dict[str, Any] | None:
    """Link document source metadata to the canonical transformed document row."""

    return row_to_dict(
        await fetch_one(connection, LINK_DOCUMENT_SOURCE_SQL, raw_document_id, document_id)
    )


async def search_rag_chunks(
    connection: Any,
    *,
    question: str,
    source_types: list[str] | None,
    corp_code: str | None,
    receipt_no: str | None,
    provider_code: str | None,
    published_from: Any | None,
    published_to: Any | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Return embedded candidate chunks that satisfy citation metadata filters."""

    rows = await fetch_all(
        connection,
        SEARCH_RAG_CHUNKS_SQL,
        question.strip(),
        source_types,
        corp_code,
        receipt_no,
        provider_code,
        published_from,
        published_to,
        limit,
    )
    return rows_to_dicts(rows)


async def insert_rag_answer_evidence(
    connection: Any,
    *,
    ai_output_id: str,
    chunk_id: str,
    source_document_id: str,
    quote_span: dict[str, Any],
    retrieval_score: float,
    rerank_score: float | None,
    confidence: float,
) -> dict[str, Any]:
    """Persist the chunk-level evidence required for a generated RAG answer."""

    row = await fetch_one(
        connection,
        INSERT_RAG_ANSWER_EVIDENCE_SQL,
        ai_output_id,
        chunk_id,
        source_document_id,
        json.dumps(quote_span, ensure_ascii=False),
        retrieval_score,
        rerank_score,
        confidence,
    )
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("rag answer evidence insert returned no row")
    return result


async def get_rag_readiness_counts(connection: Any) -> dict[str, Any]:
    """Return RAG and derived workflow readiness counters."""

    row = await fetch_one(connection, GET_RAG_READINESS_COUNTS_SQL)
    result = row_to_dict(row)
    if result is None:
        raise RuntimeError("rag readiness query returned no row")
    return result


async def insert_maturity_aftercare(
    connection: Any, *, horizon_days: int
) -> list[dict[str, Any]]:
    """Create maturity aftercare events from current portfolio holdings."""

    rows = await fetch_all(connection, INSERT_MATURITY_AFTERCARE_SQL, horizon_days)
    return rows_to_dicts(rows)


async def insert_no_contact_aftercare(
    connection: Any, *, no_contact_days: int
) -> list[dict[str, Any]]:
    """Create no-contact aftercare events from stale customer contact dates."""

    rows = await fetch_all(connection, INSERT_NO_CONTACT_AFTERCARE_SQL, no_contact_days)
    return rows_to_dicts(rows)


async def insert_nba_from_open_aftercare(connection: Any) -> list[dict[str, Any]]:
    """Create pending NBA rows from open aftercare events without AI-script metadata."""

    rows = await fetch_all(connection, INSERT_NBA_FROM_AFTERCARE_SQL)
    return rows_to_dicts(rows)
