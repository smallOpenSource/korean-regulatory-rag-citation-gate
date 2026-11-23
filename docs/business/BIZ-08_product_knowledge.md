# BIZ-08 Product Knowledge

## Product Families
| product_type_code | 명칭 | 주요 특성 |
|---|---|---|
| FUND | 펀드 | 집합투자, 환매 가능, 수수료 구조 다양 |
| BOND | 채권 | 원리금 확정, 만기·금리 리스크 |
| ELS_DLS | ELS/DLS | knock-in 조건, 원금비보장 가능, 조기상환 옵션 |
| WRAP | 랩 | 일임형 운용, PB 재량, 수수료 일체형 |
| TRUST | 신탁 | 자산 분리 보관, 목적신탁 등 활용 |
| DEPOSIT | 예금성 자산 | 원금보장, 낮은 수익, 유동성 확보 |

## Key Attributes (products 테이블)
- risk_level_code (1-5): 고객 risk_grade_code와 비교 (BIZ-07 참조).
- maturity_date: aftercare_events MATURITY_DUE 트리거 기준.
- has_knock_in / knock_in_barrier_pct: KI_TRIGGERED 이벤트 감지 기준.
- issuer_name: 발행사 부도 리스크 표시 참조.

## Harness Integration Points
- 적합성 체크: 상담 시 권유 상품 risk_level_code > 고객 risk_grade_code 경고.
- 만기 알림: maturity_date - today < 임계값 → aftercare_events MATURITY_DUE 생성.
- KI 모니터링: 배치가 knock_in_barrier_pct 대비 현재가 확인 → 이벤트 생성.
- 포트폴리오 분석: portfolio_holdings + products 조인으로 ELS 집중도, 만기 집중 등 탐지.
- 브리핑: AI가 주요 보유 상품 특성 요약 (PROMPT-02 input으로 product_context 제공).
