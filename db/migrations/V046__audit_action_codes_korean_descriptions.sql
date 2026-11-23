/* sql_id: v046_audit_action_codes_korean_descriptions */
-- V046 — 66건 audit_action_codes description 한국어 일괄 update
--          (UltraQA cycle 7 S25 follow-up, 2026-05-19)
--
-- audit_logs UI(AUDIT_VIEWER 화면)는 audit_action_codes.description을 그대로
-- 노출. 영어 description 66/89건이 화면에 raw 노출되어 PB/AUDIT 한국어 가독성
-- 위반. 이번 migration은 한국어 매핑을 idempotent UPDATE 패턴으로 일괄 적용한다.
--
-- 한국어 매핑은 각 action_code의 의미를 PB/AUDIT가 즉시 이해할 수 있도록
-- 짧은 명사구로 통일. 영어 fallback(audit_logs.action_code 원본)은
-- frontend tooltip(title)에 그대로 유지하여 기술자 식별성 보존.

/* sql_id: v046_set_aftercare_event_resolve */ UPDATE audit_action_codes SET description = '사후관리 이벤트 해결' WHERE action_code = 'aftercare_event_resolve';
/* sql_id: v046_set_ai_call_failed */ UPDATE audit_action_codes SET description = 'AI 호출 실패' WHERE action_code = 'AI_CALL_FAILED';
/* sql_id: v046_set_ai_call_started */ UPDATE audit_action_codes SET description = 'AI 호출 시작' WHERE action_code = 'AI_CALL_STARTED';
/* sql_id: v046_set_ai_call_succeeded */ UPDATE audit_action_codes SET description = 'AI 호출 성공' WHERE action_code = 'AI_CALL_SUCCEEDED';
/* sql_id: v046_set_ai_fail_closed */ UPDATE audit_action_codes SET description = 'AI 출력 차단(안전 정책)' WHERE action_code = 'ai_fail_closed';
/* sql_id: v046_set_ai_injection_detected */ UPDATE audit_action_codes SET description = 'AI 프롬프트 주입 탐지' WHERE action_code = 'ai_injection_detected';
/* sql_id: v046_set_ai_output_final_approval_revoked */ UPDATE audit_action_codes SET description = 'AI 출력 최종 승인 취소' WHERE action_code = 'ai_output_final_approval_revoked';
/* sql_id: v046_set_ai_quarantine_triggered */ UPDATE audit_action_codes SET description = 'AI 격리 컨텍스트 적용' WHERE action_code = 'ai_quarantine_triggered';
/* sql_id: v046_set_appropriateness_warning_acknowledged */ UPDATE audit_action_codes SET description = '적합성 경고 확인' WHERE action_code = 'appropriateness_warning_acknowledged';
/* sql_id: v046_set_auth_login_failure */ UPDATE audit_action_codes SET description = '로그인 실패' WHERE action_code = 'auth_login_failure';
/* sql_id: v046_set_auth_login_rate_limited */ UPDATE audit_action_codes SET description = '로그인 속도 제한' WHERE action_code = 'auth_login_rate_limited';
/* sql_id: v046_set_auth_login_success */ UPDATE audit_action_codes SET description = '로그인 성공' WHERE action_code = 'auth_login_success';
/* sql_id: v046_set_auth_logout */ UPDATE audit_action_codes SET description = '로그아웃' WHERE action_code = 'auth_logout';
/* sql_id: v046_set_auth_refresh */ UPDATE audit_action_codes SET description = '토큰 갱신' WHERE action_code = 'auth_refresh';
/* sql_id: v046_set_auth_refresh_reuse */ UPDATE audit_action_codes SET description = '갱신 토큰 재사용 탐지' WHERE action_code = 'auth_refresh_reuse';
/* sql_id: v046_set_consent_recorded */ UPDATE audit_action_codes SET description = '고객 동의 기록' WHERE action_code = 'consent_recorded';
/* sql_id: v046_set_consent_withdrawn */ UPDATE audit_action_codes SET description = '고객 동의 철회' WHERE action_code = 'consent_withdrawn';
/* sql_id: v046_set_consultation_complete */ UPDATE audit_action_codes SET description = '상담 완료' WHERE action_code = 'consultation_complete';
/* sql_id: v046_set_consultation_create */ UPDATE audit_action_codes SET description = '상담 생성' WHERE action_code = 'consultation_create';
/* sql_id: v046_set_customer_360_view */ UPDATE audit_action_codes SET description = '고객 360 조회' WHERE action_code = 'customer_360_view';
/* sql_id: v046_set_demo_mode_expired */ UPDATE audit_action_codes SET description = '데모 모드 만료' WHERE action_code = 'demo_mode_expired';
/* sql_id: v046_set_demo_mode_expiring_soon */ UPDATE audit_action_codes SET description = '데모 모드 만료 임박' WHERE action_code = 'demo_mode_expiring_soon';
/* sql_id: v046_set_demo_mode_toggle_off */ UPDATE audit_action_codes SET description = '데모 모드 비활성화' WHERE action_code = 'demo_mode_toggle_off';
/* sql_id: v046_set_demo_mode_toggle_on */ UPDATE audit_action_codes SET description = '데모 모드 활성화' WHERE action_code = 'demo_mode_toggle_on';
/* sql_id: v046_set_email_draft_approved */ UPDATE audit_action_codes SET description = '이메일 초안 승인' WHERE action_code = 'email_draft_approved';
/* sql_id: v046_set_email_drafted */ UPDATE audit_action_codes SET description = '이메일 초안 생성' WHERE action_code = 'email_drafted';
/* sql_id: v046_set_email_draft_rejected */ UPDATE audit_action_codes SET description = '이메일 초안 반려' WHERE action_code = 'email_draft_rejected';
/* sql_id: v046_set_email_draft_send */ UPDATE audit_action_codes SET description = '이메일 발송' WHERE action_code = 'email_draft_send';
/* sql_id: v046_set_email_draft_submitted */ UPDATE audit_action_codes SET description = '이메일 초안 승인 요청' WHERE action_code = 'email_draft_submitted';
/* sql_id: v046_set_email_send_blocked */ UPDATE audit_action_codes SET description = '이메일 발송 차단(전제 조건 미충족)' WHERE action_code = 'email_send_blocked';
/* sql_id: v046_set_email_send_failed */ UPDATE audit_action_codes SET description = '이메일 발송 실패' WHERE action_code = 'email_send_failed';
/* sql_id: v046_set_email_sent_via_sandbox */ UPDATE audit_action_codes SET description = '이메일 샌드박스 발송' WHERE action_code = 'email_sent_via_sandbox';
/* sql_id: v046_set_embedding_call_failed */ UPDATE audit_action_codes SET description = '임베딩 호출 실패' WHERE action_code = 'EMBEDDING_CALL_FAILED';
/* sql_id: v046_set_explanation_confirmed */ UPDATE audit_action_codes SET description = '설명의무 확인' WHERE action_code = 'explanation_confirmed';
/* sql_id: v046_set_four_gate_acknowledged */ UPDATE audit_action_codes SET description = '준법 4-게이트 확인' WHERE action_code = 'four_gate_acknowledged';
/* sql_id: v046_set_gate_evidence_recorded */ UPDATE audit_action_codes SET description = '게이트 증빙 기록' WHERE action_code = 'gate_evidence_recorded';
/* sql_id: v046_set_house_view_activate */ UPDATE audit_action_codes SET description = '하우스뷰 활성화' WHERE action_code = 'house_view_activate';
/* sql_id: v046_set_marketing_review_approved */ UPDATE audit_action_codes SET description = '마케팅 심의 승인' WHERE action_code = 'marketing_review_approved';
/* sql_id: v046_set_marketing_review_blocked */ UPDATE audit_action_codes SET description = '마케팅 심의 차단' WHERE action_code = 'marketing_review_blocked';
/* sql_id: v046_set_marketing_review_rejected */ UPDATE audit_action_codes SET description = '마케팅 심의 반려' WHERE action_code = 'marketing_review_rejected';
/* sql_id: v046_set_marketing_review_submitted */ UPDATE audit_action_codes SET description = '마케팅 심의 신청' WHERE action_code = 'marketing_review_submitted';
/* sql_id: v046_set_model_card_published */ UPDATE audit_action_codes SET description = '모델 카드 게시' WHERE action_code = 'model_card_published';
/* sql_id: v046_set_model_card_revised */ UPDATE audit_action_codes SET description = '모델 카드 수정' WHERE action_code = 'model_card_revised';
/* sql_id: v046_set_nba_complete */ UPDATE audit_action_codes SET description = 'NBA 완료' WHERE action_code = 'nba_complete';
/* sql_id: v046_set_nba_dismiss */ UPDATE audit_action_codes SET description = 'NBA 해제' WHERE action_code = 'nba_dismiss';
/* sql_id: v046_set_order_simulation_block */ UPDATE audit_action_codes SET description = '모의 주문 차단' WHERE action_code = 'order_simulation_block';
/* sql_id: v046_set_order_simulation_cancel */ UPDATE audit_action_codes SET description = '모의 주문 취소' WHERE action_code = 'order_simulation_cancel';
/* sql_id: v046_set_order_simulation_create */ UPDATE audit_action_codes SET description = '모의 주문 생성' WHERE action_code = 'order_simulation_create';
/* sql_id: v046_set_order_simulation_execute_simulated */ UPDATE audit_action_codes SET description = '모의 주문 실행' WHERE action_code = 'order_simulation_execute_simulated';
/* sql_id: v046_set_poc_auto_approval_used */ UPDATE audit_action_codes SET description = 'PoC 자동 승인 사용' WHERE action_code = 'poc_auto_approval_used';
/* sql_id: v046_set_recommendation_simulation_block */ UPDATE audit_action_codes SET description = '권유 모의 차단' WHERE action_code = 'recommendation_simulation_block';
/* sql_id: v046_set_recommendation_simulation_create */ UPDATE audit_action_codes SET description = '권유 모의 생성' WHERE action_code = 'recommendation_simulation_create';
/* sql_id: v046_set_suitability_form_submitted */ UPDATE audit_action_codes SET description = '적합성 form 제출' WHERE action_code = 'suitability_form_submitted';
/* sql_id: v046_set_ws_connection_opened */ UPDATE audit_action_codes SET description = 'WS 연결 열림' WHERE action_code = 'ws_connection_opened';
/* sql_id: v046_set_ws_connection_closed */ UPDATE audit_action_codes SET description = 'WS 연결 닫힘' WHERE action_code = 'ws_connection_closed';
/* sql_id: v046_set_ws_ticket_issued */ UPDATE audit_action_codes SET description = 'WS 티켓 발급' WHERE action_code = 'ws_ticket_issued';
/* sql_id: v046_set_ws_ticket_consumed */ UPDATE audit_action_codes SET description = 'WS 티켓 사용' WHERE action_code = 'ws_ticket_consumed';
/* sql_id: v046_set_ws_reconnect */ UPDATE audit_action_codes SET description = 'WS 재연결' WHERE action_code = 'ws_reconnect';
/* sql_id: v046_set_rights_notice_view */ UPDATE audit_action_codes SET description = '권리 고지 조회' WHERE action_code = 'rights_notice_view';
/* sql_id: v046_set_rights_notice_publish */ UPDATE audit_action_codes SET description = '권리 고지 게시' WHERE action_code = 'rights_notice_publish';
/* sql_id: v046_set_conflict_disclosure_create */ UPDATE audit_action_codes SET description = '이해상충 공시 작성' WHERE action_code = 'conflict_disclosure_create';
/* sql_id: v046_set_conflict_disclosure_check */ UPDATE audit_action_codes SET description = '이해상충 공시 검토' WHERE action_code = 'conflict_disclosure_check';
/* sql_id: v046_set_dispute_open */ UPDATE audit_action_codes SET description = '분쟁 조정 케이스 생성' WHERE action_code = 'dispute_open';
/* sql_id: v046_set_dispute_respond */ UPDATE audit_action_codes SET description = '분쟁 조정 응답' WHERE action_code = 'dispute_respond';
/* sql_id: v046_set_dispute_resolve */ UPDATE audit_action_codes SET description = '분쟁 조정 해결' WHERE action_code = 'dispute_resolve';
/* sql_id: v046_set_info_access_response */ UPDATE audit_action_codes SET description = '자료요구 응답' WHERE action_code = 'info_access_response';
/* sql_id: v046_set_info_access_received */ UPDATE audit_action_codes SET description = '자료요구 접수' WHERE action_code = 'info_access_received';
/* sql_id: v046_set_four_gate_acknowledged_by_bm */ UPDATE audit_action_codes SET description = '4-게이트 확인 (브랜치 매니저)' WHERE action_code = 'four_gate_acknowledged_by_bm';
/* sql_id: v046_set_unfair_solicitation_checked */ UPDATE audit_action_codes SET description = '불공정 권유 점검' WHERE action_code = 'unfair_solicitation_checked';
/* sql_id: v046_set_ai_decision_support_used */ UPDATE audit_action_codes SET description = '의사결정 보조 사용' WHERE action_code = 'ai_decision_support_used';
/* sql_id: v046_set_compliance_check_invoked */ UPDATE audit_action_codes SET description = '준법 점검 호출' WHERE action_code = 'compliance_check_invoked';
/* sql_id: v046_set_poc_auto_approval_aborted */ UPDATE audit_action_codes SET description = 'PoC 자동 승인 중단(게이트 실패/지연/속도)' WHERE action_code = 'poc_auto_approval_aborted';
/* sql_id: v046_set_poc_auto_approval_rate_limited */ UPDATE audit_action_codes SET description = 'PoC 자동 승인 속도 제한 초과' WHERE action_code = 'poc_auto_approval_rate_limited';
/* sql_id: v046_set_rate_limit_exceeded */ UPDATE audit_action_codes SET description = '요청 속도 제한 초과' WHERE action_code = 'rate_limit_exceeded';
/* sql_id: v046_set_recommendation_simulation_cancel */ UPDATE audit_action_codes SET description = '권유 모의 취소' WHERE action_code = 'recommendation_simulation_cancel';
/* sql_id: v046_set_risk_assessment_create */ UPDATE audit_action_codes SET description = '위험 평가 생성' WHERE action_code = 'risk_assessment_create';
/* sql_id: v046_set_sod_evidence_published */ UPDATE audit_action_codes SET description = '직무 분리 증빙 게시' WHERE action_code = 'sod_evidence_published';
/* sql_id: v046_set_suitability_confirmed */ UPDATE audit_action_codes SET description = '적합성 확인' WHERE action_code = 'suitability_confirmed';
/* sql_id: v046_set_suitability_grade_block */ UPDATE audit_action_codes SET description = '적합성 등급 차단(고객 등급 < 상품 등급)' WHERE action_code = 'suitability_grade_block';
/* sql_id: v046_set_unfair_solicitation_blocked */ UPDATE audit_action_codes SET description = '불공정 권유 차단' WHERE action_code = 'unfair_solicitation_blocked';