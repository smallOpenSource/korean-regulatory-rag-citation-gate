# PLANS.md

## Goal
하네스 문서 세트를 기준으로 Codex CLI / OMX가 추정 없이 Harness를 완전 구현할 수 있게 한다.

## Phases
| Phase | 내용 | 상태 |
|---|---|---|
| 1 | Product, business, security, config foundation | ✅ done |
| 2 | Database and API contracts | ✅ done |
| 3 | AI, prompt, batch specifications | ✅ done |
| 4 | UI, frontend, integration, test, ops | ✅ done |
| 4.5 | RALPLAN consensus planning + strict ambiguity audit | ✅ done |
| 5 | Backend code (FastAPI, migrations) | 🟡 in progress |
| 6 | Batch pipeline code | ⬜ next |
| 7 | Frontend code (React) | ⬜ next |

## Current Scope
- 단일 기관 내부 직원용 PB/WM 업무 지원 시스템.
- 직원 화면에서 고객 동의/주문 전 과정을 시뮬레이션하되 실제 고객 포털·실제 주문 전송은 제외한다.
- 추천/주문 시뮬레이션은 suitability, explanation, simulated customer consent, employee final approval 4-gate와 감사로그가 필수다.

## Completion Conditions
- 문서 간 용어 완전 일치 (BIZ-01 glossary 기준).
- DB ↔ API ↔ UI ↔ AI ↔ batch 간 참조 불일치 없음.
- 모든 제약 반영: raw SQL, no ORM, no enum, concise docs.
- 빈 파일 없음.

## Current Execution Baseline
- Canonical Python runtime: `/opt/conda/envs/wm_env/bin/python` 3.11.5.
- RALPLAN approved: `.omx/plans/ralplan-harness-full-mvp-implementation.md`.
- Test spec: `.omx/plans/test-spec-harness-full-mvp-implementation.md`.
- Recommended next lane: `$team` implementation with Backend → Batch → Frontend stage gates.



## Backend Email/RAG Feature Completion — 2026-05-16
- Task 2 added the email draft backend contract: PB/WM row-scoped `POST /email-drafts`, APPROVED-only `POST /email-drafts/{draft_id}/send`, raw-SQL repository access, display-safe content gates, SMTP fail-closed provider gating, and `email_draft_send` audit only after real SMTP delivery succeeds. (정정 2026-05-31: 본 PoC는 sandbox 전용이라 실제 발송 성공 emit 코드는 `email_sent_via_sandbox`이며 `email_draft_send`는 real-SMTP 예약/미emit — ADR-002 §Amendment.)
- Existing RAG/consultation/house-view/NBA/simulation routes were kept on their raw-SQL/audit contracts; docs and API route sync now include the email HTTP routes while live SMTP success remains credential-gated instead of mocked.

## Market Data Foundation Progress — 2026-05-16
- Task 2 added V012 raw-SQL market data foundation: domestic KR equity `securities`, identifiers, product underlyings, trading calendar, source license, `market_price_bars`, corporate action, quality, and evidence schemas.
- Batch repository writes provider quote rows to `market_price_bars`, exposes price-bar quality/reconciliation/readiness helpers, and keeps portfolio valuation SQL on `market_price_bars` only.
- Legacy `market_prices` is backfilled where eligible and protected by a write-reject trigger; docs/tests now treat it as deprecated.

## Implementation Progress — 2026-05-15
- Verification/docs/contracts lane Task 5 added contract tests for API route documentation, audited env-driven AI agents, legacy path drift, public VITE secrets, and mock import bans; it also synced API-01 with implemented `/products` and aftercare resolve routes.
- Backend API lane Task 2 added route/repository/service slices for auth, customers/Customer 360, consultations, house views, NBA/aftercare, AI jobs/outputs, audit logs, batch status, and recommendation/order simulation gates; targeted backend contract tests pass.
- DB/migrator/security foundation started under Task 1: custom raw-SQL migrator, V001~V010 migrations, synthetic seed SQL, config/security/RBAC/audit/Redis helpers, and FastAPI health shell are in place.
- Static pytest/ruff checks pass for the foundation; corrected PostgreSQL credentials now pass API
  startup preflight and deep status checks.

## Batch/External Progress — 2026-05-15
- Task 3 lane C implemented external-client and batch foundations: Redis owner locks/job logs/pubsub event helper, internal BGE embedding/rerank client with dense embedding validation, BROKER read-only OAuth/quote/sandbox balance client, public DART/ECOS/DATA_GO_KR client shells, raw document/market price persistence helpers, and real/safe smoke tests.
- Optional DART/ECOS/DATA_GO_KR smoke calls are environment-gated and report `SKIPPED/BLOCKED_WITH_REDACTED_REASON` when endpoint URLs are not configured; BROKER OAuth smoke uses configured credentials and no order/mutation calls.

## Autopilot Review/Operations Progress — 2026-05-15
- Added local PoC lifecycle scripts under `scripts/` for start, stop, and status checks with `.env`
  loading, PID/log files under `.omx/`, and no secret-value output.
- Hardened lifecycle scripts with command/cwd PID ownership checks, filtered web/npm environment,
  detached `setsid` startup when available, 2xx-only HTTP health semantics, ShellCheck-clean parsing,
  and class-only deep dependency failures.
- Added `scripts/start.sh` API startup preflight so configured PostgreSQL authentication/connectivity
  failures stop before Uvicorn launch with sanitized CLI output instead of only a post-launch log.
- Aligned the shared Redis factory with `tests/test_redis.py`: Sentinel settings take precedence over
  a direct `REDIS_URL`, then host/port fallback.
- Made local lifecycle host/port values explicit in `.env` so API/Web startup follows environment
  configuration rather than hidden defaults.
- Published synthetic PoC login accounts in the server setup runbook; after DB extension activation,
  V001~V010 migrations and synthetic seed were applied successfully and login smoke checks passed.
- Added root `README.md` with `.env`-sourced local ports, lifecycle commands, migration/seed steps,
  and synthetic PoC login accounts.
- Added root `.gitignore` to keep `.env`, runtime state/logs, caches, build outputs, and dependency
  folders out of version control.
- Set `CORS_ENABLED=false` in `.env` and moved browser calls to same-origin `/api` via Vite/Nginx
  proxy, keeping browser login E2E functional without API CORS.
- Added a Consultation Workspace nav item and updated E2E to use SPA navigation, preserving the
  memory-only JWT session instead of reloading the page.
- Synced operations/config docs for `<repo-root>` and the new `HARNESS_*` script controls.
- Fixed JWT signature decoding to reject non-canonical base64url signature tampering before accepting
  HMAC-equivalent bytes.

## Data Foundation Planning — 2026-05-15
- RALPLAN data provisioning plan created:
  `.omx/plans/ralplan-data-foundation-provisioning.md`.
- Supporting PRD/test spec created:
  `.omx/plans/prd-data-foundation-provisioning.md` and
  `.omx/plans/test-spec-data-foundation-provisioning.md`.
- Decision: use layered provisioning — deterministic synthetic operational baseline, real-provider
  market/unstructured collection, then transform/embed/derived refresh.
- Hard gate: do not insert fabricated market/provider rows under real `BROKER`, `ECOS`, `DART`, or
  `DATA_GO_KR` provenance; unavailable providers must produce sanitized SKIPPED/FAILED evidence.

## Data Foundation Derived AI/RAG Progress — 2026-05-15
- Task 5 derived lane added raw document transform/chunk helpers, RAG readiness classification, and
  aftercare/NBA derived refresh from persisted customer/portfolio/product state.
- Derived NBA rows intentionally leave AI script text/time/model NULL unless a real AI job/output
  exists; BGE embeddings remain required before RAG readiness can be READY.

## Data Foundation Implementation Progress — 2026-05-15
- Task 4/5 data seed lane added `db/seed.py --profile full-mvp`, deterministic fixture slices
  `seed_00_identity.sql` through `seed_40_manual_rag.sql`, readiness JSON thresholds, and
  provider-owned table blocking semantics.
- Full-MVP seed re-run verification passed against PostgreSQL: synthetic operational tables meet
  readiness thresholds while provider-owned market tables remain empty with SKIPPED evidence.

## API/Web/E2E Data Readiness Progress — 2026-05-15
- Task 3 API/Web/E2E lane added `/data/readiness` and enriched `/rag/query` blocked responses with `status_code`, `output_id`, `generated_at`, `model_name`, and RAG readiness metadata.
- Frontend RAG and Batch Monitor screens now show explicit READY/DEGRADED/BLOCKED/SKIPPED/FAILED states instead of placeholder AI metadata or fake provider success.
- API contract, batch docs, README, backend contract tests, and Playwright critical flow were synchronized for the readiness surface.

## UltraQA Closure — 2026-05-16
- UltraQA run `ultraqa-20260516-002835` exercised implemented API endpoints, protected screens, role matrix, row-scope rules, malformed input, prompt-injection, stale/corrupted state, hung command, and misleading-success scenarios.
- Fixed discovered API/UI contract gaps: added `/dashboard`, added `GET /house-views/{house_view_id}`, aligned list-response rendering in Customer/NBA/House View/Audit pages, and corrected Customer 360 response shape handling.
- Hardened API boundary behavior found by adversarial harness: UUID path/body validation, PB/WM-only consultation/simulation mutation guards, NBA status SQL type cast, and house-view activation transaction ordering.
- Added permanent Playwright role-matrix regression at `apps/web/e2e/role-matrix.spec.ts` and documented `E2E_SYNTHETIC_PASSWORD` usage in README.
- Synchronized API contract path inventory: documented `/health` and `/health/config`, and previously removed documented-only `/email-drafts` routes until T18 gained implemented provider-gated backend routes.
- Final evidence: API harness `162 passed / 0 failed`; Playwright `7 passed`; backend `56 passed / 3 skipped`; frontend type/lint/unit/build pass; post-mutating-E2E seed idempotency pass.

## UltraQA Root-Cause Prevention Planning — 2026-05-16
- RALPLAN consensus plan created: `.omx/plans/ralplan-ultraqa-defect-root-cause-remediation.md`.
- Supporting PRD/test spec created: `.omx/plans/prd-ultraqa-defect-root-cause-remediation.md` and `.omx/plans/test-spec-ultraqa-defect-root-cause-remediation.md`.
- Decision: use a thin contract-centered prevention mesh, not a broad refactor, to prevent route/doc drift, RBAC ambiguity, response-shape mismatch, malformed-input 5xx, SQL typing ambiguity, transaction invariant regressions, seed contamination, and false-green verification.
- Execution boundary: WebSocket push and unfinished full RAG generation remain backlog/not-current-contract; email draft/send now has a provider-gated backend HTTP contract with safety/audit semantics.


## UltraQA Prevention Mesh Implementation — 2026-05-16
- Implemented `.omx/plans/ralplan-ultraqa-defect-root-cause-remediation.md` via Ralph execution.
- Added exact FastAPI route/method ↔ `docs/api/API-01_contracts.yaml` sync and response-schema gates in `tests/test_api_doc_route_sync.py`.
- Added real local API boundary harness in `tests/test_api_boundary_harness.py` for six synthetic roles plus anonymous, row-scope checks, PB/WM-only mutation authority, malformed UUID/JSON 4xx behavior, AI/RAG fail-closed responses, and audit checks.
- Added `tests/test_house_view_activation.py` for the single ACTIVE invariant and no-supersede-on-missing-target behavior.

## Domestic Market API/UI Readiness Progress — 2026-05-16
- Task 6 API/UI lane added synthetic-customer notices, domestic market readiness subchecks,
  provider strict/local mode metadata, and portfolio valuation provenance to `/dashboard`,
  `/customers/{customer_id}`, `/data/readiness`, and `/batch/status`.
- Dashboard, Customer 360, and Batch Monitor now render Korean source/as_of/freshness/quality
  states and show blocked/degraded copy when accepted domestic price bars or DART evidence are
  missing.
- Frontend unit tests no longer mock API clients; role Playwright E2E now checks synthetic notices,
  `source_as_of` visibility, provider degraded states, and Customer 360 API provenance fields.
- Added `scripts/qa_hostile_checks.sh` and a pytest wrapper to prevent false-green verification from misleading success text, timeouts, or corrupted state parsing.
- Hardened docs: API-01 now declares concrete response schemas; PRD/BIZ/BATCH/security docs label WebSocket push/full RAG generation as backlog/not-current-contract while email draft/send is now documented as a provider-gated backend HTTP contract; ADMIN authority is clarified as system/admin authority, not PB/WM front-office mutation delegation.
- Verification evidence: `scripts/status.sh --deep --no-fail`, `ruff check apps/api db tests`, full backend pytest `64 passed / 3 skipped`, frontend type/lint/unit/build, Playwright `8 passed`, post-E2E seed idempotency, and hostile QA checks all passed.

## UX/Data/Batch Remediation Verification Lane — 2026-05-16
- Added committed executable evidence commands for the remediation team lane:
  `scripts/run_batch_pipeline.sh` and `scripts/run_verification_gate.sh`.
- The batch runner (`apps/api/harness/batch/runner.py`) covers seed, provider, transform, embed,
  derived, and house-view readiness stages, writes `batch_job_logs`, and emits JSON report
  postconditions with SQL_ID comments.
- Optional `POST /batch/run` remains intentionally unimplemented because the current Batch Monitor
  UI is read-only and no async queue/WebSocket execution contract exists.
- Current worker baseline evidence is stored under `.omx/reports/verification/` and shows full
  pytest requires a project `.env` plus local PostgreSQL in this worker runtime.

## UX/Data/Batch Remediation Closure — 2026-05-16
- Closed the false-green E2E gap: `scripts/run_verification_gate.sh` now supplies synthetic fixture
  E2E credentials by default so login, role matrix, reload, customer, workflow, admin, and wildcard
  Playwright checks cannot silently skip.
- Confirmed hard-reload auth restoration after restarting the API/Web on current code: `/auth/login`
  sets `harness_refresh_token` as an HttpOnly cookie and no refresh token is exposed to browser JS.
- Customer 360 now renders a visible Korean `포트폴리오` section with coherent seeded portfolio and
  holding names, preserving the realistic synthetic-data acceptance gate.
- Batch runner reports separate `status_code`, `local_status_code`, `provider_status_code`,
  `local_ok`, and `provider_evidence_ok` fields; local mandatory stages can pass while missing
  optional provider endpoints remain honest `SKIPPED` evidence.
- Final integrated gate evidence:
  `.omx/reports/verification/gate-20260516T014700Z.md` — status/deep checks, ruff, full pytest,
  web typecheck/lint/unit/build, Playwright `10 passed`, and full batch pipeline all passed.

## Domestic Market DART/RAG Stage 4 Slice — 2026-05-16
- Implemented the Stage 4 citation gate: OpenDART filing rows now require `document.xml` body ingestion before DART RAG evidence is persisted.
- Added parser-versioned source/chunk metadata and persisted `rag_answer_evidence` rows for READY RAG responses; uncited answers fail closed.
- Prompt-like instructions inside retrieved provider text are quarantined before chunking/answering and cannot override system/compliance policy.


## ECOS/OpenDART/KRX Provider Normalization Planning — 2026-05-16
- RALPLAN consensus plan approved: `.omx/plans/ralplan-ecos-opendart-krx-provider-normalization.md`.
- Decision: normalize ECOS/OpenDART/KRX through persisted `batch_provider_evidence` detail rather than changing `batch_job_logs.status_code`.
- V015 execution scope is fixed to `batch_provider_evidence` only; no official KRX source persistence, no DART identifier-cache table, and no unrelated schema changes.
- ECOS `INFO-200` and OpenDART `status=013` become honest `PROVIDER_NO_DATA` evidence, not parser failure or fabricated rows.
- KRX official Open API remains approval/research backlog; current implementation may only use explicit non-production `PYKRX` fallback or disabled evidence.

## Domestic Market Production Readiness Team Closure — 2026-05-16
- Integrated the `source-contract -> db-foundation -> provider-live -> market-quality -> dart-rag -> api-ui -> verification-doc` team lane without changing the raw-SQL/no-ORM/no-migration-framework rules.
- Resolved post-team migration drift by preserving the intended stage order: V012 market-data foundation, V013 DART/RAG grounding, and V014 forward-only idempotent repair for environments that observed the duplicate-version artifact.
- Kept worker-2's later V012/V013 renumbering follow-up out of the leader branch because it contradicted the approved stage ordering; equivalent safety was implemented through V014 repair instead.
- Final leader gate `.omx/reports/verification/gate-20260516T033041Z.md`: PostgreSQL and Redis deep status OK, ruff pass, full backend pytest `101 passed / 1 skipped`, web typecheck/lint/unit/build pass, Playwright role/session/API/UI E2E `11 passed`, and full batch pipeline local mandatory stages DONE.
- Live provider evidence is now explicit: BROKER collected 1 real quote row and DATA_GO_KR collected 25 real stock-price rows; ECOS and OpenDART are still FAILED for current configured targets and KRX remains SKIPPED while disabled, so overall provider status remains DEGRADED rather than fabricated READY.

## ECOS/OpenDART/KRX Provider Normalization Closure — 2026-05-16
- Implemented the approved plan `.omx/plans/ralplan-ecos-opendart-krx-provider-normalization.md` through OMX team `implement-app-poc-wma-8f4905be`.
- Added V015 `batch_provider_evidence` with SQL_ID-first raw SQL and kept `batch_job_logs.status_code` stable as `RUNNING/DONE/FAILED/SKIPPED`.
- Normalized ECOS `INFO-200` and OpenDART no-data/document-empty responses into provider evidence (`PROVIDER_NO_DATA`/skipped counters) without inserting fabricated macro/document rows.
- Kept official KRX disabled/fail-closed unless explicit `HARNESS_BATCH_KRX_SOURCE=PYKRX` is configured; UI/API labels distinguish `pykrx 비공식 보조 소스` from official KRX.
- Synced API, batch, config, DB, integration, README, UI-copy, and test-strategy docs.
- Final evidence: team status `8 completed / 0 pending / 0 in_progress / 0 failed`; `git diff --check`; `ruff check apps/api db tests`; `compileall`; targeted pytest `61 passed`; web typecheck/lint; Vitest UI-copy `2 passed`; team shutdown complete.


## T55 Live Provider Readiness Remediation Planning — 2026-05-16
- RALPLAN consensus plan approved: `.omx/plans/ralplan-t55-live-provider-readiness.md`.
- Decision: T55 closure requires active DB schema reconciliation, parseable ECOS rows, parseable OpenDART filing/document rows, and either approved official KRX evidence or explicit `PYKRX_AUXILIARY` operating policy with non-official labels.
- Current blocker evidence remains provider-specific, not fabricated: latest batch report showed BROKER/DATA_GO_KR DONE but ECOS/DART FAILED and KRX SKIPPED; redacted `.env` scan found KRX disabled and no explicit ECOS/DART target JSON.
- Added a Stage 0 migration-state gate because active `.env` DB inspection could not find `batch_provider_evidence`; provider readiness must not be assessed against an unmigrated database.

## T55 KRX/PYKRX Policy Gate Slice — 2026-05-16
- Implemented the explicit PYKRX auxiliary gate: pykrx can run only with
  `HARNESS_BATCH_KRX_POLICY=PYKRX_AUXILIARY_APPROVED`, and provider evidence/readiness/UI labels carry
  `source_policy_code=PYKRX_AUXILIARY_APPROVED` as non-official internal PoC evidence.
- Official `KRX` persistence remains blocked until terms/credentials are documented; T55 must still
  wait for schema, ECOS, OpenDART, and live provider verification evidence before closure.

## Realtime Inventory and WebSocket Foundation — 2026-05-16
- Task 1 added `docs/api/API-03_route_screen_backlog_matrix.md` as the contract index tying
  HTTP routes, `/ws`, React protected screens, and backlog items together.
- Backend `/ws` now rejects missing/refresh tokens, accepts only access JWTs, answers ping/pong,
  supports subscription filters, and fans out Redis `harness:events:{event_type}` payloads through
  RBAC/row-scope event filtering.
- API-01 indexes `/ws` as a WebSocket path while API-02 owns realtime event payload and connection
  rules; frontend WebSocket URL construction now targets same-origin `/api/ws?token=...` without
  duplicating `/ws`.

## T55 Live Provider Readiness Team Closure — 2026-05-16
- Completed team `implement-omx-plans-r-82c653e8` against
  `.omx/plans/ralplan-t55-live-provider-readiness.md` with all four tasks completed and zero failed:
  schema/readiness preflight, ECOS live parseable target discovery, OpenDART document.xml/RAG gates,
  and explicit KRX/PYKRX source-policy evidence.
- Active `.env` DB was reconciled through V015 `batch_provider_evidence`; `scripts/t55_schema_preflight.py`
  reports READY for schema/Redis preflight while provider-readiness subchecks remain honest.
- ECOS is now backed by official metadata and live parser-ready rows: final discovery passed with
  four parseable targets, and the provider stage recorded ECOS DONE with 17 collected rows and
  `macro_indicators.source_code='ECOS'` count 40/latest reference date 2026-05-15.
- OpenDART readiness now requires real filing rows plus stored `document.xml` bodies and parser-versioned
  DART chunks; missing credentials/no live document evidence remains BLOCKED rather than fabricated.
- KRX-family readiness at that stage required either official KRX approval/persistence or explicit
  `PYKRX_AUXILIARY_APPROVED` policy with non-official Korean labels; disabled/missing pykrx remains
  skipped/blocked evidence.
- Final leader verification: `git diff --check`, `ruff check apps/api db tests scripts`, targeted backend
  pytest `81 passed / 1 skipped`, `scripts/t55_schema_preflight.py`, ECOS provider discovery smoke,
  web typecheck/lint, and Vitest `9 passed` all passed.

## T55 OpenDART Live Evidence Correction — 2026-05-16
- Root cause: the DART discovery wrapper advertised `--provider dart` but only dispatched ECOS, and
  live OpenDART `document.xml` bodies contained NUL bytes that PostgreSQL rejected before persistence.
- Fixed the wrapper dispatch, raw-document sanitizer, transform SQL parameter casts, and BGE env
  handling; then collected real OpenDART evidence for 삼성전자 (`00126380`).
- Current evidence: OpenDART provider `DONE`, 2,648 persisted DART `raw_documents` and
  `document_sources`, 229 parser-versioned DART chunks, and 4 embedded DART chunks.
- Remaining T55 blocker at that point was KRX/PYKRX only: `.env` had `HARNESS_BATCH_KRX_ENABLED=false`,
  no approved official KRX persistence/credentials, no importable `pykrx`, and no
  `PYKRX_AUXILIARY_APPROVED` live rows.

## T55 PYKRX Live Closure Correction — 2026-05-16
- Cleared stale cancelled team state that was blocking the new `$ralplan` turn, then completed the requested executable path directly.
- Updated the active ignored `.env` to enable the internal PoC fallback: `HARNESS_BATCH_KRX_ENABLED=true`, `HARNESS_BATCH_KRX_SOURCE=PYKRX`, and `HARNESS_BATCH_KRX_POLICY=PYKRX_AUXILIARY_APPROVED`.
- Installed and declared `pykrx>=1.2.8` in `pyproject.toml`; official KRX credential/base-url variables were not present in `.env`, so this remains explicitly non-official PYKRX auxiliary evidence.
- Ran the KRX-family provider lane with real pykrx OHLCV for `005930` on the latest trading day and persisted one `market_price_bars.source_code='PYKRX'` row plus `batch_provider_evidence` with `source_policy_code=PYKRX_AUXILIARY_APPROVED`.
- Fixed readiness/dashboard repositories so API/UI no longer report placeholder zero market metrics after live provider rows exist; T55 provider readiness now reports READY while local provider mode remains DEGRADED because recent optional provider failures/skips are still visible.

## Data Readiness Top-Level READY Correction — 2026-05-16
- Root cause: `/data/readiness.status_code` still treated historical provider `SKIPPED`/`FAILED`/no-data
  rows and local provider-mode advisories as current degradation even after the concrete domestic-market
  and T55 gates were READY.
- Corrected readiness semantics so current gate failures still block/degrade, while historical provider
  issue counts remain visible for audit in `provider.recent_batches` and `batch_status_summary`.
- Runtime verification after API restart showed `/data/readiness.status_code=READY`,
  `domestic_market=READY`, `t55_provider_readiness=READY`, and `provider_mode=READY`; evidence saved to
  `.omx/reports/t55/data-readiness-status-ready-20260516T081906Z.json`.

## UX/Realistic Data/Recent-30-Day Batch Remediation Planning — 2026-05-16
- RALPLAN consensus plan approved: `.omx/plans/ralplan-ux-realistic-data-30day-batch.md`.
- Decision: remediate awkward mixed-language UX copy, replace placeholder-like synthetic customer/portfolio data with plausible PB/WM personas, and add executable recent-30-day batch controls before running seed/provider/transform/embed/derived/house-view stages.
- Provider-window semantics are explicit: KRX official or approved PYKRX must persist multiple daily historical rows for the 30-day price proof; BROKER and DATA_GO_KR reference/snapshot rows cannot satisfy that historical-price criterion.
- Acceptance must use `--provider-strictness required`; `--provider-strictness all` is diagnostic evidence only and must not be mixed with optional-failure closure claims.
- No implementation was performed in the planning lane; next recommended lane is `$team` with stage gates `korean-copy -> realistic-seed -> 30d-batch-controls -> run-30d-pipeline -> verification-doc`.

## UX/Data/Recent-30-Day Batch Controls Implementation — 2026-05-16
- Added executable recent-window controls for `.omx/plans/ralplan-ux-realistic-data-30day-batch.md`: `--lookback-days`, `--as-of-date`, and `--provider-strictness required|all`.
- Batch reports now distinguish required acceptance from all-provider diagnostics and include SQL_ID-backed provider-window postconditions for PYKRX/KRX trading days, ECOS observations, and OpenDART document lineage.
- KRX/PYKRX parser behavior now preserves multi-day pandas-like OHLCV rows instead of collapsing date-range payloads to the latest row.

## UX/Realistic Data/Recent-30-Day Batch Team Closure — 2026-05-16
- Completed OMX team `implement-omx-plans-r-82c653e8` for `.omx/plans/ralplan-ux-realistic-data-30day-batch.md`: task status `4 completed / 0 pending / 0 in_progress / 0 failed`.
- Koreanized user-facing NBA/priority/status copy in app/docs/prompts while keeping explicit technical allowlists for API/status-code contracts.
- Replaced placeholder-like rendered synthetic customer/portfolio names with plausible Korean PB/WM personas and added regression guards against generic numeric `고객 NN`, raw synthetic IDs, and stale placeholder portfolio labels.
- Repaired batch runner integration regressions: single authoritative CLI definitions for `--lookback-days`, `--as-of-date`, `--provider-strictness`, provider-window postconditions, and required-provider failure reporting.
- Ran recent 30-day live pipeline with real provider rows only: BROKER snapshot DONE, DATA_GO_KR 25 rows, PYKRX 21 historical daily rows for `005930`, OpenDART 110 live filing/document-body observations, ECOS observation postcondition present, BGE embed DONE with batch size 16, and no fabricated provider rows.
- Final verification gate passed: `.omx/reports/verification/gate-20260516T093806Z.md` with `failures=0` covering runtime status, ruff, full pytest, web typecheck/lint/unit/build, Playwright `11 passed`, all-provider diagnostic batch, and required-provider acceptance batch.

## Official KRX OpenAPI Provider Readiness — 2026-05-16
- Implemented official KRX OpenAPI branch: `HARNESS_BATCH_KRX_SOURCE=KRX`, `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`, `KRX_API_BASE_URL`, and `KRX_API_KEY` via `AUTH_KEY` now collect KOSPI/KOSDAQ daily trading rows into `market_price_bars.source_code='KRX'` without automatic PYKRX fallback.
- Added V016 raw-SQL migration to allow `market_price_bars.source_code='KRX'` through a named `chk_market_price_bars_source_code` CHECK and update KRX source-license metadata.
- Readiness/dashboard/API/UI now require official persisted `KRX` rows plus `OFFICIAL_KRX_APPROVED` provider evidence for official readiness, while PYKRX remains a separate non-official auxiliary branch.

## Live Canonical Serviceable Validator Artifacts Closure — 2026-05-16
- Completed OMX team `implement-omx-plans-r-82c653e8` for
  `.omx/plans/ralplan-live-canonical-serviceable-validator-artifacts.md`: status
  `5 completed / 0 pending / 0 in_progress / 0 failed`, then shutdown completed.
- Canonical source-governance, top-200/30-day batch, data-readiness, and autoresearch validator
  artifacts now fail closed with current BLOCKED evidence instead of relying on missing or stale
  green latest files.
- Official KRX daily trading payload handling now prefers `ISU_SRT_CD` as the six-digit ticker and
  preserves `ISU_CD` as ISIN, preventing official KRX top-200 rows from being persisted under ISIN-like
  identifiers.
- Final leader verification: targeted serviceable/provider pytest `46 passed`, full pytest
  `179 passed`, targeted ruff, compileall, `git diff --check`, and a fail-closed
  `scripts/run_serviceable_canonical_readiness.py` smoke with `.env.example` that generated BLOCKED
  source/batch/readiness/result artifacts without secrets or fabricated provider rows.

## Live READY Serviceable Closure — 2026-05-16
- Closed T65 against the active `.env` PostgreSQL/Redis/official-provider runtime after the canonical wrapper returned `ok=true`.
- Root cause of the final false completion was twofold: code accepted official KRX KR8 ISINs, but DB CHECK constraints still allowed only `KR7...`; and OpenDART `document.xml` status `014` needed no-data handling rather than schema failure.
- Added V018 forward-only raw-SQL constraint normalization for `securities`, `security_identifiers`, and `market_universe_candidates`; fresh V012/V017 definitions now use `^KR[0-9A-Z]{10}$`.
- Final live evidence: `.omx/reports/verification/serviceable-canonical-run-20260516T132815Z.json` returned `ok=true`; `.omx/specs/autoresearch-service-readiness-top200-30d/result.json` returned `passed=true`, `selected_count=200`, `coverage_ratio=1.0`, and zero errors.
- Latest serviceable artifact shows official KRX `DOMESTIC_TOP200_MARKET_CAP`, `expected_member_days=4200`, `observed_member_days=4200`, `missing_member_days=0`, `status_code=READY`, with provider rows marked non-synthetic.
- Verification: V018 applied by `db/migrator.py`, targeted pytest `65 passed`, full pytest `182 passed`, and live batch logs for the final run show KRX/DART/ECOS/DATA_GO_KR/BROKER provider jobs `DONE` with zero failed rows.

## Claude Code Handoff — 2026-05-16
- Created `docs/dev/DEV-03_claude_code_handoff.md` so Claude Code can continue without reading stale chat context.
- The handoff records the verified baseline: latest full gate `.omx/reports/verification/gate-20260516T144732Z.md` passed with `failures=0`, and total readiness `.omx/reports/verification/total-product-readiness-result-20260516T145428Z.json` passed with `passed=true`.
- The first recommended follow-up is truth reconciliation: compare current code and latest verification artifacts with `BACKLOG.md` partial/open labels before doing new development.
- The handoff intentionally excludes secrets and directs future agents to use `.env` locally without printing or committing values.

---

## Wave 5 Final Documentation and Operations Handoff — 2026-05-17

### Project Closure Documentation

**Development Close-Out Records:**
- `docs/dev/DEV-05_wave1_close_out.md` — Wave 1 (security baseline: auth/middleware/WS/rate-limit) execution summary, 41 tasks, validator evidence
- `docs/dev/DEV-06_wave2_close_out.md` — Wave 2 (backend features: RAG/email/4-gate/suitability/house-view/NBA) execution summary, 23 tasks, validator evidence
- `docs/dev/DEV-07_wave3_close_out.md` — Wave 3 (module splits & compatibility: batch/scheduler/APScheduler/LLM content safety) execution summary, 8 tasks, validator evidence
- `docs/dev/DEV-08_wave4_close_out.md` — Wave 4 (UI and data readiness: 3-pane workspace/governance/model cards/domestic market) execution summary, performance analysis, 30-day batch closure
- `docs/dev/DEV-09_wave5_close_out.md` — Wave 5 (final documentation/operations/compliance) execution summary, deliverables list, acceptance gate, team roster post-mortem

**Operations Runbooks (RUN series):**
- `docs/runbooks/RUN-03_incident_response.md` — PoC operational incident response (auth lock, demo abort, token breach, audit chain break)
- `docs/runbooks/RUN-08_audit_retention_partitions.md` — Audit log partitioning design with offline migration script (5y/10y retention, row-count parity)
- `docs/runbooks/RUN-10_final_ops.md` — Operations handoff checklist, secrets rotation schedule, monitoring dashboards, incident escalation matrix, compliance procedures

**Consensus Planning References:**
- `ralplan-harness-full-mvp-implementation.md` § 13 — Consensus Review Record with final verification evidence, APPROVED verdict, acceptance gate completed
- `ralplan-harness-full-mvp-implementation.md` § 14 — Cutline appendix listing deferred items (REG-01/03/04/06, T300–T323 validators, future production readiness)

### Final Deliverables Checklist (Wave 5 T#16 W5-T3)

- [x] RUN-03_incident_response.md — 200+ lines, 4 incident types, detection/resolution/escalation/verification for each
- [x] RUN-08_audit_retention_partitions.md — 250+ lines, two-tier partition scheme, offline migration with parity checks, rollback procedures
- [x] RUN-10_final_ops.md — 400+ lines, env vars/secrets rotation/monitoring/escalation, daily/monthly ops checklists, 30-day tail support contacts
- [x] BACKLOG.md final pass — Added Wave 5 summary section, completion stats (209/324 items), deferred items classification (115 items)
- [x] PLANS.md close-out — Added Wave 5 section with links to DEV-05~09, ralplan §13/§14 references
- [x] MEMORIES.md update — Updated with Wave 5 completion status, key technical decisions, ADR cross-links, post-mortem notes
- [x] DEV-09_wave5_close_out.md — Final project close-out with deliverables list, verification evidence, acceptance gate, Wave roster, cutline status, commit posture

### Acceptance Gate Status

**PoC Ready for Ops Handoff:** ✅  
- All 7 Wave 5 deliverables completed
- Code: pytest 376 passed, validators green, ADR-001~007 cross-linked
- Documentation: 50+ technical docs synced, no stale references
- Compliance: BACKLOG marked, deferred items clearly labeled, cutline defined
- Operations: 3 new runbooks (RUN-03/08/10), team contacts, incident procedures documented

**30-Day Wave 5 Tail Support:** Available via Wave 5 integrator (contact in MEMORIES.md)  
**Production Handoff Candidates:** Documented in DEV-09 (security audit, high-availability, disaster recovery, enterprise SIEM integration)

---

## Reference — Waves Summary

| Wave | Scope | Status | Key Deliverables |
|---|---|---|---|
| 0 | BACKLOG curation + planning (T200–T323, 120 E17 items) | ✅ Closed | REG-01~06 research, ralplan consensus |
| 1 | Security baseline (auth/middleware/WS/RL/HTTPS) | ✅ Closed | REG-05 T280–T299, 41 tasks, DEV-05 |
| 2 | Backend features (RAG/email/4-gate/KYC/house-view/NBA) | ✅ Closed | V019–V022, 23 tasks, DEV-06 |
| 3 | Module splits & compatibility (batch/APScheduler/LLM) | ✅ Closed | V023–V027, 8 tasks, DEV-07 |
| 4 | UI/data readiness (3-pane/governance/30-day batch) | ✅ Closed | V028–V036, DEV-08, serviceable-canonical verified |
| 5 | Final docs/operations/compliance | ✅ Closed | RUN-03/08/10, BACKLOG/PLANS/MEMORIES/DEV-09, ready for ops handoff |
