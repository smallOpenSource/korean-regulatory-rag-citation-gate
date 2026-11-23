/* sql_id: create_batch_provider_evidence_table */
CREATE TABLE IF NOT EXISTS batch_provider_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_job_log_id UUID NOT NULL REFERENCES batch_job_logs(id) ON DELETE CASCADE,
    provider_code VARCHAR(30) NOT NULL,
    provider_status_code VARCHAR(40) NOT NULL CHECK (provider_status_code IN (
        'PROVIDER_DONE',
        'PROVIDER_NO_DATA',
        'PROVIDER_SKIPPED_CONFIG',
        'PROVIDER_SKIPPED_DISABLED',
        'PROVIDER_FAILED_AUTH',
        'PROVIDER_FAILED_RATE_LIMIT',
        'PROVIDER_FAILED_SCHEMA',
        'PROVIDER_FAILED_NETWORK'
    )),
    target_ref VARCHAR(160) NOT NULL,
    rows_collected INTEGER NOT NULL DEFAULT 0 CHECK (rows_collected >= 0),
    rows_skipped INTEGER NOT NULL DEFAULT 0 CHECK (rows_skipped >= 0),
    rows_failed INTEGER NOT NULL DEFAULT 0 CHECK (rows_failed >= 0),
    reason_message TEXT,
    provider_detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (batch_job_log_id, provider_code, target_ref)
);

/* sql_id: index_batch_provider_evidence_log */
CREATE INDEX IF NOT EXISTS idx_batch_provider_evidence_log ON batch_provider_evidence(batch_job_log_id);

/* sql_id: index_batch_provider_evidence_provider_observed */
CREATE INDEX IF NOT EXISTS idx_batch_provider_evidence_provider_observed ON batch_provider_evidence(provider_code, observed_at DESC);

/* sql_id: index_batch_provider_evidence_status_observed */
CREATE INDEX IF NOT EXISTS idx_batch_provider_evidence_status_observed ON batch_provider_evidence(provider_status_code, observed_at DESC);
