# BIZ-05 Aftercare Rules

## Event Types and Trigger Thresholds
| event_type_code | 트리거 조건 | 기본 임계값 | 후속 조치 우선순위 |
|---|---|---|---|
| MATURITY_DUE | 만기일까지 N일 이하 | 30일, 7일 (2단계) | 높음 / 긴급 |
| KI_TRIGGERED | ELS/DLS 녹인 조건 발생 | barrier 터치 즉시 | 긴급 |
| DRAWDOWN_BREACH | 포트폴리오 손실률 초과 | -10%, -20% | 높음 / 긴급 |
| REVIEW_DUE | 정기 리뷰 주기 초과 | 6개월 | 보통 |
| NO_CONTACT | 최종 상담일 이후 N일 초과 | 90일 | 높음 |

## Processing Flow
1. 배치 평가 (매일): aftercare_events 대상 조건 확인.
2. 신규 이벤트 생성: aftercare_events INSERT (진행 필요 상태).
3. 후속 조치 생성: nba_actions INSERT (업무 유형 매핑).
4. 현재는 대시보드/후속 조치 관리함에 노출한다. PB WebSocket 알림은 ADR-001 구현 후 future path이다.
5. PB 후속 연락 후 consultation 기록.
6. 결과 기록: aftercare_events 상태 → 해결, resolved_at 설정.

## Rules
- 동일 고객의 동일 event_type_code는 진행 필요 상태에서 중복 생성 금지.
- 임계값은 DB lookup table로 관리 (하드코딩 금지).
- 이벤트 발생 시 audit_logs에 기록.
