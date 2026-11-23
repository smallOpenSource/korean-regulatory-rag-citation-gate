# TEST-01 Test Strategy

## Scope
- 실제 고객 데이터 테스트 환경 사용 금지 (합성 데이터만).
- mocking/test double/local simulator 금지: 외부 API도 사용자가 제공한 실제 sandbox/live credential로 검증한다.

## Test Types
| 유형 | 도구 | 대상 |
|---|---|---|
| Unit | pytest | service 로직, NBA/aftercare 평가 함수 |
| Integration | pytest + asyncpg + real external credentials | DB 쿼리, API 라우트, Redis, 내부 BGE, BROKER/DART/ECOS/공공데이터포털/SMTP |
| E2E | Playwright | role matrix, Customer 360 합성 고지/source_as_of, Batch provider degraded 상태, 상담 생성→완료 전체 흐름 |
| Load | locust | NBA 배치 평가, 동시 상담 생성 |

## Test Data
- db/fixtures/seed_test.sql: 합성 branches, employees, customers, products.
- 모든 고객 데이터: 가상의 이름 + 무작위 자산 규모.

## CI Pipeline
1. lint (ruff + tsc --noEmit)
2. unit tests
3. integration tests (실제 PostgreSQL/Redis 및 제공된 외부 credential)
4. build (vite build)
5. E2E (playwright, staging URL)
6. local verification evidence when services are available:
   `scripts/run_verification_gate.sh --continue-on-failure`

## Coverage Target
- Backend: 70% 이상 (compliance_check, nba_evaluation 집중).
- Frontend: 주요 흐름 E2E 커버.


## External Test Result Semantics
- PASS: 실제 configured credential로 안전한 read-only/sandbox 호출 성공.
- FAIL: credential은 있으나 provider 응답이 계약과 다르거나 보안/권한 오류가 발생.
- SKIPPED/BLOCKED_WITH_REDACTED_REASON: credential 미존재, provider outage, 네트워크 차단 등 외부 사유.
- 어떤 경우에도 mock 성공, silent success, secret 포함 실패 로그를 남기지 않는다.
- Frontend API/UI 회귀는 `vi.mock`, `vi.fn`, fetch test double 대신 실제 local API와
  합성 seed 계정 기반 Playwright E2E로 검증한다.
- Provider normalization 정적 게이트는 `batch_job_logs.status_code` 어휘를
  `RUNNING/DONE/FAILED/SKIPPED`으로 고정하고, 공식 KRX 행은 `source_code=KRX`와
  `OFFICIAL_KRX_APPROVED` 증거로만, 보조 PYKRX 행은 `PYKRX_AUXILIARY_APPROVED` 라벨로만
  READY 취급되는지 검사한다.
- KRX/PYKRX 정책 게이트는 공식 branch에서는 `HARNESS_BATCH_KRX_SOURCE=KRX`와
  `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`, 보조 branch에서는
  `HARNESS_BATCH_KRX_SOURCE=PYKRX`와 `PYKRX_AUXILIARY_APPROVED` 없이는 READY로 취급하지 않고,
  API/UI가 branch별 정책 라벨을 그대로 표시하는지 검사한다.
- T55 readiness 회귀 테스트는 가격행, KRX provider `DONE`, 런타임 정책, 그리고
  `batch_provider_evidence.provider_detail_json.source_policy_code`가 동일 branch로 일치할 때만
  `provider.krx_policy`가 READY가 되는지 검사한다.


## Contract Consistency Tests
- AI-05 endpoint matrix와 API-01 response status/ai_jobs/audit/ai_outputs 정책 일치 여부를 검사한다.
- OBS-02 canonical audit action_code 외 값이 코드/테스트에 등장하면 실패한다.
- DB-02와 DB-04 batch table column lists가 불일치하면 실패한다.
- order_simulation code path에 BROKER order/trading mutation endpoint 문자열이 있으면 실패한다.
- `tests/test_batch_pipeline_runner.py` locks the committed batch runner CLI, verification-gate
  script contents, and SQL_ID postcondition statements.
- `scripts/validate_architecture_contracts.py` locks Stage 0.5/current-contract doc sync for
  WebSocket, email authority, dependency, large-module, and operations status contracts.
- `tests/test_verification_contracts.py` bans frontend mock/test-double helpers and locks provider
  normalization hard rules: stable batch status vocabulary, `market_price_bars` source CHECK without
  official `KRX`, and explicit `PYKRX` fallback labeling.

## Verification Gate Scripts
- `scripts/run_batch_pipeline.sh --profile full-mvp --all-stages --report .omx/reports/batch/latest.json`
  is the reproducible batch evidence command.
- Recent-30-day acceptance evidence uses
  `scripts/run_batch_pipeline.sh --profile full-mvp --all-stages --lookback-days 30 --as-of-date 2026-05-16 --provider-strictness required --report .omx/reports/batch/recent-30d-required-<ts>.json`.
  The companion all-provider diagnostic run uses `--provider-strictness all` and is evidence only;
  optional BROKER/DATA_GO_KR failures from that diagnostic must not be reported as acceptance blockers.
- Batch report assertions must inspect `postconditions.provider_window`: PYKRX/KRX trading-day
  coverage must be more than one day for a 30-day historical claim, ECOS must have real
  observations, and OpenDART must have persisted document lineage or an explicit blocking failure.
- Serviceable top-200 evidence must run `scripts/run_serviceable_canonical_readiness.py` or, for
  validator-only reruns, `scripts/verify_serviceable_readiness.py` against
  `.omx/reports/verification/krx-source-governance-latest.json`,
  `.omx/reports/verification/serviceable-top200-30d-latest.json`, and `/data/readiness`. The
  validator must include `--require-docs-sync`, `--no-fabricated-provider-rows`, and
  `--result-json`; the result JSON path must be
  `.omx/specs/autoresearch-service-readiness-top200-30d/result.json`, and the result is passing only
  when `DOMESTIC_TOP200_MARKET_CAP` has `selected_count >= 200`, `coverage_ratio=1.0`,
  `missing_member_days=0`, official `OFFICIAL_KRX_APPROVED` policy evidence, OpenDART/ECOS lineage,
  docs sync, and no fabricated provider rows.
- Artifact-producer regression tests must prove latest pointers are refreshed with current
  fail-closed BLOCKED evidence instead of leaving stale green artifacts, source-governance reports
  contain no KRX secrets, and every DB proof query is raw SQL with a leading `sql_id`.
- Secret scan evidence must cover `.omx/reports`, validator output, logs, and API samples.
  `AUTH_KEY`, `KRX_API_KEY`, provider keys, bearer tokens, and database credentials must be
  redacted as `<redacted>` rather than echoed in failure output.
- `/opt/conda/envs/wm_env/bin/python scripts/t55_schema_preflight.py` is the
  T55 Stage 0 schema/Redis evidence command. Its SQL constants are covered by
  `tests/test_sql_contracts.py`, and its JSON output must stay secret-free.
- `scripts/run_verification_gate.sh` aggregates runtime status, ruff, pytest, web
  typecheck/lint/unit/build, Playwright, and the batch runner into a timestamped Markdown report.
- `scripts/verify_total_product_readiness.py --verification-gate-report <gate.md> --serviceable-result-json .omx/specs/autoresearch-service-readiness-top200-30d/result.json --result-json .omx/reports/verification/total-product-readiness-result.json`
  is the total-product readiness validator. It fails closed when a required gate section such as
  Playwright E2E or required-provider batch acceptance is absent, when a section reports nonzero
  exit status despite success-looking output, when serviceable top-200 evidence is not passed, or
  when docs/runbooks lack the false-green controls.
- Use `--skip-e2e` or `--skip-batch` only to document unavailable browser/services; do not turn a
  skipped external dependency into a green result. The total-product readiness validator treats
  missing E2E/batch evidence as `failed`, not `passed`.
