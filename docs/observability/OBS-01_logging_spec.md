# OBS-01 Logging Specification

## Log Format
- 형식: JSON (structlog 사용)
- 필드: timestamp, level, service, trace_id, actor_id, action, resource, message, error

## Log Levels
- DEBUG: 개발 환경 쿼리 파라미터 등
- INFO: 요청 처리, 배치 완료, AI 호출 성공
- WARNING: 폴백 발생, 재시도, 낮은 RAG 신뢰도
- ERROR: 예외, AI 호출 실패, DB 오류

## AI Call Log Fields
| 필드 | 내용 |
|---|---|
| model_name | 호출 모델명 |
| agent_id | AI-02 에이전트 ID |
| prompt_tokens | 입력 토큰 수 |
| completion_tokens | 출력 토큰 수 |
| latency_ms | 응답 시간 |
| resource_type | 연결 리소스 유형 |
| resource_id | 연결 리소스 ID |

## Alert Thresholds
| 조건 | 알림 방식 |
|---|---|
| batch job FAILED | current: 로그 ERROR + `/batch/status`; future: ADMIN WebSocket after ADR-001 |
| AI 호출 실패 3회 연속 | 로그 CRITICAL |
| RAG cosine similarity < 0.7 | 로그 WARNING |
| DB 연결 실패 | 로그 CRITICAL + 프로세스 재시작 시도 |

## Audit vs Application Log
- audit_logs (DB): 비즈니스 이벤트, 규정 준수 목적 (SEC-01, BIZ-06 참조).
- 애플리케이션 로그 (structlog): 기술 이벤트, 디버깅 목적.
두 로그는 trace_id로 연결 가능.

## Operations Status Evidence
- Local status evidence command: `scripts/status.sh --deep --no-fail`. It reports process, HTTP, PostgreSQL, and Redis status with sanitized class-level failure reasons.
- Current operations readiness is pull-based through `/health`, `/batch/status`, `/data/readiness`, and reports under `.omx/reports/`.
- WebSocket operations alerts are `backlog/not-current-contract` until ADR-001 is implemented.
- Secret values, provider keys, bearer tokens, SMTP credentials, and database passwords must be redacted as `<redacted>` in logs and reports.
