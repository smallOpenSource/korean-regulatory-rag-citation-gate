/* sql_id: v036_nba_p1p2p3_aftercare_quarterly_migration */
-- V036: NBA card P1/P2/P3 priority + SLA timers (T17, T243)
--        Aftercare quarterly queue support (T244, T257)

-- ─── NBA actions: widen priority + add score / why_link / sla_timer ───────────

/* sql_id: v025_drop_nba_priority_check */
ALTER TABLE nba_actions DROP CONSTRAINT IF EXISTS nba_actions_priority_code_check;

/* sql_id: v025_add_nba_priority_check */
ALTER TABLE nba_actions ADD CONSTRAINT nba_actions_priority_code_check
    CHECK (priority_code IN ('P1', 'P2', 'P3', 'URGENT', 'HIGH', 'MEDIUM', 'LOW'));

/* sql_id: v025_add_nba_score_columns */
-- score 0.0000-1.0000; why_link_json {house_view_id, signal_event_id, rule_id}; sla_timer_seconds P1=3600 P2=14400 P3=86400
ALTER TABLE nba_actions
    ADD COLUMN IF NOT EXISTS score             NUMERIC(5, 4),
    ADD COLUMN IF NOT EXISTS why_link_json     JSONB,
    ADD COLUMN IF NOT EXISTS sla_timer_seconds INTEGER;

/* sql_id: v025_index_nba_sla */
CREATE INDEX IF NOT EXISTS idx_nba_sla_timer ON nba_actions (sla_timer_seconds, priority_code);

/* sql_id: v025_drop_aftercare_status_check */
-- ─── Aftercare events: quarterly queue support ────────────────────────────────
ALTER TABLE aftercare_events DROP CONSTRAINT IF EXISTS aftercare_events_status_code_check;

/* sql_id: v025_add_aftercare_status_check */
ALTER TABLE aftercare_events ADD CONSTRAINT aftercare_events_status_code_check
    CHECK (status_code IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'PENDING', 'COMPLETED', 'SKIPPED'));

/* sql_id: v025_add_aftercare_quarterly_columns */
ALTER TABLE aftercare_events
    ADD COLUMN IF NOT EXISTS quarter_code    VARCHAR(10),   -- e.g. 2025Q2
    ADD COLUMN IF NOT EXISTS due_date        DATE,
    ADD COLUMN IF NOT EXISTS completion_notes TEXT;

/* sql_id: v025_index_aftercare_quarterly */
CREATE INDEX IF NOT EXISTS idx_aftercare_quarterly
    ON aftercare_events (quarter_code, status_code, due_date);
