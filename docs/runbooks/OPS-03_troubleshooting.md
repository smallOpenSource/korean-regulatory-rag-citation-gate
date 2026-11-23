# OPS-03 Troubleshooting

## Common Issues

### AI 호출 실패 (429 / 503)
- Azure API 상태 확인 (status.azure.com).
- AZURE_OPENAI_ENDPOINT, API_KEY 환경변수 확인.
- 로그에서 latency_ms 이상값 확인.
- 재시도 3회 실패 → 사용자에게 오류 표시 (정상 동작).

### 배치 FAILED
- /batch/status 또는 batch_job_logs 확인.
- error_message 필드 확인.
- 외부 API (BROKER, DART) 장애 여부 확인.
- 폴백 소스 (FDR, pykrx) 수동 실행 테스트.

### Serviceable top-200 readiness BLOCKED 또는 stale green 의심
- 공식 KRX top-200/30일 서비스 가능성은 `DOMESTIC_TOP200_MARKET_CAP` universe에서
  `selected_count >= 200`, `coverage_ratio=1.0`, `missing_member_days=0`, Redis ping/lock,
  OpenDART/ECOS lineage, `OFFICIAL_KRX_APPROVED` 정책 증거가 모두 맞을 때만 READY로 본다.
- 전체 재생성은 프로젝트 루트에서 다음 명령으로 실행한다.
  ```bash
  /opt/conda/envs/wm_env/bin/python scripts/run_serviceable_canonical_readiness.py \
    --env-file .env
  ```
- 이미 공식 provider rows가 DB에 있고 검증/캡처만 다시 할 때는 다음처럼 batch run을 건너뛴다.
  ```bash
  /opt/conda/envs/wm_env/bin/python scripts/run_serviceable_canonical_readiness.py \
    --env-file .env \
    --skip-batch-run
  ```
- wrapper는 fail-closed로 `.omx/reports/verification/krx-source-governance-latest.json`,
  `.omx/reports/verification/serviceable-top200-30d-latest.json`,
  `.omx/reports/verification/data-readiness-latest.json`, 그리고
  `.omx/specs/autoresearch-service-readiness-top200-30d/result.json`을 현재 APPROVED/READY 또는
  BLOCKED 상태로 갱신한다. 실패 후 과거 green latest 파일을 그대로 두지 않는다.
- validator만 직접 실행할 때도
  `scripts/verify_serviceable_readiness.py --require-docs-sync --no-fabricated-provider-rows
  --result-json .omx/specs/autoresearch-service-readiness-top200-30d/result.json` 형태를 유지한다.
- PYKRX/Data.go.kr/BROKER/current snapshot row는 이 official top-200 gate를 닫을 수 없다. provider
  row가 `is_synthetic=true` 이거나 `AUTH_KEY`, `KRX_API_KEY`, bearer token, DB password가 보고서에
  평문으로 남으면 BLOCKED로 처리하고 `<redacted>` evidence만 남긴다.

### NBA 미생성
- nba_evaluation job 실행 여부 확인 (batch_job_logs).
- nba_actions 중복 방지 조건 확인 (PENDING/IN_PROGRESS 중복).
- 배치 스케줄 시간 확인 (ASYNC-01 참조).

### WebSocket 연결 끊김
- Current status: WebSocket push is `backlog/not-current-contract`; first verify polling fallbacks (`/ai-jobs/{job_id}`, `/batch/status`, `/data/readiness`).
- If ADR-001 implementation is present in a future branch, check Nginx WebSocket proxy_read_timeout 설정 (권장 3600).
- Redis 연결 상태 확인.
- 클라이언트 재연결 로직 정상 동작 여부 확인.
- Do not treat missing WebSocket delivery as a current production incident until the route is promoted to API-01.

### DB 연결 고갈
- asyncpg pool_size, max_overflow 설정 확인 (CFG-01).
- 장기 트랜잭션 확인: `SELECT * FROM pg_stat_activity`.

### 상태 점검 결과 blocked
- `scripts/status.sh --deep --no-fail`의 `status=blocked failures=N no_fail=1`는 정직한 차단 증거다.
- process/HTTP/PostgreSQL/Redis 중 어떤 줄이 blocked인지 확인하고, secret-free class reason만 공유한다.
- `.env` 원문, bearer token, provider key, SMTP password, database password를 티켓이나 보고서에 붙여 넣지 않는다.
