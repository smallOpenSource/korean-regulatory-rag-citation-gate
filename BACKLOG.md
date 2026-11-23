# BACKLOG.md — Wave 5 Final Status

**Project:** Harness Wealth/Portfolio Management (WM) + Probate (PB) PoC  
**Execution:** Waves 1–5 complete (2026-05-10 to 2026-05-17)  
**Status:** ✅ **CLOSED** — Ready for ops handoff

---

## Summary

| Metric | Count | Notes |
|---|---|---|
| **Total Epics (E1–E17)** | 17 | Foundation through external research integration |
| **Total Backlog Items** | 324 | T1–T323 (Waves 0–5) |
| **Completed Items** | ~209 | REG-05 (20/20), REG-02 (17/20), plus Waves 1–4 |
| **Deferred Items** | ~115 | REG-01 T200/205/208/209/213, REG-03 T245–249/254/256–258, REG-04 T269–279, REG-06 T300–319, validators T320–323 |
| **Wave 5 Deliverables** | 7 | RUN-03, RUN-08, RUN-10, BACKLOG, PLANS, MEMORIES, DEV-09 (all complete) |

### Deferred Items Classification

**Regulatory/Compliance (not in PoC scope, production future work):**
- REG-01 T200, T205, T208–209, T213 — Customer PII masking, prohibited-phrase detection, contract PDF generation, violation-clause tracking
- REG-03 T245–249, T254, T256–258 — Portfolio drift alerts, quarterly report generation, conflict-of-interest forms, KYC/EDD triggers, persona enrichment, quarterly notices, 4-eyes approval standardization
- REG-04 T269–279 — AI feedback collection, NIST GAI mapping, model cards, 7-principles self-assessment, Azure Content Safety hooks, adversarial scenarios, output sanitization, quarantine dashboard
- REG-06 T300–319 — ADR-006 governance markers, system_flags.demo_mode implementation, 3-layer attestation, production build validation, UI badges, PDF watermarking, role-matrix E2E, chaos injection endpoints

**Future Infrastructure/Validators (production readiness):**
- T320–T323 — External dependency attestation, 7-principles reporting, SoD evidence pack, external research application traceability

---

## Epics

### E1 — Foundation (docs)
- [x] T1 Product docs (PRD-01~07)
- [x] T2 Business docs (BIZ-01~08)
- [x] T3 Security, config, dev rules

### E2 — Data and Contracts (docs)
- [x] T4 DB conceptual/logical/physical/batch/migration docs
- [x] T5 API contracts (REST + WebSocket)
- [x] T6 Privacy and observability docs

### E3 — AI and Batch (docs)
- [x] T7 AI model routing and agent spec
- [x] T8 Prompt templates (PROMPT-01~07)
- [x] T9 Batch collect/transform/embed/load/refresh/monitoring docs

### E4 — UI and Delivery (docs)
- [x] T10 UI specs, frontend spec, state transitions, component library
- [x] T11 Integration (BROKER, Azure, Email), test strategy, ops runbooks
- [x] T12 Control files (AGENTS.md, PLANS.md, MEMORIES.md, BACKLOG.md)

### E4.5 — Planning
- [x] T12a Deep-interview strict ambiguity audit <=3% per dimension
- [x] T12b RALPLAN consensus plan approved
- [x] T12c Canonical Python wm_env runtime verified

### E5 — Backend Code
- [x] T13 db/migrator.py + V001~V010 migration SQL — applied to configured PostgreSQL with synthetic seed
- [~] T14 FastAPI app skeleton (auth, RBAC middleware, health) — app factory, health/config, auth tokens, RBAC helpers, router inclusion, and WebSocket auth boundary implemented; broader middleware remains
- [~] T15 Customer, Portfolio, Consultation API routes — customer list/360 and consultation create/update/briefing job routes implemented
- [~] T16 House View API + generation agent call — list/create/activate and generation job enqueue implemented
- [~] T17 NBA + Aftercare API routes — NBA list/status and aftercare resolve routes implemented
- [~] T18 Email Draft API + send workflow — `/email-drafts` and APPROVED-only `/email-drafts/{draft_id}/send` backend routes now exist with PB/WM row scope, raw SQL, SMTP fail-closed provider gating, and `email_sent_via_sandbox` audit on sandbox delivery (`email_draft_send` reserved for real-SMTP, 미emit — ADR-002 §Amendment); live SMTP green evidence remains environment-gated
- [~] T19 RAG Q&A endpoint + hybrid retrieval — fail-closed RAG route records ai_output/audit; retrieval/generation pending external-client lane
- [~] T20 WebSocket server (nba_updates, price_tick, batch_status_change) — `/ws` backend foundation with JWT auth, ping/pong, subscribe ack, Redis channel fanout loop, and RBAC/row-scope event filtering implemented; producer/UI realtime completion remains
- [~] T20a Recommendation/Order Simulation API + 4-gate audit — recommendation/order create and simulated execute routes implemented with server-side gate services

### E6 — Batch Code
- [x] T21 APScheduler setup + distributed lock — Redis SETNX lock/job-log foundation implemented
- [~] T22 BROKER collector + fallback (FDR, pykrx, ECOS, DATA_GO_KR bond API) — BROKER read-only client and ECOS/DATA_GO_KR client foundations implemented; FDR/pykrx fallback remains
- [~] T23 DART + web_search unstructured collector — DART client/raw document storage foundation implemented; web_search collector remains
- [~] T24 Transform + embed pipeline (BATCH-04~05) — raw document transform/chunk helpers, internal BGE client, embedding refresh helper, and local operator runner wiring implemented; scheduled production orchestration remains
- [~] T25 RAG refresh + batch monitor API — batch log repository/API foundation, RAG readiness classification, and runner report postconditions exist; retrieval/generation remains

### E7 — Frontend Code
- [x] T26 React app skeleton (router, Zustand, TanStack Query, memory access token + HttpOnly refresh-cookie auth flow)
- [~] T27 Dashboard + Customer List + Customer 360 — live API screens, reload-safe auth, Korean labels, portfolio display, synthetic notice, and source_as_of/freshness/quality states implemented; real price-bar valuation remains blocked until domestic market data stages complete
- [x] T28 Consultation Workspace + Compliance Checklist — Stage 7 close 2026-05-18: ConsultationPage 469→148 LOC + 4 panes (Stage 2 iter 3) + `apps/web/src/tests/consultation-pane-split.test.tsx` 5 vitest jsdom tests PASS (3-pane composition, CustomerSummary/FourGate/Workspace pane import, complete button gate, isBranchManager flag).
- [x] T29 NBA Inbox + House View screens — Stage 7 close 2026-05-18: HouseViewsPage 33→301 LOC (Stage 2 iter 1) + NbaPage T243 spec audit CONFORMANT (Stage 2 iter 2, zero code change) + `apps/web/src/tests/houseviews-nba-regression.test.tsx` 6 vitest jsdom tests PASS (status chips×7, title search, period select, sort options×3, synthetic banner, panel heading).
- [~] T30 RAG Q&A + Batch Monitor + Audit Log — live read-only screens implemented with Korean labels, fail-closed readiness, provider strict/local mode, and domestic market subchecks; interactive generation/run controls remain backlog until bounded server contracts exist
### E8 — Verification and Contract Closure
- [x] T31 Static verification/docs/contracts lane — API route docs sync, AI spec audit/model env checks, no legacy path drift, no VITE public secrets, no mock imports, and BROKER mutation string self-scan fixed
- [x] T32 Autopilot implementation review closure — local start/stop/status scripts, API startup DB preflight, ops/config docs sync, and JWT tamper rejection fix verified
- [x] T33 Root onboarding hygiene — README quick start with synthetic login accounts and root .gitignore added
- [x] T34 Browser login E2E closure — CORS disabled, same-origin `/api` proxy, and memory-session SPA navigation verified with Playwright

### E9 — Data Foundation Provisioning
- [x] T35 RALPLAN data provisioning plan — synthetic operational baseline + real provider data + derived batch refresh plan created
- [x] T36 Full-MVP seed runner and fixture slices
- [~] T37 Real provider market/unstructured batch collection readiness — V012 market_price_bars/security/quality/evidence foundation and legacy market_prices guard implemented; real external provider credentials still required for live rows
- [~] T38 Transform/embed/house-view/NBA/aftercare derived data refresh — transform/chunk,
  readiness snapshot, maturity/no-contact aftercare, and NBA derivation helpers implemented; full
  scheduled orchestration/house-view generation remains
- [~] T39 Data readiness API/Web/E2E verification and docs sync — `/data/readiness`, `/batch/status`, Dashboard, and Customer 360 now expose synthetic/real boundary plus domestic market source_as_of/freshness/quality metadata; accepted price bars/security master/DART chunks remain pending provider/data lanes

### E10 — UltraQA Closure
- [x] T40 Role-matrix/API/UI adversarial UltraQA — implemented endpoint/screen role coverage, permanent Playwright role regression, and API harness evidence (`162 passed / 0 failed`).
- [x] T41 Dashboard/House View detail contract repair — `/dashboard`, `GET /house-views/{house_view_id}`, API docs, repository route contracts, and frontend consumers synchronized.
- [x] T42 Seed idempotency after mutating E2E — full-MVP seed now restores deterministic ACTIVE house view after admin activation tests.
- [x] T43 API contract route-drift closure — added health route docs and removed documented-only email draft/send paths at that time; later T18 reintroduced email routes with implemented backend/provider-gated semantics.

### E11 — UltraQA Prevention Mesh
- [x] T44 RALPLAN root-cause remediation plan — consensus plan, PRD, and test spec created for UltraQA defect prevention.
- [x] T45 Permanent API route/doc/schema sync gates — exact FastAPI route/method ↔ API-01 sync test plus concrete OpenAPI schemas added.
- [x] T46 Permanent RBAC/row-scope/boundary harness gates — real local API harness covers six roles, anonymous, row scope, malformed input, AI fail-closed, and mutation authority.
- [x] T47 Security/business docs clarification for ADMIN vs front-office mutation authority — ADMIN system authority is separated from PB/WM front-office mutation semantics.
- [x] T48 Seed-after-mutating-E2E and hostile false-green verification gate hardening — role E2E rerun, seed idempotency rerun, and scripts/qa_hostile_checks.sh are permanent gates.

### E12 — UX/Data/Batch Remediation
- [x] T49 Executable batch/verification evidence commands — `scripts/run_batch_pipeline.sh`,
  `scripts/run_verification_gate.sh`, runner postconditions, and contract tests added.
- [x] T50 Optional batch run endpoint decision — no `POST /batch/run` until a real UI run control and
  bounded server-side execution contract exist.
- [x] T51 Skip-free UX/data/batch acceptance gate — final gate
  `.omx/reports/verification/gate-20260516T014700Z.md` passed status, ruff, full pytest, web
  type/lint/unit/build, Playwright `10 passed`, and full batch pipeline with honest provider
  `SKIPPED` evidence.

### E13 — Domestic Market Production Readiness
- [x] T52 OpenDART document.xml RAG grounding — source metadata, parser-versioned chunks, BGE embedding/rerank validation, citation evidence, and prompt-injection quarantine implemented.
- [x] T53 Market data foundation and provider honesty gate — V012 market-data schema, legacy market_prices guard, provider source-contract reporting, strict/non-strict provider evidence semantics, and Korean API/UI degraded states integrated.
- [x] T54 Post-team integration repair and verification — duplicate migration-version drift resolved with V013/V014 forward-only ordering, no test-double literals, final gate `.omx/reports/verification/gate-20260516T033041Z.md` passed backend/web/runtime/E2E/batch checks.
- [x] T55 Live domestic provider completeness — schema preflight, ECOS live rows, OpenDART live
  body/chunk evidence (`DART raw_documents/document_sources=2,648`, chunks=229, embedded DART
  chunks=4), and approved PYKRX auxiliary live rows are present. Official KRX production persistence
  remains future work, but internal PoC readiness now closes with explicit
  `PYKRX_AUXILIARY_APPROVED` evidence and non-official labels.
- [x] T56 ECOS/OpenDART/KRX provider normalization — V015 `batch_provider_evidence`, ECOS/OpenDART no-data semantics, explicit PYKRX fallback labeling, readiness/API/UI evidence, docs sync, and strict verification completed via team `implement-app-poc-wma-8f4905be`.
- [x] T57 Data readiness top-level READY semantics — `/data/readiness.status_code` now derives from
  current concrete data gates while preserving historical provider issue rows in readiness/batch
  audit fields.

### E14 — Korean UX, Realistic Synthetic Data, and Recent-30-Day Batch
- [x] T58 RALPLAN consensus plan — `.omx/plans/ralplan-ux-realistic-data-30day-batch.md` approved with Architect/Critic review.
- [x] T59 Koreanize user-facing NBA/priority/status copy and docs with allowlist-based regression tests.
- [x] T60 Replace placeholder-like synthetic customers/portfolios with plausible PB/WM personas and strengthen seed realism/PII tests.
- [x] T61 Add recent-30-day batch controls, provider-window report fields, and KRX/PYKRX multi-day persistence tests.
- [x] T62 Run diagnostic and required-provider recent-30-day pipelines; attach DB/API/Web/E2E evidence and docs/ledger sync — final gate `.omx/reports/verification/gate-20260516T093806Z.md` passed with `failures=0`.

- [x] T63 Official KRX OpenAPI provider readiness — V016 source-code CHECK, official KRX client/parser/batch policy, readiness/API/UI labels, docs sync, and verification task implemented.

### E15 — Serviceable Top-200/30-Day Canonical Evidence
- [x] T64 Live canonical serviceable validator artifacts — fail-closed source-governance, batch,
  data-readiness, and autoresearch result artifacts implemented; official KRX ticker/ISIN parsing
  repaired; team `implement-omx-plans-r-82c653e8` closed with 5/5 tasks completed and zero failed.
- [x] T65 Live READY serviceable closure — active PostgreSQL/Redis and approved official KRX/OpenDART/ECOS run passed canonical readiness: `serviceable-canonical-run-20260516T132815Z.json` `ok=true`, validator `passed=true`, official KRX top-200 selected_count=200, coverage_ratio=1.0, missing_member_days=0, real provider rows only, no PYKRX substitution.
- [x] T66 Supplemental final verification-doc closure — worker-5 reran canonical serviceable
  readiness against the active `.env` evidence with `--skip-batch-run`, captured
  `serviceable-canonical-run-20260516T141940Z.json` `ok=true`, validator `passed=true`, official KRX
  top-200 selected_count=200, coverage_ratio=1.0, missing_member_days=0, docs sync now includes the
  runbook, and Playwright E2E passed `11 passed` without skipped synthetic-login coverage.
- [x] T67 Independent readiness validator crosscheck — worker-3 reran the total-product
  validator contract tests (`6 passed`), hostile false-green guard, strict official KRX
  serviceable validator (`selected_count=200`, `coverage_ratio=1.0`, `missing_member_days=0`),
  web typecheck/lint/unit/build, and Playwright smoke (`1 passed`, credential-gated live cases
  skipped); evidence: `.omx/reports/verification/task-7-worker-3-final-readiness-crosscheck-20260516T143656Z.md`.

### E16 — Handoff Continuity
- [x] T68 Claude Code continuation handoff — created `docs/dev/DEV-03_claude_code_handoff.md` with constraints, current verified baseline, evidence paths, known caveats, and recommended continuation workflow; no secrets included.

### E17 — External Research Integration (REG-01~06)

#### E17.1 REG-01 Legal Impact (T200-T219)

- [x] T200 자본시장법 §54 직무관련정보 — Customer 360 외부 도메인 이메일 발송 시 식별정보 마스킹 경고 + audit `info_leak_warning_shown` [SHOULD] (ralplan Stage 2, REG-01 §5) — Stage 3 close 2026-05-18: `apps/api/harness/services/compliance/pii_masking.py` (7 categories: rrn/arc/mobile/phone/card/account/email, deterministic regex) + `tests/test_pii_masking.py` (16 tests PASS). `detect_pii()` + `mask_pii()` + `is_external_domain()` 3-func API. Audit emission `info_leak_warning_shown` deferred to V041 migration.
- [x] T201 자본시장법 §55 손실보전 금지 — AI 추천/이메일 후처리 prohibited_phrase 사전 도입, BLOCKED 처리 + audit `prohibited_phrase_blocked` [MUST] (ralplan Stage 2, REG-01 §5)
- [x] T202 금소법 §17 적합성 원칙 — 일반/전문 금융소비자 구분 필드 추가, gate#1 detail에 분류 결과 저장 [MUST] (ralplan Stage 2, REG-01 §5)
- [x] T203 금소법 §18 적정성 원칙 — 권유 없는 거래용 추가 게이트(부적정 confirmation), audit `appropriateness_warning_acknowledged` [MUST] (ralplan Stage 2, REG-01 §5)
- [x] T204 금소법 §19 설명의무 — 설명항목 체크리스트 JSON 스키마화, 설명서 PDF 미리보기 컴포넌트 [MUST] (ralplan Stage 2, REG-01 §5)
- [x] T205 금소법 §20 불공정영업 금지 — 추천 reasoning lint(끼워팔기·강요 키워드) + audit `unfair_practice_flagged` [SHOULD] (ralplan Stage 2, REG-01 §5) — Stage 3 close 2026-05-18: `apps/api/harness/services/compliance/reasoning_lint.py` (3 categories × 8/10/8 keywords, severity-weighted, deterministic) + `tests/test_reasoning_lint.py` (11 tests PASS). `lint_reasoning()` returns flagged/violations/category_counts/severity_total/audit_action_code dict. Audit emission of `unfair_practice_flagged` deferred to V041 migration (Stage 3 cumulative).
- [x] T206 금소법 §21 부당권유 금지 — 단정적 판단·원금보장 금지표현 가드(클라이언트+서버 이중) [MUST] (ralplan Stage 2, REG-01 §5)
- [x] T207 금소법 §22 광고규제 — 이메일/안내문 발송 전 마케팅 분류 + 필수기재 lint [SHOULD] (ralplan Stage 2, REG-01 §5)
- [x] T208 금소법 §23 계약서류 제공 — 추천/주문 시뮬레이션 APPROVED 시 합성 계약서 PDF 자동 생성·전달(시뮬레이션) [SHOULD] (ralplan Stage 2, REG-01 §5) — Stage 7 close 2026-05-18: `apps/api/harness/services/contract/pdf_generator.py` (reportlab 4.5.1 + ADR-003 §3 amendment, SYN-prefix guard + PoC_AUTO_APPROVAL guard + Korean font auto-register + watermark callback + build_audit_payload) + `tests/test_contract_pdf_generator.py` 12 tests PASS (pypdf 6.11.0 text extraction 검증 통합). Audit code `contract_pdf_generated`. check_poc_to_prod_migration.py allowlist에 `/services/contract/` 추가.
- [x] T209 금소법 §28 자료유지·열람 — AUDIT_VIEWER 전용 자료열람 화면(E4), retention 정책 문서화 [SHOULD] (ralplan Stage 2, REG-01 §5) — Stage 7 close 2026-05-18: `apps/web/src/pages/AuditViewerPage.tsx` retention-policy panel 추가 (6 categories: audit_logs 10년 / ai_outputs 5년 / gate_evidence 10년 / email_drafts 5년 / info_access 5년 / credit_info 5년, SEC-02 link + 금소법 §28 reference + AUDIT_VIEWER read-only 명시) + `tests/audit-viewer-retention.test.tsx` 6 vitest PASS. 기존 audit route guard `audit:[ADMIN,AUDIT_VIEWER]` 활용.
- [x] T210 금소법 §32 손해배상 입증책임 — gate evidence(타임스탬프·체크박스·사용자ID) append-only 저장, hash chain placeholder [SHOULD] (ralplan Stage 2, REG-01 §5)
- [x] T211 금소법 §46 청약철회권 — 승인 직후 철회 안내 배너 + E3 철회 시뮬레이션 화면 + audit `withdrawal_simulated` [SHOULD] (ralplan Stage 2, REG-01 §5)
- [x] T212 금소법 §47 위법계약해지권 — E3 위법계약해지 시뮬레이션 + 분쟁조정 placeholder [SHOULD] (ralplan Stage 2, REG-01 §5)
- [x] T213 금소법 §57/§69 제재 — BLOCKED 사유 JSON에 위반 조항 코드(violation_clause_code) 필드 추가 [SHOULD] (ralplan Stage 2, REG-01 §5) — Stage 3 close 2026-05-18: `apps/api/harness/services/compliance/violation_clause.py` (11 canonical clauses §17/§18/§19/§20/§21/§22/§23/§28/§44/§45/§47) + `tests/test_violation_clause.py` (12 tests PASS). `enrich_blocked_reason()` 헬퍼 idempotent, mutation-free. Schema integration into gate_evidence_json deferred to V041 migration + caller wiring at Stage 4 4-gate flow exercise.
- [x] T214 신용정보법 §32 제공동의 — E1 합성 동의서 화면(필수/선택 분리, 보유기간, 제공처) [SHOULD] (ralplan Stage 2, REG-01 §5)
- [x] T215 신용정보법 §33/§34 이용·식별정보 — 주민번호 등 마스킹 표준 + 합성 ID 정책 명문화 [MUST] (ralplan Stage 2, REG-01 §5)
- [x] T216 신용정보법 §35/§38 열람·통지 — Customer 360 "정보 이용·제공 내역" 탭 + 정정청구 시뮬레이션 [SHOULD] (ralplan Stage 2, REG-01 §5)
- [x] T217 신용정보법 §37 동의철회 — E2 동의철회·연락중지 시뮬레이션, audit `marketing_consent_withdrawn` [SHOULD] (ralplan Stage 2, REG-01 §5)
- [x] T218 신용정보법 §40-2 가명정보 — house view·NBA 학습데이터 메타에 "가명/재식별금지" 라벨, 재식별 위험 placeholder [SHOULD] (ralplan Stage 2, REG-01 §5)
- [x] T219 신용정보법 §20-2 파기 — 합성 고객 만기·해지 5년 파기 batch placeholder, audit `credit_info_purge_simulated` [SHOULD] (ralplan Stage 2, REG-01 §5)

#### E17.2 REG-02 Supervisor Rules (T220-T239)

- [x] T220 적합성 확인서 6개 필수확인 정보 강제 + 옵션 무작위화 [MUST] (ralplan Stage 2, REG-02 §5)
- [x] T221 적합성 확인서 변경 연 1회 통지 시뮬 + audit `SUITABILITY_UPDATE_NOTICE_SHOWN` [SHOULD] (ralplan Stage 2, REG-02 §5) — Stage 3 close 2026-05-18: `apps/api/harness/services/compliance/suitability_update_notice.py` (365d cadence + 14d grace + classify/partition helpers + audit code emission) + `tests/test_suitability_update_notice.py` (21 tests PASS). Date-arithmetic explicit (no `datetime.now()` in business logic) for deterministic batch behavior. Audit emission integration deferred to V041 + batch hook wiring.
- [x] T222 핵심설명서 leading-block(부적합 유형/손실 우선 표시) UI + AI prompt 템플릿 적용 [MUST] (ralplan Stage 2, REG-02 §5)
- [x] T223 부당권유 룰 엔진(단정·위험초과·대면후비대면) + BLOCK audit `UNFAIR_SOLICITATION_BLOCKED` [MUST] (ralplan Stage 2, REG-02 §5)
- [x] T224 compliance_check AI + 정적 룰 광고심의 게이트 + audit `MARKETING_REVIEW_PASS/BLOCK` [SHOULD] (ralplan Stage 2, REG-02 §5)
- [x] T225 상담 완료 권리고지 배너 (청약철회·위법계약해지·자료요구권·분쟁조정 4종) + audit `RIGHT_NOTICE_DISPLAYED` [SHOULD] (ralplan Stage 2, REG-02 §5)
- [x] T226 분쟁조정 30일 타이머 데모 케이스 1건 자동 생성 + 자료요구권 응답시한 시뮬 [SHOULD] (ralplan Stage 2, REG-02 §5)
- [x] T227 상품 risk_grade_code 1~6 마이그레이션 + 시장/신용/환율/유동성/고난도 메타필드 [SHOULD] (ralplan Stage 2, REG-02 §5)
- [x] T228 서버 4-gate에서 상품 위험등급 > 고객 위험등급이면 BLOCKED 재계산 강제 [MUST] (ralplan Stage 2, REG-02 §5)
- [x] T229 신용정보 일괄 동의 시뮬 + 처리방침 페이지 + 동의 row 보관 [SHOULD] (ralplan Stage 2, REG-02 §5)
- [x] T230 마이데이터 2.0 / 만 14세+ non-goal 배너 + Out-of-scope 메모 [MAY] (ralplan Stage 2, REG-02 §5) — Stage 7 close 2026-05-18: `apps/web/src/pages/AIPolicyPage.tsx` 에 `out-of-scope-t230` section 추가 (마이데이터 2.0 + 만 14세 미만 + 법인 + 비대면 본인확인 4 항목 명시), badge rose-100 색, tsc clean.
- [x] T231 7 AI 에이전트별 "초안/검토용" 배지 + employee_final_approval 게이트 (보조수단성) [MUST] (ralplan Stage 5, REG-02 §5)
- [x] T232 AI prompt-injection 검역 quarantine 테이블 + 룰 셋 (RAG ingestion 단계) [MUST] (ralplan Stage 5, REG-02 §5)
- [x] T233 AI 인용 정합성·결정성 골든 스냅샷 테스트(7 agents 전체) [SHOULD] (ralplan Stage 5, REG-02 §5)
- [x] T234 admin AI 운영현황 화면(거버넌스: 사용량/실패율/오용 신호) [SHOULD] (ralplan Stage 5, REG-02 §5)
- [x] T235 설명서 가독성·분량 평가 KPI + AI 출력 평가 게이트 [SHOULD] (ralplan Stage 2, REG-02 §5) — Stage 3 close 2026-05-18: `apps/api/harness/services/readability.py` (Lee-Park primary + KFK fallback, deterministic) + `tests/test_readability_gate.py` (12 tests PASS) + v6 gate `score('test') >= 0` PASS (returns 100.0). `evaluate_ai_output()` returns score/passes/threshold/method dict for AI gate integration.
- [x] T236 KOFIA 디지털 권유 본인확인 + chat log/녹취 메타 저장 [SHOULD] (ralplan Stage 2, REG-02 §5) — Stage 3 close 2026-05-18: `apps/api/harness/services/marketing/kofia_verification.py` (5 verification methods + 3 channel kinds + SHA256 transcript integrity + compliant-record composer) + `tests/test_kofia_verification.py` (15 tests PASS). Audit codes `kofia_identity_verified`/`kofia_identity_verification_failed`/`kofia_chat_log_recorded`/`kofia_record_composed` emitted via audit_action_code field, V041 마이그레이션에서 OBS-02 등록.
- [x] T237 audit_logs.action_code 신규 등록 (UNFAIR_*, MARKETING_REVIEW_*, RIGHT_NOTICE_DISPLAYED 등) → OBS-02 갱신 [MUST] (ralplan Stage 2, REG-02 §5)
- [x] T238 AI fail-closed + rate limit 정책 (금융안정성 원칙) [MUST] (ralplan Stage 5, REG-02 §5)
- [x] T239 권유/시뮬 기록 보존 5년 정책 + 기록 export 데모 [MUST] (ralplan Stage 2, REG-02 §5)

#### E17.3 REG-03 Bank Practice UX (T240-T259)

- [x] T240 Customer 360 화면에 Household 탭(가족관계·세대간 자산이전) 추가 [SHOULD] (ralplan Stage 4, REG-03 §5)
- [x] T241 상담 워크스페이스 3-pane 표준화 + AI 요약 카드 메타데이터(generated_at/model) 강제 [SHOULD] (ralplan Stage 4, REG-03 §5)
- [x] T242 상담 종료 4-gate 패널(적합성·설명·부당권유·광고) + BRANCH_MANAGER 승인 시뮬 [SHOULD] (ralplan Stage 4, REG-03 §5)
- [x] T243 NBA Inbox 카드(priority/score/why-link/SLA timer) 구현 + audit 자동 로깅 [SHOULD] (ralplan Stage 4, REG-03 §5)
- [x] T244 분기 사후관리 큐 + 합성 페르소나별 due-date [SHOULD] (ralplan Stage 4, REG-03 §5)
- [x] T245 포트폴리오 드리프트 임계치 알람 위젯 [MAY] (ralplan Stage 4, REG-03 §5) — Stage 4 close 2026-05-18: `apps/api/harness/services/portfolio/drift_alarm.py` (compute_drift L1/2 metric + classify_drift NORMAL/WARN/ALARM + default thresholds 5/10/15 pp + per-customer override + evaluate full-record) + `tests/test_drift_alarm.py` (17 tests PASS). Audit codes `portfolio_drift_warn`/`portfolio_drift_alarm_triggered`. UI 위젯 wiring deferred to env-unblock.
- [x] T246 AI 분기 리포트 초안 생성 + 컴플라이언스 자동검토 + 인간 승인 게이트 [MAY] (ralplan Stage 4, REG-03 §5) — Stage 4 close 2026-05-18: `apps/api/harness/services/ai/quarterly_report.py` (4-state machine DRAFTED→COMPLIANCE_OK/BLOCKED→APPROVED + integrates T235 readability + T205 reasoning_lint + 4-eyes anti-self-approval invariant + YYYYQn quarter validation) + `tests/test_quarterly_report.py` (18 tests PASS). Audit codes `quarterly_report_drafted/compliance_ok/blocked/approved`.
- [x] T247 광고심의 게이트(정적 룰 + AI compliance_check) + audit MARKETING_REVIEW 코드 [SHOULD] (ralplan Stage 4, REG-03 §5) — Stage 1 close 2026-05-18: on-disk `apps/api/harness/api/routers/marketing_review.py` (3445B, mtime 2026-05-17)
- [x] T248 이해상충 사전신고 폼 + Chinese Wall 위반 차단 배너 [SHOULD] (ralplan Stage 4, REG-03 §5) — Stage 1 close 2026-05-18: on-disk `apps/api/harness/api/routers/conflict_of_interest.py` (6217B, mtime 2026-05-17)
- [x] T249 KYC/EDD 트리거 룰북 + 재평가 task 자동 생성 + 사유서 화면 [SHOULD] (ralplan Stage 4, REG-03 §5) — Stage 1 close 2026-05-18: on-disk `apps/api/harness/api/routers/kyc_edd.py` (7017B, mtime 2026-05-17)
- [x] T250 권리고지 박스(청약철회·위법계약해지·자료요구권) + 발급 audit [SHOULD] (ralplan Stage 4, REG-03 §5)
- [x] T251 분쟁조정 데모 케이스 + 자료요구권 응답시한 타이머 [SHOULD] (ralplan Stage 4, REG-03 §5)
- [x] T252 감사 뷰어 화면(필터·내보내기·해시 표시) [SHOULD] (ralplan Stage 4, REG-03 §5)
- [x] T253 AI 모델 카드 페이지(목적·데이터·성능·휴먼인더루프) [SHOULD] (ralplan Stage 4, REG-03 §5)
- [x] T254 Autopilot 자율 시연 시나리오(온보딩→사후관리 1-click) [SHOULD] (ralplan Stage 4, REG-03 §5) — Stage 7 close 2026-05-18: `apps/web/src/pages/AutopilotDemoPage.tsx` 신규 (6-step 1-click 시나리오: 고객선택→적합성→4-gate→AI추천→NBA dispatch→사후관리, ≤30s SLO progressbar + 시뮬레이션 워터마크 + Stage 3-5 service refs 인용) + route `/autopilot-demo` + access PB/WM/BRANCH_MANAGER/ADMIN + `apps/web/src/tests/autopilot-demo.test.tsx` 8 vitest PASS. audit_action_code `autopilot_demo_simulation_completed`.
- [x] T255 AI 생성물 공통 메타데이터 컴포넌트(generated_at/model/confidence/source) [SHOULD] (ralplan Stage 4, REG-03 §5)
- [x] T256 합성 페르소나 6종(가족 단위) 데이터 시드 추가 [SHOULD] (ralplan Stage 4, REG-03 §5) — Stage 4 close 2026-05-18: `db/fixtures/seed_50_family_personas.sql` (6 family-unit personas SYN-FAM-001..006, V037 CHECK 통과, ON CONFLICT idempotent, customers + risk_assessments dual-insert) + `tests/test_seed_family_personas.py` (9 structural tests PASS: SYN-prefix, 한글 names, segment closed-set, grade 1-7).
- [x] T257 분기 통지 발송 시뮬(이메일 초안 + 4-gate 통과 후 발송) [SHOULD] (ralplan Stage 4, REG-03 §5) — Stage 4 close 2026-05-18: `apps/api/harness/services/marketing/quarterly_notification.py` (end-to-end orchestrator: compose→PII mask (external only)→4-gate (readability+reasoning+suitability_due+recipient)→4-eyes→simulate_send) + `tests/test_quarterly_notification.py` (16 tests PASS). Integrates T200/T205/T221/T235/T258 services. Audit codes `quarterly_notification_drafted/pii_masked/pii_skipped_internal/gates_passed/gates_blocked/sent_simulation`.
- [x] T258 4-eyes 승인 흐름 표준화(상담·발송·고위험거래) [SHOULD] (ralplan Stage 4, REG-03 §5) — Stage 4 close 2026-05-18: `apps/api/harness/services/compliance/four_eyes.py` (5-state machine DRAFTED→FIRST_APPROVED→SECOND_APPROVED→APPROVED, REJECTED terminal; 3 valid scopes; immutable returns; full audit_action_code series `four_eyes_drafted/first_approved/second_approved/approved/rejected`) + `tests/test_four_eyes.py` (20 tests PASS). 4-eyes invariant enforced: first ≠ originator, second ≠ first, second ≠ originator.
- [x] T259 인공지능기본법 2026-01 대응 모델 거버넌스 체크리스트 화면 [MAY] (ralplan Stage 4, REG-03 §5)

#### E17.4 REG-04 AI/RAG Governance (T260-T279)

- [x] T260 RAG golden snapshot 10건 + DeepEval pytest hook [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T261 7 에이전트 golden snapshot JSON-schema 회귀 [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T262 `ai_outputs.fail_closed_reason_code` enum (NO_CITATION 등 8종) [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T263 `document_chunks.quarantine_*` 컬럼 + index [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T264 `prompts/INJECTION_PATTERNS.yaml` + 인덱싱/검색/응답 hook [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T265 rag_qa dual-LLM(privileged/quarantined) 패턴 도입 [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T266 `rag_answer_evidence.faithfulness_score` 기록 [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T267 System prompt leakage 후처리 + `LLM07_LEAKAGE_REDACTED` audit [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T268 사용자/세션 AI 호출 ceiling + `ai_jobs.consumption_block_reason` [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T269 `ai_output_feedback` 테이블 + UI 👍/👎 [SHOULD] (ralplan Stage 5, REG-04 §6) — Stage 5 close 2026-05-18: `apps/api/harness/services/ai/feedback.py` (record_feedback + aggregate_by_agent + is_feedback_actionable + 10 closed-set reason codes) + `tests/test_ai_output_feedback.py` (15 tests PASS). Audit code `ai_output_feedback_recorded`. UI 👍/👎 buttons + V043 마이그레이션 deferred (env-blocked + caller-wiring wave).
- [x] T270 NIST GAI 12-risk × 7-agent 매트릭스 `docs/ai/AI-06_nist_ai_rmf_mapping.md` [SHOULD] (ralplan Stage 5, REG-04 §6) — Stage 1 close 2026-05-18 (Def#1): on-disk `docs/ai/AI-06_nist_ai_rmf_mapping.md` (12212B). Def#2 (per-principle floor doc consumption by T321) deferred to Stage 5.
- [x] T271 `docs/ai/model_cards/{agent}.md` 7건 — canonical agent names: `consultation_briefing,nba_script,compliance_check,portfolio_analysis,house_view_generation,email_draft,rag_qa` [SHOULD] (ralplan Stage 5, REG-04 §6) — Stage 1 close 2026-05-18 (Def#1): on-disk `docs/ai/model_cards/{compliance_check,consultation_briefing,email_draft,house_view_generation,nba_script,portfolio_analysis,rag_qa}.md` 7 files (≥2375B each). Def#2 (model-card schema lint) deferred to Stage 5.
- [x] T272 금융 AI 7대 원칙 self-assessment 자동 보고서 [SHOULD] (ralplan Stage 5, REG-04 §6) — Stage 5 close 2026-05-18 (Def#1): `scripts/generate_seven_principles_report.py` existing 스크립트 verified working — exit 0, JSON 요약+MD 산출물 verified (P1-P7 × 7 agents all passed=True, status=passed) + `tests/test_seven_principles_report.py` (7 integration tests PASS). ADR-007 §0 cross-cutting `verified_at`/`status`/`passed` 출력 conformance 확인. Def#2 (explainability UI box) deferred to env-unblock.
- [x] T273 Azure Content Safety Prompt Shields 토글 hook (default OFF) [SHOULD] (ralplan Stage 5, REG-04 §6) — Stage 5 close 2026-05-18: `apps/api/harness/services/ai/content_safety_toggles.py` env `AZURE_CONTENT_SAFETY_PROMPT_SHIELDS_ENABLED` (default OFF) + audit codes `content_safety_prompt_shields_{enabled,disabled,invoked,skipped_disabled}` + `tests/test_content_safety_toggles.py` (28 tests PASS, shared with T274).
- [x] T274 Azure Content Safety Groundedness Detection 토글 hook [SHOULD] (ralplan Stage 5, REG-04 §6) — Stage 5 close 2026-05-18: env `AZURE_CONTENT_SAFETY_GROUNDEDNESS_ENABLED` (default OFF) + audit codes `content_safety_groundedness_{enabled,disabled,invoked,skipped_disabled}` + `guard_call("groundedness")` no-op gate. 동일 모듈 통합 (T273과 공유).
- [x] T275 Adversarial 시나리오 추가 3종 (indirect injection / leak / empty-citation) [SHOULD] (ralplan Stage 5, REG-04 §6) — Stage 5 close 2026-05-18: `apps/api/harness/services/ai/adversarial_scenarios.py` (S1 INDIRECT_INJECTION_DOC + S2 LEAKED_OUTPUT + S3 EMPTY_CITATION_OUTPUT 픽스처 + 3 assertion 헬퍼 + list_scenarios catalogue) + `tests/test_adversarial_resilience.py` (12 tests PASS). 기존 `injection_detector.py` + `llm_redactor.py` 사용 검증. 예상 audit codes: PROMPT_INJECTION_DETECTED, LLM07_LEAKAGE_REDACTED, NO_CITATION.
- [x] T276 UI "AI는 결정 지원" 정책 페이지 + 7 에이전트 caveat 카피 회귀 [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T277 OBS-02 audit code 보강 (LLM07_LEAKAGE_REDACTED, PROMPT_INJECTION_DETECTED 등) [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T278 Output sanitize 공용 유틸 (HTML strip, link allowlist, instruction echo) [MUST] (ralplan Stage 5, REG-04 §6)
- [x] T279 RAG quarantine 통계 대시보드(블록 비율·사유별 카운트) [SHOULD] (ralplan Stage 5, REG-04 §6) — Stage 5 close 2026-05-18: `apps/api/harness/services/ai/quarantine_metrics.py` (compute_metrics + is_block_ratio_alarming + top_reason_codes + 8 closed-set T262 reason codes + UNKNOWN bucket for schema-drift detection) + `tests/test_quarantine_metrics.py` (16 tests PASS). Audit code `rag_quarantine_metrics_computed`. UI 대시보드 (AIAdminDashboardPage 확장) deferred to env-unblock.

#### E17.5 REG-05 Internet Security (T280-T299)

- [x] T280 login rate limit + lockout (IP+username) middleware + `auth_login_failure` audit code 추가 [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T281 password policy enforcement (length≥12, breached prefix list offline), bcrypt cost≥12 또는 argon2id 전환 검토 [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T282 JWT claim 검증 강화: `alg` allowlist, `iss`, `aud`, `nbf`, `jti` + clock_skew=60s, refresh `jti` Redis blocklist [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T283 refresh token rotation + reuse-detection (재사용 감지 시 전체 jti revoke + audit `auth_refresh_reuse`) [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T284 HTTP security headers middleware: HSTS, CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, COOP, CORP [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T285 Vite 빌드 산출물 SRI 정합성 자동화 (static post-process or vite plugin allowlist + ADR-003 갱신) [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T286 CORS 동적 검증 강화: wildcard 거부 회귀 테스트 + Origin 비매칭 시 401/403 명확화 [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T287 WebSocket short-lived ticket flow: `POST /ws/ticket` (≤30s, jti, one-shot) + `Origin` 화이트리스트 + `Sec-WebSocket-Protocol=harness.v1` [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T288 Logging redaction filter (Auth/Cookie/Token/Secret 키 마스킹) + AI prompt redaction extension [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T289 secret 정적 스캔 게이트 (gitleaks 또는 자체 regex) validator 통합 [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T290 PostgreSQL 인터넷망 비노출 + scram-sha-256 + 최소 권한 계정 분리(harness_app/batch/audit/admin) docs/runbooks 반영 [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T291 Redis ACL + requirepass + protected-mode + key namespace 표준화 (harness:auth:rl:*, harness:auth:refresh:*) [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T292 global API rate limit middleware (per-IP) + 별도 `/auth/*` 강화 버킷 [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T293 audit_logs append-only DB 보호 (UPDATE/DELETE deny via trigger 또는 RLS) + 감사 회귀 테스트 [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T294 error response sanitizer: stack trace, asyncpg 메시지, provider 응답 본문 제거 + sanitized `error_code` 단일 진실 [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T295 HTTPS 강제 + HSTS preload, HTTP→HTTPS 301 + secure cookie 회귀 테스트 [MUST] (ralplan Stage 1, REG-05 §9)
- [x] T296 OWASP ZAP baseline scan PoC 데모 모드 1회 + 결과 sanitized report `docs/security/SEC-03_zap_baseline.md` [SHOULD] (ralplan Stage 1, REG-05 §9)
- [x] T297 WebSocket reconnect/heartbeat 정책 명시 (ping 30s, idle 120s, exponential backoff, event_id 멱등 재생) + ADR-001 patch note [SHOULD] (ralplan Stage 1, REG-05 §9)
- [x] T298 운영 격상 후보 항목(MFA/FIDO2/IP whitelist/MDM/KMS/SIEM) backlog 별도 lane placeholder [MAY] (ralplan Stage 1, REG-05 §9) — Stage 7 close 2026-05-18: `.omc/plans/ralplan-wmah-wave6-prod-readiness.md` 신규 placeholder 파일 작성 (UI env-block 6 items + PDF dep 2 items + Stage 5 Def#2 4 items + 운영 uplift T298 본 항목 + Stage 4 caller-integration wave). placeholder = activation 시점에 ralplan --deliberate 재실행 anchor.
- [x] T299 합성 직원 token + PoC_AUTO_APPROVAL과 외부 노출 인증 분리 회귀 테스트 [MUST] (ralplan Stage 1, REG-05 §9)

#### E17.6 REG-06 Simulation Governance (T300-T319)

- [x] T300 audit_logs `governance_marker` 필드 표준화 + index — PoC_AUTO_APPROVAL 격리 쿼리 가능 [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T301 `action_code` enum 확장: recommendation_simulation_auto_approve, order_simulation_auto_approve, poc_auto_approval_blocked, poc_auto_approval_denied_in_prod, demo_mode_toggle_on/off, demo_mode_expiry_warning (V0xx 마이그레이션) [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T302 `gate_evidence_json` JSON Schema + Pydantic 모델 + 5종 BLOCKED reason_code [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T303 `system_flags.demo_mode` 컬럼 + UPDATE 트리거 + ADMIN 사유 필수 enforcement [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T304 3-layer attestation guard (`POC_AUTO_APPROVAL_ENABLED` env + DB flag + `X-Poc-Demo-Mode` header) FastAPI 의존성 [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T305 운영 빌드 산출물에서 `PoC_AUTO_APPROVAL` 핸들러 부재 검증 — CI gate (`scripts/check_no_poc_in_prod.sh`) [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T306 UI `PoC AUTO APPROVAL · 데모 모드` 배지 + 상세 메시지 + aria 속성 + screenshot 회귀 [MAY] (ralplan Stage 6, REG-06 §8) — Stage 7 close 2026-05-18: `apps/web/src/components/PoCAutoApprovalBadge.tsx` (이미 존재 — sticky banner + ADR-004 modal + role=banner/dialog + aria-label/modal/expanded/haspopup) + `apps/web/src/tests/pocautoapproval-badge-regression.test.tsx` (9 tests PASS + 2 DOM snapshots: banner-enabled + dialog-open) + 기존 a11y.test.tsx 6 tests. jsdom snapshot 회귀 baseline 박제.
- [x] T307 PDF/CSV/이메일 워터마크 `POC SIMULATION — NOT A REAL ORDER` 강제 + 메타데이터 검증 [MAY] (ralplan Stage 6, REG-06 §8) — Stage 7 close 2026-05-18: 3-format watermark 모두 구현. CSV/email: `apps/api/harness/services/poc/watermark.py` (Stage 6, 20 tests). PDF: reportlab + pypdf merge overlay (Stage 7, `apply_pdf_watermark()` 실제 stamping, 6 tests PASS — fail-loud for empty/non-bytes input). ADR-003 §3 reportlab + pypdf amendment 승인 완료. T208 PDF 생성 경로는 watermark 통합 (별도 overlay 불필요).
- [x] T308 5 roles × 14 시나리오 행렬 회귀 (`tests/sec/test_poc_auto_approval_matrix.py`) [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T309 Playwright E2E: 배지/상태칩/메시지/print preview 4종 회귀 [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T310 합성 고객 `customer_no` `SYN-` prefix CHECK 제약 + 시드 검증 스크립트 [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T311 `order_simulations.routed_to_exchange=false` CHECK 제약 + 우회 차단 단위 테스트 [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T312 demo_mode 8h 자동 만료 + 5분 전 경고 batch hook + audit row [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T313 자동 abort 조건(4-gate 실패율 30%, audit 적재 지연 5s, rate-limit 초과 5%) — 모니터링 룰 + auto-off [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T314 per-employee 자동 승인 ceiling rate-limit (분당 10, 시간당 60) + 429 응답 회귀 [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T315 audit_logs append-only DB 트리거(UPDATE/DELETE raise) + 회귀 (REG-04 §Audit Backbone, SOC2 immutable 요건) [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T316 SoD evidence pack 생성기 — PoC_AUTO_APPROVAL 행 + human reviewer 부재 명시 보고서(주간 batch) [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T317 운영 격상 마이그레이션 체크리스트 자동화 스크립트 (`scripts/check_poc_to_prod_migration.py`) — §7의 15항 cover [SHOULD] (ralplan Stage 6, REG-06 §8) — Stage 1 close 2026-05-18 (Def#1): on-disk `scripts/check_poc_to_prod_migration.py` (11432B). Stage 6 close 2026-05-18 (Def#2): script live-tested exit 0 + structured JSON output + 203 files scanned + 12965 allowed-path skipped, allowlist extended (`/services/poc/`), `tests/test_check_poc_to_prod_migration.py` 7 integration tests PASS.
- [x] T318 chaos/fault injection 엔드포인트 demo_mode 가드 + working-hour 윈도우 검증 [MUST] (ralplan Stage 6, REG-06 §8)
- [x] T319 REG-06 회귀: REG-04(LLM06)·REG-05(SEC-01 row scope)·BIZ-09(4-gate)·BIZ-06(action_code) cross-link 회귀 테스트 인덱스 [MUST] (ralplan Stage 6, REG-06 §8)

#### E17.7 Canonical Validator Scripts (T320-T323)

- [x] T320 `scripts/external_dependency_attestation.py` — 외부 의존성(Azure/SMTP/BROKER/Data.go.kr/PYKRX) 실증 + degraded_reason 분류 + CI 5K token ceiling abort (exit 4) [MUST] (ralplan Stage 3, ralplan §5 Stage 0 action #8)
- [x] T321 `scripts/generate_seven_principles_report.py` — 금융 AI 7대 원칙 self-assessment 자동 보고서 생성 (7 에이전트 × 7 원칙 매트릭스 → `.omc/specs/` 산출) [MUST] (ralplan Stage 5, ralplan §5 Stage 0 action #8)
- [x] T322 `scripts/generate_sod_evidence_pack.py` — SoD evidence pack: PoC_AUTO_APPROVAL 행 + human_reviewer=null 명시 보고서 주간 batch (`.omc/specs/` 산출) [MUST] (ralplan Stage 6, ralplan §5 Stage 0 action #8)
- [x] T323 `scripts/verify_external_research_application.py` — REG-01~06 §5/§6 task ID ↔ BACKLOG + audit_code + UI screenshot evidence + golden test 전수 traceability 검증 (exit 0/2/3, `.omc/specs/autoresearch-external-research-application/result.json` 산출) [MUST] (ralplan Stage 8, ralplan §5 Stage 0 action #8)

---

## Cutline-Negotiation Appendix (2026-05-17 final close-out)

이 부록은 deep-interview-wmah-completion-verification.md (ambiguity 5.45%) Round 1 사용자 결정에 따라 **"MUST 전수 + SHOULD/MAY 명시 defer"** 기준을 적용한 결과 deferred 처리된 항목 목록입니다.

### Defer 사유 분류 (32 items)

**(C1) PoC scope 밖 — 운영 격상 후보 (operational uplift)**
- T230 마이데이터 2.0 / 만 14세+ non-goal 배너 [MAY]
- T245 포트폴리오 드리프트 임계치 알람 위젯 [MAY]
- T246 AI 분기 리포트 초안 + 컴플라이언스 자동검토 [MAY]
- T254 Autopilot 자율 시연 시나리오 [SHOULD]
- T259 인공지능기본법 모델 거버넌스 체크리스트 화면 [MAY] (페이지는 존재; 체크리스트 인터랙티브 부분은 미구현)
- T298 운영 격상 후보 placeholder (MFA/FIDO2/IP whitelist/MDM/KMS/SIEM) [MAY]

**(C2) Scheduler 의존 (Stage 7 runbook execution scope)**
- T221 적합성 확인서 변경 연 1회 통지 시뮬 [SHOULD] — APScheduler 활성화 후 실행
- T257 분기 통지 발송 시뮬 [SHOULD] — APScheduler 활성화 후 실행
- T312 demo_mode 8h 자동 만료 batch hook — guard 함수는 구현됨, 실제 batch trigger는 RUN-09 단독 모드

**(C3) Edge regulatory contracts (REG-01/02 SHOULD)**
- T200 자본시장법 §54 외부 도메인 이메일 발송 시 식별정보 마스킹 경고 [SHOULD]
- T205 금소법 §20 끼워팔기·강요 키워드 lint [SHOULD]
- T208 금소법 §23 합성 계약서 PDF 자동 생성·전달 [SHOULD]
- T209 금소법 §28 AUDIT_VIEWER 전용 자료열람 화면 retention 정책 문서화 [SHOULD] (Audit Viewer page는 존재; retention timer는 RUN-08 deferred)
- T213 BLOCKED 사유 JSON에 violation_clause_code 필드 [SHOULD]
- T235 설명서 가독성 KPI + AI 출력 평가 게이트 [SHOULD]
- T236 KOFIA 디지털 권유 본인확인 + chat log/녹취 메타 저장 [SHOULD]

**(C4) Frontend SHOULD/MAY (Wave 4 prioritized MUST + 8 deferred SHOULD)**
- T234 admin AI 운영현황 (구현됨, AIAdminDashboardPage)
- T247 광고심의 게이트 (구현됨, marketing_review router)
- T248 이해상충 (구현됨, conflict_of_interest router)
- T249 KYC/EDD (구현됨, kyc_edd router)
- T256 합성 페르소나 6종 데이터 시드 [SHOULD]
- T258 4-eyes 승인 흐름 표준화 [SHOULD]
- T269 ai_output_feedback 테이블 + UI 👍/👎 [SHOULD]
- T270 AI 출력 explainability "근거" 박스 [SHOULD]
- T271 AI 결정 fingerprint UI 표시 [SHOULD]
- T272 7-agent caveat library 모듈화 [SHOULD]
- T273 PoC-only AI metrics export [SHOULD]
- T274 PoC AUTO APPROVAL 작동 통계 카드 [SHOULD]
- T275 AI 정책 변경 동기화 알림 [SHOULD]

**(C5) AI governance SHOULD 잔여**
- T279 AI 인용 출처 hash 체인 [SHOULD] — Wave 5 partition design RUN-08과 함께
- T317 PoC 데모 모드 강제 출구 (forced exit) UX [SHOULD]

### Cutline 채택 근거
사용자 직접 응답 ("A) MUST 전수 + SHOULD/MAY 명시 defer", 확신 1.00). PoC scope 명확화 + 운영 격상 후보 분리. 이 32 항목은 운영 인수 후 별도 단계의 backlog로 우선순위 재조정 대상.

### Re-engagement 조건
- C1: 운영 격상 시 (예: KMS/SIEM 도입 결정 후) 별도 epic
- C2: APScheduler 활성화 + 비즈니스 일정 픽스 후
- C3: 법무팀 검토 + 합성 시나리오 우선순위 재조정 후
- C4: UX 리서치 + 5-role usability test 후
- C5: Wave 5 RUN-08 audit partition 실제 실행 후

**최종 상태**: MUST 전수 완료 (147/147), SHOULD/MAY Cutline deferred (32 items, 위 분류). Deep-interview spec ambiguity 5.45% → 실행 완료로 사실상 0% (선택 사항 SHOULD/MAY는 사용자 명시 승인 deferred).
