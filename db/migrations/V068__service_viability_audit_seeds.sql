/* sql_id: service_viability_v068 */
-- V068: Service Viability Audit v1 — incremental synthetic fixture seeds
-- (2026-05-24)
--
-- Predecessor plan: .omc/plans/ralplan-wmah-service-viability-audit-v1.2.md §3.0 Step 0
-- Cycle: svc-via-audit-v1 (4-axis audit — UI / business workflow / data integrity / Korean copy)
--
-- Purpose: V067 시드된 dispute_cases / kyc_edd_triggers OPEN row 일부가 직전 cycle
-- (backend-bug-hunt v3, 730242b) status-transition test에서 RESOLVED/CLOSED로 전이됨.
-- 본 cycle Axis 2/3 시나리오 진입을 위해 OPEN/GENERATED/DRAFT row를 +3건 incremental seed.
--
-- Baseline divergence (psql 실측, 2026-05-24):
--   dispute_cases OPEN = 0 (plan v1.2:273-276 가정 2; V067 1201/1203 → RESOLVED)
--   kyc_edd_triggers OPEN = 0 (plan v1.2:273-276 가정 3; V067 601/602/605 → CLOSED)
--   house_views GENERATED = 63 (plan v1.2 가정 0; runtime mutation 출처 추적은 Follow-up)
--   email_drafts DRAFT = 98 (plan v1.2 가정 0; runtime mutation 출처 추적은 Follow-up)
--
-- §4 Axis 3 (5) criterion refine (lead 결정): baseline-relative +12 row (3+3+3+3)
-- assertion으로 재해석. plan SoT 의도 보존.
--
-- All FK references existing synthetic entities:
--   - customers.id (SYN- prefix CHECK V037 enforced — 33333333-...-333301 등)
--   - employees.id (PB1 = 22222222-...-222201, V067 시드)
--   - consultations.id (V067 시드 66666666-...-666301~303 — dispute_cases.consultation_id 용)
--
-- All INSERTs use deterministic UUID + ON CONFLICT (id) DO NOTHING for idempotency
-- (per [[on-conflict-id-for-mutable-content]] — content_hash PK는 본 V068 대상 테이블에 부재).
--
-- 각 statement는 sql_id 헤더로 시작 (per [[v-sql-sql-id-validator]]) — V067 pre-existing
-- failure는 본 cycle scope 외 (Follow-up).
--
-- ─── dispute_cases (+3 OPEN — id 1205/1206/1207) ─────────────────────
INSERT INTO dispute_cases (id, customer_id, consultation_id, employee_id, dispute_type, status, response_due_at)
VALUES
    ('88888888-8888-8888-8888-880000001205',
     '33333333-3333-3333-3333-333333333301', '66666666-6666-6666-6666-666666666301',
     '22222222-2222-2222-2222-222222222201', '부당권유', 'OPEN', now() + interval '10 day'),
    ('88888888-8888-8888-8888-880000001206',
     '33333333-3333-3333-3333-333333333302', '66666666-6666-6666-6666-666666666302',
     '22222222-2222-2222-2222-222222222201', '광고', 'OPEN', now() + interval '12 day'),
    ('88888888-8888-8888-8888-880000001207',
     '33333333-3333-3333-3333-333333333303', '66666666-6666-6666-6666-666666666303',
     '22222222-2222-2222-2222-222222222201', '계약', 'OPEN', now() + interval '8 day')
ON CONFLICT (id) DO NOTHING;

/* sql_id: service_viability_v068 */
-- ─── kyc_edd_triggers (+3 OPEN — id 606/607/608) ──────────────────────
INSERT INTO kyc_edd_triggers (id, customer_id, trigger_type, trigger_value, status, reason_text)
VALUES
    ('88888888-8888-8888-8888-880000000606',
     '33333333-3333-3333-3333-333333333301', 'ASSET_CHANGE_PCT',
     '{"prev_aum": 200000000, "new_aum": 500000000, "change_pct": 150}'::jsonb,
     'OPEN', '[SYN] 자산 6개월 150% 증가 — service viability audit v1 시드'),
    ('88888888-8888-8888-8888-880000000607',
     '33333333-3333-3333-3333-333333333302', 'OVERSEAS_TRANSFER',
     '{"amount_krw": 120000000, "country": "US"}'::jsonb,
     'OPEN', '[SYN] 해외 송금 1.2억 — service viability audit v1 시드'),
    ('88888888-8888-8888-8888-880000000608',
     '33333333-3333-3333-3333-333333333303', 'PEP_FLAG',
     '{"position": "synthetic_pep_audit_v1", "since": "2026-05"}'::jsonb,
     'OPEN', '[SYN] PEP 신규 분류 — service viability audit v1 시드')
ON CONFLICT (id) DO NOTHING;

/* sql_id: service_viability_v068 */
-- ─── house_views (+3 GENERATED — id 901/902/903, version_no 999001~999003) ───
-- version_no UNIQUE constraint: max(version_no) 측정 결과 202872 → 999001~999003 안전.
-- created_by_id = PB1 employee.
INSERT INTO house_views (
    id, version_no, period_code, title, status_code, summary,
    asset_views_json, model_portfolios_json, risks_json,
    created_by_id, ai_generated_at, ai_model_name,
    market, asset_class, region, empty_intent
)
VALUES
    ('88888888-8888-8888-8888-880000000901', 999001, '2026-Q2',
     '[SYN] Service Viability Audit v1 — 글로벌 주식 시각',
     'GENERATED',
     '[SYN] 본 House View는 service viability audit v1 cycle용 합성 데이터입니다. PB perspective 검수 대상.',
     '{"by_design": "synthetic"}'::jsonb,
     '{"models": ["SYN-MP-001"]}'::jsonb,
     '{"market_risk": "보통", "liquidity_risk": "보통"}'::jsonb,
     '22222222-2222-2222-2222-222222222201',
     now() - interval '2 hour', 'SYN-MODEL-v1',
     'GLOBAL', 'EQUITY', 'WORLD', 'by_design'),
    ('88888888-8888-8888-8888-880000000902', 999002, '2026-Q2',
     '[SYN] Service Viability Audit v1 — 국내 채권 시각',
     'GENERATED',
     '[SYN] 본 House View는 service viability audit v1 cycle용 합성 데이터입니다.',
     '{"by_design": "synthetic"}'::jsonb,
     '{"models": ["SYN-MP-002"]}'::jsonb,
     '{"credit_risk": "낮음"}'::jsonb,
     '22222222-2222-2222-2222-222222222201',
     now() - interval '3 hour', 'SYN-MODEL-v1',
     'KR', 'FIXED_INCOME', 'KR', 'by_design'),
    ('88888888-8888-8888-8888-880000000903', 999003, '2026-Q2',
     '[SYN] Service Viability Audit v1 — 대체투자 시각',
     'GENERATED',
     '[SYN] 본 House View는 service viability audit v1 cycle용 합성 데이터입니다.',
     '{"by_design": "synthetic"}'::jsonb,
     '{"models": ["SYN-MP-003"]}'::jsonb,
     '{"market_risk": "높음"}'::jsonb,
     '22222222-2222-2222-2222-222222222201',
     now() - interval '4 hour', 'SYN-MODEL-v1',
     'GLOBAL', 'ALTERNATIVE', 'WORLD', 'by_design')
ON CONFLICT (id) DO NOTHING;

/* sql_id: service_viability_v068 */
-- ─── email_drafts (+3 DRAFT — id e01/e02/e03) ─────────────────────────
-- schema에 recipient_email column 부재 (psql \d email_drafts 측정): subject + body에
-- synthetic recipient 정보를 inline. Axis 2 NP3 (recipient_not_synthetic 503) trigger는
-- email send 시점 application-layer guardrail이 수행 — fixture 단계는 application-layer
-- guardrail 검증 대상이 아님.
INSERT INTO email_drafts (
    id, customer_id, employee_id, consultation_id,
    subject, body, status_code,
    ai_generated_at, ai_model_name, marketing_classified
)
VALUES
    ('88888888-8888-8888-8888-880000000e01',
     '33333333-3333-3333-3333-333333333301',
     '22222222-2222-2222-2222-222222222201',
     '66666666-6666-6666-6666-666666666301',
     '[SYN] Service Viability Audit v1 — 상담 안내 (DRAFT 1)',
     E'[SYN] 안녕하세요. 본 메일은 service viability audit v1 cycle용 합성 초안입니다.\nRecipient (synthetic): synthetic.recipient.pb1@example.invalid\n원금손실 가능성, 적합하지 않은 투자자: 위험회피형.',
     'DRAFT',
     now() - interval '1 hour', 'SYN-EMAIL-MODEL-v1',
     false),
    ('88888888-8888-8888-8888-880000000e02',
     '33333333-3333-3333-3333-333333333302',
     '22222222-2222-2222-2222-222222222201',
     '66666666-6666-6666-6666-666666666302',
     '[SYN] Service Viability Audit v1 — 운영 안내 (DRAFT 2)',
     E'[SYN] 본 메일은 service viability audit v1 cycle용 합성 초안입니다.\nRecipient (synthetic): synthetic.recipient.pb1+2@example.invalid\n운영성 안내문구이며 마케팅 분류 대상이 아닙니다.',
     'DRAFT',
     now() - interval '2 hour', 'SYN-EMAIL-MODEL-v1',
     false),
    ('88888888-8888-8888-8888-880000000e03',
     '33333333-3333-3333-3333-333333333303',
     '22222222-2222-2222-2222-222222222201',
     '66666666-6666-6666-6666-666666666303',
     '[SYN] Service Viability Audit v1 — 마케팅 (DRAFT 3)',
     E'[SYN] 본 메일은 service viability audit v1 cycle용 합성 초안입니다.\nRecipient (synthetic): synthetic.recipient.pb1+3@example.invalid\n[부적합 유형] 원금손실 가능, 적합하지 않은 투자자: 안정형. 광고지침 사전심의 필요.',
     'DRAFT',
     now() - interval '3 hour', 'SYN-EMAIL-MODEL-v1',
     true)
ON CONFLICT (id) DO NOTHING;
