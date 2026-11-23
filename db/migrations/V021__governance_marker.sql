/* sql_id: add_governance_marker_column */
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS governance_marker TEXT;

/* sql_id: drop_governance_marker_check */
ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS chk_governance_marker_values;

/* sql_id: add_governance_marker_check */
ALTER TABLE audit_logs ADD CONSTRAINT chk_governance_marker_values
CHECK (governance_marker IS NULL OR governance_marker IN ('PoC_AUTO_APPROVAL', 'HUMAN_REVIEW', 'AUTO_SYSTEM'));

/* sql_id: create_governance_marker_index */
CREATE INDEX IF NOT EXISTS idx_audit_governance_marker
ON audit_logs(governance_marker, created_at DESC)
WHERE governance_marker IS NOT NULL;
