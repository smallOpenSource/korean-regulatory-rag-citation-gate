# BIZ-04 후속 조치 규칙

## Trigger Events
| trigger_code | 설명 | 기본 우선순위 |
|---|---|---|
| MATURITY_DUE | 상품 만기 N일 이내 | 긴급(7일) / 높음(30일) |
| KI_TRIGGERED | ELS/DLS 녹인 발생 | 긴급 |
| DRAWDOWN_BREACH | 포트폴리오 손실 임계값 초과 | 긴급(-20%) / 높음(-10%) |
| NO_CONTACT | 최종 접촉 후 N일 초과 | 높음 |
| HOUSE_VIEW_CHANGED | 새 하우스뷰 활성화 | 보통 |
| RISK_SURVEY_OVERDUE | 위험 성향 설문 갱신 기한 초과 | 보통 |
| ALLOCATION_DRIFT | 현재 배분 vs 하우스뷰 괴리 초과 | 보통 |
| LIFE_EVENT | 고객 생애 이벤트 (은퇴, 상속 등) | 높음 |

## 우선순위 표시
- 긴급: 즉시 대응 필요(당일 연락 권장)
- 높음: 3일 이내 대응
- 보통: 1주 이내 대응
- 낮음: 정보성, 여유 있을 때

## 후속 조치 생성 규칙
- 배치 평가: 매일 1회 이상 전체 대상 고객 평가.
- 중복 방지: 같은 고객/업무 유형 조합이 대기 또는 진행 중 상태이면 신규 생성 금지.
- 스크립트: nba_script 에이전트가 생성, 후속 조치 생성 직후 비동기 주입.
- 기한: 발생 사유별 기본 기한 오프셋 적용(lookup table 기반).

## 후속 조치 생애주기
- 생성 → 대기(배치 또는 이벤트 기반)
- PB가 확인 → 진행 중
- 후속 연락 완료 → 완료
- 나중에 처리 → 보류(보류 해제 시각 설정)
- 해당 없음 → 해제
- 완료 / 해제 후 재활성화 불가.

## Action Type Codes
MATURITY_FOLLOW_UP, KI_FOLLOW_UP, DRAWDOWN_FOLLOW_UP,
NO_CONTACT_OUTREACH, HOUSE_VIEW_UPDATE, SURVEY_DUE,
REBALANCING_REVIEW, LIFE_EVENT_CONSULTATION
