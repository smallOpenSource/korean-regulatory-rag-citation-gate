# BIZ-06 Compliance

## Core Legal Obligations (자본시장법 기준)
- **적합성 원칙**: 고객 위험등급 이하 위험 상품만 권유 가능 (제46조).
- **설명의무**: 상품 주요 내용, 위험, 수수료 등 설명 및 고객 확인 (제47조).
- **기록 보존**: 상담·거래 기록 5년 이상 보존.
- **이해충돌 방지**: 직원 이익과 고객 이익 충돌 시 고객 우선.

## Harness Implementation Requirements
- 상담 시작 시 적합성 확인 체크박스 필수(완료 전환 조건).
- 상담 완료 전 설명의무 확인 체크박스 필수.
- 고객 위험등급 코드 < 권유 상품 위험등급 코드 → 경고 표시 + 로그.
- AI 생성 내용 화면 표시 시 반드시 "AI 생성 · {generated_at} · {model}" 표기.
- 중요 행위(상담 저장, 이메일 발송, house view 활성화) → audit_logs 기록 필수.

## Audit Log Required Actions
- customer_360_view, consultation_create, consultation_complete
- nba_complete, nba_dismiss, house_view_activate
- email_sent_via_sandbox (발송 성공 시 emit; email_draft_send 는 real-SMTP 예약/미emit, OBS-02 §REG-02 참조), risk_assessment_create, aftercare_event_resolve
- recommendation_simulation_create, recommendation_simulation_block, order_simulation_create, order_simulation_block, order_simulation_execute_simulated


## Recommendation/Order Simulation Gate
- 추천/주문 시뮬레이션은 실제 주문이 아니며 합성 고객/포트폴리오 데이터에만 적용한다.
- 생성 조건: suitability pass, explanation check, simulated customer consent, employee final approval 네 조건을 모두 만족해야 한다.
- 하나라도 실패하면 차단(BLOCKED) 상태로 저장하고 사유를 audit_logs.detail_json에 남긴다.
- 직원 최종 승인 전까지 AI 결과는 “초안/검토용”으로만 표시한다.


## Audit Code Source
- Canonical audit action_code 목록은 docs/observability/OBS-02_audit_action_codes.md를 따른다.
