# DB-03 Physical Model

## Column Type Rules
| 유형 | PostgreSQL 타입 |
|---|---|
| Primary Key | UUID DEFAULT gen_random_uuid() |
| 상태·코드 | VARCHAR(30) + CHECK constraint |
| 금액 | NUMERIC(20,2) |
| 비율·퍼센트 | NUMERIC(8,4) |
| 벡터 | vector(1024) |
| JSON | JSONB |
| 텍스트 원문 | TEXT |
| 타임스탬프 | TIMESTAMPTZ DEFAULT now() |

## Key Indexes
```sql
-- 고객 검색
CREATE INDEX idx_customers_assigned_pb ON customers(assigned_pb_id);
CREATE INDEX idx_customers_branch ON customers(branch_id);
-- customer_name is a NOT NULL synthetic Korean display label added by V011.

-- NBA 조회
CREATE INDEX idx_nba_employee_status ON nba_actions(employee_id, status_code);
CREATE INDEX idx_nba_customer ON nba_actions(customer_id);

-- 상담 조회
CREATE INDEX idx_consultations_customer ON consultations(customer_id);
CREATE INDEX idx_consultations_employee ON consultations(employee_id, created_at DESC);

-- 감사로그
CREATE INDEX idx_audit_actor ON audit_logs(actor_id, created_at DESC);

-- 추천/주문 시뮬레이션
CREATE INDEX idx_reco_customer_status ON recommendation_simulations(customer_id, status_code);
CREATE INDEX idx_order_sim_reco ON order_simulations(recommendation_simulation_id);

-- 벡터 검색 (ivfflat)
CREATE INDEX idx_chunks_embedding ON document_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- House View ACTIVE 단일 제약
CREATE UNIQUE INDEX idx_house_views_one_active
  ON house_views(status_code)
  WHERE status_code = 'ACTIVE';

-- Full-text search (BM25 대체)
ALTER TABLE document_chunks ADD COLUMN fts tsvector
  GENERATED ALWAYS AS (to_tsvector('korean', chunk_text)) STORED;
CREATE INDEX idx_chunks_fts ON document_chunks USING GIN(fts);
```

## Partitioning
- audit_logs: 월별 RANGE 파티션 (created_at 기준).
- batch_job_logs: 월별 RANGE 파티션 (created_at 기준).
- market_price_bars: 연도별 RANGE 파티션 후보 (price_date 기준). V012 현재는 단일 테이블 + `(security_id, price_date DESC)` 인덱스이며 데이터량 증가 시 신규 migration으로 파티셔닝한다.
- market_prices: 레거시 테이블, V012 이후 쓰기 금지.

## ivfflat Tuning
- lists = max(10, sqrt(row_count))로 동적 설정.
- 검색 시 SET ivfflat.probes = 10.
- 행 수 < 10,000: 인덱스 불필요, 순차 스캔 허용.


## SQL File Rule
- 모든 DDL/DML 파일과 앱 내 SQL 문자열 첫 줄은 `/* sql_id: short_human_readable_id */` 주석으로 시작한다.
- 위 예시는 논리 인덱스 설명이며 실제 migration 파일에는 각 statement 앞에 sql_id 주석을 붙인다.


## V013 DART RAG Grounding
- Adds `document_sources`, chunk-level citation metadata columns, and `rag_answer_evidence`.
- All statements use SQL_ID comments and the custom migrator; no migration framework is introduced.

## V014 Document Chunk Source Repair
- Re-applies the V013 source/citation DDL idempotently for environments that observed the
  pre-integration duplicate-version artifact.
- This is a forward-only repair migration; do not rewrite applied migration rows manually.
