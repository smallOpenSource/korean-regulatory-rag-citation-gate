# INT-04 Provider Source Contracts

## Purpose
Provider collectors must produce auditable live-source evidence without fabricating provider rows.
The batch runner exposes the current contract matrix in every report under `provider_contracts`.
Secrets and credential values are never included in that matrix.

## Contract Matrix
| Provider | Job | Persistence target | Source code | Required gate/config |
|---|---|---|---|---|
| BROKER | `broker_market_collector` / `PROVIDER_BROKER` | `market_price_bars` | `BROKER` | `BROKER_BASE_URL`, `BROKER_APP_KEY`, `BROKER_APP_SECRET` |
| DATA_GO_KR | `data_go_kr_market_collector` / `PROVIDER_DATA_GO_KR` | `market_price_bars` | `DATA_GO_KR` | `DATA_GO_KR_API_BASE_URL`, decoded-or-encoded service key, `/getStockPriceInfo`, explicit field mapping, or `HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON` |
| OpenDART | `dart_disclosure_collector` / `PROVIDER_DART` | `raw_documents` | `DART` source type | `DART_API_BASE_URL`, `DART_API_KEY`, `HARNESS_BATCH_DART_TARGETS_JSON` or corp/stock target env |
| ECOS | `ecos_macro_collector` / `PROVIDER_ECOS` | `macro_indicators` | `ECOS` | `ECOS_API_BASE_URL`, `ECOS_API_KEY`, `HARNESS_BATCH_ECOS_TARGETS_JSON` or scalar statistic target env |
| KRX official / pykrx | `krx_market_collector` / `PROVIDER_KRX` | `market_price_bars` | `KRX` for official OpenAPI, `PYKRX` for fallback | Official: `HARNESS_BATCH_KRX_ENABLED=true`, `HARNESS_BATCH_KRX_SOURCE=KRX`, `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`, `KRX_API_BASE_URL`, `KRX_API_KEY` via `AUTH_KEY`; auxiliary: `PYKRX_AUXILIARY_APPROVED` plus optional pykrx |

## Strict Mode
- Local default: missing optional providers produce sanitized `SKIPPED` batch evidence and the runner can still exit `0` when mandatory local stages pass.
- Strict mode: `--strict-external`, `HARNESS_PROVIDER_STRICT=true`, or `APP_ENV=production` exits `2` when provider evidence is `SKIPPED` or `FAILED`.
- `APP_ENV=production` is fail-closed even when `.env` contains `HARNESS_PROVIDER_STRICT=false`; use
  the explicit `--no-strict-external` CLI flag only for a documented break-glass local run.
- Mandatory local stages still exit `1` on failure; strict provider failures use `2` so operators can distinguish local breakage from external/live-source incompleteness.

## Provider-detail taxonomy
`batch_job_logs.status_code` remains the stable job lifecycle vocabulary:
`RUNNING | DONE | FAILED | SKIPPED`. Provider-specific outcomes are persisted in
`batch_provider_evidence.provider_status_code`:

- `PROVIDER_DONE`: real provider rows were collected or refreshed.
- `PROVIDER_NO_DATA`: the provider returned an official success/no-data response for a
  secret-free target; do not create provider rows and do not label this as parser failure.
- `PROVIDER_SKIPPED_CONFIG`: required endpoint/credential/target configuration is missing.
- `PROVIDER_SKIPPED_DISABLED`: the lane is intentionally disabled or a lock prevented duplicate work.
- `PROVIDER_FAILED_AUTH`: provider authentication/authorization failed.
- `PROVIDER_FAILED_RATE_LIMIT`: rate/quota/request-limit response.
- `PROVIDER_FAILED_SCHEMA`: success payload could not be parsed according to the provider contract.
- `PROVIDER_FAILED_NETWORK`: timeout/connectivity/DNS failure.

Each evidence row includes `target_ref`, counters, redacted `reason_message`, and
`provider_detail_json`. `target_ref` must never contain API keys or bearer tokens.

## Operator Commands
```bash
./scripts/run_batch_pipeline.sh --stages provider --report .omx/reports/batch/provider.json
./scripts/run_batch_pipeline.sh --stages provider --strict-external --report .omx/reports/batch/provider-strict.json
./scripts/provider_discovery.sh --provider dart --output .omx/reports/t55/dart-discovery.json
./scripts/provider_smoke.sh
./scripts/provider_smoke.sh --strict-external
```

`provider_discovery.sh --provider dart` is read-only. It downloads OpenDART `corpCode.xml`, scans
configured domestic stock-code seeds over 365/180/90/30/1-day windows, checks listing rows, verifies a
matching `document.xml` body, and emits secret-free target JSON candidates for
`HARNESS_BATCH_DART_TARGETS_JSON`.

`provider_smoke.sh` performs safe read-only client checks only when the relevant provider endpoint
and credentials are present. In strict mode, any `SKIPPED/BLOCKED_WITH_REDACTED_REASON` provider
smoke evidence exits `2`.

## Non-Fabrication Rules
- Seed and local transforms must not insert provider-owned rows into `market_prices`,
  `financial_ratios`, `investor_flows`, or `macro_indicators`.
- Provider errors are redacted before persistence in `batch_job_logs.error_message`.
- Provider details are persisted through V015 `batch_provider_evidence`; no-data rows are unavailable
  evidence, not fabricated success.
- DART collection stores provider lineage and redacted `document.xml` source URLs without embedding
  `crtfc_key` query secrets. A target is `PROVIDER_DONE` only after at least one matching
  `document.xml` body is accepted for raw-document persistence; list-only evidence remains
  `PROVIDER_NO_DATA`.
- OpenDART `document.xml` bodies may contain NUL bytes that PostgreSQL text columns reject; the
  collector strips those control bytes before hashing/inserting while preserving provider lineage,
  receipt number, corp code, parser version, and canonical URL evidence.
- OpenDART target resolution accepts either an 8-digit `corp_code` or a 6-digit `stock_code`.
  Stock-code targets are resolved through `/api/corpCode.xml` during the locked provider run and are
  kept in memory only; no cache artifact is persisted.
- DART `status=013` listing or document no-data is persisted as skipped/no-data evidence, not as a
  parser failure and never as fabricated `raw_documents` or `document_sources` rows.
- DATA_GO_KR stock-price calls should use `DATA_GO_KR_SERVICE_KEY_DECODING` when present; otherwise
  decode `DATA_GO_KR_SERVICE_KEY_ENCODING` and let the HTTP client encode exactly once. The stock-price
  endpoint uses `resultType=json`; recommended target JSON carries `likeSrtnCd` per domestic ticker.
- KRX is disabled by default. Official `KRX` OpenAPI persistence is executable only when
  `HARNESS_BATCH_KRX_SOURCE=KRX`, `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`, the official base URL,
  and `KRX_API_KEY` are configured. `PYKRX` remains a separate auxiliary fallback and must be labeled as
  a non-production auxiliary source in API/UI evidence. Enabling KRX without either a complete official
  branch or a complete `HARNESS_BATCH_KRX_SOURCE=PYKRX` + `PYKRX_AUXILIARY_APPROVED` + importable `pykrx`
  auxiliary branch records sanitized skipped/failed evidence instead of falling back to mock data.
- Successful official KRX evidence must carry `source_code=KRX`, `source_policy_code=OFFICIAL_KRX_APPROVED`, `source_official=true`, redacted `AUTH_KEY` proof, endpoint paths, market/date window, and persisted row counts. Successful PYKRX fallback evidence must carry `source_code=PYKRX` and
  `source_policy_code=PYKRX_AUXILIARY_APPROVED` in `provider_detail_json`; T55 closure wording must
  match the active branch and must not describe PYKRX auxiliary evidence as official KRX production readiness.
