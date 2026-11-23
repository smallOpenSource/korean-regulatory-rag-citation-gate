/* sql_id: drop_old_status_check */
-- Extend email_drafts with full state machine columns per ADR-002 Wave 1 patch.
-- Idempotent: all ALTER TABLE use IF NOT EXISTS / IF EXISTS guards.
ALTER TABLE email_drafts DROP CONSTRAINT IF EXISTS email_drafts_status_code_check;

/* sql_id: add_new_status_check */
ALTER TABLE email_drafts ADD CONSTRAINT email_drafts_status_code_check
    CHECK (status_code IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'SENT', 'FAILED', 'CANCELLED'));

/* sql_id: add_submitted_at */
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;

/* sql_id: add_approved_at */
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

/* sql_id: add_approved_by_id */
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS approved_by_id UUID REFERENCES employees(id);

/* sql_id: add_transport_message_id */
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS transport_message_id TEXT;

/* sql_id: add_failure_reason_code */
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS failure_reason_code VARCHAR(60)
    CHECK (failure_reason_code IS NULL OR failure_reason_code IN (
        'transport_disallowed', 'transport_unreachable', 'recipient_not_synthetic',
        'recipient_rate_limited', 'redaction_blocked', 'marketing_lint_failed',
        'provider_5xx', 'provider_timeout', 'internal_error'
    ));

/* sql_id: add_marketing_classified */
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS marketing_classified BOOLEAN NOT NULL DEFAULT false;

/* sql_id: add_pre_review_number */
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS "사전심의필번호" TEXT;

/* sql_id: add_marketing_review_id_stub */
-- FK to marketing_reviews added in V025 after that table is created
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS marketing_review_id UUID;

/* sql_id: drop_marketing_review_fk_idempotent */
-- FK to marketing_reviews is safe here: marketing_reviews created in V025 (runs before V034)
ALTER TABLE email_drafts
    DROP CONSTRAINT IF EXISTS email_drafts_marketing_review_id_fkey;

/* sql_id: add_marketing_review_fk */
ALTER TABLE email_drafts
    ADD CONSTRAINT email_drafts_marketing_review_id_fkey
    FOREIGN KEY (marketing_review_id) REFERENCES marketing_reviews(id);

/* sql_id: seed_audit_action_codes_email_state_machine */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('email_drafted',           'Email draft created with status DRAFT'),
    ('email_draft_submitted',   'Email draft submitted for approval (PENDING_APPROVAL)'),
    ('email_draft_approved',    'Email draft approved by reviewer (APPROVED)'),
    ('email_draft_rejected',    'Email draft rejected; status reverted to DRAFT'),
    ('email_sent_via_sandbox',  'Email sent via Mailpit sandbox transport (SENT)'),
    ('email_send_failed',       'Email sandbox send failed; status set to FAILED'),
    ('email_send_blocked',      'Email send blocked by precondition gate (lint/PII/transport)')
ON CONFLICT (action_code) DO NOTHING;
