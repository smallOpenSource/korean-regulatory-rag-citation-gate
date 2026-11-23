/* sql_id: v076_extend_consultation_status_check_pending_approval */
-- V076: svc-viability-v4 I4 — extend consultations.status_code domain with
-- PENDING_APPROVAL so the 4-eye preventive gate (ADR-019) has a stable
-- intermediate state between SAVED and COMPLETED.
--
-- Pre-V076 domain (V062 applied):
--   {DRAFT, SAVED, COMPLETED, CANCELLED, REJECTED, DISMISSED, EXPIRED} (7 codes)
-- V076 adds PENDING_APPROVAL → 8 codes.
--
-- Strictly broader extension — every existing row remains valid.
-- Mirror of V062 ALTER pattern (DROP IF EXISTS + ADD).
--
-- IMPORTANT: target constraint is consultations_status_code_check only.
-- The anonymous CHECK consultations_complete_checks (V005:15-17,
-- "status_code <> 'COMPLETED' OR (suitability_checked IS TRUE AND
-- explanation_checked IS TRUE)") is NOT touched and must remain intact
-- after this migration. Post-apply verification:
--   psql -c "\d+ consultations" | grep consultations_complete_checks

ALTER TABLE consultations
    DROP CONSTRAINT IF EXISTS consultations_status_code_check;

/* sql_id: v076_add_extended_consultation_status_check */
ALTER TABLE consultations
    ADD CONSTRAINT consultations_status_code_check
    CHECK (status_code IN (
        'DRAFT', 'SAVED', 'PENDING_APPROVAL', 'COMPLETED',
        'CANCELLED', 'REJECTED', 'DISMISSED', 'EXPIRED'
    ));

/* sql_id: v076_consultation_submitted_for_approval_action_code */
INSERT INTO audit_action_codes (action_code, description)
VALUES (
    'consultation_submitted_for_approval',
    'Consultation transitioned to PENDING_APPROVAL state (DRAFT|SAVED → PENDING_APPROVAL) — 4-eye gate entered'
)
ON CONFLICT (action_code) DO NOTHING;
