/* sql_id: v063_create_idempotency_keys */
-- V063: Wave-Z5 B.2 — Idempotency-Key middleware backing store (ADR-011).
-- Per-route server-side dedupe table. Status lifecycle:
--   in_flight (handler running)
--   completed (response cached for replay)
--   failed    (handler raised; client must wait TTL to retry the same key)
-- 24h TTL is enforced by an out-of-band cleanup job, not by trigger here.
-- Append-only does NOT apply: this is operational state, not audit evidence.
CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key      UUID        NOT NULL,
    route_template       TEXT        NOT NULL,
    request_hash         TEXT        NOT NULL,
    status               TEXT        NOT NULL CHECK (status IN ('in_flight','completed','failed')),
    response_body        JSONB,
    response_status_code SMALLINT,
    actor_id             UUID,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at         TIMESTAMPTZ,
    PRIMARY KEY (idempotency_key, route_template)
);

/* sql_id: v063_idempotency_keys_created_at_idx */
-- Index supports the 24h-TTL sweep cron without table scan.
CREATE INDEX IF NOT EXISTS idempotency_keys_created_at_idx
    ON idempotency_keys (created_at);
