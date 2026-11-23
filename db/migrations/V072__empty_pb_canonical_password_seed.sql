/* sql_id: v072_empty_pb_canonical_password_seed */
-- V072: svc-viability-v3 A2 — seed canonical password (HarnessSynthetic!2026)
-- for syn.pb@v8test.local so audit_v1_copy_pb_perspective.py:339
-- empty_state Playwright login can succeed (resolves Unverified-2 from
-- svc-viability-v2 closure handoff).
--
-- Hash algorithm: PBKDF2-HMAC-SHA256 per apps/api/harness/core/security.py:
--   PASSWORD_ALG       = "pbkdf2_sha256"  (security.py:16)
--   PBKDF2_ITERATIONS  = 210_000           (security.py:17)
--   SALT_BYTES         = 16                (security.py:18)
-- Plaintext: HarnessSynthetic!2026 (사용자 verbatim canonical, 2026-05-25).
--
-- Target row was confirmed present via psql probe at W0 entry:
--   id          = acb31f2d-8ddb-4f87-9d9b-f7fa6061e1f2
--   email       = syn.pb@v8test.local
--   role_code   = PB
--   branch_id   = 11111111-1111-1111-1111-111111111111
-- Only password_hash is rewritten; the row's identifiers are immutable.
UPDATE employees
SET password_hash = 'pbkdf2_sha256$210000$QuAJeQf-xGaDuUhao8q0VQ$ruMhuWPnot7X_nLS9zFm5CSDpkGTi4FA-zH8bJ-03w4'
WHERE email = 'syn.pb@v8test.local';
