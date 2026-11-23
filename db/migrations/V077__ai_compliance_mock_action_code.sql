/* sql_id: v077_ai_compliance_mock_action_code */
-- V077: svc-viability-v4 I7 — register ai_compliance_mock_used audit action
-- code (ADR-019.1 sidecar). Emitted at most once per process when
-- AI_COMPLIANCE_MODE != 'live'; production startup safety in main.py
-- prevents the non-live mode from running in production at all.
--
-- Schema change: zero. INSERT only. No ALTER TABLE.
--
-- Cardinality contract enforced in services/marketing/core.py via the
-- module-level _MOCK_EMIT_STATE singleton:
--   first non-live invocation per process → 1 audit row + WARNING log
--   subsequent N invocations → 0 additional rows

INSERT INTO audit_action_codes (action_code, description)
VALUES (
    'ai_compliance_mock_used',
    'AI_COMPLIANCE_MODE is non-live (mock_pass|mock_fail) for the current process — singleton emit per process startup'
)
ON CONFLICT (action_code) DO NOTHING;
