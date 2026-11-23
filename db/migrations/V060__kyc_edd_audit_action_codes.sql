/* sql_id: v060_kyc_edd_audit_action_codes */
-- V060: Wave-Audit-Defect-Fix C2 — register canonical audit_action_codes for
-- the four kyc_edd lifecycle events that previously had no distinct entry:
--
--   kyc_edd_completed             — /triggers/{id}/complete endpoint emit
--                                   (was misclassified as kyc_edd_reassessed
--                                   at routers/kyc_edd.py:184)
--   kyc_edd_trigger_listed        — GET /kyc-edd/triggers list view audit
--   kyc_edd_trigger_detail_viewed — GET /kyc-edd/triggers/{id} detail view audit
--   kyc_edd_evaluated             — POST /kyc-edd/triggers initial evaluation
--                                   (paired with the existing kyc_edd_triggered
--                                   to keep legacy code working)
--
-- Resolves OQ-1 (kyc_edd_completed canonical needed) + OQ-5 (3 trigger
-- lifecycle codes pending). additive-only per
-- [[on-conflict-id-for-mutable-content]] — V054 in-place 금지.
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('kyc_edd_completed',             'KYC/EDD trigger 종결 (C2 split — was kyc_edd_reassessed)'),
    ('kyc_edd_trigger_listed',        'KYC/EDD triggers list 조회 audit (C2)'),
    ('kyc_edd_trigger_detail_viewed', 'KYC/EDD trigger 상세 조회 audit (C2)'),
    ('kyc_edd_evaluated',             'KYC/EDD trigger 평가 — POST /kyc-edd/triggers (C2)')
ON CONFLICT (action_code) DO NOTHING;
