# DB-02 Logical Model

## Naming
- table: plural snake_case
- primary key: id UUID
- timestamps: created_at, updated_at where needed

## Key Tables

### branches
(id, branch_code, branch_name, region_code, created_at)

### employees
(id, employee_no, name, role_code, branch_id, email, password_hash, is_active, created_at)
- role_code: PB | WM | BRANCH_MANAGER | ADMIN | AUDIT_VIEWER

### customers
(id, customer_no, customer_name, assigned_pb_id, branch_id, risk_grade_code, segment_code,
 total_assets_krw, last_contacted_at, is_active, created_at, updated_at)
- customer_no: deterministic synthetic/internal ID; UI displays customer_name instead of raw IDs.
- customer_name: synthetic Korean display label such as `합성고객 강남 01`; no real customer PII.
- risk_grade_code: 1 | 2 | 3 | 4 | 5
- segment_code: HNWI_CORE | HNWI_ULTRA | EMERGING_HNWI

### risk_assessments
(id, customer_id, score, risk_grade_code, surveyed_at, surveyed_by_id, created_at)

### portfolios
(id, customer_id, portfolio_name, base_currency, valuation_date, created_at, updated_at)

### portfolio_holdings
(id, portfolio_id, product_id, quantity, market_value_krw, weight_pct, as_of_date)

### products
(id, product_code, product_name, product_type_code, risk_level_code,
 maturity_date, has_knock_in, knock_in_barrier_pct, issuer_name,
 fee_pct, currency, is_active, created_at)
- product_type_code: FUND | BOND | ELS_DLS | WRAP | TRUST | DEPOSIT
- risk_level_code: 1 | 2 | 3 | 4 | 5

### consultations
(id, customer_id, employee_id, house_view_id, consultation_at, channel_code,
 status_code, summary, suitability_checked, explanation_checked,
 created_at, updated_at)
- status_code: DRAFT | SAVED | COMPLETED
- channel_code: FACE_TO_FACE | PHONE | VIDEO | WRITTEN

### consultation_notes
(id, consultation_id, author_id, note_text, created_at, updated_at)

### house_views
(id, version_no, period_code, title, status_code, summary,
 asset_views_json, model_portfolios_json, risks_json, leading_block_json,
 created_by_id, activated_at, superseded_at, ai_generated_at, ai_model_name,
 faithfulness_json, created_at, updated_at)
- leading_block_json (V079): REG-02 손실/부적합/불확실성 선두 블록 마커 (nullable JSONB)
- faithfulness_json (V081): P2-3 생성 본문의 결정성 faithfulness 평가 (nullable JSONB)
- status_code: DRAFT | PENDING_REVIEW | ACTIVE | SUPERSEDED | ARCHIVED
- ACTIVE는 동시에 1개 제한: partial unique index (WHERE status_code = 'ACTIVE')

### house_view_applications
(id, house_view_id, consultation_id, applied_at)

### nba_actions
(id, customer_id, employee_id, action_type_code, priority_code, status_code,
 trigger_code, script_text, script_generated_at, script_model_name, due_date, snoozed_until, completed_at,
 created_at, updated_at)
- status_code: PENDING | IN_PROGRESS | DONE | SNOOZED | DISMISSED
- priority_code: URGENT | HIGH | MEDIUM | LOW
- action_type_code: (BIZ-04 참조)

### aftercare_events
(id, customer_id, product_id, employee_id, event_type_code, event_date,
 status_code, notes, resolved_at, created_at, updated_at)
- status_code: OPEN | IN_PROGRESS | RESOLVED
- event_type_code: MATURITY_DUE | KI_TRIGGERED | DRAWDOWN_BREACH | REVIEW_DUE | NO_CONTACT

### documents
(id, source_type_code, source_id, title, content_hash, raw_content,
 source_url, published_at, created_at)
- source_type_code: DART | REG_PAGE | RESEARCH | MANUAL | WEB_SEARCH

### document_chunks
(id, document_id, chunk_no, chunk_text, embedding vector(1024),
 token_count, is_embedded, provider_code, corp_code, receipt_no, source_url,
 published_at, section_path, parser_version, metadata_json, created_at)

### document_sources
(id, raw_document_id, document_id, provider_code, source_document_id,
 receipt_no, corp_code, canonical_url, published_at, content_hash,
 parser_version, source_payload_json, created_at)
- provider_code: DART | REG_PAGE | RESEARCH | MANUAL | WEB_SEARCH

### rag_answer_evidence
(id, ai_output_id, chunk_id, source_document_id, quote_span_json,
 retrieval_score, rerank_score, confidence, created_at)
- READY RAG 응답이 실제 인용 청크를 반환할 때만 저장한다.

### ai_jobs
(id, job_type_code, status_code, requested_by_id, resource_type, resource_id,
 result_resource_type, result_resource_id, result_summary, error_code,
 error_message, created_at, started_at, finished_at)
- status_code: PENDING | RUNNING | SUCCEEDED | FAILED | CANCELLED
- 202 응답 AI endpoint의 durable job 상태 저장.
- error_message는 secret/PII 원문 제거 후 저장.

### recommendation_simulations
(id, customer_id, employee_id, consultation_id, product_id, status_code,
 suitability_passed, explanation_checked, simulated_customer_consented,
 employee_final_approved, gate_detail_json, created_at, updated_at)
- status_code: DRAFT | BLOCKED | APPROVED | CANCELLED
- 실제 권유 확정이 아니라 직원 화면 내 시뮬레이션 기록.

### order_simulations
(id, recommendation_simulation_id, customer_id, employee_id, product_id,
 side_code, quantity, amount_krw, status_code, gate_detail_json,
 simulated_executed_at, created_at, updated_at)
- side_code: BUY | SELL
- status_code: DRAFT | BLOCKED | APPROVED | SIMULATED_EXECUTED | CANCELLED
- 실제 주문 API 호출 금지.


### ai_outputs
(id, agent_id, model_name, generated_at, resource_type, resource_id,
 job_id, prompt_hash, output_json, citations_json, created_at)
- 모든 AI 생성 결과 metadata/display/audit 원천.
- prompt_hash만 저장하고 raw PII 포함 prompt 원문 저장 금지.

### audit_logs
(id, actor_id, action_code, resource_type, resource_id,
 ip_address, user_agent, detail_json, created_at)
- append-only, 절대 UPDATE/DELETE 금지

### email_drafts
(id, customer_id, employee_id, consultation_id, subject, body,
 ai_generated_at, ai_model_name, status_code, sent_at, created_at, updated_at)
- status_code: DRAFT | APPROVED | SENT | CANCELLED

### batch_job_logs
(id, job_name, job_type_code, status_code, started_at, finished_at,
 rows_collected, rows_skipped, rows_failed, error_message, created_at)
- status_code: RUNNING | DONE | FAILED | SKIPPED

### raw_documents
(id, source_type_code, source_url, content_hash, raw_text,
 collected_at, is_processed, processed_at)
- unique: (content_hash, source_url)

### source_licenses
(source_code, source_name, license_status_code, domestic_equity_only,
 terms_url, notes, updated_at)
- source_code: KRX | BROKER | DATA_GO_KR | PYKRX
- domestic_equity_only: TRUE only for MVP market-data sources.

### securities
(id, ticker, isin, security_name_kr, market_code, country_code,
 security_type_code, currency, is_active, listed_at, delisted_at, created_at, updated_at)
- ticker: six-digit Korea short code.
- isin: KR-prefixed Korea ISIN matching `^KR[0-9A-Z]{10}$`; official KRX `ISU_CD` values such as KR8... foreign-company listings are allowed when paired with a six-digit domestic ticker.
- market_code: KOSPI | KOSDAQ | KONEX
- country_code/security_type_code/currency are constrained to KR/EQUITY/KRW.

### security_identifiers
(id, security_id, identifier_type_code, identifier_value, source_code,
 is_primary, valid_from, valid_to, created_at)
- identifier_type_code: TICKER | ISIN | KRX_SHORT_CODE
- unique: (identifier_type_code, identifier_value, source_code)

### product_underlyings
(id, product_id, security_id, underlying_role_code, weight_pct, created_at)
- underlying_role_code: PRIMARY | BASKET | HEDGE
- Only references `securities`; non-Korea/non-equity underlyings are not represented in MVP.

### trading_calendar
(market_code, calendar_date, is_trading_day, holiday_name, source_code, created_at)
- market_code: KOSPI | KOSDAQ | KONEX
- primary key: (market_code, calendar_date)

### market_universe_snapshots
(id, universe_code, as_of_date, resolved_trading_date, source_code, source_policy_code,
 rank_method_code, target_size, selected_count, raw_candidate_count, excluded_count,
 coverage_status_code, provider_evidence_id, created_at, updated_at)
- `DOMESTIC_TOP200_MARKET_CAP` snapshots persist the official KRX as-of universe contract.
- coverage_status_code: PENDING | READY | DEGRADED | BLOCKED
- unique: (universe_code, as_of_date, source_code, source_policy_code)

### market_universe_candidates
(id, snapshot_id, security_id, ticker, isin, security_name_kr, market_code,
 rank_before_filter, rank_after_filter, market_cap_krw, listed_shares, close_price,
 section_type_name, company_key, company_key_source_code, raw_payload_hash, included,
 exclusion_reason_code, provider_evidence_id, created_at, updated_at)
- One row per official KRX rankable/raw issue candidate; excluded rows keep reason evidence.
- market_code: KOSPI | KOSDAQ
- unique: (snapshot_id, ticker)

### market_universe_members
(id, snapshot_id, security_id, ticker, company_key, rank_no, market_code, market_cap_krw,
 listed_shares, close_price, included_reason_code, created_at, updated_at)
- Selected top-200 rows only; ranks are unique within a snapshot.
- unique: (snapshot_id, ticker), (snapshot_id, rank_no), (snapshot_id, security_id)

### market_trading_calendar
(calendar_date, market_code, source_code, source_policy_code, is_expected_trading_day,
 is_observed_trading_day, no_trading_reason_code, batch_provider_evidence_id, created_at, updated_at)
- Official/observed KRX denominator for 30 calendar-day lookback; closed days are evidence, not fabricated bars.
- primary key: (market_code, calendar_date, source_code, source_policy_code)

### market_universe_coverage_daily
(id, snapshot_id, member_id, security_id, market_code, calendar_date, is_expected_trading_day,
 has_valid_bar, market_price_bar_id, missing_reason_code, quality_status_code,
 batch_provider_evidence_id, created_at, updated_at)
- One row per selected member/date coverage fact; missing expected member-days keep reason codes.
- quality_status_code: RAW | VALID | WARN | REJECTED | RECONCILED | MISSING | NO_TRADING
- unique: (snapshot_id, member_id, calendar_date)

### market_data_evidence
(id, source_code, evidence_type_code, provider_reference, payload_hash,
 source_as_of, collected_at, evidence_json)
- evidence_type_code: RAW_PAYLOAD | API_RESPONSE | BACKFILL | RECONCILIATION | QUALITY_CHECK
- unique: (source_code, evidence_type_code, payload_hash)

### market_price_bars
(id, security_id, source_code, price_date, timeframe_code, open_price, high_price,
 low_price, close_price, adjusted_close_price, volume, trading_value_krw, market_cap_krw,
 listed_shares, change_price, change_rate_pct, source_as_of, evidence_id,
 quality_status_code, quality_message, is_synthetic, created_at, updated_at)
- source_code: KRX | BROKER | DATA_GO_KR | PYKRX
- timeframe_code: 1D only
- quality_status_code: RAW | VALID | WARN | REJECTED | RECONCILED
- is_synthetic: constrained FALSE; no fake provider-labelled price bars.
- unique: (security_id, price_date, source_code, timeframe_code)

### corporate_actions
(id, security_id, source_code, action_type_code, effective_date, announced_at,
 cash_amount_krw, split_ratio, evidence_id, quality_status_code, created_at)
- action_type_code: DIVIDEND | SPLIT | MERGER | SPINOFF

### market_data_quality_checks
(id, check_code, security_id, source_code, price_date, status_code, severity_code,
 observed_json, evidence_id, created_at)
- status_code: PASS | WARN | FAIL
- severity_code: INFO | WARN | ERROR

### market_prices
(id, ticker, source_code, price_date, open_price, high_price, low_price,
 close_price, volume, created_at)
- Legacy table from V009. V012 installs a trigger that rejects INSERT/UPDATE/DELETE.
- New repository, readiness, and valuation SQL must use `market_price_bars` only.

### financial_ratios
(id, ticker, source_code, ratio_date, per, pbr, roe, debt_ratio, eps,
 dividend_yield, created_at)
- unique: (ticker, ratio_date, source_code)

### investor_flows
(id, fund_code, fund_name, fund_type_code, flow_date, net_flow_krw,
 aum_krw, source_code, created_at)
- unique: (fund_code, flow_date, source_code)

### macro_indicators
(id, indicator_code, indicator_name, reference_date, value, unit,
 source_code, created_at)
- source_code: ECOS; FRED/WORLDBANK는 미래 확장 source_code로 예약하며 MVP 수집 대상은 아니다.
- unique: (indicator_code, reference_date, source_code)

## Full-MVP Seed Readiness Matrix
`db/seed.py --profile full-mvp` reports readiness for the following minimums:

| Domain | Minimum | Provenance |
|---|---:|---|
| branches / employees | 2 / 6 | synthetic operational |
| customers / risk_assessments | 20 / 20 | Korean scenario customer display names + synthetic operational |
| products / portfolios / portfolio_holdings | 12 / 20 / 60 | Korean product/portfolio labels; holdings reconcile to customer assets and weights sum to 100 |
| house_views / consultations / consultation_notes | 2 / 10 / 10 | synthetic operational |
| house_view_applications | 5 | synthetic operational |
| nba_actions / aftercare_events | 20 / 20 | synthetic operational |
| recommendation_simulations / order_simulations | 12 / 12 | synthetic operational with 4-gate variants |
| audit_logs / email_drafts / ai_jobs / ai_outputs | 6 / 2 / 2 / 1 | synthetic operational, no raw PII, env-driven AI model metadata |
| raw_documents / documents / document_chunks | 5 / 5 / 30 | MANUAL internal baseline, unembedded until real BGE refresh |
| batch_job_logs | 5 | sanitized DONE/SKIPPED evidence for seed/provider/BGE gates |
| market_price_bars / market_prices / financial_ratios / investor_flows / macro_indicators | 0 | provider-owned; no seed inserts; `market_prices` is legacy write-guarded |

Provider-owned tables must be populated only by real provider batch jobs. Seed fixtures may record
sanitized SKIPPED batch-log evidence for unavailable providers but must not insert provider-labelled
success data.

## Status Code Rules
- enum class 금지: 모든 status_code / type_code는 VARCHAR + CHECK constraint 또는 lookup table 사용.
- 허용값은 위 각 테이블 정의에 명시한 것이 전부.
- 추가 값은 docs/db 수정 + migration SQL 추가 필요.


## Stage 4 DART RAG Grounding
- `document_sources` links raw provider documents to transformed documents with provider_code, source_document_id, receipt_no, corp_code, canonical_url, published_at, content_hash, parser_version, and sanitized source payload metadata.
- `document_chunks` carries citation metadata for provider/corp/receipt/source_url/published_at/section_path/parser_version so RAG filters do not infer provenance from text.
- `rag_answer_evidence` stores one row per cited chunk for READY RAG answers.


## Appendix — Operational Tables (added 2026-05-23 per docs/service drift audit)

Wave-Audit-Defect-Fix audit (2026-05-23) found 18 operational tables present in migrations but
missing from earlier §sections. Canonical 1-line purpose + originating migration below.
Full schema in `db/migrations/V*.sql`.

| Table | V*.sql | Purpose (1-line) |
|---|---|---|
| audit_action_codes | V008 | Enumeration lookup for canonical audit event types (action_code) |
| audit_logs_v8_archive | V054 | 90-day archive copy of audit_logs (FK-decoupled for archive independence) |
| batch_provider_evidence | V015 | Provider success/failure/skipped counts per batch_job_log (UNIQUE per provider+target) |
| conflict_disclosures | V030 | Pre-trade/post-trade/related-party conflict declarations + Chinese Wall violation flag |
| consultation_gates | V023 | 4-gate (suitability/explanation/unfair_solicitation/marketing) checkpoint state per consultation |
| customer_consents | V027 | Synthetic consent ledger per REG-01 (GENERAL_BUNDLE/INFO_USE/MARKETING/3RD_PARTY); synthetic=true CHECK |
| data_purge_schedules | V033 | REG-01 §20-2 retention-deletion placeholder (5-year purge_due_at) |
| dispute_cases | V028 | REG-01 분쟁 complaint case (30-day response_due_at via trigger) |
| gate_evidence | V031 | Immutable gate decision evidence (PASS/BLOCK/PENDING + schema-validated JSON + ≥16-char hash). Has own append-only triggers. |
| idempotency_keys | V063 | Server-side request dedup store (24h TTL sweep — see RUN-13); PK (idempotency_key, route_template) |
| info_access_requests | V027 | REG-01 §38 data ACCESS/CORRECTION request log (audit chain via employee_id) |
| kyc_edd_triggers | V029 | Reassessment triggers (ASSET_CHANGE_PCT / OVERSEAS_TRANSFER / PEP_FLAG / HIGH_RISK_PRODUCT) |
| marketing_reviews | V025 | Marketing copy compliance gate (static lint + AI reasoning → MARKETING_REVIEW_PASS/BLOCK) |
| order_simulations | V010 | Simulated order placement (V038 CHECK chk_order_sim_no_real_routing enforces routed_to_exchange=FALSE) |
| recommendation_simulations | V010 | Recommendation workflow state (4 gates → APPROVED requires all PASSED) |
| rights_notices | V026 | Investor rights notice (권리고지) issuance log per REG-01 |
| suitability_assessments | V023 | 6-factor investor suitability (objective + JSONB subjective; REG-02 T220/T228) |
| system_flags | V020 | Global operational flags (demo_mode 8h auto-expire per ADR-004); change_reason ≥8 + ticket_id ≥3 |

All 18 follow project-wide invariants: synthetic-only data, no enum class (VARCHAR + CHECK).
Append-only invariant applies only to `audit_logs` (V008/V019) and `gate_evidence` (V031 triggers).
Other 16 are mutable by design (e.g., consultation_gates status transitions, dispute_cases.responded_at).
