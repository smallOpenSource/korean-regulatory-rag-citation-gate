# PRD-06 Success Metrics

## Primary KPIs
- 후속 조치 완료율: 생성된 후속 조치 중 완료 전환 비율 (목표 ≥ 70%)
- 브리핑 열람률: 상담 시작 전 브리핑 조회 비율 (목표 ≥ 60%)
- 만기 사후관리 처리율: 만기 이벤트 중 해결 비율 (목표 ≥ 95%)
- 미접촉 고객 감소율: 90일 이상 미접촉 고객 수 감소율

## Secondary KPIs
- 하우스뷰 연결률: 상담 중 활성 하우스뷰 연결 비율
- 컴플라이언스 체크리스트 완료율: 완료 상담 중 체크리스트 100% 비율
- AI 초안 채택률: 생성된 이메일 초안 중 발송 전환 비율

## Measurement
모든 KPI는 audit_logs, nba_actions, aftercare_events, consultations 테이블에서 계산.
BRANCH_MANAGER / ADMIN 대시보드에서 주간 집계 확인.
