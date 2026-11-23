/* sql_id: v041_audit_action_codes_nba_card */
-- V041 — audit_action_codes nba_card_* registration (Wave 6.5 R34 ForeignKeyViolation fix)
--
-- routers/nba.py emits four audit action codes when PB/WM interacts with NBA cards:
--   nba_card_created      (created via POST /nba-cards/)
--   nba_card_acknowledged (POST /nba-cards/{id}/acknowledge)
--   nba_card_completed    (POST /nba-cards/{id}/complete)
--   nba_card_dismissed    (POST /nba-cards/{id}/dismiss)
--
-- OBS-02_audit_action_codes.md already documents all four codes (NBA 카드 생성 /
-- 확인 / 기각 / 완료), but the DB never had the matching audit_action_codes
-- rows. Every emit hit audit_logs.action_code FK and raised
-- ForeignKeyViolationError, returning HTTP 500 on the four endpoints —
-- 30 of these were captured in the harness-api.log analysis that closed
-- R34 in commit 898713e.
--
-- This migration registers the four codes idempotently so a re-run is safe.

/* sql_id: insert_audit_action_code_nba_card_created */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('nba_card_created', 'NBA 카드 생성')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: insert_audit_action_code_nba_card_acknowledged */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('nba_card_acknowledged', 'NBA 카드 확인')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: insert_audit_action_code_nba_card_completed */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('nba_card_completed', 'NBA 카드 완료')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: insert_audit_action_code_nba_card_dismissed */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('nba_card_dismissed', 'NBA 카드 기각')
ON CONFLICT (action_code) DO NOTHING;
