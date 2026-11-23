/* sql_id: create_recommendation_simulations_table */
CREATE TABLE IF NOT EXISTS recommendation_simulations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    consultation_id UUID NOT NULL REFERENCES consultations(id),
    product_id UUID NOT NULL REFERENCES products(id),
    status_code VARCHAR(30) NOT NULL CHECK (status_code IN ('DRAFT', 'BLOCKED', 'APPROVED', 'CANCELLED')),
    suitability_passed BOOLEAN NOT NULL DEFAULT FALSE,
    explanation_checked BOOLEAN NOT NULL DEFAULT FALSE,
    simulated_customer_consented BOOLEAN NOT NULL DEFAULT FALSE,
    employee_final_approved BOOLEAN NOT NULL DEFAULT FALSE,
    gate_detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT recommendation_approved_gates CHECK (
        status_code <> 'APPROVED'
        OR (
            suitability_passed IS TRUE
            AND explanation_checked IS TRUE
            AND simulated_customer_consented IS TRUE
            AND employee_final_approved IS TRUE
        )
    )
);

/* sql_id: index_reco_customer_status */
CREATE INDEX IF NOT EXISTS idx_reco_customer_status ON recommendation_simulations(customer_id, status_code);

/* sql_id: index_reco_consultation */
CREATE INDEX IF NOT EXISTS idx_reco_consultation ON recommendation_simulations(consultation_id, created_at DESC);

/* sql_id: create_order_simulations_table */
CREATE TABLE IF NOT EXISTS order_simulations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_simulation_id UUID NOT NULL REFERENCES recommendation_simulations(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    product_id UUID NOT NULL REFERENCES products(id),
    side_code VARCHAR(10) NOT NULL CHECK (side_code IN ('BUY', 'SELL')),
    quantity NUMERIC(20,6) CHECK (quantity IS NULL OR quantity > 0),
    amount_krw NUMERIC(20,2) CHECK (amount_krw IS NULL OR amount_krw > 0),
    status_code VARCHAR(30) NOT NULL CHECK (status_code IN ('DRAFT', 'BLOCKED', 'APPROVED', 'SIMULATED_EXECUTED', 'CANCELLED')),
    gate_detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    simulated_executed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT order_quantity_or_amount_required CHECK (quantity IS NOT NULL OR amount_krw IS NOT NULL)
);

/* sql_id: index_order_sim_reco */
CREATE INDEX IF NOT EXISTS idx_order_sim_reco ON order_simulations(recommendation_simulation_id);

/* sql_id: index_order_sim_customer_status */
CREATE INDEX IF NOT EXISTS idx_order_sim_customer_status ON order_simulations(customer_id, status_code);
