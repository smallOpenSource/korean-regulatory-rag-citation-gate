/* sql_id: v061_audit_event_ts */
-- V061: Wave-Audit-Defect-Fix E5 — add ``audit_logs.event_ts`` column to
-- distinguish the logical event time (when the action happened) from the
-- physical INSERT time (``audit_logs.created_at``). Useful for late-
-- arriving audits (batch backfills, queue replay) where the canonical
-- ``created_at`` would otherwise mask the true chronology and break
-- scipy.stats timestamp_spread tests on synthetic fixtures.
--
-- The plan originally named this V058 (Iter3 §S4) but Wave C consumed
-- V058 (rights_notice_acknowledged) + V059 (dispute_responded) + V060
-- (kyc_edd 4 codes), so V061 is the additive slot here. additive-only
-- per [[on-conflict-id-for-mutable-content]] — V054 in-place 금지.
--
-- audit_logs is append-only (V008 trg_audit_logs_no_update + V019 no_truncate),
-- so the original "backfill UPDATE event_ts = created_at" plan is invalid.
-- Pre-V061 rows stay event_ts NULL; queries that need a logical timestamp on
-- legacy rows should COALESCE(event_ts, created_at). New INSERTs after this
-- migration auto-populate via DEFAULT now().
ALTER TABLE audit_logs
    ADD COLUMN IF NOT EXISTS event_ts TIMESTAMPTZ;

/* sql_id: v061_event_ts_default_now */
ALTER TABLE audit_logs
    ALTER COLUMN event_ts SET DEFAULT now();

/* sql_id: v061_index_audit_event_ts */
CREATE INDEX IF NOT EXISTS idx_audit_event_ts
    ON audit_logs(event_ts DESC);
