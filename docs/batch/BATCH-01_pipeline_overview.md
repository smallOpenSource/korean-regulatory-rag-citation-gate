# BATCH-01 Pipeline Overview

## Data Flow
```
[외부 소스] → Collect → raw_documents
raw_documents → Transform → documents + document_chunks (텍스트)
raw_documents → Transform → market_price_bars, financial_ratios, macro_indicators (정형)
document_chunks → Embed → document_chunks.embedding (pgvector)
document_chunks → RAG Refresh → 검색 인덱스 최신화
```

## Job Dependencies
1. Collect jobs: 외부 소스 → raw_documents (병렬 가능)
2. Transform jobs: raw_documents → 정규화 (collect 완료 후)
3. Embed job: 신규 청크만 배치 임베딩 (transform 완료 후)
4. NBA/Aftercare evaluation: market_price_bars 최신화 후 실행

## Failure Policy
- 개별 row 실패: 스킵 후 rows_failed 카운트.
- 전체 job 실패: status_code=FAILED, 30분 후 1회 재시도.
- 재시도 실패 시 ADMIN WebSocket 알림은 `/ws`의 `batch_status_change` transport를 사용한다. 현재 운영 증거의 기준은 여전히 batch_job_logs와 /batch/status 조회다.

## Implemented Batch Foundation
- Batch jobs use Redis `SETNX` owner-value locks through `apps/api/harness/core/redis_client.py` and persist RUNNING/DONE/FAILED/SKIPPED rows in `batch_job_logs`.
- `apps/api/harness/batch/jobs.py` records SKIPPED when a lock is already held and releases locks only when the owner value matches.
- `apps/api/harness/batch/providers.py` wraps real provider collectors in the same lock/log boundary. Provider failures are redacted before persistence; unavailable providers create SKIPPED/FAILED evidence, never local success rows.
- V015 adds `batch_provider_evidence` as the provider-detail source of truth. `batch_job_logs.status_code`
  remains limited to `RUNNING`, `DONE`, `FAILED`, and `SKIPPED`; provider-specific detail uses
  `PROVIDER_DONE`, `PROVIDER_NO_DATA`, `PROVIDER_SKIPPED_CONFIG`,
  `PROVIDER_SKIPPED_DISABLED`, `PROVIDER_FAILED_AUTH`, `PROVIDER_FAILED_RATE_LIMIT`,
  `PROVIDER_FAILED_SCHEMA`, and `PROVIDER_FAILED_NETWORK`.
- Provider-labelled persistence is limited to rows parsed from provider payloads: BROKER/DATA_GO_KR
  market prices, ECOS macro indicators, DART raw document lineage, and explicitly enabled
  KRX/pykrx market prices.
- Market-price collectors write only parsed live provider rows to `market_price_bars`; after a
  successful insert, the shared collector marks rows `VALID` only when the DB-level OHLC checks pass.
  This quality promotion never fabricates missing provider rows.
- `apps/api/harness/batch/documents.py` provides the derived-data stage for unprocessed
  `raw_documents` → `documents`/`document_chunks`, RAG readiness snapshots, and aftercare/NBA
  refresh from persisted customer/portfolio/product state.
- Derived aftercare/NBA refresh never creates provider-labelled market data and never fabricates AI
  script metadata; unavailable provider or embedding paths remain visible as SKIPPED/FAILED
  `batch_job_logs`.

## Operator Runner
- The implemented local runner is `apps/api/harness/batch/runner.py`, invoked through
  `scripts/run_batch_pipeline.sh`.
- Canonical full local command:
  ```bash
  ./scripts/run_batch_pipeline.sh \
    --profile full-mvp \
    --all-stages \
    --report .omx/reports/batch/latest.json
  ```
- Recent-30-day acceptance command:
  ```bash
  ./scripts/run_batch_pipeline.sh \
    --profile full-mvp \
    --all-stages \
    --lookback-days 30 \
    --as-of-date 2026-05-16 \
    --provider-strictness required \
    --embedding-batch-size 16 \
    --report .omx/reports/batch/recent-30d-required-20260516T000000Z.json
  ```
- Serviceable official-KRX acceptance uses the `full-mvp` operational baseline plus
  `HARNESS_BATCH_KRX_UNIVERSE_CODE=DOMESTIC_TOP200_MARKET_CAP`, universe size `200`,
  KOSPI/KOSDAQ markets, `HARNESS_BATCH_KRX_SOURCE=KRX`, and
  `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`. `READY` requires selected_count >= 200,
  30-calendar-day official expected-trading-day coverage ratio `1.0`, and
  `missing_member_days=0`; PYKRX/BROKER/DATA_GO_KR evidence cannot satisfy this official top-200 gate.
- `--provider-strictness required` is the acceptance mode: seed, KRX/PYKRX historical price rows,
  OpenDART documents, ECOS observations, transform/embed, derived rows, and house-view evidence must
  close. `--provider-strictness all` is non-acceptance diagnostic mode and also fails optional
  current/as-of providers such as BROKER or DATA_GO_KR when they are skipped or failed.
- Equivalent explicit stage list:
  `--stages seed,provider,transform,embed,derived,house-view`.
- The runner writes a JSON report with selected stages, individual `batch_job_logs` evidence, fatal
  local-stage failures, SQL_ID-protected postcondition counts, `provider_contracts`, and
  `provider_governance`. The governance matrix preserves official KRX vs PYKRX branch separation and
  records that only `KRX` + `OFFICIAL_KRX_APPROVED` may satisfy official top-200/30-day readiness.
- The canonical serviceable closure command is
  `/opt/conda/envs/wm_env/bin/python scripts/run_serviceable_canonical_readiness.py --env-file .env`.
  Use `--skip-batch-run` only for a validator/capture rerun against already-persisted provider rows.
  It is fail-closed: `krx-source-governance-latest.json`,
  `serviceable-top200-30d-latest.json`, and `data-readiness-latest.json` are refreshed with the
  current APPROVED/READY or BLOCKED state, so stale green evidence is not reused after a failed live
  capture. The batch artifact must prove raw-SQL PostgreSQL evidence plus Redis ping/lock evidence
  for the official top-200 contract.
- Recent-window reports include `as_of_date`, `requested_lookback_days`,
  `requested_window_start`, `requested_window_end`, `provider_strictness`,
  `provider_strictness_failures`, and `postconditions.provider_window` proof counts for PYKRX/KRX
  trading-day coverage, ECOS observations, and OpenDART document lineage.
- Missing provider credentials or missing BGE keys are not treated as mock success. They produce
  explicit SKIPPED logs and report entries. Provider HTTP/contract failures produce FAILED evidence
  without inserting fabricated provider-labelled rows.
- `/batch/status` attaches persisted `provider_evidence` rows to matching provider job logs. A
  provider `PROVIDER_NO_DATA` row means the upstream provider was reached and returned no usable rows
  for the target; it must be displayed as honest unavailable evidence, not parser failure and not READY.
- The report includes `provider_contracts`, a redacted source-contract matrix for BROKER,
  DATA_GO_KR, OpenDART, ECOS, and KRX/pykrx. `APP_ENV=production`, `HARNESS_PROVIDER_STRICT=true`,
  or `--strict-external` makes provider `SKIPPED`/`FAILED` evidence exit `2`; local development
  defaults to required-provider acceptance for recent-window runs; use
  `--provider-strictness all` only to collect diagnostic optional-provider blockers.
- KRX-family batch collection has two fail-closed branches: official `KRX` OpenAPI with `HARNESS_BATCH_KRX_SOURCE=KRX`, `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`, `KRX_API_BASE_URL`, and `KRX_API_KEY` supplied as the `AUTH_KEY` header; or explicit non-production `PYKRX` fallback with `PYKRX_AUXILIARY_APPROVED` and importable `pykrx>=1.2.8`. Official failure never falls back to PYKRX automatically.
- The current product does not expose `POST /batch/run`; the Batch Monitor UI reads
  `/batch/status` and `/data/readiness` only. WebSocket transport exists for status fanout, but
  async queue/run-control semantics remain unimplemented until a bounded server contract exists.

## Scheduler Controls
- `scripts/run_batch_scheduler.py --plan-only` prints the scheduler plan, built-in jobs, and
  provider-governance matrix without secret values.
- `scripts/run_batch_scheduler.py --run-once` executes every runnable scheduled job once by calling
  `apps/api/harness/batch/runner.py`; it does not bypass Redis owner locks or batch_job_logs.
- Built-in `rag_refresh` runs `transform,embed` and built-in `derived_refresh` runs
  `derived,house-view`. They are controlled by `HARNESS_BATCH_RAG_REFRESH_ENABLED`,
  `HARNESS_BATCH_RAG_REFRESH_INTERVAL_SECONDS`, `HARNESS_BATCH_DERIVED_REFRESH_ENABLED`, and
  `HARNESS_BATCH_DERIVED_REFRESH_INTERVAL_SECONDS`.
- Built-in `serviceable_top200_30d` stays disabled until
  `HARNESS_BATCH_SERVICEABLE_TOP200_SCHEDULER_ENABLED=true` and official KRX governance is complete.
  If the env requests PYKRX, omits the KRX key/base URL, lowers universe size, or lowers coverage
  ratio, the scheduler reports `BLOCKED` rather than running an auxiliary or partial official gate.
- `HARNESS_BATCH_SCHEDULES_JSON` can define custom jobs, but all jobs remain blocked unless the
  global `HARNESS_BATCH_SCHEDULER_ENABLED=true` gate is set.

## Scheduler Controls
- `scripts/run_batch_scheduler.py --plan-only` prints the scheduler plan, built-in jobs, and
  provider-governance matrix without secret values.
- `scripts/run_batch_scheduler.py --run-once` executes every runnable scheduled job once by calling
  `apps/api/harness/batch/runner.py`; it does not bypass Redis owner locks or batch_job_logs.
- Built-in `rag_refresh` runs `transform,embed` and built-in `derived_refresh` runs
  `derived,house-view`. They are controlled by `HARNESS_BATCH_RAG_REFRESH_ENABLED`,
  `HARNESS_BATCH_RAG_REFRESH_INTERVAL_SECONDS`, `HARNESS_BATCH_DERIVED_REFRESH_ENABLED`, and
  `HARNESS_BATCH_DERIVED_REFRESH_INTERVAL_SECONDS`.
- Built-in `serviceable_top200_30d` stays disabled until
  `HARNESS_BATCH_SERVICEABLE_TOP200_SCHEDULER_ENABLED=true` and official KRX governance is complete.
  If the env requests PYKRX, omits the KRX key/base URL, lowers universe size, or lowers coverage
  ratio, the scheduler reports `BLOCKED` rather than running an auxiliary or partial official gate.
- `HARNESS_BATCH_SCHEDULES_JSON` can define custom jobs, but all jobs remain blocked unless the
  global `HARNESS_BATCH_SCHEDULER_ENABLED=true` gate is set.

## Scheduler Controls
- `scripts/run_batch_scheduler.py --plan-only` prints the scheduler plan, built-in jobs, and
  provider-governance matrix without secret values.
- `scripts/run_batch_scheduler.py --run-once` executes every runnable scheduled job once by calling
  `apps/api/harness/batch/runner.py`; it does not bypass Redis owner locks or batch_job_logs.
- Built-in `rag_refresh` runs `transform,embed` and built-in `derived_refresh` runs
  `derived,house-view`. They are controlled by `HARNESS_BATCH_RAG_REFRESH_ENABLED`,
  `HARNESS_BATCH_RAG_REFRESH_INTERVAL_SECONDS`, `HARNESS_BATCH_DERIVED_REFRESH_ENABLED`, and
  `HARNESS_BATCH_DERIVED_REFRESH_INTERVAL_SECONDS`.
- Built-in `serviceable_top200_30d` stays disabled until
  `HARNESS_BATCH_SERVICEABLE_TOP200_SCHEDULER_ENABLED=true` and official KRX governance is complete.
  If the env requests PYKRX, omits the KRX key/base URL, lowers universe size, or lowers coverage
  ratio, the scheduler reports `BLOCKED` rather than running an auxiliary or partial official gate.
- `HARNESS_BATCH_SCHEDULES_JSON` can define custom jobs, but all jobs remain blocked unless the
  global `HARNESS_BATCH_SCHEDULER_ENABLED=true` gate is set.

## Data Readiness Surface
- `/data/readiness` reports API/Web/E2E readiness without fabricating provider success.
- `READY` means the synthetic operational baseline and required derived artifacts are present.
- `BLOCKED` means a required baseline such as active customers, portfolios, active house view, or BGE-embedded RAG chunks is missing.
- `DEGRADED` means current required data gates are incomplete or degraded. Historical provider
  `SKIPPED`/`FAILED`/no-data evidence remains visible for audit in `batch_status_summary` and
  `provider.recent_batches`, but it does not downgrade `/data/readiness.status_code` after the
  current domestic-market and T55 gates are `READY`.
- The domestic-market readiness checks include `provider.krx_policy`; it is `READY` only when an
  official KRX persisted rows plus `OFFICIAL_KRX_APPROVED` provider evidence exist, or current PYKRX evidence carries
  `source_policy_code=PYKRX_AUXILIARY_APPROVED`.
- Serviceable domestic-market readiness adds `domestic_market.top200_coverage` for
  `DOMESTIC_TOP200_MARKET_CAP`: universe counts, official KRX source policy, expected/observed
  member-day denominator, coverage ratio, and blocking reasons. Partial coverage is `DEGRADED` or
  `BLOCKED`, not a green provider-history warning.
- T55 provider readiness additionally requires the runtime policy branch to match persisted evidence: official `KRX` rows with `OFFICIAL_KRX_APPROVED`, or PYKRX rows with `PYKRX_AUXILIARY_APPROVED`; PYKRX price rows or provider `DONE` logs alone
  remain blocked.
- `/batch/status` remains the ADMIN batch log surface and returns `{items, limit, offset}` from `batch_job_logs`.

## Full-MVP Provisioning Order
1. `db/migrator.py` applies V001~V011 raw-SQL migrations.
2. `db/seed.py --profile full-mvp` applies deterministic Korean PB/WM customer, product, portfolio, consultation, and MANUAL baseline RAG fixtures.
3. Provider collectors run with Redis locks and either insert real provider rows or write sanitized SKIPPED/FAILED logs.
4. Transform converts raw documents to documents/chunks; MANUAL baseline chunks are present but unembedded after seed.
5. Internal BGE embedding refresh writes 1024-d vectors and marks chunks embedded only after real BGE validation succeeds.

Run the operator batch command after migrations when PostgreSQL, Redis, and any intended provider/BGE env are configured:

```bash
./scripts/run_batch_pipeline.sh \
  --profile full-mvp \
  --all-stages \
  --lookback-days 30 \
  --as-of-date 2026-05-16 \
  --provider-strictness required \
  --report .omx/reports/batch/full-mvp-latest.json
```

`--all-stages` executes the explicit stage order `seed,provider,transform,embed,derived,house-view`. The JSON report records per-stage `results` from the `batch_job_logs` boundary plus `postconditions.batch_job_logs`, `postconditions.readiness`, and `postconditions.rag_readiness` DB evidence. Mandatory local stages (`seed`, `transform`, `derived`, `house-view`) fail the command on `FAILED`; provider and BGE unavailability must remain visible as sanitized `SKIPPED`/`FAILED` evidence and must not be counted as fabricated local success. The report also exposes `status_code`, `local_status_code`, `provider_status_code`, `local_ok`, and `provider_evidence_ok` so local mandatory success is separate from provider evidence.

Seed success is not provider success. Market/public provider data remains blocked until real configured providers complete. Seed customer numbers remain stable internal IDs, while UI/API display uses Korean `customer_name`, portfolio names, and product names.
