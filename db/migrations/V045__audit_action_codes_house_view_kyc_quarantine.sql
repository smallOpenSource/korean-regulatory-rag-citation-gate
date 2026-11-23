/* sql_id: v045_audit_action_codes_house_view_kyc_quarantine */
-- V045 — register missing audit_action_codes for HouseView lifecycle, KYC EDD,
--          quarantine release, and AI token rate-limit telemetry
--          (UltraQA cycle 5 S24 fix, 2026-05-19)
--
-- Routers/services emit these action_codes but they were not registered in
-- audit_action_codes — every emit would raise ForeignKeyViolationError
-- (audit_logs_action_code_fkey) and force the caller to fail. This is the
-- same FK-gap pattern that cycle 3 R34/V041 (nba_card_*) and cycle 5
-- V044 (aftercare_completed/skipped) fixed for other code families.
--
-- All seven inserts are idempotent (ON CONFLICT DO NOTHING).

/* sql_id: insert_audit_action_code_house_view_generated */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('house_view_generated', '하우스뷰 생성 (AI)')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: insert_audit_action_code_house_view_reviewed */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('house_view_reviewed', '하우스뷰 검토 완료')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: insert_audit_action_code_house_view_activated */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('house_view_activated', '하우스뷰 활성화')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: insert_audit_action_code_kyc_edd_triggered */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('kyc_edd_triggered', 'KYC EDD 트리거 생성')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: insert_audit_action_code_kyc_edd_reassessed */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('kyc_edd_reassessed', 'KYC EDD 재평가')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: insert_audit_action_code_quarantine_released */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('quarantine_released', '격리 청크 해제')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: insert_audit_action_code_ai_token_rate_limited */
INSERT INTO audit_action_codes (action_code, description)
VALUES ('ai_token_rate_limited', 'AI 토큰 사용량 한도 초과')
ON CONFLICT (action_code) DO NOTHING;
