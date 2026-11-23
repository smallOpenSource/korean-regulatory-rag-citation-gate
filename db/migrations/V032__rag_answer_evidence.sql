/* sql_id: alter_ai_outputs_fail_closed_reason_code */
ALTER TABLE ai_outputs ADD COLUMN IF NOT EXISTS fail_closed_reason_code TEXT NULL;

/* sql_id: alter_document_chunks_quarantine_flag */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS quarantine_flag BOOLEAN NOT NULL DEFAULT FALSE;

/* sql_id: alter_document_chunks_quarantine_pattern_code */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS quarantine_pattern_code VARCHAR(20) NULL;

/* sql_id: alter_document_chunks_quarantine_score */
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS quarantine_score NUMERIC(5,4) NULL;

/* sql_id: create_rag_answer_evidence_table */
CREATE TABLE IF NOT EXISTS rag_answer_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ai_output_id UUID NOT NULL REFERENCES ai_outputs(id),
    chunk_id UUID NOT NULL REFERENCES document_chunks(id),
    quote_span TEXT,
    retrieval_score NUMERIC(5,4),
    faithfulness_score NUMERIC(5,4),
    support_confidence NUMERIC(5,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

/* sql_id: index_rag_answer_evidence_ai_output */
CREATE INDEX IF NOT EXISTS idx_rag_answer_evidence_ai_output
    ON rag_answer_evidence(ai_output_id);

/* sql_id: index_rag_answer_evidence_chunk_created */
CREATE INDEX IF NOT EXISTS idx_rag_answer_evidence_chunk_created
    ON rag_answer_evidence(chunk_id, created_at DESC);
