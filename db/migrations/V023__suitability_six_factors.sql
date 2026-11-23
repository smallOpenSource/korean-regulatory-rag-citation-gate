/* sql_id: add_customers_investor_classification */
ALTER TABLE customers
    ADD COLUMN IF NOT EXISTS investor_classification VARCHAR(20) NOT NULL DEFAULT 'GENERAL'
        CHECK (investor_classification IN ('GENERAL', 'PROFESSIONAL'));

/* sql_id: create_suitability_assessments */
CREATE TABLE IF NOT EXISTS suitability_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consultation_id UUID NOT NULL REFERENCES consultations(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    investment_objective VARCHAR(30) NOT NULL
        CHECK (investment_objective IN ('안전형', '안정형', '위험중립형', '적극투자형', '공격투자형')),
    financial_situation JSONB NOT NULL,
    investment_experience JSONB NOT NULL,
    age_bracket VARCHAR(10) NOT NULL
        CHECK (age_bracket IN ('20s', '30s', '40s', '50s', '60s', '70s+')),
    loss_tolerance_pct NUMERIC(5,2) NOT NULL
        CHECK (loss_tolerance_pct BETWEEN 0 AND 100),
    investment_horizon_months INTEGER NOT NULL
        CHECK (investment_horizon_months > 0),
    investor_classification VARCHAR(20) NOT NULL DEFAULT 'GENERAL'
        CHECK (investor_classification IN ('GENERAL', 'PROFESSIONAL')),
    form_option_orders JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_suitability_consultation */
CREATE INDEX IF NOT EXISTS idx_suitability_consultation
    ON suitability_assessments(consultation_id, created_at DESC);

/* sql_id: index_suitability_customer */
CREATE INDEX IF NOT EXISTS idx_suitability_customer
    ON suitability_assessments(customer_id, created_at DESC);

/* sql_id: create_consultation_gates */
CREATE TABLE IF NOT EXISTS consultation_gates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consultation_id UUID NOT NULL REFERENCES consultations(id),
    gate_name VARCHAR(40) NOT NULL
        CHECK (gate_name IN ('suitability', 'explanation', 'unfair_solicitation', 'marketing')),
    gate_status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (gate_status IN ('PENDING', 'PASSED', 'BLOCKED', 'ACKNOWLEDGED')),
    gate_evidence_json JSONB NOT NULL DEFAULT '{}',
    gate_acknowledged_at TIMESTAMPTZ,
    gate_acknowledged_by UUID REFERENCES employees(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (consultation_id, gate_name)
);

/* sql_id: index_consultation_gates_consultation */
CREATE INDEX IF NOT EXISTS idx_consultation_gates_consultation
    ON consultation_gates(consultation_id);

/* sql_id: seed_audit_action_codes_reg02_suitability */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('suitability_confirmed', 'REG-02 T220: suitability confirmed — all 6 factors present and grade passed'),
    ('suitability_grade_block', 'REG-02 T228: suitability blocked — customer grade < product grade'),
    ('appropriateness_warning_acknowledged', 'REG-01 T203: appropriateness warning acknowledged by actor'),
    ('explanation_confirmed', 'REG-02 T222: explanation checklist confirmed by employee'),
    ('four_gate_acknowledged', 'REG-03 T242: 4-gate compliance gate acknowledged by actor')
ON CONFLICT (action_code) DO NOTHING;
