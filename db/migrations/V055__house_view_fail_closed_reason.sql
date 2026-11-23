/* sql_id: v055_house_view_fail_closed_reason */
-- V055: persist fail_closed_reason_code on house_views (Wave-Audit-Defect-Fix A5 / CR-6).
--
-- 목적:
--   T265 safety branch가 generate_house_view_content에서 leakage/injection/parse
--   분기를 만났을 때 reason_code를 house_views row에 박제. 현재 router (house_views.py)
--   는 result.fail_closed_reason_code를 무시한 채 빈 content만 GENERATED로 전이 →
--   감사 추적 불가. ADR-005 § fail-closed reason code 정합.
--
-- 컬럼:
--   fail_closed_reason_code TEXT NULL — NULL=success / 'LLM07_LEAKAGE_REDACTED' /
--   'PROMPT_INJECTION_DETECTED' / 'PARSE_ERROR' (services/house_view.py:185-196 SoT).
ALTER TABLE house_views ADD COLUMN IF NOT EXISTS fail_closed_reason_code TEXT NULL;
