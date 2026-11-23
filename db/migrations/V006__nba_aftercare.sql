/* sql_id: create_nba_actions_table */
CREATE TABLE IF NOT EXISTS nba_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    action_type_code VARCHAR(60) NOT NULL,
    priority_code VARCHAR(30) NOT NULL CHECK (priority_code IN ('URGENT', 'HIGH', 'MEDIUM', 'LOW')),
    status_code VARCHAR(30) NOT NULL CHECK (status_code IN ('PENDING', 'IN_PROGRESS', 'DONE', 'SNOOZED', 'DISMISSED')),
    trigger_code VARCHAR(60) NOT NULL,
    script_text TEXT,
    script_generated_at TIMESTAMPTZ,
    script_model_name VARCHAR(120),
    due_date DATE,
    snoozed_until TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_nba_employee_status */
CREATE INDEX IF NOT EXISTS idx_nba_employee_status ON nba_actions(employee_id, status_code);

/* sql_id: index_nba_customer */
CREATE INDEX IF NOT EXISTS idx_nba_customer ON nba_actions(customer_id);

/* sql_id: index_nba_priority_due */
CREATE INDEX IF NOT EXISTS idx_nba_priority_due ON nba_actions(priority_code, due_date);

/* sql_id: create_aftercare_events_table */
CREATE TABLE IF NOT EXISTS aftercare_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    product_id UUID REFERENCES products(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    event_type_code VARCHAR(60) NOT NULL CHECK (event_type_code IN ('MATURITY_DUE', 'KI_TRIGGERED', 'DRAWDOWN_BREACH', 'REVIEW_DUE', 'NO_CONTACT')),
    event_date DATE NOT NULL,
    status_code VARCHAR(30) NOT NULL CHECK (status_code IN ('OPEN', 'IN_PROGRESS', 'RESOLVED')),
    notes TEXT,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_aftercare_customer_status */
CREATE INDEX IF NOT EXISTS idx_aftercare_customer_status ON aftercare_events(customer_id, status_code);

/* sql_id: index_aftercare_employee_status */
CREATE INDEX IF NOT EXISTS idx_aftercare_employee_status ON aftercare_events(employee_id, status_code);
