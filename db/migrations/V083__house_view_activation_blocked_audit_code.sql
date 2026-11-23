/* sql_id: house_view_activation_blocked_audit_code */
-- ADR-020 F2 — register the house_view_activation_blocked audit action code.
--
-- A house view activation refused by the single-global-live-view invariant
-- (ADR-020: the app guard assert_single_live_house_view OR the V082 DB index
-- idx_house_views_single_live) rolls the activation back and returns 409. F2
-- emits an append-only audit_logs row so the refused activation leaves a ledger
-- entry (the row persists even though the activation transaction rolled back —
-- it is written on a fresh transaction in the router's except handler).
--
-- audit_logs.action_code is FK-constrained to audit_action_codes, so this row
-- must exist before any emit. Registered in all three sources (two-source rule):
--   1. this INSERT (DB)
--   2. apps/api/harness/core/audit.py::CANONICAL_AUDIT_ACTION_CODES (Python)
--   3. docs/observability/OBS-02_audit_action_codes.md (doc)
-- The DB <-> CANONICAL symmetric-diff drift gate is tests/test_audit_action_code_drift.py.
--
-- Emit sites:
--   routers/house_views.py activate_house_view (legacy /activate) except branch
--   routers/house_views.py activate_lifecycle_house_view (/activate-lifecycle) except branch

INSERT INTO audit_action_codes (action_code, description) VALUES
    ('house_view_activation_blocked',
     'House view activation refused by the single-global-live-view invariant (ADR-020); activation rolled back, 409')
ON CONFLICT (action_code) DO NOTHING;
