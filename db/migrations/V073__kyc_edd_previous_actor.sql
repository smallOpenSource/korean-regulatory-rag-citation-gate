/* sql_id: v073_kyc_edd_previous_actor */
-- V073: svc-viability-v4 I1 — add nullable previous_actor_id to kyc_edd_triggers
-- so the same-actor invariant emit (same_actor_mutation_blocked) can compare
-- the current reassessor against the prior actor recorded on the row.
--
-- Design: pure additive nullable (ADR-017 Option-A, Input-8 (a)).
--   - SQL-side COALESCE intentionally absent. The router is responsible for
--     passing `existing["reassessor_employee_id"]` as the $3::uuid bind value
--     on every REASSESS/COMPLETE call.
--   - Legacy rows where the column is NULL are correctly skipped by the
--     same_actor() predicate (any None operand → False).
--
-- Pre-V073 schema: V029__kyc_edd.sql:5-19 (reassessor_employee_id NULLABLE,
-- set only on COMPLETE).
--
-- Backward compatibility: every existing row remains valid because the
-- ADD COLUMN ... DEFAULT NULL is a non-blocking metadata-only ALTER.

ALTER TABLE kyc_edd_triggers
    ADD COLUMN IF NOT EXISTS previous_actor_id UUID
        REFERENCES employees(id)
        DEFAULT NULL;
