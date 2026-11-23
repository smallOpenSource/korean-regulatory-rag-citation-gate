/* sql_id: v044_audit_action_codes_aftercare_quarterly */
-- V044 — register audit_action_codes for aftercare quarterly lifecycle
--          (UltraQA cycle 5 S22 fix, 2026-05-19)
--
-- routers/nba.py emits two audit action_codes when PB/WM closes a
-- quarterly aftercare task:
--   aftercare_completed   (POST /aftercare-events/{id}/complete)
--   aftercare_skipped     (POST /aftercare-events/{id}/skip)
--
-- Both were missing from audit_action_codes — every emit raised
-- ForeignKeyViolationError audit_logs_action_code_fkey and the endpoints
-- returned HTTP 500, identical pattern to cycle 3 R34/V041 (nba_card_*
-- codes). This migration registers the two codes idempotently so a re-run
-- is safe.

/* sql_id: insert_audit_action_code_aftercare_completed */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('aftercare_completed', '사후관리 분기 완료')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: insert_audit_action_code_aftercare_skipped */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('aftercare_skipped', '사후관리 분기 보류')
ON CONFLICT (action_code) DO NOTHING;
