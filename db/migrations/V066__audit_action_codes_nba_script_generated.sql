/* sql_id: v066_insert_audit_action_code_nba_script_generated */
-- V066: W2-2 (2026-05-24) — register the canonical action_code
-- `nba_script_generated` so the new synchronous endpoint
-- POST /nba-cards/{id}/generate-script can land its audit row.
--
-- The code was added to apps/api/harness/core/audit.py CANONICAL and
-- documented in docs/observability/OBS-02_audit_action_codes.md in the
-- same commit, but the audit_logs.action_code FK to audit_action_codes
-- still rejects the INSERT until the seed row exists. The first live
-- smoke test surfaced ForeignKeyViolationError.
--
-- Additive only per [[pattern-id-additive-not-rename]] — no existing
-- code is modified.
INSERT INTO audit_action_codes (action_code, description)
VALUES (
    'nba_script_generated',
    'NBA conversational script가 Azure GPT 호출로 동기 생성됨 (W2 신설)'
)
ON CONFLICT (action_code) DO NOTHING;
