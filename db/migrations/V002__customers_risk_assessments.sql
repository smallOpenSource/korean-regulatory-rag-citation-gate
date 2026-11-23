/* sql_id: create_customers_table */
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_no VARCHAR(40) NOT NULL UNIQUE,
    assigned_pb_id UUID NOT NULL REFERENCES employees(id),
    branch_id UUID NOT NULL REFERENCES branches(id),
    risk_grade_code VARCHAR(1) NOT NULL CHECK (risk_grade_code IN ('1', '2', '3', '4', '5')),
    segment_code VARCHAR(30) NOT NULL CHECK (segment_code IN ('HNWI_CORE', 'HNWI_ULTRA', 'EMERGING_HNWI')),
    total_assets_krw NUMERIC(20,2) NOT NULL CHECK (total_assets_krw >= 0),
    last_contacted_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_customers_assigned_pb */
CREATE INDEX IF NOT EXISTS idx_customers_assigned_pb ON customers(assigned_pb_id);

/* sql_id: index_customers_branch */
CREATE INDEX IF NOT EXISTS idx_customers_branch ON customers(branch_id);

/* sql_id: index_customers_risk_segment */
CREATE INDEX IF NOT EXISTS idx_customers_risk_segment ON customers(risk_grade_code, segment_code);

/* sql_id: create_risk_assessments_table */
CREATE TABLE IF NOT EXISTS risk_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    risk_grade_code VARCHAR(1) NOT NULL CHECK (risk_grade_code IN ('1', '2', '3', '4', '5')),
    surveyed_at TIMESTAMPTZ NOT NULL,
    surveyed_by_id UUID NOT NULL REFERENCES employees(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_risk_assessments_customer */
CREATE INDEX IF NOT EXISTS idx_risk_assessments_customer ON risk_assessments(customer_id, surveyed_at DESC);
