/* sql_id: repair_create_document_sources_table */
CREATE TABLE IF NOT EXISTS document_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_document_id UUID REFERENCES raw_documents(id),
    document_id UUID REFERENCES documents(id),
    provider_code VARCHAR(30) NOT NULL CHECK (provider_code IN ('DART', 'REG_PAGE', 'RESEARCH', 'MANUAL', 'WEB_SEARCH')),
    source_document_id VARCHAR(120) NOT NULL,
    receipt_no VARCHAR(40),
    corp_code VARCHAR(20),
    canonical_url TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    content_hash VARCHAR(128) NOT NULL,
    parser_version VARCHAR(40) NOT NULL,
    source_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider_code, source_document_id, parser_version, content_hash)
);

/* sql_id: repair_index_document_sources_raw */
CREATE INDEX IF NOT EXISTS idx_document_sources_raw ON document_sources(raw_document_id);

/* sql_id: repair_index_document_sources_document */
CREATE INDEX IF NOT EXISTS idx_document_sources_document ON document_sources(document_id);

/* sql_id: repair_index_document_sources_receipt */
CREATE INDEX IF NOT EXISTS idx_document_sources_receipt ON document_sources(receipt_no);

/* sql_id: repair_index_document_sources_corp */
CREATE INDEX IF NOT EXISTS idx_document_sources_corp ON document_sources(corp_code, published_at DESC);

/* sql_id: repair_chunk_provider_code */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS provider_code VARCHAR(30);

/* sql_id: repair_chunk_corp_code */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS corp_code VARCHAR(20);

/* sql_id: repair_chunk_receipt_no */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS receipt_no VARCHAR(40);

/* sql_id: repair_chunk_source_url */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS source_url TEXT;

/* sql_id: repair_chunk_published_at */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;

/* sql_id: repair_chunk_section_path */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS section_path TEXT;

/* sql_id: repair_chunk_parser_version */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS parser_version VARCHAR(40);

/* sql_id: repair_chunk_metadata_json */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;

/* sql_id: repair_index_chunks_receipt */
CREATE INDEX IF NOT EXISTS idx_document_chunks_receipt ON document_chunks(receipt_no, chunk_no);

/* sql_id: repair_index_chunks_corp_provider */
CREATE INDEX IF NOT EXISTS idx_document_chunks_corp_provider ON document_chunks(corp_code, provider_code, published_at DESC);

/* sql_id: repair_create_rag_answer_evidence_table */
CREATE TABLE IF NOT EXISTS rag_answer_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ai_output_id UUID NOT NULL REFERENCES ai_outputs(id),
    chunk_id UUID NOT NULL REFERENCES document_chunks(id),
    source_document_id VARCHAR(120) NOT NULL,
    quote_span_json JSONB NOT NULL,
    retrieval_score NUMERIC(10,6) NOT NULL CHECK (retrieval_score >= 0),
    rerank_score NUMERIC(10,6),
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ai_output_id, chunk_id)
);

/* sql_id: repair_index_rag_evidence_output */
CREATE INDEX IF NOT EXISTS idx_rag_answer_evidence_output ON rag_answer_evidence(ai_output_id);

/* sql_id: repair_index_rag_evidence_chunk */
CREATE INDEX IF NOT EXISTS idx_rag_answer_evidence_chunk ON rag_answer_evidence(chunk_id);
