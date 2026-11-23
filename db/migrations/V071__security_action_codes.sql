/* sql_id: v071_security_action_codes */
-- V071: svc-viability-v3 T0-1 — register 3 security audit_action_codes for
-- B5 (same-actor mutation invariant audit emit, narrow scope = email + consultations)
-- and B6 (kyc_edd RBAC enforcement audit via try/except wrapper, Option-c).
--
--   four_eyes_violation_blocked   — email.py:421+1 emit (4-eye block 직전, plural
--                                   namespace consistent with services/compliance/
--                                   four_eyes.py:92-169 existing PLURAL codes)
--   same_actor_mutation_blocked   — consultations.py:101+1 emit (post 404
--                                   None-check, audit-only detective control,
--                                   HTTP 200 behavior preserved)
--   role_forbidden                — kyc_edd.py 5 call site (:40, :76, :112,
--                                   :177, :211) try/except wrapper emit
--                                   (Option-c, _require_compliance_role pure
--                                   validator signature unchanged)
--
-- Multi-code single-file precedent: V060 (4 kyc_edd codes) +
-- V034 (email state machine codes) + V039 (T201/T231/T276 codes).
-- additive-only per [[on-conflict-id-for-mutable-content]] — UPDATE/DELETE 금지.
--
-- Tracking: svc-viability-v3 W0 T0-1 (plan §7 build sequence).
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('four_eyes_violation_blocked', '4-eye 위반 차단 (marketing 승인자 == 작성자, email.py)'),
    ('same_actor_mutation_blocked', '동일 actor 후속 수정 감지 (consultations.py audit-only)'),
    ('role_forbidden',              'RBAC role 거부 (kyc_edd PB 시도 등, role_code mismatch)')
ON CONFLICT (action_code) DO NOTHING;
