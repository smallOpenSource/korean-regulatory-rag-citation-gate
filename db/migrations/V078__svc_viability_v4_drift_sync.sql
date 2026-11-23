/* sql_id: v078_svc_viability_v4_drift_sync */
-- V078: svc-viability-v4 W2 I8 drift sync — register 4 audit action codes
-- that exist in apps/api/harness/core/audit.py::CANONICAL_AUDIT_ACTION_CODES
-- but were never INSERTed into audit_action_codes. The drift test
-- tests/test_audit_action_code_drift.py caught the reverse-drift gap.
--
-- Emit sites grep:
--   conflict_disclosed              — routers/conflict_of_interest.py:116
--   conflict_of_interest_blocked    — routers/conflict_of_interest.py:114
--   aftercare_queued                — service-layer scheduler invocation
--   house_view_archived             — T16 lifecycle archived transition
--
-- Without these rows the audit_logs INSERT would fail FK validation at
-- runtime when any of the four code paths fire.

INSERT INTO audit_action_codes (action_code, description) VALUES
    ('conflict_disclosed',
     'Conflict-of-interest declaration recorded (no Chinese-wall violation)'),
    ('conflict_of_interest_blocked',
     'Conflict-of-interest declaration blocked due to Chinese-wall violation'),
    ('aftercare_queued',
     'Aftercare event scheduled for follow-up (queued state)'),
    ('house_view_archived',
     'House view transitioned to ARCHIVED in T16 lifecycle')
ON CONFLICT (action_code) DO NOTHING;
