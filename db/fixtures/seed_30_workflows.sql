/* sql_id: seed_workflows_supersede_nonseed_active_house_views */
-- Retire every other live house view before seeding this profile's single live
-- view. Must clear BOTH 'ACTIVE' (legacy) AND 'ACTIVATED' (T16 lifecycle): the
-- V082 idx_house_views_single_live index (ADR-020 F1) forbids two non-fixture
-- live rows, and V052's 2099Q4 ACTIVATED row is non-fixture and survives the
-- migrations — clearing only 'ACTIVE' left it live and aborted the fresh seed.
-- Mirrors SUPERSEDE_ACTIVE_HOUSE_VIEWS_SQL in repositories/house_views.py.
UPDATE house_views
SET status_code = 'SUPERSEDED',
    superseded_at = COALESCE(superseded_at, now()),
    updated_at = now()
WHERE status_code IN ('ACTIVE', 'ACTIVATED')
  AND id <> '77777777-7777-7777-7777-777777777701'::uuid;

/* sql_id: seed_workflows_active_house_view */
INSERT INTO house_views(
    id, version_no, period_code, title, status_code, summary, asset_views_json,
    model_portfolios_json, risks_json, created_by_id, activated_at,
    ai_generated_at, ai_model_name, prompt_tokens, completion_tokens, inputs_hash
)
VALUES (
    '77777777-7777-7777-7777-777777777701', 202605, '2026M05',
    '2026년 5월 교육용 하우스 뷰', 'ACTIVE',
    '금리 변동성 구간에서 우량채와 현금흐름 자산을 중심으로 점검하고, 고위험 ELS 녹인 위험은 사후관리 경보와 함께 확인한다.',
    '{"equity":"neutral","bond":"overweight","cash":"neutral"}'::jsonb,
    '{"balanced":{"equity":35,"bond":45,"cash":20},"income":{"equity":20,"bond":60,"cash":20}}'::jsonb,
    '{"risks":["rate_volatility","ki_monitoring","liquidity_gap"]}'::jsonb,
    '22222222-2222-2222-2222-222222222203', now(),
    '2026-05-01 09:30:00+09'::timestamptz, 'gpt-5.5', 2400, 850,
    'a1b2c3d4e5f67890aabbccddeeff00112233445566778899aabbccddeeff0011'
)
ON CONFLICT (version_no) DO UPDATE SET
    period_code = EXCLUDED.period_code,
    title = EXCLUDED.title,
    status_code = EXCLUDED.status_code,
    summary = EXCLUDED.summary,
    asset_views_json = EXCLUDED.asset_views_json,
    model_portfolios_json = EXCLUDED.model_portfolios_json,
    risks_json = EXCLUDED.risks_json,
    created_by_id = EXCLUDED.created_by_id,
    activated_at = COALESCE(house_views.activated_at, EXCLUDED.activated_at),
    ai_generated_at = EXCLUDED.ai_generated_at,
    ai_model_name = EXCLUDED.ai_model_name,
    prompt_tokens = EXCLUDED.prompt_tokens,
    completion_tokens = EXCLUDED.completion_tokens,
    inputs_hash = EXCLUDED.inputs_hash,
    updated_at = now();

/* sql_id: seed_workflows_draft_house_view */
INSERT INTO house_views(
    id, version_no, period_code, title, status_code, summary, asset_views_json,
    model_portfolios_json, risks_json, created_by_id,
    ai_generated_at, ai_model_name, prompt_tokens, completion_tokens, inputs_hash
)
VALUES (
    '77777777-7777-7777-7777-777777777702', 202606, '2026M06',
    '2026년 6월 검토용 하우스 뷰', 'DRAFT',
    '다음 월간 회의에서 해외 주식 비중과 단기채 만기 재투자 방안을 검토하는 교육용 초안이다.',
    '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
    '22222222-2222-2222-2222-222222222203',
    '2026-05-17 11:00:00+09'::timestamptz, 'gpt-5.5', 2050, 720,
    'b9c8d7e6f5a4321098765432deadbeefcafef00d1234567890abcdef01234567'
)
ON CONFLICT (version_no) DO UPDATE SET
    title = EXCLUDED.title,
    status_code = EXCLUDED.status_code,
    summary = EXCLUDED.summary,
    ai_generated_at = EXCLUDED.ai_generated_at,
    ai_model_name = EXCLUDED.ai_model_name,
    prompt_tokens = EXCLUDED.prompt_tokens,
    completion_tokens = EXCLUDED.completion_tokens,
    inputs_hash = EXCLUDED.inputs_hash,
    updated_at = now();

/* sql_id: seed_workflows_consultations */
WITH consultation_seed(consultation_no, summary_text) AS (
    VALUES
        (1, '은퇴소득 방어형 포트폴리오와 단기예금 만기 재예치 방안을 점검했다.'),
        (2, '상속증여 현금흐름 준비 시나리오의 유동성과 목적 신탁 활용 가능성을 설명했다.'),
        (3, '배당·멀티에셋 균형성장 포트폴리오 비중을 재확인했다.'),
        (4, '글로벌 성장 자산 편입 비중과 환율 변동 위험을 안내했다.'),
        (5, 'ELS 녹인 가능성과 조기상환 조건의 사후관리 기준을 확인했다.'),
        (6, '법인오너 단기 유동성 자금의 만기 분산과 지급 일정 대응을 점검했다.'),
        (7, '절세 목적 채권과 신탁 계좌 활용 범위를 설명했다.'),
        (8, '자녀교육 목적 자금의 중기 투자성과와 위험등급을 재확인했다.'),
        (9, '해외분산 포트폴리오의 리밸런싱 후보와 설명의무를 점검했다.'),
        (10, '부산 월지급 ELS 사후관리 시나리오의 녹인 연락 기준을 재확인했다.')
), consultation_rows AS (
    SELECT
        ('66666666-6666-6666-6666-' || lpad((666666666300 + consultation_no)::text, 12, '0'))::uuid AS id,
        ('33333333-3333-3333-3333-' || lpad((333333333300 + consultation_no)::text, 12, '0'))::uuid AS customer_id,
        CASE WHEN consultation_no <= 6 THEN '22222222-2222-2222-2222-222222222201'::uuid ELSE '22222222-2222-2222-2222-222222222204'::uuid END AS employee_id,
        CASE WHEN consultation_no <= 5 THEN 'COMPLETED' ELSE 'SAVED' END AS status_code,
        consultation_no,
        summary_text
    FROM consultation_seed
)
INSERT INTO consultations(
    id, customer_id, employee_id, house_view_id, consultation_at, channel_code, status_code,
    summary, suitability_checked, explanation_checked
)
SELECT id, customer_id, employee_id, '77777777-7777-7777-7777-777777777701',
       now() - (consultation_no * interval '2 days'),
       CASE WHEN consultation_no % 3 = 0 THEN 'PHONE' ELSE 'FACE_TO_FACE' END,
       status_code,
       summary_text,
       status_code = 'COMPLETED',
       status_code = 'COMPLETED'
FROM consultation_rows
ON CONFLICT (id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    employee_id = EXCLUDED.employee_id,
    house_view_id = EXCLUDED.house_view_id,
    consultation_at = EXCLUDED.consultation_at,
    channel_code = EXCLUDED.channel_code,
    status_code = EXCLUDED.status_code,
    summary = EXCLUDED.summary,
    suitability_checked = EXCLUDED.suitability_checked,
    explanation_checked = EXCLUDED.explanation_checked,
    updated_at = now();

/* sql_id: seed_workflows_consultation_notes */
WITH note_seed(note_no, note_text) AS (
    VALUES
        (1, '식별정보 없이 적합성 확인과 설명 확인 체크가 완료된 교육용 상담 기록.'),
        (2, '상속세 유동성 재원과 신탁 목적을 분리해 설명하고 후속 자료 발송 예정.'),
        (3, '성장형 자산 비중 확대 전 위험등급과 손실 가능성 재고지 필요.'),
        (4, '환율 변동성과 해외펀드 환매 주기를 다음 상담에서 재점검.'),
        (5, 'ELS 녹인 barrier와 조기상환 조건을 사후관리 항목으로 등록.'),
        (6, '법인오너 단기 유동성 현금흐름 캘린더와 단기채 만기를 연결해 점검.'),
        (7, '증여 일정과 신탁 현금흐름 시나리오를 분리해 안내.'),
        (8, '교육자금 목적 계좌의 중기 위험 허용범위를 확인.'),
        (9, '리밸런싱 후보 상품의 설명의무 체크리스트를 상담 전 준비.'),
        (10, '고위험 ELS 사후관리 연락 예정일과 담당자를 확인.')
)
INSERT INTO consultation_notes(id, consultation_id, author_id, note_text)
SELECT ('66666666-6666-6666-7777-' || lpad((666666666300 + note_no)::text, 12, '0'))::uuid,
       ('66666666-6666-6666-6666-' || lpad((666666666300 + note_no)::text, 12, '0'))::uuid,
       CASE WHEN note_no <= 6 THEN '22222222-2222-2222-2222-222222222201'::uuid ELSE '22222222-2222-2222-2222-222222222204'::uuid END,
       note_text
FROM note_seed
ON CONFLICT (id) DO UPDATE SET
    consultation_id = EXCLUDED.consultation_id,
    author_id = EXCLUDED.author_id,
    note_text = EXCLUDED.note_text,
    updated_at = now();

/* sql_id: seed_workflows_house_view_apps */
WITH app_seed(app_no) AS (
    SELECT series_no FROM generate_series(1, 5) AS series(series_no)
)
INSERT INTO house_view_applications(id, house_view_id, consultation_id)
SELECT ('77777777-7777-7777-8888-' || lpad((777777777300 + app_no)::text, 12, '0'))::uuid,
       '77777777-7777-7777-7777-777777777701'::uuid,
       ('66666666-6666-6666-6666-' || lpad((666666666300 + app_no)::text, 12, '0'))::uuid
FROM app_seed
ON CONFLICT (id) DO UPDATE SET
    house_view_id = EXCLUDED.house_view_id,
    consultation_id = EXCLUDED.consultation_id,
    applied_at = now();

/* sql_id: seed_workflows_nba_actions */
WITH nba_seed(nba_no) AS (
    SELECT series_no FROM generate_series(1, 20) AS series(series_no)
), nba_rows AS (
    SELECT nba_no,
           c.risk_grade_code,
           CASE
               WHEN c.risk_grade_code IN ('4', '5') AND nba_no % 5 = 0 THEN 'KI_FOLLOW_UP'
               WHEN nba_no % 5 = 1 THEN 'MATURITY_CALL'
               WHEN nba_no % 5 = 2 THEN 'RISK_REVIEW'
               WHEN nba_no % 5 = 3 THEN 'PORTFOLIO_REBALANCE'
               ELSE 'NO_CONTACT'
           END AS action_type_code,
           CASE
               WHEN c.risk_grade_code = '5' THEN 'URGENT'
               WHEN c.risk_grade_code = '4' THEN 'HIGH'
               WHEN c.risk_grade_code = '3' THEN 'MEDIUM'
               ELSE 'LOW'
           END AS priority_code
    FROM nba_seed
    JOIN customers c ON c.id = ('33333333-3333-3333-3333-' || lpad((333333333300 + nba_no)::text, 12, '0'))::uuid
)
INSERT INTO nba_actions(
    id, customer_id, employee_id, action_type_code, priority_code, status_code, trigger_code,
    script_text, script_generated_at, script_model_name, due_date, snoozed_until, completed_at
)
SELECT ('88888888-8888-8888-8888-' || lpad((888888888300 + nba_no)::text, 12, '0'))::uuid,
       ('33333333-3333-3333-3333-' || lpad((333333333300 + nba_no)::text, 12, '0'))::uuid,
       CASE WHEN nba_no <= 12 THEN '22222222-2222-2222-2222-222222222201'::uuid ELSE '22222222-2222-2222-2222-222222222204'::uuid END,
       action_type_code,
       priority_code,
       CASE nba_no % 5 WHEN 0 THEN 'DONE' WHEN 1 THEN 'PENDING' WHEN 2 THEN 'IN_PROGRESS' WHEN 3 THEN 'SNOOZED' ELSE 'DISMISSED' END,
       'KOREAN_PB_WM_SCENARIO',
       NULL, NULL, NULL,
       current_date + nba_no,
       CASE WHEN nba_no % 5 = 3 THEN now() + interval '7 days' ELSE NULL END,
       CASE WHEN nba_no % 5 = 0 THEN now() - interval '1 day' ELSE NULL END
FROM nba_rows
ON CONFLICT (id) DO UPDATE SET
    action_type_code = EXCLUDED.action_type_code,
    priority_code = EXCLUDED.priority_code,
    status_code = EXCLUDED.status_code,
    trigger_code = EXCLUDED.trigger_code,
    script_text = EXCLUDED.script_text,
    script_generated_at = NULL,
    script_model_name = NULL,
    due_date = EXCLUDED.due_date,
    snoozed_until = EXCLUDED.snoozed_until,
    completed_at = EXCLUDED.completed_at,
    updated_at = now();

/* sql_id: seed_workflows_aftercare_events */
WITH aftercare_seed(event_no) AS (
    SELECT series_no FROM generate_series(1, 20) AS series(series_no)
), aftercare_rows AS (
    SELECT event_no,
           c.risk_grade_code,
           CASE
               WHEN c.risk_grade_code IN ('4', '5') AND event_no % 5 = 0 THEN 'KI_TRIGGERED'
               WHEN event_no % 4 = 1 THEN 'MATURITY_DUE'
               WHEN event_no % 4 = 2 THEN 'DRAWDOWN_BREACH'
               WHEN event_no % 4 = 3 THEN 'REVIEW_DUE'
               ELSE 'NO_CONTACT'
           END AS event_type_code,
           CASE c.risk_grade_code
               WHEN '1' THEN '44444444-4444-4444-4444-444444444402'::uuid
               WHEN '2' THEN '44444444-4444-4444-4444-444444444404'::uuid
               WHEN '3' THEN '44444444-4444-4444-4444-444444444407'::uuid
               WHEN '4' THEN CASE WHEN event_no % 5 = 0 THEN '44444444-4444-4444-4444-444444444409'::uuid ELSE '44444444-4444-4444-4444-444444444408'::uuid END
               ELSE CASE WHEN event_no % 5 = 0 THEN '44444444-4444-4444-4444-444444444412'::uuid ELSE '44444444-4444-4444-4444-444444444411'::uuid END
           END AS product_id
    FROM aftercare_seed
    JOIN customers c ON c.id = ('33333333-3333-3333-3333-' || lpad((333333333300 + event_no)::text, 12, '0'))::uuid
)
INSERT INTO aftercare_events(
    id, customer_id, product_id, employee_id, event_type_code, event_date, status_code,
    notes, resolved_at
)
SELECT ('99999999-9999-9999-9999-' || lpad((999999999300 + event_no)::text, 12, '0'))::uuid,
       ('33333333-3333-3333-3333-' || lpad((333333333300 + event_no)::text, 12, '0'))::uuid,
       product_id,
       CASE WHEN event_no <= 12 THEN '22222222-2222-2222-2222-222222222201'::uuid ELSE '22222222-2222-2222-2222-222222222204'::uuid END,
       event_type_code,
       current_date + event_no,
       CASE event_no % 4 WHEN 0 THEN 'RESOLVED' WHEN 1 THEN 'OPEN' WHEN 2 THEN 'IN_PROGRESS' ELSE 'OPEN' END,
       CASE event_type_code
           WHEN 'KI_TRIGGERED' THEN '고위험 ELS knock-in 및 ELS 녹인 사후관리 연락 필요.'
           WHEN 'MATURITY_DUE' THEN '만기 도래 자금의 재투자 성향과 설명의무 확인 필요.'
           WHEN 'DRAWDOWN_BREACH' THEN '평가손실 확대에 따른 위험등급 재확인 필요.'
           WHEN 'REVIEW_DUE' THEN '정기 포트폴리오 리뷰와 리밸런싱 후보 점검 필요.'
           ELSE '장기 미접촉 계좌의 안부 연락과 최신 투자목적 확인 필요.'
       END,
       CASE WHEN event_no % 4 = 0 THEN now() - interval '2 days' ELSE NULL END
FROM aftercare_rows
ON CONFLICT (id) DO UPDATE SET
    product_id = EXCLUDED.product_id,
    employee_id = EXCLUDED.employee_id,
    event_type_code = EXCLUDED.event_type_code,
    event_date = EXCLUDED.event_date,
    status_code = EXCLUDED.status_code,
    notes = EXCLUDED.notes,
    resolved_at = EXCLUDED.resolved_at,
    updated_at = now();

/* sql_id: seed_workflows_remove_legacy_order_simulations */
DELETE FROM order_simulations
WHERE id::text LIKE 'cccccccc-cccc-cccc-cccc-cccccccc%';

/* sql_id: seed_workflows_prune_obsolete_order_simulations */
WITH seed_customers AS (
    SELECT ('33333333-3333-3333-3333-' || lpad((333333333300 + customer_no)::text, 12, '0'))::uuid AS id
    FROM generate_series(1, 20) AS customer(customer_no)
), expected_orders AS (
    SELECT ('cccccccc-cccc-cccc-cccc-' || lpad((3000 + order_no)::text, 12, '0'))::uuid AS id
    FROM generate_series(1, 12) AS order_seed(order_no)
)
DELETE FROM order_simulations os
USING seed_customers sc
WHERE os.customer_id = sc.id
  AND NOT EXISTS (
      SELECT 1
      FROM expected_orders eo
      WHERE eo.id = os.id
  );

/* sql_id: seed_workflows_remove_legacy_recommendation_simulations */
DELETE FROM recommendation_simulations
WHERE id::text LIKE 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbb%';

/* sql_id: seed_workflows_prune_obsolete_recommendation_simulations */
WITH seed_customers AS (
    SELECT ('33333333-3333-3333-3333-' || lpad((333333333300 + customer_no)::text, 12, '0'))::uuid AS id
    FROM generate_series(1, 20) AS customer(customer_no)
), expected_recommendations AS (
    SELECT ('bbbbbbbb-bbbb-bbbb-bbbb-' || lpad((3000 + recommendation_no)::text, 12, '0'))::uuid AS id
    FROM generate_series(1, 12) AS recommendation_seed(recommendation_no)
)
DELETE FROM recommendation_simulations rs
USING seed_customers sc
WHERE rs.customer_id = sc.id
  AND NOT EXISTS (
      SELECT 1
      FROM expected_recommendations er
      WHERE er.id = rs.id
  );

/* sql_id: seed_workflows_simulations */
WITH recommendation_seed(recommendation_no) AS (
    SELECT series_no FROM generate_series(1, 12) AS series(series_no)
), recommendation_targets AS (
    SELECT recommendation_no,
           ('33333333-3333-3333-3333-' || lpad((333333333300 + recommendation_no)::text, 12, '0'))::uuid AS customer_id,
           CASE
               WHEN recommendation_no % 3 = 2
                    AND (((recommendation_no - 1) % 5) + 1) < 5
                   THEN (((recommendation_no - 1) % 5) + 2)::varchar
               ELSE (((recommendation_no - 1) % 5) + 1)::varchar
           END AS target_product_risk
    FROM recommendation_seed
), recommendation_rows AS (
    SELECT recommendation_targets.recommendation_no,
           recommendation_targets.customer_id,
           product_choice.id AS product_id,
           product_choice.risk_level_code::integer <= customers.risk_grade_code::integer AS suitability_passed,
           CASE
               WHEN product_choice.risk_level_code::integer > customers.risk_grade_code::integer THEN 'BLOCKED'
               WHEN recommendation_targets.recommendation_no % 3 = 1 THEN 'APPROVED'
               ELSE 'DRAFT'
           END AS status_code
    FROM recommendation_targets
    JOIN customers ON customers.id = recommendation_targets.customer_id
    JOIN LATERAL (
        SELECT products.id, products.risk_level_code
        FROM products
        WHERE products.risk_level_code = recommendation_targets.target_product_risk
        ORDER BY products.product_code
        LIMIT 1
    ) product_choice ON TRUE
)
INSERT INTO recommendation_simulations(
    id, customer_id, employee_id, consultation_id, product_id, status_code,
    suitability_passed, explanation_checked, simulated_customer_consented,
    employee_final_approved, gate_detail_json
)
SELECT ('bbbbbbbb-bbbb-bbbb-bbbb-' || lpad((3000 + recommendation_no)::text, 12, '0'))::uuid,
       customer_id,
       CASE WHEN recommendation_no <= 6 THEN '22222222-2222-2222-2222-222222222201'::uuid ELSE '22222222-2222-2222-2222-222222222204'::uuid END,
       ('66666666-6666-6666-6666-' || lpad((666666666300 + (((recommendation_no - 1) % 10) + 1))::text, 12, '0'))::uuid,
       product_id,
       status_code,
       suitability_passed,
       status_code IN ('APPROVED', 'BLOCKED'),
       status_code = 'APPROVED',
       status_code = 'APPROVED',
       CASE
           WHEN status_code = 'APPROVED'
               THEN '{"passed":["suitability_passed","explanation_checked","simulated_customer_consented","employee_final_approved"],"failed":[]}'::jsonb
           WHEN suitability_passed IS FALSE
               THEN '{"failed":["suitability_passed","employee_final_approved"]}'::jsonb
           ELSE '{"failed":["employee_final_approved"]}'::jsonb
       END
FROM recommendation_rows
ON CONFLICT (id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    employee_id = EXCLUDED.employee_id,
    consultation_id = EXCLUDED.consultation_id,
    product_id = EXCLUDED.product_id,
    status_code = EXCLUDED.status_code,
    suitability_passed = EXCLUDED.suitability_passed,
    explanation_checked = EXCLUDED.explanation_checked,
    simulated_customer_consented = EXCLUDED.simulated_customer_consented,
    employee_final_approved = EXCLUDED.employee_final_approved,
    gate_detail_json = EXCLUDED.gate_detail_json,
    updated_at = now();

/* sql_id: seed_workflows_order_simulations */
WITH order_seed(order_no) AS (
    SELECT series_no FROM generate_series(1, 12) AS series(series_no)
), order_rows AS (
    SELECT order_no,
           recommendation_simulations.product_id,
           CASE
               WHEN recommendation_simulations.status_code = 'APPROVED'
                    AND order_no % 3 = 1 THEN 'SIMULATED_EXECUTED'
               WHEN recommendation_simulations.status_code = 'BLOCKED' THEN 'BLOCKED'
               ELSE 'DRAFT'
           END AS status_code
    FROM order_seed
    JOIN recommendation_simulations
      ON recommendation_simulations.id = ('bbbbbbbb-bbbb-bbbb-bbbb-' || lpad((3000 + order_no)::text, 12, '0'))::uuid
)
INSERT INTO order_simulations(
    id, recommendation_simulation_id, customer_id, employee_id, product_id, side_code,
    quantity, amount_krw, status_code, gate_detail_json, simulated_executed_at
)
SELECT ('cccccccc-cccc-cccc-cccc-' || lpad((3000 + order_no)::text, 12, '0'))::uuid,
       ('bbbbbbbb-bbbb-bbbb-bbbb-' || lpad((3000 + order_no)::text, 12, '0'))::uuid,
       ('33333333-3333-3333-3333-' || lpad((333333333300 + order_no)::text, 12, '0'))::uuid,
       CASE WHEN order_no <= 6 THEN '22222222-2222-2222-2222-222222222201'::uuid ELSE '22222222-2222-2222-2222-222222222204'::uuid END,
       product_id,
       CASE WHEN order_no % 2 = 0 THEN 'SELL' ELSE 'BUY' END,
       CASE WHEN order_no % 2 = 1 THEN (order_no + 1)::numeric(20,6) ELSE NULL END,
       CASE WHEN order_no % 2 = 0 THEN (order_no * 10000000)::numeric(20,2) ELSE NULL END,
       status_code,
       CASE WHEN status_code = 'SIMULATED_EXECUTED' THEN '{"passed":["recommendation_approved","product_match","quantity_or_amount_present"]}'::jsonb ELSE '{"failed":["recommendation_approved"]}'::jsonb END,
       CASE WHEN status_code = 'SIMULATED_EXECUTED' THEN now() - interval '1 day' ELSE NULL END
FROM order_rows
ON CONFLICT (id) DO UPDATE SET
    recommendation_simulation_id = EXCLUDED.recommendation_simulation_id,
    customer_id = EXCLUDED.customer_id,
    employee_id = EXCLUDED.employee_id,
    product_id = EXCLUDED.product_id,
    side_code = EXCLUDED.side_code,
    quantity = EXCLUDED.quantity,
    amount_krw = EXCLUDED.amount_krw,
    status_code = EXCLUDED.status_code,
    gate_detail_json = EXCLUDED.gate_detail_json,
    simulated_executed_at = EXCLUDED.simulated_executed_at,
    updated_at = now();

/* sql_id: seed_workflows_audit_logs */
WITH audit_seed(audit_no, action_code, resource_type, resource_id, detail_json) AS (
    VALUES
        (1, 'customer_360_view', 'customer', '33333333-3333-3333-3333-333333333301'::uuid, '{"seed":"full-mvp"}'::jsonb),
        (2, 'consultation_create', 'consultation', '66666666-6666-6666-6666-666666666301'::uuid, '{"seed":"full-mvp"}'::jsonb),
        (3, 'consultation_complete', 'consultation', '66666666-6666-6666-6666-666666666301'::uuid, '{"suitability_checked":true,"explanation_checked":true}'::jsonb),
        (4, 'recommendation_simulation_create', 'recommendation_simulation', 'bbbbbbbb-bbbb-bbbb-bbbb-000000003001'::uuid, '{"four_gate":"passed"}'::jsonb),
        (5, 'recommendation_simulation_block', 'recommendation_simulation', 'bbbbbbbb-bbbb-bbbb-bbbb-000000003002'::uuid, '{"blocked_reason":"risk_grade_exceeded"}'::jsonb),
        (6, 'order_simulation_block', 'order_simulation', 'cccccccc-cccc-cccc-cccc-000000003002'::uuid, '{"blocked_reason":"recommendation_blocked"}'::jsonb)
)
INSERT INTO audit_logs(id, actor_id, action_code, resource_type, resource_id, detail_json)
SELECT ('dddddddd-dddd-dddd-dddd-' || lpad((3000 + audit_no)::text, 12, '0'))::uuid,
       '22222222-2222-2222-2222-222222222201'::uuid,
       action_code,
       resource_type,
       resource_id,
       detail_json
FROM audit_seed
ON CONFLICT (id) DO NOTHING;

/* sql_id: seed_workflows_email_drafts */
INSERT INTO email_drafts(
    id, customer_id, employee_id, consultation_id, subject, body, ai_generated_at,
    ai_model_name, status_code, sent_at
)
VALUES
    ('eeeeeeee-eeee-eeee-eeee-eeeeeeee0301', '33333333-3333-3333-3333-333333333301', '22222222-2222-2222-2222-222222222201', '66666666-6666-6666-6666-666666666301', '은퇴소득 점검 후속 안내', '교육용 초안입니다. 개인 식별정보 없이 상담 후속 설명 항목만 포함합니다.', NULL, NULL, 'DRAFT', NULL),
    ('eeeeeeee-eeee-eeee-eeee-eeeeeeee0302', '33333333-3333-3333-3333-333333333302', '22222222-2222-2222-2222-222222222201', '66666666-6666-6666-6666-666666666302', '채권 만기 체크리스트', '교육용 승인 초안입니다. 만기 재투자와 설명 확인 항목을 정리했습니다.', NULL, NULL, 'APPROVED', NULL)
ON CONFLICT (id) DO UPDATE SET
    subject = EXCLUDED.subject,
    body = EXCLUDED.body,
    ai_generated_at = NULL,
    ai_model_name = NULL,
    status_code = EXCLUDED.status_code,
    sent_at = EXCLUDED.sent_at,
    updated_at = now();

/* sql_id: seed_workflows_ai_jobs */
INSERT INTO ai_jobs(
    id, job_type_code, status_code, requested_by_id, resource_type, resource_id,
    result_resource_type, result_resource_id, result_summary, error_code, error_message,
    started_at, finished_at
)
VALUES
    ('ffffffff-ffff-ffff-ffff-ffffffff0301', 'consultation_briefing', 'SUCCEEDED', '22222222-2222-2222-2222-222222222201', 'consultation', '66666666-6666-6666-6666-666666666301', 'ai_output', 'f1f1f1f1-f1f1-f1f1-f1f1-f1f1f1f10301', '교육용 AI 출력 메타데이터 행은 환경변수 모델 설정을 사용한다.', NULL, NULL, now() - interval '1 hour', now() - interval '59 minutes'),
    ('ffffffff-ffff-ffff-ffff-ffffffff0302', 'rag_qa', 'FAILED', '22222222-2222-2222-2222-222222222201', 'document', NULL, NULL, NULL, NULL, 'PROVIDER_BLOCKED', 'Seed does not fabricate embeddings or provider data.', now() - interval '1 hour', now() - interval '59 minutes')
ON CONFLICT (id) DO UPDATE SET
    status_code = EXCLUDED.status_code,
    result_resource_type = EXCLUDED.result_resource_type,
    result_resource_id = EXCLUDED.result_resource_id,
    result_summary = EXCLUDED.result_summary,
    error_code = EXCLUDED.error_code,
    error_message = EXCLUDED.error_message,
    started_at = EXCLUDED.started_at,
    finished_at = EXCLUDED.finished_at;

/* sql_id: seed_workflows_ai_outputs */
INSERT INTO ai_outputs(
    id, agent_id, model_name, generated_at, resource_type, resource_id, job_id,
    prompt_hash, output_json, citations_json
)
VALUES (
    'f1f1f1f1-f1f1-f1f1-f1f1-f1f1f1f10301',
    'consultation_briefing',
    current_setting('harness.seed_ai_model_name'),
    now() - interval '59 minutes',
    'consultation',
    '66666666-6666-6666-6666-666666666301',
    'ffffffff-ffff-ffff-ffff-ffffffff0301',
    '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    '{"summary":"교육용 AI 메타데이터 예시이며 개인별 원문 정보는 포함하지 않는다.","employee_must_review":true}'::jsonb,
    '[]'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
    model_name = EXCLUDED.model_name,
    generated_at = EXCLUDED.generated_at,
    output_json = EXCLUDED.output_json,
    citations_json = EXCLUDED.citations_json;
