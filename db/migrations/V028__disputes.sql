/* sql_id: create_dispute_cases_table */
CREATE TABLE IF NOT EXISTS dispute_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    consultation_id UUID REFERENCES consultations(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    opened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dispute_type VARCHAR(20) NOT NULL
        CHECK (dispute_type IN ('부당권유', '광고', '계약', '기타')),
    status VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'RESPONDED', 'RESOLVED', 'EXPIRED')),
    response_due_at TIMESTAMPTZ NOT NULL,
    responded_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ
);

/* sql_id: dispute_cases_response_due_trigger_fn */
-- response_due_at must equal opened_at + 30 days; we maintain this via a trigger because
-- (timestamptz + interval) is STABLE not IMMUTABLE and therefore cannot live in a GENERATED column.
CREATE OR REPLACE FUNCTION dispute_cases_set_response_due_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.response_due_at := NEW.opened_at + INTERVAL '30 days';
    RETURN NEW;
END;
$$;

/* sql_id: dispute_cases_response_due_trigger_drop */
DROP TRIGGER IF EXISTS trg_dispute_cases_response_due_at ON dispute_cases;

/* sql_id: dispute_cases_response_due_trigger_create */
CREATE TRIGGER trg_dispute_cases_response_due_at
BEFORE INSERT OR UPDATE OF opened_at ON dispute_cases
FOR EACH ROW EXECUTE FUNCTION dispute_cases_set_response_due_at();

/* sql_id: index_dispute_cases_customer */
CREATE INDEX IF NOT EXISTS idx_dispute_cases_customer
    ON dispute_cases(customer_id, opened_at DESC);

/* sql_id: index_dispute_cases_status */
CREATE INDEX IF NOT EXISTS idx_dispute_cases_status
    ON dispute_cases(status, response_due_at);

/* sql_id: seed_audit_action_codes_reg01_dispute_idempotent */
-- dispute_case_opened / resolved are already seeded in V022.
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('dispute_case_opened', 'REG-01 분쟁: dispute case opened'),
    ('dispute_case_resolved', 'REG-01 분쟁: dispute case resolved')
ON CONFLICT (action_code) DO NOTHING;
