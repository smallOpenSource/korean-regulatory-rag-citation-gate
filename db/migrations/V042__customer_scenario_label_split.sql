/* sql_id: v042_customer_scenario_label_split */
-- V042 — customer_name PII separation (UltraQA cycle 4 S1 fix, 2026-05-19)
--
-- UltraQA cycle 4 sweep discovered that seed_10_customers_risk.sql +
-- seed_synthetic.sql had written scenario text ("강남 법인오너 단기 유동성
-- 관리", "부산 글로벌 인컴 성장관리", etc.) directly into the
-- customers.customer_name column. The PB-facing 성명 field must be a Korean
-- personal name (2-4 chars, 3 chars dominant) per enterprise WM convention.
-- The scenario phrase still has demo value, so it moves into a new
-- scenario_label column and the 성명 field is populated with synthetic
-- Korean 3-char names.
--
-- This migration is idempotent:
--   * ADD COLUMN IF NOT EXISTS for scenario_label
--   * scenario_label only adopts a value when previously NULL and the
--     existing customer_name still matches the regional scenario prefix
--   * customer_name is rewritten only when customer_no matches a known
--     SYN-CUST-NNN slot

ALTER TABLE customers ADD COLUMN IF NOT EXISTS scenario_label varchar;

/* sql_id: v042_migrate_scenario_text_from_customer_name */
UPDATE customers
   SET scenario_label = CASE
                          WHEN scenario_label IS NULL AND customer_name ~ '^(강남|부산) '
                          THEN customer_name
                          ELSE scenario_label
                        END,
       customer_name  = CASE customer_no
                          WHEN 'SYN-CUST-001' THEN '김민호'
                          WHEN 'SYN-CUST-002' THEN '이서연'
                          WHEN 'SYN-CUST-003' THEN '박지훈'
                          WHEN 'SYN-CUST-004' THEN '정수아'
                          WHEN 'SYN-CUST-005' THEN '최영민'
                          WHEN 'SYN-CUST-006' THEN '강하늘'
                          WHEN 'SYN-CUST-007' THEN '윤도윤'
                          WHEN 'SYN-CUST-008' THEN '조하준'
                          WHEN 'SYN-CUST-009' THEN '임채원'
                          WHEN 'SYN-CUST-010' THEN '신유진'
                          WHEN 'SYN-CUST-011' THEN '한지수'
                          WHEN 'SYN-CUST-012' THEN '오민준'
                          WHEN 'SYN-CUST-013' THEN '문서영'
                          WHEN 'SYN-CUST-014' THEN '배준혁'
                          WHEN 'SYN-CUST-015' THEN '안도현'
                          WHEN 'SYN-CUST-016' THEN '구지원'
                          WHEN 'SYN-CUST-017' THEN '하예린'
                          WHEN 'SYN-CUST-018' THEN '서민재'
                          WHEN 'SYN-CUST-019' THEN '권나윤'
                          WHEN 'SYN-CUST-020' THEN '노승우'
                          ELSE customer_name
                        END
 WHERE customer_no LIKE 'SYN-CUST-%';
