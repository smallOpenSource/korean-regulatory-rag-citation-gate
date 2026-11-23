/* sql_id: create_rights_notices_table */
CREATE TABLE IF NOT EXISTS rights_notices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consultation_id UUID NOT NULL REFERENCES consultations(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    notice_kinds JSONB NOT NULL DEFAULT '[]',
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    audit_chain_hash VARCHAR(128)
);

/* sql_id: index_rights_notices_consultation */
CREATE INDEX IF NOT EXISTS idx_rights_notices_consultation
    ON rights_notices(consultation_id);

/* sql_id: index_rights_notices_customer */
CREATE INDEX IF NOT EXISTS idx_rights_notices_customer
    ON rights_notices(customer_id, issued_at DESC);

/* sql_id: seed_audit_action_codes_reg01_rights */
-- rights_notice_issued is already seeded in V022; this migration is idempotent.
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('rights_notice_issued', 'REG-01 권리고지: investor rights notice issued at consultation end')
ON CONFLICT (action_code) DO NOTHING;
