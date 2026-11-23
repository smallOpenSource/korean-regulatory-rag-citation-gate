/* sql_id: order_sim_four_eyes_approval */
-- P1-b: genuine second-person 4-eye approval for order simulations.
--
-- Previously evaluate_order_gates auto-set APPROVED on pass (driven by the
-- creator's own employee_final_approved self-attestation on the upstream
-- recommendation), so the SAME employee could self-approve and self-execute a
-- simulated order — there was no second-person sign-off at the highest-risk
-- (simulated execution) step. Now a passing order simulation enters
-- PENDING_APPROVAL and a DIFFERENT employee must approve it before the creator
-- can execute-simulated, preserving the human 4-eye handoff (REG-03 §3).
--
-- Additive + back-compatible: the existing status values stay valid;
-- PENDING_APPROVAL is added to the CHECK set; the approver columns are nullable
-- so existing rows are unaffected.

ALTER TABLE order_simulations DROP CONSTRAINT IF EXISTS order_simulations_status_code_check;
ALTER TABLE order_simulations ADD CONSTRAINT order_simulations_status_code_check
    CHECK (status_code IN ('DRAFT', 'BLOCKED', 'PENDING_APPROVAL', 'APPROVED', 'SIMULATED_EXECUTED', 'CANCELLED'));

ALTER TABLE order_simulations ADD COLUMN IF NOT EXISTS approver_id UUID REFERENCES employees(id);
ALTER TABLE order_simulations ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;

/* sql_id: order_sim_approved_audit_code */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('order_simulation_approved', '모의 주문 4-eye 승인 (승인자 ≠ 작성자, PENDING_APPROVAL → APPROVED)')
ON CONFLICT (action_code) DO NOTHING;
