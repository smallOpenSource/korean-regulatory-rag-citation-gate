/* sql_id: create_gate_evidence_table */
CREATE TABLE IF NOT EXISTS gate_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    consultation_id UUID NOT NULL REFERENCES consultations(id),
    gate_kind TEXT NOT NULL,
    gate_status TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_hash TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    governance_marker TEXT NOT NULL DEFAULT 'HUMAN_REVIEW'
);

/* sql_id: drop_gate_evidence_kind_check */
ALTER TABLE gate_evidence DROP CONSTRAINT IF EXISTS chk_gate_evidence_kind;

/* sql_id: add_gate_evidence_kind_check */
ALTER TABLE gate_evidence ADD CONSTRAINT chk_gate_evidence_kind
CHECK (gate_kind IN ('SUITABILITY', 'APPROPRIATENESS', 'EXPLANATION', 'UNFAIR_SOLICITATION', 'MARKETING_REVIEW'));

/* sql_id: drop_gate_evidence_status_check */
ALTER TABLE gate_evidence DROP CONSTRAINT IF EXISTS chk_gate_evidence_status;

/* sql_id: add_gate_evidence_status_check */
ALTER TABLE gate_evidence ADD CONSTRAINT chk_gate_evidence_status
CHECK (gate_status IN ('PASS', 'BLOCK', 'PENDING'));

/* sql_id: drop_gate_evidence_governance_check */
ALTER TABLE gate_evidence DROP CONSTRAINT IF EXISTS chk_gate_evidence_governance_marker;

/* sql_id: add_gate_evidence_governance_check */
ALTER TABLE gate_evidence ADD CONSTRAINT chk_gate_evidence_governance_marker
CHECK (governance_marker IN ('PoC_AUTO_APPROVAL', 'HUMAN_REVIEW', 'AUTO_SYSTEM'));

/* sql_id: index_gate_evidence_consultation */
CREATE INDEX IF NOT EXISTS idx_gate_evidence_consultation
    ON gate_evidence(consultation_id, recorded_at DESC);

/* sql_id: index_gate_evidence_governance_marker */
CREATE INDEX IF NOT EXISTS idx_gate_evidence_governance_marker
    ON gate_evidence(governance_marker, recorded_at DESC)
    WHERE governance_marker = 'PoC_AUTO_APPROVAL';

/* sql_id: index_gate_evidence_kind_status */
CREATE INDEX IF NOT EXISTS idx_gate_evidence_kind_status
    ON gate_evidence(gate_kind, gate_status, recorded_at DESC);

/* sql_id: create_is_valid_gate_evidence_fn */
CREATE OR REPLACE FUNCTION is_valid_gate_evidence(p_kind TEXT, p_evidence JSONB)
RETURNS BOOLEAN
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    required_keys TEXT[];
    missing_key TEXT;
BEGIN
    IF p_evidence IS NULL OR jsonb_typeof(p_evidence) <> 'object' THEN
        RETURN FALSE;
    END IF;
    IF p_kind = 'SUITABILITY' THEN
        required_keys := ARRAY[
            'investor_classification',
            'six_factors_completeness',
            'grade_delta',
            'customer_grade',
            'product_grade'
        ];
    ELSIF p_kind = 'APPROPRIATENESS' THEN
        required_keys := ARRAY[
            'product_complexity',
            'customer_experience_years',
            'derivatives_eligibility',
            'appropriateness_outcome'
        ];
    ELSIF p_kind = 'EXPLANATION' THEN
        required_keys := ARRAY[
            'doc_versions',
            'ack_at',
            'leading_block_state',
            'explanation_outcome'
        ];
    ELSIF p_kind = 'UNFAIR_SOLICITATION' THEN
        required_keys := ARRAY[
            'pattern_codes',
            'matched_pattern_count',
            'solicitation_outcome'
        ];
    ELSIF p_kind = 'MARKETING_REVIEW' THEN
        required_keys := ARRAY[
            'submission_id',
            'reviewer_role',
            'review_outcome',
            'reviewed_at'
        ];
    ELSE
        RETURN FALSE;
    END IF;
    FOREACH missing_key IN ARRAY required_keys LOOP
        IF NOT (p_evidence ? missing_key) THEN
            RETURN FALSE;
        END IF;
    END LOOP;
    RETURN TRUE;
END;
$$;

/* sql_id: create_enforce_gate_evidence_schema_fn */
CREATE OR REPLACE FUNCTION enforce_gate_evidence_schema()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.evidence_hash IS NULL OR LENGTH(NEW.evidence_hash) < 16 THEN
        RAISE EXCEPTION 'gate_evidence.evidence_hash must be set (>=16 chars)';
    END IF;
    IF NOT is_valid_gate_evidence(NEW.gate_kind, NEW.evidence) THEN
        RAISE EXCEPTION 'gate_evidence schema invalid for gate_kind=% (required keys missing)', NEW.gate_kind;
    END IF;
    IF NEW.governance_marker IS NULL THEN
        NEW.governance_marker := 'HUMAN_REVIEW';
    END IF;
    RETURN NEW;
END;
$$;

/* sql_id: drop_gate_evidence_schema_trigger */
DROP TRIGGER IF EXISTS trg_gate_evidence_schema ON gate_evidence;

/* sql_id: create_gate_evidence_schema_trigger */
CREATE TRIGGER trg_gate_evidence_schema
BEFORE INSERT ON gate_evidence
FOR EACH ROW EXECUTE FUNCTION enforce_gate_evidence_schema();

/* sql_id: create_prevent_gate_evidence_mutation_fn */
CREATE OR REPLACE FUNCTION prevent_gate_evidence_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'gate_evidence is append-only (PoC governance invariant)';
END;
$$;

/* sql_id: drop_gate_evidence_no_update_trigger */
DROP TRIGGER IF EXISTS trg_gate_evidence_no_update ON gate_evidence;

/* sql_id: create_gate_evidence_no_update_trigger */
CREATE TRIGGER trg_gate_evidence_no_update
BEFORE UPDATE ON gate_evidence
FOR EACH ROW EXECUTE FUNCTION prevent_gate_evidence_mutation();

/* sql_id: drop_gate_evidence_no_delete_trigger */
DROP TRIGGER IF EXISTS trg_gate_evidence_no_delete ON gate_evidence;

/* sql_id: create_gate_evidence_no_delete_trigger */
CREATE TRIGGER trg_gate_evidence_no_delete
BEFORE DELETE ON gate_evidence
FOR EACH ROW EXECUTE FUNCTION prevent_gate_evidence_mutation();

/* sql_id: seed_audit_action_codes_v031_poc_governance */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('poc_auto_approval_rate_limited', 'REG-06 governance: per-employee PoC_AUTO_APPROVAL rate ceiling breached (V031)'),
    ('demo_mode_expiring_soon', 'REG-06 governance: 5-minute pre-expiry WS warning broadcast (V031, ADR-004 T312)'),
    ('demo_mode_expired', 'REG-06 governance: 8h ceiling reached, demo_mode auto-toggled off (V031)'),
    ('gate_evidence_recorded', 'REG-06 governance: gate_evidence row appended (V031 schema validated)')
ON CONFLICT (action_code) DO NOTHING;
