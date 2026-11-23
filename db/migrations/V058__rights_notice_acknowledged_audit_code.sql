/* sql_id: v058_rights_notice_acknowledged_audit_code */
-- V058: Wave-Audit-Defect-Fix C6 — register canonical action_code for
-- ``rights_notice_acknowledged``. The RightsNoticePage previously called a
-- stub (no real POST), so PB acknowledgement of the four-rights notice left
-- no audit trail; only the issuance side (``rights_notice_issued``, V022)
-- was canonical.
--
-- additive-only per [[on-conflict-id-for-mutable-content]] (V054 in-place 금지).
-- OQ-1 + OQ-5 (4 kyc_edd codes) reserved for V059 when Wave C C2 lands.
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('rights_notice_acknowledged', 'REG-01 — 권리고지 PB 확인 (C6 RightsNoticePage POST wiring)')
ON CONFLICT (action_code) DO NOTHING;
