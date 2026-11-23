/* sql_id: v039_seed_prohibited_phrase_audit */
-- T201 (REG-01 §5 자본시장법 §55): prohibited_phrase post-processing guard audit code.
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('prohibited_phrase_blocked',
     'AI output or outbound email blocked for matching 자본시장법 §55 prohibited phrase '
     '(손실보전·이익보장·확정수익 등).')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: v039_add_ai_outputs_employee_final_approval */
-- T231 (REG-02 §5 보조수단성): every AI output requires explicit employee final approval
-- before customer-facing delivery. The column defaults FALSE so unmarked rows behave as
-- "draft / review-only" — badge text on the frontend keys off this column.
ALTER TABLE ai_outputs
    ADD COLUMN IF NOT EXISTS employee_final_approval BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS employee_final_approval_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS employee_final_approval_by UUID REFERENCES employees(id);

/* sql_id: v039_seed_employee_final_approval_audit */
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('ai_output_final_approved',
     'AI output (any of 7 agents) marked employee_final_approval=true before customer delivery '
     '(REG-02 §5 보조수단성).'),
    ('ai_output_final_approval_revoked',
     'AI output employee_final_approval reverted to false (e.g. after detected issue or recall).')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: v039_index_ai_outputs_pending_review */
CREATE INDEX IF NOT EXISTS idx_ai_outputs_pending_review
    ON ai_outputs (agent_id, generated_at DESC)
    WHERE employee_final_approval = FALSE;
