/* sql_id: seed_audit_action_codes_reg05_auth */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('auth_login_success', 'REG-05 auth: login success'),
    ('auth_login_failure', 'REG-05 auth: login failure (bad credentials, locked, etc.)'),
    ('auth_refresh', 'REG-05 auth: access token refreshed via valid refresh token'),
    ('auth_logout', 'REG-05 auth: logout (refresh token revoked)'),
    ('auth_refresh_reuse', 'REG-05 auth: refresh token reuse detected (token chain revoked)'),
    ('auth_login_rate_limited', 'REG-05 auth: login attempt blocked by rate limiter')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg05_websocket */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('ws_ticket_issued', 'REG-05 WS: short-lived WebSocket ticket issued'),
    ('ws_ticket_consumed', 'REG-05 WS: ticket consumed during handshake (single-use)'),
    ('ws_connection_opened', 'REG-05 WS: WebSocket connection established'),
    ('ws_connection_closed', 'REG-05 WS: WebSocket connection closed'),
    ('ws_reconnect', 'REG-05 WS: client reconnect with backoff')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg05_rate_limit */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('rate_limit_exceeded', 'REG-05 rate-limit: request rejected by per-route limiter')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg04_quarantine */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('ai_quarantine_triggered', 'REG-04 AI: quarantined LLM context applied (OWASP LLM01)'),
    ('ai_fail_closed', 'REG-04 AI: AI output fail-closed per fail_closed_reason_code'),
    ('ai_injection_detected', 'REG-04 AI: prompt injection pattern matched in INJECTION_PATTERNS.yaml')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg01_rights_notice */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('rights_notice_issued', 'REG-01 권리고지: investor rights notice issued')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg01_dispute */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('dispute_case_opened', 'REG-01 분쟁: dispute case opened'),
    ('dispute_case_resolved', 'REG-01 분쟁: dispute case resolved')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg01_consent */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('consent_recorded', 'REG-01 consent: customer consent recorded'),
    ('consent_withdrawn', 'REG-01 consent: customer consent withdrawn')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg02_marketing */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('marketing_review_submitted', 'REG-02 marketing: marketing copy submitted for review'),
    ('marketing_review_approved', 'REG-02 marketing: marketing copy approved by supervisor'),
    ('marketing_review_rejected', 'REG-02 marketing: marketing copy rejected by supervisor')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg02_unfair */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('unfair_solicitation_blocked', 'REG-02 unfair: solicitation pattern blocked by validator')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg04_model_card */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('model_card_published', 'REG-04 model: model card published'),
    ('model_card_revised', 'REG-04 model: model card revised')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg06_governance */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('demo_mode_toggle_on', 'REG-06 governance: system_flags.demo_mode toggled ON (PoC_AUTO_APPROVAL)'),
    ('demo_mode_toggle_off', 'REG-06 governance: system_flags.demo_mode toggled OFF or expired'),
    ('poc_auto_approval_used', 'REG-06 governance: PoC_AUTO_APPROVAL path used by an action'),
    ('poc_auto_approval_aborted', 'REG-06 governance: PoC_AUTO_APPROVAL path aborted (gate fail / lag / rate)')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: seed_audit_action_codes_reg06_sod */
INSERT INTO audit_action_codes(action_code, description) VALUES
    ('sod_evidence_published', 'REG-06 SoD: segregation-of-duties evidence pack published')
ON CONFLICT (action_code) DO NOTHING;
