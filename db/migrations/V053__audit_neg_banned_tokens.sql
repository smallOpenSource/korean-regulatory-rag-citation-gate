/* sql_id: v053_audit_neg_banned_tokens */
-- S5 dead-detection 보장: AUDIT-NEG-001 summary에 BANNED_TEST_FIXTURE 토큰 명시 박제
--
-- 목적: visual-fullwalk.spec.ts AC3a — AUDIT-NEG-001 detail page 진입 시
--       banned 패턴 매칭 ≥1 검증 (detector live 증명).
--       T4/T5 fix로 정상 fixture는 banned 0이지만 결함 fixture는 banned ≥1 이어야 함.
--
-- 안전성: AUDIT-NEG-001 title='AUDIT-NEG-001' (AUDIT-% prefix)
--   → LIST_HOUSE_VIEWS_SQL `AND title NOT LIKE 'AUDIT-%'` 조건으로 PB/WM 목록 차단
--   → PB/WM 화면에 노출 안 됨 (T3 SQL filter 보장)
--   → ADMIN role만 UUID 직접 접근 가능 → AC3a spec 검증 시만 visible
--
-- 포함 banned 토큰: GOLDEN_TEST → BANNED_TEST_FIXTURE 패턴 매칭

UPDATE house_views
SET summary = '감사 결함 fixture - GOLDEN_TEST 회귀 검사용 (visual audit BANNED_TEST_FIXTURE detector live 증명)'
WHERE id = 'a0000048-0000-0000-0000-000000000001'::uuid;
