# DB-05 Migration Guide

## Rules
- ORM(Flyway, Alembic) 금지.
- 파일 형식: db/migrations/V{version:03d}__{description}.sql
- 버전은 001부터 순차 증가, 동일 번호 재사용 금지.
- 모든 migration은 멱등성 보장 (IF NOT EXISTS, DO NOTHING).
- DDL 포함 모든 SQL statement 첫 줄에 `/* sql_id: short_human_readable_id */` 주석 필수.
- 배포 전 staging 환경에서 먼저 실행 확인.

## Runner (db/migrator.py)
- migration_versions 테이블로 적용 이력 관리.
- 실행: `python db/migrator.py` → 미적용 migration 순서대로 실행.
- 롤백 지원 없음 (롤백 필요 시 새 버전 migration 작성).


## Seed Runner (db/seed.py)
- 실행: `python db/seed.py --profile full-mvp` after migrations.
- `--dry-run`은 DB 연결 없이 fixture SQL과 `sql_id` 규칙만 검증한다.
- 지원 profile: `synthetic` (legacy minimal fixture), `full-mvp` (seed_00~40 deterministic slices).
- full-mvp는 synthetic PB/WM operational baseline과 MANUAL RAG baseline만 적재한다.
- `market_price_bars`, `market_prices`, `financial_ratios`, `investor_flows`, `macro_indicators`는 provider-owned table로 seed가 fabricated row를 넣지 않는다. `market_prices`는 V012 이후 legacy/write-guarded table이다.
- provider/BGE 미가용 상태는 sanitized `batch_job_logs.status_code='SKIPPED'` row로 표현한다.
- readiness JSON은 table minimum, row_count, provenance를 출력하며 profile 재실행 시 stable UUID와 `ON CONFLICT`로 idempotent해야 한다.

## Migration File Order
- V001: pgvector extension + branches + employees
- V002: customers + risk_assessments
- V003: products + portfolios + portfolio_holdings
- V004: house_views + house_view_applications
- V005: consultations + consultation_notes
- V006: nba_actions + aftercare_events
- V007: documents + document_chunks (ivfflat index)
- V008: audit_logs + email_drafts + ai_jobs + ai_outputs
- V009: legacy batch tables (market_prices, financial_ratios, investor_flows, macro_indicators, raw_documents, batch_job_logs)
- V010: recommendation_simulations + order_simulations
- V011: synthetic customer display names
- V012: market data foundation (source_licenses, securities, identifiers, product_underlyings, trading_calendar, market_price_bars, corporate_actions, quality/evidence, legacy market_prices write guard)
- V013: DART RAG grounding (document_sources, chunk source metadata, rag_answer_evidence, prompt-injection quarantine indexes)
- V014: forward-only repair for document source/chunk citation columns in pre-integration environments
- V015: provider status normalization (`batch_provider_evidence`) without changing `batch_job_logs.status_code`

## Implemented Runner Contract
- `db/migrator.py` is the project-owned runner and validates each migration statement before execution.
- The runner rejects non-sequential versions, missing `/* sql_id: ... */` comments, and `SELECT *` in migration statements.
- `migration_versions` records version, name, checksum, and applied timestamp; reruns skip already recorded versions.
- Current implemented files are `V001__extensions_branches_employees.sql` through `V016__official_krx_provider_readiness.sql`, `db/seed.py`, legacy `db/fixtures/seed_synthetic.sql`, and full-MVP slices `db/fixtures/seed_00_identity.sql` through `db/fixtures/seed_40_manual_rag.sql`.
- If configured PostgreSQL credentials fail, report the provider error with secrets redacted; do not substitute a mock database.
- Before claiming live-provider READY, run
  `/opt/conda/envs/wm_env/bin/python scripts/t55_schema_preflight.py`.
  The generated report verifies active PostgreSQL V012-V018 state, provider evidence
  tables/columns, Redis reachability, and SQL_ID-clean migration files without exposing
  credentials.


## V013__dart_rag_grounding.sql
- Apply after V012. It adds OpenDART/RAG provenance and evidence tables used by Stage 4.

## V014__document_chunk_source_columns_repair.sql
- Apply after V013. It repeats the source/citation DDL with `IF NOT EXISTS` as a safe
  repair path for environments that recorded a duplicate-version team artifact before
  the leader integration renamed DART/RAG grounding to V013.
- Preserve forward-only numbering; do not edit already-applied migration rows by hand.

## V017__domestic_market_universe_top200.sql / V018__kr_isin_constraint_normalization.sql
- V017 adds the official KRX top-200 universe, candidate/member, market-calendar, and 30-day coverage tables.
- V018 is a forward-only constraint repair: it keeps six-digit domestic tickers, but changes KR ISIN checks from `^KR7[0-9A-Z]{9}$` to `^KR[0-9A-Z]{10}$` for `securities`, `security_identifiers`, and `market_universe_candidates`.
- This is required because official KRX `ISU_CD` is the ISIN field and may include valid KR8... listings such as foreign-company Korea-listed equities; do not coerce, truncate, or fabricate alternate ISINs.

## V015__provider_status_normalization.sql
- Apply after V014. It creates only `batch_provider_evidence`.
- It must not alter `batch_job_logs.status_code`, add official `KRX` row persistence, or create
  provider security identifier tables.
- Every provider target reference must be deterministic and secret-free so `/batch/status`,
  readiness, and UI evidence can distinguish provider no-data from failures.
