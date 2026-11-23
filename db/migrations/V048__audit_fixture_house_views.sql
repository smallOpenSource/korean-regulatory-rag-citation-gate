/* sql_id: v048_audit_fixture_house_views */
-- V048 — empty_intent DDL + AUDIT-NEG/POS fixture INSERT (Visual Full-Walk Audit Phase 1)
-- PRD §7 Architecture, §18 C1 Option B (sentinel 'null'::jsonb)
-- [[v-sql-sql-id-validator]], [[on-conflict-id-for-mutable-content]]
-- Authored: 2026-05-19
--
-- empty_intent column 추가 (P2 측정 좌표):
--   by_design | failure | unspecified
ALTER TABLE house_views
  ADD COLUMN IF NOT EXISTS empty_intent VARCHAR(30)
    CHECK (empty_intent IN ('by_design', 'failure', 'unspecified'))
    NOT NULL DEFAULT 'unspecified';

/* sql_id: v048_insert_neg_001 */
-- AUDIT-NEG-001: db_null + db_empty_object 결함 노출 fixture
--
-- C1 mechanism (§18 Conditional Notes C1, Option B):
--   asset_views_json = 'null'::jsonb
--     → jsonb_typeof = 'null'  (db_null 의도 보존)
--     → IS NOT NULL = True     (V004 NOT NULL 제약 만족, schema ALTER 불필요)
--
-- model_portfolios_json = '{}'::jsonb  → db_empty_object
-- risks_json            = '{}'::jsonb  → db_empty_object
-- empty_intent = 'failure'             → 의도적 결함 라벨 (AC3a dead-detection)
INSERT INTO house_views
  (id, version_no, period_code, title, status_code, summary,
   asset_views_json, model_portfolios_json, risks_json,
   created_by_id, empty_intent)
VALUES
  ('a0000048-0000-0000-0000-000000000001'::uuid,
   9901, 'AUDIT', 'AUDIT-NEG-001', 'DRAFT',
   '감사 결함 fixture: db_null + db_empty_object 케이스',
   'null'::jsonb,
   '{}'::jsonb,
   '{}'::jsonb,
   (SELECT id FROM employees ORDER BY id LIMIT 1),
   'failure')
ON CONFLICT (id) DO UPDATE SET
  summary               = EXCLUDED.summary,
  empty_intent          = EXCLUDED.empty_intent,
  asset_views_json      = EXCLUDED.asset_views_json,
  model_portfolios_json = EXCLUDED.model_portfolios_json,
  risks_json            = EXCLUDED.risks_json;

/* sql_id: v048_insert_pos_001 */
-- AUDIT-POS-001: db_valid 정상 fixture
--
-- 세 json column 모두 non-null valid object → frontend 올바른 렌더링 시
-- 금지 패턴 0건이어야 함 (AC3b dead-detection).
-- empty_intent = 'by_design' → 의도된 정상 상태
INSERT INTO house_views
  (id, version_no, period_code, title, status_code, summary,
   asset_views_json, model_portfolios_json, risks_json,
   created_by_id, empty_intent)
VALUES
  ('a0000048-0000-0000-0000-000000000002'::uuid,
   9902, 'AUDIT', 'AUDIT-POS-001', 'GENERATED',
   '감사 정상 fixture: db_valid 케이스',
   '{"key":"value"}'::jsonb,
   '{"key":"value"}'::jsonb,
   '{"key":"value"}'::jsonb,
   (SELECT id FROM employees ORDER BY id LIMIT 1),
   'by_design')
ON CONFLICT (id) DO UPDATE SET
  summary               = EXCLUDED.summary,
  empty_intent          = EXCLUDED.empty_intent,
  asset_views_json      = EXCLUDED.asset_views_json,
  model_portfolios_json = EXCLUDED.model_portfolios_json,
  risks_json            = EXCLUDED.risks_json;
