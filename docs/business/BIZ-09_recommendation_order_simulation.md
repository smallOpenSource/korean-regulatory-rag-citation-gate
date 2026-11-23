# BIZ-09 Recommendation and Order Simulation

## Purpose
직원 화면에서 고객 권유와 주문 전 단계의 업무 흐름을 PoC로 검증한다. 실제 고객 주문이나 계좌 반영은 수행하지 않는다.

## Four Required Gates
| gate | 필수 조건 | 실패 시 처리 |
|---|---|---|
| 적합성 통과 | 고객 위험등급 코드 >= 상품 위험등급 코드 | 차단 저장 + 감사 로그 |
| 설명의무 확인 | 설명의무 체크 완료 | 차단 저장 + 감사 로그 |
| 합성 고객 동의 확인 | 직원 화면에서 고객 동의 시뮬레이션 기록 | 차단 저장 + 감사 로그 |
| 직원 최종 승인 | 직원 최종 승인 | 차단 저장 + 감사 로그 |

## 상태 코드(기술 사양)
- recommendation_simulations.status_code: DRAFT(초안) | BLOCKED(차단) | APPROVED(승인) | CANCELLED(취소)
- order_simulations.status_code: DRAFT(초안) | BLOCKED(차단) | APPROVED(승인) | SIMULATED_EXECUTED(모의 실행 완료) | CANCELLED(취소)

## Rules
- 실제 주문 API 호출 금지.
- 실제 고객/계좌 데이터 사용 금지.
- 모든 생성, 차단, 승인, 취소 이벤트는 audit_logs에 기록한다.
- UI에는 “시뮬레이션 / 실제 주문 아님” 배지를 항상 표시한다.


## Server-side Gate Evaluation
- 적합성 통과 여부는 클라이언트 입력을 신뢰하지 않고 서버가 고객 위험등급 코드와 상품 위험등급 코드로 재계산한다.
- 설명의무 확인, 합성 고객 동의 확인, 직원 최종 승인도 서버 트랜잭션에서 검증하고 gate_detail_json에 저장한다.
- 주문 시뮬레이션 생성 시 승인된 추천 시뮬레이션을 다시 조회하고 현재 고객/상품 상태로 4-gate를 재검증한다.
- 승인된 추천이 취소되었거나 고객/상품 상태가 바뀌어 gate가 실패하면 주문 시뮬레이션은 차단(BLOCKED)으로 저장한다.


## Audit Code Source
- Canonical audit action_code 목록은 docs/observability/OBS-02_audit_action_codes.md를 따른다.
