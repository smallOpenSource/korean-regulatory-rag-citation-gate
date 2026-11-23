/* sql_id: v056_auth_refresh_rate_limited_audit_code */
-- V056: Wave-Audit-Defect-Fix B5 — register canonical action_code for
-- ``auth_refresh_rate_limited``. The /auth/refresh handler (routers/auth.py)
-- raised HTTP 429 silently when T280 rate-limit fired, leaving no audit
-- trail for repeated refresh abuse. ``auth_refresh`` (success) is already
-- canonical (core/audit.py:30) and seeded by prior migrations, so this
-- migration only adds the rate-limit row.
--
-- additive-only per [[on-conflict-id-for-mutable-content]] (V054 in-place 금지).
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('auth_refresh_rate_limited', 'REG-05 T280 — /auth/refresh per-IP 429 차단')
ON CONFLICT (action_code) DO NOTHING;
