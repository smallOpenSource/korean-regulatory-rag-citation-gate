# ASYNC-01 Realtime and Async Spec

## Long AI Job Flow
1. 클라이언트 POST → API 즉시 202 + job_id 반환.
2. 서버 백그라운드 Task (asyncio.create_task) 실행.
3. 완료 시 DB 업데이트. WebSocket `ai_job_done`은 ADR-001 구현 후 future push path로 추가한다.
4. 현재 클라이언트는 `GET /ai-jobs/{job_id}` 폴링으로 결과를 확인하며, WebSocket은 `backlog/not-current-contract`이다.

## Durable AI Job Contract
- `ai_jobs` 테이블에 job_id, job_type_code, status_code, requested_by_id, resource_type, resource_id, result_resource_type, result_resource_id, result_summary, error_code, error_message, created_at, started_at, finished_at을 저장한다.
- status_code: PENDING | RUNNING | SUCCEEDED | FAILED | CANCELLED.
- 202 응답을 반환하는 모든 AI endpoint는 DB에 PENDING job을 먼저 생성한 뒤 background task를 시작한다.
- background task 시작 시 RUNNING, 성공 시 SUCCEEDED + result 링크, 실패 시 FAILED + redacted error 저장.
- `GET /ai-jobs/{job_id}`는 요청자 RBAC/row-level scope 안의 job만 조회한다.
- WebSocket `ai_job_done` 이벤트를 구현할 때도 동일한 row-level 필터를 통과한 사용자에게만 전달한다. 현재 계약은 폴링 기반 조회이다.
- error_message에는 secret, raw PII, 외부 API token/body 원문을 넣지 않는다.

## APScheduler Jobs
| job_id | 스케줄 | 역할 |
|---|---|---|
| market_price_collect | 매일 18:30 KST | 시세 수집 |
| dart_collect | 매일 07:00 KST | DART 공시 수집 |
| nba_evaluation | 매일 08:00 KST | NBA 대상 고객 평가 |
| aftercare_evaluation | 매일 08:10 KST | 사후관리 이벤트 평가 |
| embedding_refresh | 매일 02:00 KST | 신규 청크 임베딩 |

## Distributed Lock
- Redis SETNX 기반 잠금. TTL = job 최대 예상 실행 시간 × 1.5.
- lock value는 owner_id + timestamp로 저장하고, release 시 value 일치 여부를 확인한다.
- 잠금 획득 실패 시 job SKIPPED (batch_job_logs에 기록).
- lock TTL 만료/재시도는 batch_job_logs와 운영 로그에 기록한다.

## Error Handling
- job 실패 시 batch_job_logs status_code=FAILED + error_message.
- 현재는 batch_job_logs, `/batch/status`, `/data/readiness`, 운영 로그로 ADMIN 상태를 확인한다. WebSocket `batch_status_change` 알림은 ADR-001 구현 후 future path이다.
- 재시도: 30분 후 1회 자동 재실행 (영구 실패 시 알림 종료).
