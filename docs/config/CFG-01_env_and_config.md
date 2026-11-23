# CFG-01 Environment and Config

## Environment Variable Catalog
```bash
# Python runtime
PYTHON_PATH=/opt/conda/envs/wm_env/bin/python
PYTHON_VERSION=3.11.5
PYTHON_ENV_NAME=wm_env
PYTHON_ENV_PREFIX=/opt/conda/envs/wm_env

# Database (asyncpg raw SQL)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=harness
POSTGRES_USER=harness_app
POSTGRES_PASSWORD=...
DATABASE_URL=postgresql://harness_app:...@localhost:5432/harness

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_SENTINEL_HOSTS=
REDIS_SENTINEL_SERVICE_NAME=
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=...
REDIS_DB=0
REDIS_SOCKET_TIMEOUT=5
REDIS_SOCKET_CONNECT_TIMEOUT=5
REDIS_MAX_CONNECTIONS=20

# Azure OpenAI / Microsoft Foundry (LLM only)
AZURE_OPENAI_ENDPOINT=https://xxx.openai.azure.com
AZURE_OPENAI_BASE_URL=https://xxx.openai.azure.com/openai/v1/
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT_NAME=...
AZURE_GPT5_DEPLOYMENT=...
AZURE_GPT5_MINI_DEPLOYMENT=...
# AZURE_OPENAI_API_VERSION is legacy-only when using dated Azure API versions.

# Internal BGE Embedding & Rerank API
EMBEDDING_PROVIDER=internal_bge
BGE_EMBEDDING_API_URL=https://internal.example/embeddings
BGE_AUTH_SCHEME=Bearer
BGE_EMBEDDING_API_KEY=...
BGE_EMBEDDING_MODEL=BAAI/bge-m3
BGE_EMBEDDING_DIMENSIONS=1024
BGE_EMBEDDING_BATCH_SIZE=100
BGE_EMBEDDING_TIMEOUT_SECONDS=300
BGE_BATCH_SIZE=16
BGE_RERANK_API_URL=https://internal.example/rerank
BGE_RERANK_API_KEY=...
BGE_RERANK_MODEL=BAAI/bge-reranker-v2-m3
BGE_RERANK_TOP_N=5

# JWT
JWT_SECRET=...
JWT_ACCESS_EXPIRE_SECONDS=3600
JWT_REFRESH_EXPIRE_SECONDS=604800
# HttpOnly refresh-token cookie; browser JS must never read or persist this token.
AUTH_REFRESH_COOKIE_NAME=harness_refresh_token
AUTH_REFRESH_COOKIE_SECURE=false
AUTH_REFRESH_COOKIE_SAMESITE=lax
AUTH_REFRESH_COOKIE_PATH=/
AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS=604800

# 증권사 Open API (운영자 주입)
# Brokerage Open API base URL (set your provider endpoint)
BROKER_BASE_URL=
BROKER_APP_KEY=...
BROKER_APP_SECRET=...
BROKER_ACCOUNT_NO=...
BROKER_ACCOUNT_PROD_CD=...
BROKER_IS_VIRTUAL=false
BROKER_TIMEOUT_SECONDS=10
# Provider-specific read-only endpoint paths and transaction ids (set from your provider docs)
BROKER_TOKEN_PATH=
BROKER_QUOTE_PATH=
BROKER_QUOTE_TR_ID=
BROKER_BALANCE_PATH=
BROKER_BALANCE_TR_ID=
HARNESS_BATCH_BROKER_TICKERS=005930
BROKER_MARKET_CODE=J

# DART / ECOS / 공공데이터포털
DART_API_KEY=...
ECOS_API_KEY=...
DATA_GO_KR_SERVICE_KEY_ENCODING=...
DATA_GO_KR_SERVICE_KEY_DECODING=...
DART_API_BASE_URL=https://opendart.fss.or.kr
ECOS_API_BASE_URL=https://ecos.bok.or.kr/api
DATA_GO_KR_API_BASE_URL=https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService
DATA_GO_KR_MARKET_PATH=/getStockPriceInfo
DATA_GO_KR_TICKER_FIELD=srtnCd
DATA_GO_KR_DATE_FIELD=basDt
DATA_GO_KR_CLOSE_FIELD=clpr
DATA_GO_KR_OPEN_FIELD=mkp
DATA_GO_KR_HIGH_FIELD=hipr
DATA_GO_KR_LOW_FIELD=lopr
DATA_GO_KR_VOLUME_FIELD=trqu
DATA_GO_KR_NUM_ROWS=10
HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON=[{"path":"/getStockPriceInfo","query":{"numOfRows":5,"likeSrtnCd":"005930"},"ticker_field":"srtnCd","date_field":"basDt","close_field":"clpr","open_field":"mkp","high_field":"hipr","low_field":"lopr","volume_field":"trqu"}]
DART_TIMEOUT_SECONDS=10
HARNESS_BATCH_DART_BEGIN_DATE=2026-05-01
HARNESS_BATCH_DART_END_DATE=2026-05-15
HARNESS_BATCH_DART_CORP_CODES=00126380
HARNESS_BATCH_DART_TARGETS_JSON=[{"stock_code":"005930","report_type":"A","lookback_days":365,"page_count":100}]
HARNESS_BATCH_DART_LOOKBACK_DAYS=365
HARNESS_BATCH_DART_DISCOVERY_STOCK_CODES=005930,000660,035420,005380,068270
HARNESS_BATCH_DART_PAGE_COUNT=100
ECOS_TIMEOUT_SECONDS=10
HARNESS_BATCH_ECOS_START_DATE=2026-05-01
HARNESS_BATCH_ECOS_END_DATE=2026-05-15
ECOS_STATISTIC_CODE=722Y001
ECOS_CYCLE=D
ECOS_INDICATOR_NAME=base_rate
ECOS_UNIT=연%
ECOS_ITEM_CODES=0101000
HARNESS_BATCH_ECOS_LOOKBACK_DAYS=14
HARNESS_BATCH_ECOS_DATE_LAG_DAYS=1
HARNESS_BATCH_ECOS_TARGETS_JSON=[{"statistic_code":"722Y001","cycle":"D","indicator_name":"base_rate","unit":"연%","item_codes":["0101000"],"lookback_days":14,"date_lag_days":1},{"statistic_code":"731Y001","cycle":"D","indicator_name":"usd_krw_reference_rate","unit":"원","item_codes":["0000001"],"lookback_days":14,"date_lag_days":1}]
KRX_API_BASE_URL=https://data-dbg.krx.co.kr
KRX_API_KEY=
KRX_API_TIMEOUT_SECONDS=20
KRX_API_RATE_LIMIT_SLEEP_MS=200
HARNESS_BATCH_KRX_ENABLED=true
HARNESS_BATCH_KRX_SOURCE=KRX
HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED
HARNESS_BATCH_KRX_MARKETS=KOSPI,KOSDAQ
HARNESS_BATCH_KRX_TICKERS=005930
HARNESS_BATCH_KRX_UNIVERSE_CODE=DOMESTIC_TOP200_MARKET_CAP
HARNESS_BATCH_KRX_UNIVERSE_SIZE=200
HARNESS_BATCH_KRX_UNIVERSE_MARKETS=KOSPI,KOSDAQ
HARNESS_BATCH_KRX_UNIVERSE_EXCLUDE_PREFERRED=true
HARNESS_BATCH_KRX_MIN_TRADING_DAY_COVERAGE_RATIO=1.0
HARNESS_BATCH_KRX_RESOLVE_AS_OF_TRADING_DAY=true
HARNESS_BATCH_KRX_LOOKBACK_DAYS=30
HARNESS_BATCH_KRX_START_DATE=2026-04-15
HARNESS_BATCH_KRX_END_DATE=2026-05-15
HARNESS_BATCH_LOOKBACK_DAYS=30
HARNESS_BATCH_AS_OF_DATE=2026-05-16
HARNESS_PROVIDER_STRICT=false
HARNESS_PROVIDER_STRICTNESS=required

# Email (Brevo SMTP or compatible SMTP)
HARNESS_EMAIL_SEND_ENABLED=false
BREVO_API_KEY=...
BREVO_API_ENDPOINT=...
BREVO_SENDER_EMAIL=...
BREVO_SENDER_NAME=...
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_SENDER_EMAIL=...
SMTP_SENDER_NAME=Harness
TEST_RECIPIENT_EMAIL=...
SMTP_TIMEOUT_SECONDS=10

# App / Frontend
APP_ENV=development
LOG_LEVEL=INFO
VITE_API_BASE_URL=/api
VITE_WS_BASE_URL=/api/ws

# Local PoC lifecycle scripts
HARNESS_ROOT=<repo-root>
HARNESS_API_HOST=127.0.0.1
HARNESS_API_PORT=8000
HARNESS_WEB_HOST=0.0.0.0
HARNESS_WEB_PORT=5173
HARNESS_STATUS_TIMEOUT_SECONDS=5
HARNESS_STOP_TIMEOUT_SECONDS=10
HARNESS_DRY_RUN=0
HARNESS_AUTO_NPM_INSTALL=0
CORS_ENABLED=false
CORS_ALLOWED_ORIGINS=
```

## Rules
- `PYTHON_PATH` is the canonical backend/batch/test interpreter and must point to `/opt/conda/envs/wm_env/bin/python` with `PYTHON_VERSION=3.11.5`.
- `DATABASE_URL` uses the asyncpg/libpq-style PostgreSQL URI, not SQLAlchemy's `postgresql+asyncpg://` form.
- Redis connection priority is Sentinel first when both `REDIS_SENTINEL_HOSTS` and
  `REDIS_SENTINEL_SERVICE_NAME` are configured, then `REDIS_URL`, then `REDIS_HOST`/`REDIS_PORT`.
- `AZURE_OPENAI_BASE_URL` is the preferred v1 API base URL. Keep dated `AZURE_OPENAI_API_VERSION` only for legacy Azure client compatibility.
- Azure OpenAI variables are for LLM generation only. Embeddings and reranking use the internal BGE API variables.
- Internal BGE embedding/rerank calls use `Authorization: Bearer ${BGE_EMBEDDING_API_KEY}` or `Authorization: Bearer ${BGE_RERANK_API_KEY}`.
- `BGE_EMBEDDING_MODEL` and `BGE_RERANK_MODEL` are configured by environment variables; do not hardcode model names.
- `BGE_EMBEDDING_DIMENSIONS` must exactly match the PostgreSQL `document_chunks.embedding vector(N)` dimension and migration SQL.
- `AUTH_REFRESH_COOKIE_NAME` defaults to `harness_refresh_token`; `/auth/login` sets the refresh
  token as an HttpOnly cookie and `/auth/refresh` reads this cookie when no refresh Bearer token is
  supplied. Responses still return only a new access token plus employee metadata, not a refresh
  token JSON field.
- `VITE_*` values are browser-visible. Never put secrets, tokens, passwords, or API keys behind `VITE_`.
- `AUTH_REFRESH_COOKIE_*` controls the HttpOnly refresh-token cookie. Keep `AUTH_REFRESH_COOKIE_NAME`,
  `AUTH_REFRESH_COOKIE_PATH`, and SameSite/Secure settings identical for login, refresh, and logout.
  `AUTH_REFRESH_COOKIE_SAMESITE=none` is valid only with `AUTH_REFRESH_COOKIE_SECURE=true`.
  `AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS` defaults to `JWT_REFRESH_EXPIRE_SECONDS` when omitted.
- Browser session continuity is access-token-in-memory plus refresh-cookie-only. Do not introduce
  `localStorage` or `sessionStorage` token persistence to compensate for reloads.
- `HARNESS_*` lifecycle variables are non-secret local PoC controls for `scripts/start.sh`,
  `scripts/stop.sh`, and `scripts/status.sh`; secrets must still stay in provider/database-specific
  variables and must not be printed by scripts.
- `scripts/start.sh` runs a PostgreSQL preflight with `/* sql_id: startup_preflight_select */`
  before launching Uvicorn, so rejected database credentials fail fast with a sanitized message.
- `CORS_ENABLED=false` disables API CORS middleware. Local browser flows use the same-origin `/api` Vite/Nginx proxy path instead of cross-origin calls.
- When `CORS_ENABLED=true`, `CORS_ALLOWED_ORIGINS` must list explicit origins and must not be `*`;
  credentialed browser refresh/logout flows use `allow_credentials=true` only for those explicit
  origins.
- If the frontend is deployed on a different origin, configure `CORS_ALLOWED_ORIGINS` to the exact
  HTTPS origin(s), set `AUTH_REFRESH_COOKIE_SECURE=true`, and use `AUTH_REFRESH_COOKIE_SAMESITE=none`
  only when cross-site cookies are intentionally required.
- `scripts/start.sh` filters the web/npm child-process environment to safe shell variables plus
  `VITE_*` and `HARNESS_*`; backend/provider credentials must not be passed to Vite.
- `scripts/run_batch_pipeline.sh` is the local operator batch runner. It loads the same `.env`,
  requires PostgreSQL and Redis for execution, and writes a report path supplied by `--report`.
  `--lookback-days 30` and `--as-of-date YYYY-MM-DD` set the default recent-window contract for
  provider targets, while provider-specific explicit start/end env values remain authoritative for
  their own targets.
- The runner treats `DART_API_BASE_URL`, `HARNESS_BATCH_DART_TARGETS_JSON`,
  `HARNESS_BATCH_DART_CORP_CODES`, `ECOS_API_BASE_URL`, `DATA_GO_KR_API_BASE_URL`,
  `DATA_GO_KR_MARKET_PATH`, `HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON`, and the `DATA_GO_KR_*_FIELD`
  mapping variables as provider-stage controls. Missing values create sanitized SKIPPED evidence
  instead of fake provider rows.
- OpenDART targets prefer `HARNESS_BATCH_DART_TARGETS_JSON` entries with either `corp_code` or
  six-digit `stock_code`. Stock-code targets use `/api/corpCode.xml` discovery in memory during the
  locked provider run; the runner does not write a local corp-code cache file.
- If no DART target env is set, the provider stage derives stock-code targets from active domestic
  securities and queries a rolling `HARNESS_BATCH_DART_LOOKBACK_DAYS` window. The default is 365 days
  so routine filings are discoverable before operators narrow to shorter windows.
- `./scripts/provider_discovery.sh --provider dart --output .omx/reports/t55/dart-discovery.json`
  performs read-only OpenDART target discovery: it downloads `corpCode.xml`, scans the configured
  discovery tickers over 365/180/90/30/1-day windows, verifies at least one matching `document.xml`
  body, and emits secret-free `HARNESS_BATCH_DART_TARGETS_JSON` candidates.
- Official DART `status=013` no-data responses are reported as provider no-data evidence and do not
  create `raw_documents` rows. A filing-list row is not provider-ready until its matching
  `document.xml` body is accepted for DART/RAG transform.
- Provider source contracts are exposed in batch reports under `provider_contracts`; they map
  BROKER→`market_price_bars.source_code='BROKER'`,
  DATA_GO_KR→`market_price_bars.source_code='DATA_GO_KR'`,
  OpenDART→`raw_documents.source_type_code='DART'`, ECOS→`macro_indicators.source_code='ECOS'`,
  and KRX-family→`market_price_bars.source_code='KRX'` for official OpenAPI or `PYKRX` for the explicit auxiliary fallback.
- `HARNESS_PROVIDER_STRICTNESS=required` is the local recent-window acceptance mode. It requires
  KRX/PYKRX historical rows, OpenDART document lineage, ECOS observations, and BGE embedding when
  those stages are selected, but leaves BROKER snapshots and DATA_GO_KR base-date reference rows as
  optional diagnostic evidence. `HARNESS_PROVIDER_STRICTNESS=all`, `HARNESS_PROVIDER_STRICT=true`,
  `--strict-external`, or `APP_ENV=production` makes the batch runner exit `2` when any provider
  evidence is `SKIPPED`/`FAILED` even if mandatory local stages pass. Production defaults to all
  unless an operator deliberately supplies a CLI override such as `--provider-strictness required`
  or legacy `--no-strict-external` for a documented break-glass/local run.
- Serviceable official-KRX mode uses `HARNESS_BATCH_KRX_UNIVERSE_CODE=DOMESTIC_TOP200_MARKET_CAP`,
  `HARNESS_BATCH_KRX_UNIVERSE_SIZE=200`, `HARNESS_BATCH_KRX_UNIVERSE_MARKETS=KOSPI,KOSDAQ`,
  and `HARNESS_BATCH_KRX_MIN_TRADING_DAY_COVERAGE_RATIO=1.0`. In that mode
  `HARNESS_BATCH_KRX_TICKERS` is only a smoke-test override and must not restrict the selected
  market-cap universe.
- `HARNESS_BATCH_KRX_RESOLVE_AS_OF_TRADING_DAY=true` means a weekend/holiday as-of date is resolved
  to the latest official KRX observed trading day before coverage is evaluated; closed-market days
  remain denominator evidence rather than fabricated bars.
- `scripts/run_serviceable_canonical_readiness.py` enforces the serviceable env contract before any
  canonical latest artifact refresh: `HARNESS_BATCH_KRX_ENABLED=true`, official `KRX` source/policy,
  `DOMESTIC_TOP200_MARKET_CAP`, universe size `200`, `KOSPI,KOSDAQ`, coverage ratio `1.0`, configured
  `KRX_API_BASE_URL`/`KRX_API_KEY`, PostgreSQL, and Redis. Secret-like env values are summarized only
  as `<configured>` in generated reports.
- Batch scheduling is opt-in through `HARNESS_BATCH_SCHEDULER_ENABLED=true` and
  `scripts/run_batch_scheduler.py`. Built-in jobs are `rag_refresh` (`transform,embed`),
  `derived_refresh` (`derived,house-view`), and disabled-by-default `serviceable_top200_30d`
  (`seed,provider,transform,embed,derived,house-view`). The scheduler does not create a second
  batch implementation; it calls the same Redis-locking runner and emits the same JSON reports.
- `HARNESS_BATCH_SERVICEABLE_TOP200_SCHEDULER_ENABLED=true` is accepted only when official KRX
  governance is complete: `HARNESS_BATCH_KRX_SOURCE=KRX`,
  `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`, configured `KRX_API_BASE_URL`/`KRX_API_KEY`,
  `DOMESTIC_TOP200_MARKET_CAP`, universe size at least `200`, and coverage ratio `1.0`. PYKRX
  auxiliary evidence remains blocked for this official top-200 scheduler job.
- `HARNESS_BATCH_SCHEDULES_JSON` may override built-in jobs with a JSON list of `{name, stages,
  interval_seconds, profile, lookback_days, as_of_date, provider_strictness}` objects; custom jobs
  are still blocked unless the global scheduler gate is true.

## Config File (config.yaml, optional override)
- DB 연결 풀 크기: pool_size=10, max_overflow=5
- 배치 스케줄: cron 표현식 per job (ASYNC-01 참조)
- NBA 임계값 오프셋: maturity_urgent_days=7, maturity_high_days=30
- Aftercare 임계값: drawdown_urgent_pct=-20.0, drawdown_high_pct=-10.0

## Secrets Management
- 개발: .env 파일 (gitignore 필수)
- 스테이징/운영: 서버 환경변수 또는 Vault
- API 키 코드 하드코딩 금지


## Startup Required vs Integration Required
- Core startup required: APP_ENV, LOG_LEVEL, PYTHON_PATH/PYTHON_VERSION, DATABASE_URL 또는 POSTGRES_*, REDIS_URL 또는 REDIS_*, JWT_SECRET, Azure LLM deployment names, internal BGE endpoint/model/dimension, VITE_* for frontend build.
- Integration-test required: BROKER_*, DART_API_KEY, ECOS_API_KEY, DATA_GO_KR_SERVICE_KEY_*, and SMTP/BREVO_* values with `HARNESS_EMAIL_SEND_ENABLED=true` for live email send evidence.
- 앱 startup은 integration-test key 부재만으로 실패하지 않는다. 해당 provider 호출/테스트 시 PASS, FAIL, 또는 SKIPPED/BLOCKED_WITH_REDACTED_REASON로 판정한다.
- 운영 배포 profile에서는 필요한 provider key를 배포 gate에서 별도 검증한다.

## Batch Provider Endpoint Overrides
- `DART_API_BASE_URL=https://opendart.fss.or.kr`, `ECOS_API_BASE_URL=https://ecos.bok.or.kr/api`,
  `DATA_GO_KR_API_BASE_URL=https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService`,
  and official KRX `KRX_API_BASE_URL=https://data-dbg.krx.co.kr` are the documented read-only
  provider endpoints for local integration smoke and batch collector clients. Official KRX requests
  use the `AUTH_KEY` header populated from secret `KRX_API_KEY`; the key value must not appear in
  logs, reports, target refs, docs, or provider evidence.
- If these endpoint URLs or provider credentials are absent, provider smoke tests report `SKIPPED/BLOCKED_WITH_REDACTED_REASON` instead of using mocks or local simulators.
- `BROKER_TIMEOUT_SECONDS`, `DART_TIMEOUT_SECONDS`, `ECOS_TIMEOUT_SECONDS`, and `DATA_GO_KR_TIMEOUT_SECONDS` tune real provider calls and must remain environment-driven.
- For `DATA_GO_KR` market collection through the batch runner, configure
  `DATA_GO_KR_MARKET_PATH=/getStockPriceInfo`, `DATA_GO_KR_TICKER_FIELD=srtnCd`,
  `DATA_GO_KR_DATE_FIELD=basDt`, and `DATA_GO_KR_CLOSE_FIELD=clpr`; optional open/high/low/volume
  fields are `DATA_GO_KR_OPEN_FIELD=mkp`, `DATA_GO_KR_HIGH_FIELD=hipr`,
  `DATA_GO_KR_LOW_FIELD=lopr`, and `DATA_GO_KR_VOLUME_FIELD=trqu`.
- When `DATA_GO_KR_SERVICE_KEY_DECODING` is set it is the canonical service key input; otherwise the
  client decodes `DATA_GO_KR_SERVICE_KEY_ENCODING` and URL-encodes it once per request. Requests use
  `resultType=json` for the stock-price endpoint.
- Prefer `HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON` for the security-master ticker set so each target can
  carry its own `likeSrtnCd`, path, and field mapping. Current local PoC targets are 005930, 000660,
  035420, 005380, and 068270; each row must still be parsed from the live provider payload.
- `HARNESS_BATCH_KRX_ENABLED=false` remains the safe default for environments without an approved
  KRX-family source. The current local PoC `.env` sets `HARNESS_BATCH_KRX_ENABLED=true` with
  `HARNESS_BATCH_KRX_SOURCE=KRX`, `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`,
  `KRX_API_BASE_URL`, and `KRX_API_KEY` to run the official KRX OpenAPI branch. The official branch
  persists rows as `source_code=KRX` and must never silently fall back to PYKRX.
- To run the non-production auxiliary fallback instead, set `HARNESS_BATCH_KRX_SOURCE=PYKRX` and
  `HARNESS_BATCH_KRX_POLICY=PYKRX_AUXILIARY_APPROVED`, then enable the gate only when the declared
  `pykrx>=1.2.8` runtime package imports in `wm_env` and outbound KRX access is available; otherwise
  the provider stage records sanitized SKIPPED evidence instead of pretending success.
- The readiness/API/UI policy label must match the active branch: official KRX evidence uses
  `OFFICIAL_KRX_APPROVED`; auxiliary fallback evidence uses `PYKRX_AUXILIARY_APPROVED`. T55 readiness
  closes only when the runtime policy and persisted provider evidence carry the same branch-specific
  `source_policy_code`.
- `/data/readiness.status_code` uses the current gate result, not the mere existence of historical
  provider issue rows. Those historical rows stay visible in readiness and batch-monitor payloads for
  audit and troubleshooting.
