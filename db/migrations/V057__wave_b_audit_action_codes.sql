/* sql_id: v057_wave_b_audit_action_codes */
-- V057: Wave-Audit-Defect-Fix B7 / B9 / B10 / B12-followup — register canonical
-- audit_action_codes for the remaining Wave B audit gaps:
--
--   B7  ai_job_get                 — /ai-jobs/{id} GET (sensitive read trail)
--   B7  ai_output_get              — /ai-outputs/{id} GET
--   B9  citation_gate_failed       — rag/query no-citation block (was AI_CALL_FAILED)
--   B9  provider_failure           — Azure-side AI provider failure (generative path)
--   B10 consultation_status_changed — non-COMPLETED PATCH status transitions
--   B12 nba_ws_broadcast_failed    — WS broadcast failure (paired with logger.warning)
--
-- additive-only per [[on-conflict-id-for-mutable-content]] — V054 in-place 금지.
-- OQ-5 C2 kyc_edd codes will land in V058+ when Wave C executes.
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('ai_job_get',                 'REG-05 — /ai-jobs/{id} GET 민감 read'),
    ('ai_output_get',              'REG-05 — /ai-outputs/{id} GET 민감 read'),
    ('citation_gate_failed',       'REG-04 — RAG citation gate 차단 (no-citation)'),
    ('provider_failure',           'REG-04 — Azure AI provider 호출 실패'),
    ('consultation_status_changed','REG-02 — consultation 비-COMPLETED 상태 전이'),
    ('nba_ws_broadcast_failed',    'REG-03 — NBA WS broadcast 실패 (logger.warning 보조)')
ON CONFLICT (action_code) DO NOTHING;
