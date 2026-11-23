/* sql_id: create_audit_action_codes_table */
CREATE TABLE IF NOT EXISTS audit_action_codes (
    action_code VARCHAR(80) PRIMARY KEY,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: seed_audit_action_codes */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('AI_CALL_STARTED', 'AI call started'),
    ('AI_CALL_SUCCEEDED', 'AI call succeeded'),
    ('AI_CALL_FAILED', 'AI call failed'),
    ('EMBEDDING_CALL_FAILED', 'Internal BGE embedding or rerank failed'),
    ('customer_360_view', 'Customer 360 viewed'),
    ('consultation_create', 'Consultation created'),
    ('consultation_complete', 'Consultation completed'),
    ('nba_complete', 'NBA completed'),
    ('nba_dismiss', 'NBA dismissed'),
    ('house_view_activate', 'House view activated'),
    ('email_draft_send', 'Email draft sent'),
    ('risk_assessment_create', 'Risk assessment created'),
    ('aftercare_event_resolve', 'Aftercare event resolved'),
    ('recommendation_simulation_create', 'Recommendation simulation created or approved'),
    ('recommendation_simulation_block', 'Recommendation simulation blocked by gates'),
    ('recommendation_simulation_cancel', 'Recommendation simulation cancelled'),
    ('order_simulation_create', 'Order simulation created or approved'),
    ('order_simulation_block', 'Order simulation blocked by gates'),
    ('order_simulation_execute_simulated', 'Order simulation marked simulated executed'),
    ('order_simulation_cancel', 'Order simulation cancelled')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: create_audit_logs_table */
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID REFERENCES employees(id),
    action_code VARCHAR(80) NOT NULL REFERENCES audit_action_codes(action_code),
    resource_type VARCHAR(80) NOT NULL,
    resource_id UUID,
    ip_address INET,
    user_agent TEXT,
    detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_audit_actor */
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_id, created_at DESC);

/* sql_id: index_audit_action */
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action_code, created_at DESC);

/* sql_id: create_prevent_audit_mutation_fn */
CREATE OR REPLACE FUNCTION prevent_audit_log_update_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs are append-only';
END;
$$;

/* sql_id: create_audit_no_update_trigger */
DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs;

/* sql_id: create_audit_no_update_trigger_body */
CREATE TRIGGER trg_audit_logs_no_update
BEFORE UPDATE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_update_delete();

/* sql_id: create_audit_no_delete_trigger */
DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs;

/* sql_id: create_audit_no_delete_trigger_body */
CREATE TRIGGER trg_audit_logs_no_delete
BEFORE DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_update_delete();

/* sql_id: create_email_drafts_table */
CREATE TABLE IF NOT EXISTS email_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    consultation_id UUID REFERENCES consultations(id),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    ai_generated_at TIMESTAMPTZ,
    ai_model_name VARCHAR(120),
    status_code VARCHAR(30) NOT NULL CHECK (status_code IN ('DRAFT', 'APPROVED', 'SENT', 'CANCELLED')),
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_email_drafts_customer */
CREATE INDEX IF NOT EXISTS idx_email_drafts_customer ON email_drafts(customer_id, created_at DESC);

/* sql_id: create_ai_jobs_table */
CREATE TABLE IF NOT EXISTS ai_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type_code VARCHAR(80) NOT NULL,
    status_code VARCHAR(30) NOT NULL CHECK (status_code IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    requested_by_id UUID NOT NULL REFERENCES employees(id),
    resource_type VARCHAR(80),
    resource_id UUID,
    result_resource_type VARCHAR(80),
    result_resource_id UUID,
    result_summary TEXT,
    error_code VARCHAR(80),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

/* sql_id: index_ai_jobs_requested_by */
CREATE INDEX IF NOT EXISTS idx_ai_jobs_requested_by ON ai_jobs(requested_by_id, created_at DESC);

/* sql_id: index_ai_jobs_status */
CREATE INDEX IF NOT EXISTS idx_ai_jobs_status ON ai_jobs(status_code, created_at);

/* sql_id: create_ai_outputs_table */
CREATE TABLE IF NOT EXISTS ai_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(80) NOT NULL,
    model_name VARCHAR(120) NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    resource_type VARCHAR(80) NOT NULL,
    resource_id UUID,
    job_id UUID REFERENCES ai_jobs(id),
    prompt_hash VARCHAR(128) NOT NULL,
    output_json JSONB NOT NULL,
    citations_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_ai_outputs_resource */
CREATE INDEX IF NOT EXISTS idx_ai_outputs_resource ON ai_outputs(resource_type, resource_id, generated_at DESC);
