/* sql_id: v075_disputes_actor_tracking */
-- V075: svc-viability-v4 I3 — add nullable responded_by_actor_id +
-- resolved_by_actor_id to dispute_cases so same-actor emit can compare
-- the current actor against the previous responder/resolver on the row.
--
-- Design: pure additive nullable (ADR-017 Option-A, Input-8 (a)). Router
-- responsibility — UPDATE_DISPUTE_STATUS_SQL accepts the actor as a $3::uuid
-- bind parameter on the RESPONDED branch and $4::uuid on the RESOLVED branch.
-- SQL-side COALESCE intentionally absent.
--
-- Scope: RESPONDED + RESOLVED only.
-- EXPIRED transition is APScheduler-driven (actor=NULL) and is gated by
-- services/disputes.py:31 ("No scheduler is wired in Wave 2"). EXPIRED
-- same-actor handling is deferred to F-V5-8 (Stage 7 RUN-09 wiring).
--
-- Pre-V075 schema: V028__disputes.sql:1-15 (no resolver columns).

ALTER TABLE dispute_cases
    ADD COLUMN IF NOT EXISTS responded_by_actor_id UUID
        REFERENCES employees(id)
        DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS resolved_by_actor_id UUID
        REFERENCES employees(id)
        DEFAULT NULL;
