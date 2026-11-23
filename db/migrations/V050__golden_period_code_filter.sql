/* sql_id: v050_golden_period_code_filter */
-- DEFENSE-IN-DEPTH: house_views period_code 차단 보완
--
-- 원인: period_code='GOLDEN_TEST' 항목이 HouseViewsPage에서
--       "v{N} · GOLDEN_TEST"로 렌더링되어 BANNED_TEST_FIXTURE 위반.
--       LIST_HOUSE_VIEWS_SQL이 status_code/title/summary만 차단하고
--       period_code를 누락함 (T5 Lane C UX sweep 진단).
--
-- 처리:
--   1. SQL 레벨 (house_views.py): period_code NOT IN (...) 조건 추가 (primary)
--   2. 데이터 레벨 (본 migration): period_code 값을 안전한 한국어 코드로 교체 (defense)
--
-- Before: period_code = 'GOLDEN_TEST' (BANNED_TEST_FIXTURE 패턴 매칭)
-- After:  period_code = 'GT-REG'      (회귀 테스트용 안전 코드, 패턴 미매칭)

UPDATE house_views
SET period_code = 'GT-REG'
WHERE period_code = 'GOLDEN_TEST';

/* sql_id: v050_period_code_defense_in_depth_cleanup */
-- 잔여 차단 대상 period_code 일반 cleanup
UPDATE house_views
SET period_code = 'GT-' || period_code
WHERE period_code IN (
    'GOLDEN', 'RALPH', 'RALPH-QA', 'RALPH_QA',
    'SYNTHETIC_BOUNDARY', 'TEST', 'TEST_FIXTURE',
    'ULTRAQA', 'ULTRA_QA', 'ULTRA-QA', 'QA_DRAFT'
)
  AND period_code NOT LIKE 'GT-%';
