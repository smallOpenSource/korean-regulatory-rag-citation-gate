/* sql_id: v047_consultation_summary_korean_placeholder */
-- V047 — consultations.summary 영어 placeholder 한국어화 (UltraQA cycle 16 S38 fix, 2026-05-19)
--
-- UltraQA E2E test에서 생성된 합성 데이터 6건이 영어 placeholder
-- 'UltraQA synthetic note'로 남아 있어 PB-facing Customer 360 / 상담 이력
-- 화면 노출 시 한국어 일관성 위반. 한국어 placeholder로 일괄 교체.
--
-- Idempotent: 동일 영어 placeholder만 매치하므로 재실행 시 no-op.

UPDATE consultations
   SET summary = '합성 데모 상담 - 자동 생성된 기록 (UltraQA 회귀 테스트)'
 WHERE summary = 'UltraQA synthetic note';
