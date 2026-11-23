/* sql_id: v030_conflict_of_interest_migration */
-- V030: Conflict of interest pre-disclosure + Chinese Wall block (T249)

/* sql_id: v030_create_conflict_disclosures_table */
CREATE TABLE IF NOT EXISTS conflict_disclosures (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id             UUID        NOT NULL REFERENCES employees(id),
    customer_id             UUID        NOT NULL REFERENCES customers(id),
    disclosure_type         VARCHAR(20) NOT NULL
        CHECK (disclosure_type IN ('PRE_TRADE', 'POST_TRADE', 'RELATED_PARTY')),
    description_redacted    TEXT,
    disclosed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    chinese_wall_violation  BOOLEAN     NOT NULL DEFAULT false,
    blocked_at              TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: v030_index_conflict_employee_customer */
CREATE INDEX IF NOT EXISTS idx_conflict_employee_customer
    ON conflict_disclosures (employee_id, customer_id, disclosed_at DESC);

/* sql_id: v030_index_conflict_wall_violations */
CREATE INDEX IF NOT EXISTS idx_conflict_wall_violations
    ON conflict_disclosures (chinese_wall_violation, blocked_at)
    WHERE chinese_wall_violation = true;

/* sql_id: v030_synthetic_conflict_seed */
-- Synthetic demo pair: employee 00000000-0000-0000-0000-000000000001
-- and customer 00000000-0000-0000-0000-000000000002 (test UUIDs).
-- Inserted only if both records exist (safe FK guard via DO block).
DO $$
DECLARE
    v_emp_id UUID := '00000000-0000-0000-0000-000000000001';
    v_cust_id UUID := '00000000-0000-0000-0000-000000000002';
BEGIN
    IF EXISTS (SELECT 1 FROM employees WHERE id = v_emp_id)
       AND EXISTS (SELECT 1 FROM customers WHERE id = v_cust_id) THEN
        INSERT INTO conflict_disclosures (
            employee_id, customer_id, disclosure_type,
            description_redacted, chinese_wall_violation, blocked_at
        ) VALUES (
            v_emp_id, v_cust_id, 'RELATED_PARTY',
            '[합성 테스트 데이터] 이해상충 사전신고 위반 — 거래 차단됨',
            true, now()
        ) ON CONFLICT DO NOTHING;
    END IF;
END $$;
