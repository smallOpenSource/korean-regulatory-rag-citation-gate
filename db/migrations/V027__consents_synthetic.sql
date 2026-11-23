/* sql_id: v027_create_customer_consents */
CREATE TABLE IF NOT EXISTS customer_consents (
    id                    UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id           UUID        NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    consent_type          TEXT        NOT NULL CHECK (consent_type IN (
                              'GENERAL_BUNDLE',
                              'INFORMATION_USE',
                              'MARKETING_CONTACT',
                              'DATA_SHARING_THIRD_PARTY'
                          )),
    consent_scope         JSONB       NOT NULL DEFAULT '{}',
    granted_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    withdrawn_at          TIMESTAMPTZ NULL,
    granted_by_employee_id UUID       NOT NULL,
    synthetic             BOOL        NOT NULL DEFAULT true
);

/* sql_id: v027_customer_consents_synthetic_check */
ALTER TABLE customer_consents
    DROP CONSTRAINT IF EXISTS customer_consents_synthetic_must_be_true;

/* sql_id: v027_add_synthetic_constraint */
ALTER TABLE customer_consents
    ADD CONSTRAINT customer_consents_synthetic_must_be_true
    CHECK (synthetic = true);

/* sql_id: v027_create_info_access_requests */
CREATE TABLE IF NOT EXISTS info_access_requests (
    id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id               UUID        NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    request_type              TEXT        NOT NULL CHECK (request_type IN ('ACCESS', 'CORRECTION')),
    requested_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at              TIMESTAMPTZ NULL,
    response_summary_redacted TEXT        NULL,
    employee_id               UUID        NOT NULL
);

/* sql_id: v027_comment_customer_consents */
COMMENT ON TABLE customer_consents IS
    'REG-01 신용정보법 §32/§33/§37 synthetic consent records. synthetic=true enforced; PoC only.';

/* sql_id: v027_comment_info_access_requests */
COMMENT ON TABLE info_access_requests IS
    'REG-01 신용정보법 §38 열람·정정 request log. Audit chain via employee_id → audit_logs.';

/* sql_id: v027_seed_consent_action_codes */
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('consent_recorded',            'REG-01 신용정보법 §32: synthetic consent recorded'),
    ('consent_withdrawn',           'REG-01 신용정보법 §37: consent withdrawn'),
    ('marketing_consent_withdrawn', 'REG-01 신용정보법 §37: MARKETING_CONTACT consent withdrawn / 연락중지'),
    ('info_access_requested',       'REG-01 신용정보법 §38: info access or correction request created'),
    ('info_access_responded',       'REG-01 신용정보법 §38: info access or correction request responded'),
    ('general_bundle_consent',      'REG-01 신용정보법 §32 일괄동의: general bundle consent recorded')
ON CONFLICT (action_code) DO NOTHING;
