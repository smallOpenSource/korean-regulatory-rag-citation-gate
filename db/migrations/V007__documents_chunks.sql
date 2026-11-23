/* sql_id: create_documents_table */
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type_code VARCHAR(30) NOT NULL CHECK (source_type_code IN ('DART', 'REG_PAGE', 'RESEARCH', 'MANUAL', 'WEB_SEARCH')),
    source_id VARCHAR(120),
    title VARCHAR(300) NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    raw_content TEXT,
    source_url TEXT,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_documents_content_hash */
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);

/* sql_id: create_document_chunks_table */
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id),
    chunk_no INTEGER NOT NULL CHECK (chunk_no >= 0),
    chunk_text TEXT NOT NULL,
    embedding vector(1024),
    token_count INTEGER NOT NULL CHECK (token_count >= 0),
    is_embedded BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fts tsvector GENERATED ALWAYS AS (to_tsvector('simple', chunk_text)) STORED,
    UNIQUE (document_id, chunk_no)
);

/* sql_id: index_document_chunks_document */
CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks(document_id, chunk_no);

/* sql_id: index_chunks_fts */
CREATE INDEX IF NOT EXISTS idx_chunks_fts ON document_chunks USING GIN(fts);

/* sql_id: index_chunks_embedding */
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
