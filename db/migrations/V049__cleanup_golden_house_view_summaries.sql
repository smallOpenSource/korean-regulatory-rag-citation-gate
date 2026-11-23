/* sql_id: v049_cleanup_golden_house_view_summaries */
-- DATA CLEANUP: 골든 스냅샷 테스트 하우스뷰 summary 내부 식별자 제거
--
-- 대상: summary = 'REG-04 T261 golden regression test entry.' (49건 확인)
-- 원인: BANNED_INTERNAL_ID(REG-04) + BANNED_TEST_FIXTURE(golden regression test)
--       이 두 패턴이 PB/WM 화면에 노출되어 visual-fullwalk spec 위반
-- 조치: 한국어 설명 문자열로 교체
--
-- Before: 'REG-04 T261 golden regression test entry.'
-- After:  '골든 스냅샷 회귀 테스트 기준 항목 (합성 데이터)'

UPDATE house_views
SET summary = '골든 스냅샷 회귀 테스트 기준 항목 (합성 데이터)'
WHERE summary = 'REG-04 T261 golden regression test entry.';

/* sql_id: v049_cleanup_internal_reference_patterns */
-- 잔여 ADR-/REG-0 패턴 일반 cleanup (다른 미확인 fixture 대비 방어)
UPDATE house_views
SET summary = regexp_replace(
    regexp_replace(summary, '\mADR-[0-9]+\M', '(내부참조)', 'g'),
    '\mREG-0[0-9]\M', '(내부참조)', 'g'
)
WHERE (summary ~ '\mADR-[0-9]+\M' OR summary ~ '\mREG-0[0-9]\M')
  AND summary != '골든 스냅샷 회귀 테스트 기준 항목 (합성 데이터)';
