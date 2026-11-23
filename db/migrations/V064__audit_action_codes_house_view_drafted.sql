/* sql_id: v064_insert_audit_action_code_house_view_drafted */
-- V064: Cycle Z5 B.2 phase 3 — register the canonical action_code
-- `house_view_drafted` so POST /house-views can land its audit row.
--
-- The code is declared in apps/api/harness/core/audit.py CANONICAL but
-- has never been seeded into audit_action_codes. The DB CHECK rejects
-- the INSERT, the handler raises ForeignKeyViolationError, and
-- test_api_boundary_harness::test_nba_aftercare_and_house_view_mutation_boundaries
-- has been failing 500 on the create-house-view assertion.
--
-- Additive only per [[pattern-id-additive-not-rename]] — no existing
-- code is modified.
INSERT INTO audit_action_codes (action_code, description)
VALUES ('house_view_drafted', '하우스뷰 DRAFT 생성 (PB/WM 수동)')
ON CONFLICT (action_code) DO NOTHING;
