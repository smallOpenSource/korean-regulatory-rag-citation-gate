/* sql_id: v059_dispute_responded_audit_code */
-- V059: Wave-Audit-Defect-Fix C7 — register canonical action_code for
-- ``dispute_responded``. ``dispute_case_opened`` (V022) and
-- ``dispute_case_resolved`` (V022) were already canonical, but the
-- intermediate OPEN→RESPONDED transition (PATCH /disputes/{id} status=RESPONDED)
-- emitted no audit row, leaving a gap in the dispute lifecycle audit trail.
--
-- additive-only per [[on-conflict-id-for-mutable-content]] — V054 in-place 금지
-- (the plan §6 C7 row mentions V054 historically but the rule forbids it).
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('dispute_responded', 'REG-01 — 분쟁 사건 응답 단계 전이 (OPEN→RESPONDED, C7)')
ON CONFLICT (action_code) DO NOTHING;
