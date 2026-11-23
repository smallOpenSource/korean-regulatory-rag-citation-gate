"""Canonical audit action-code contract."""

from __future__ import annotations

CANONICAL_AUDIT_ACTION_CODES: tuple[str, ...] = (
    "AI_CALL_STARTED",
    "AI_CALL_SUCCEEDED",
    "AI_CALL_FAILED",
    "EMBEDDING_CALL_FAILED",
    "customer_360_view",
    "consultation_create",
    "consultation_complete",
    "nba_complete",
    "nba_dismiss",
    "house_view_activate",
    "email_draft_send",
    "risk_assessment_create",
    "aftercare_event_resolve",
    "recommendation_simulation_create",
    "recommendation_simulation_block",
    "recommendation_simulation_cancel",
    "order_simulation_create",
    "order_simulation_block",
    # P1-b order simulation second-person 4-eye approval (V080)
    "order_simulation_approved",
    "order_simulation_execute_simulated",
    "order_simulation_cancel",
    # REG-05 T280/T283 — auth security audit codes (V022 expands DB CHECK constraint)
    "auth_login_success",
    "auth_login_failure",
    "auth_login_rate_limited",
    "auth_refresh",
    "auth_refresh_rate_limited",
    "auth_refresh_reuse",
    "auth_logout",
    # REG-05 T292 — global rate limit
    "rate_limit_exceeded",
    # REG-04 / ADR-005 W3-T6 — AI token rate ceiling (LLM10)
    "ai_token_rate_limited",
    # REG-05 T287/T297 — WebSocket ticket-flow audit codes
    "ws_ticket_issued",
    "ws_ticket_consumed",
    "ws_connection_opened",
    "ws_connection_closed",
    "ws_reconnect",
    # T16 — House view lifecycle (V035)
    "house_view_drafted",
    "house_view_generated",
    "house_view_reviewed",
    "house_view_activated",
    "house_view_archived",
    # T17/T243 — NBA card lifecycle
    "nba_card_created",
    "nba_card_acknowledged",
    "nba_card_dismissed",
    "nba_card_completed",
    # T244/T257 — Aftercare quarterly lifecycle
    "aftercare_queued",
    "aftercare_completed",
    "aftercare_skipped",
    # T248 — KYC/EDD trigger lifecycle (V029)
    # KYC/EDD lifecycle (V022 + V060 OQ-1/OQ-5 split)
    "kyc_edd_triggered",
    "kyc_edd_reassessed",
    "kyc_edd_completed",
    "kyc_edd_trigger_listed",
    "kyc_edd_trigger_detail_viewed",
    "kyc_edd_evaluated",
    # T249 — Conflict of interest pre-disclosure (V030)
    "conflict_disclosed",
    "conflict_of_interest_blocked",
    # REG-01 T214-T217, T229 — synthetic consent + 열람정정 + 연락중지 (V027)
    "consent_recorded",
    "consent_withdrawn",
    "marketing_consent_withdrawn",
    "info_access_requested",
    "info_access_responded",
    "general_bundle_consent",
    # REG-01 T219 — 신용정보법 §20-2 파기 placeholder (V033)
    "credit_info_purge_simulated",
    # REG-04 AI governance (V022 + V045 quarantine_released + V058 B7/B9 split)
    "ai_quarantine_triggered",
    "quarantine_released",
    "ai_fail_closed",
    "ai_job_get",
    "ai_output_get",
    "citation_gate_failed",
    "provider_failure",
    "consultation_status_changed",
    "nba_ws_broadcast_failed",
    "nba_script_generated",
    "ai_injection_detected",
    "model_card_published",
    "model_card_revised",
    # REG-01 rights + disputes (V022 + V058 C6 + V059 C7)
    "rights_notice_issued",
    "rights_notice_acknowledged",
    "dispute_case_opened",
    "dispute_responded",
    "dispute_case_resolved",
    # REG-02 marketing review (V022 + V025)
    "marketing_review_submitted",
    "marketing_review_approved",
    "marketing_review_rejected",
    "marketing_review_blocked",
    # ADR-002 email state machine (V034, T18/T207/T224/T247)
    "email_drafted",
    "email_draft_submitted",
    "email_draft_approved",
    "email_draft_rejected",
    "email_sent_via_sandbox",
    "email_send_failed",
    "email_send_blocked",
    # REG-02 unfair solicitation (V022)
    "unfair_solicitation_blocked",
    # REG-06 governance (V022)
    "demo_mode_toggle_on",
    "demo_mode_toggle_off",
    "poc_auto_approval_used",
    "poc_auto_approval_aborted",
    "sod_evidence_published",
    # REG-02 T220/T228 suitability gate (V023)
    "suitability_confirmed",
    "suitability_grade_block",
    # REG-01 T203 appropriateness gate (V023)
    "appropriateness_warning_acknowledged",
    # REG-02 T222 explanation gate (V023)
    "explanation_confirmed",
    # REG-03 T242 four-gate acknowledge (V023)
    "four_gate_acknowledged",
    # svc-viability-v3 B5 + B6 security codes (V071)
    "four_eyes_violation_blocked",
    "same_actor_mutation_blocked",
    "role_forbidden",
    # svc-viability-v4 I2/I4/I7 codes (V074/V076/V077)
    "house_view_regenerated_by_admin",
    "consultation_submitted_for_approval",
    "ai_compliance_mock_used",
    # svc-viability-v4 W2 I8 drift catch — prior V*.sql INSERTs that were
    # registered in audit_action_codes but missing from this tuple. The drift
    # test (tests/test_audit_action_code_drift.py) caught the gap; each code
    # below already exists in audit_action_codes and is emitted by existing
    # backend code paths. Adding them here closes require_audit_action() trips.
    "ai_output_final_approval_revoked",
    "ai_output_final_approved",
    "demo_mode_expired",
    "demo_mode_expiring_soon",
    "gate_evidence_recorded",
    "poc_auto_approval_rate_limited",
    "prohibited_phrase_blocked",
    "v8_cell_visited",
    "v8_unreachable_marked",
    # ADR-020 F2 (V083) — refused house_view activation (single-live invariant).
    "house_view_activation_blocked",
)


def is_valid_audit_action(action_code: str) -> bool:
    """Return whether ``action_code`` is documented in OBS-02."""

    return action_code in CANONICAL_AUDIT_ACTION_CODES


def require_audit_action(action_code: str) -> str:
    """Validate and return an audit action code."""

    if not is_valid_audit_action(action_code):
        raise ValueError(f"Unknown audit action_code: {action_code}")
    return action_code
