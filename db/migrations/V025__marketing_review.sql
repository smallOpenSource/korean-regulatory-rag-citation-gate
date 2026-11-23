/* sql_id: marketing_review_v1 */
-- Create marketing_reviews table and link to email_drafts per T224/T247 gate.
-- Idempotent: CREATE TABLE IF NOT EXISTS + IF NOT EXISTS column guards.

/* sql_id: create_marketing_reviews_table */
CREATE TABLE IF NOT EXISTS marketing_reviews (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_draft_id          UUID NOT NULL REFERENCES email_drafts(id),
    classification          VARCHAR(20) NOT NULL CHECK (classification IN ('MARKETING', 'OPERATIONAL')),
    leading_block_text      TEXT,
    static_rule_pass        BOOLEAN NOT NULL DEFAULT false,
    ai_compliance_pass      BOOLEAN,
    ai_reasoning_redacted   TEXT,
    decision                VARCHAR(30) NOT NULL
                            CHECK (decision IN ('MARKETING_REVIEW_PASS', 'MARKETING_REVIEW_BLOCK')),
    reviewed_by             UUID REFERENCES employees(id),
    reviewed_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_marketing_reviews_draft */
CREATE INDEX IF NOT EXISTS idx_marketing_reviews_draft
    ON marketing_reviews(email_draft_id, created_at DESC);

/* sql_id: seed_audit_action_codes_marketing_review_blocked */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('marketing_review_blocked', 'REG-02 marketing: marketing copy blocked by static or AI rule')
ON CONFLICT (action_code) DO NOTHING;
