/* sql_id: v067_service_readiness_fixture_seeds */
-- V067: Service-readiness v2 (2026-05-24) — seed synthetic rows for
-- compliance-pillar pages whose UI rendered an empty list because the
-- underlying entity had 0 rows in this PoC database.
--
-- Phase 2 measurement (.omc/handoffs/wave-fix-service-readiness-*)
-- found these 6 tables completely empty + 3 tables with only 1 row,
-- making the corresponding pages (KycEdd / RightsNotice /
-- ConflictOfInterest / Consents / DataGovernance / Dispute /
-- MarketingReview / ConsultationGates) impossible to demo even though
-- the routes themselves rendered successfully.
--
-- Each insert uses a deterministic UUID (`'88...88-' || lpad(...)`)
-- so the migration is idempotent (`ON CONFLICT DO NOTHING`) and a
-- rerun creates no duplicates.
--
-- All rows reference existing synthetic customers
-- (33333333-...-33330[1-5]) and employees (PB/ADMIN). The synthetic
-- prefix CHECK (V037) is honored where applicable.

-- ─── kyc_edd_triggers (was 0) ────────────────────────────────────────
INSERT INTO kyc_edd_triggers (id, customer_id, trigger_type, trigger_value, status, reason_text)
VALUES
    ('88888888-8888-8888-8888-880000000601', '33333333-3333-3333-3333-333333333301', 'ASSET_CHANGE_PCT',
     '{"prev_aum": 100000000, "new_aum": 250000000, "change_pct": 150}'::jsonb, 'OPEN',
     '자산 규모 6개월 내 150% 변동 — EDD 재평가 필요'),
    ('88888888-8888-8888-8888-880000000602', '33333333-3333-3333-3333-333333333302', 'OVERSEAS_TRANSFER',
     '{"amount_krw": 80000000, "country": "SG"}'::jsonb, 'OPEN',
     '해외 송금 8천만원 이상 — 출처 확인 필요'),
    ('88888888-8888-8888-8888-880000000603', '33333333-3333-3333-3333-333333333303', 'PEP_FLAG',
     '{"position": "synthetic_pep", "since": "2025-01"}'::jsonb, 'IN_PROGRESS',
     'PEP(정치적주요인물) 분류 — 강화된 실사 진행 중'),
    ('88888888-8888-8888-8888-880000000604', '33333333-3333-3333-3333-333333333304', 'HIGH_RISK_PRODUCT',
     '{"product": "구조화상품", "risk_rating": "1등급"}'::jsonb, 'CLOSED',
     '고위험 상품 권유 — 적합성 재확인 완료'),
    ('88888888-8888-8888-8888-880000000605', '33333333-3333-3333-3333-333333333305', 'ASSET_CHANGE_PCT',
     '{"prev_aum": 50000000, "new_aum": 30000000, "change_pct": -40}'::jsonb, 'OPEN',
     '자산 40% 감소 — 손실 사유 면담 필요')
ON CONFLICT (id) DO NOTHING;

-- ─── rights_notices (was 0) ──────────────────────────────────────────
-- Use existing COMPLETED consultations so the customer/consultation FKs hold.
INSERT INTO rights_notices (id, consultation_id, customer_id, employee_id, notice_kinds, audit_chain_hash)
VALUES
    ('88888888-8888-8888-8888-880000000701',
     '66666666-6666-6666-6666-666666666301',
     '33333333-3333-3333-3333-333333333301',
     '22222222-2222-2222-2222-222222222201',
     '["청약철회권", "민원접수권"]'::jsonb,
     'SYN-rn-hash-aa01'),
    ('88888888-8888-8888-8888-880000000702',
     '66666666-6666-6666-6666-666666666302',
     '33333333-3333-3333-3333-333333333302',
     '22222222-2222-2222-2222-222222222201',
     '["민원접수권"]'::jsonb,
     'SYN-rn-hash-aa02'),
    ('88888888-8888-8888-8888-880000000703',
     '66666666-6666-6666-6666-666666666303',
     '33333333-3333-3333-3333-333333333303',
     '22222222-2222-2222-2222-222222222201',
     '["청약철회권", "분쟁조정신청권"]'::jsonb,
     'SYN-rn-hash-aa03')
ON CONFLICT (id) DO NOTHING;

-- ─── conflict_disclosures (was 0) ────────────────────────────────────
INSERT INTO conflict_disclosures (id, employee_id, customer_id, disclosure_type, description_redacted, chinese_wall_violation)
VALUES
    ('88888888-8888-8888-8888-880000000801',
     '22222222-2222-2222-2222-222222222201', '33333333-3333-3333-3333-333333333301',
     'PRE_TRADE',
     '[SYN] 자사 발행 ETF 추천 — 이해상충 사전공시', false),
    ('88888888-8888-8888-8888-880000000802',
     '22222222-2222-2222-2222-222222222201', '33333333-3333-3333-3333-333333333302',
     'RELATED_PARTY',
     '[SYN] 계열사 펀드 권유 — 관계자거래 공시', false),
    ('88888888-8888-8888-8888-880000000803',
     '22222222-2222-2222-2222-222222222201', '33333333-3333-3333-3333-333333333303',
     'POST_TRADE',
     '[SYN] 매매 후 자사 펀드 보유 사실 사후공시', false),
    ('88888888-8888-8888-8888-880000000804',
     '22222222-2222-2222-2222-222222222203', '33333333-3333-3333-3333-333333333304',
     'PRE_TRADE',
     '[SYN] Chinese Wall 위반 의심 — 차단됨', true),
    ('88888888-8888-8888-8888-880000000805',
     '22222222-2222-2222-2222-222222222201', '33333333-3333-3333-3333-333333333305',
     'RELATED_PARTY',
     '[SYN] 가족 보유 종목 추천 — 관계자거래 공시', false)
ON CONFLICT (id) DO NOTHING;

-- ─── customer_consents (was 0) ───────────────────────────────────────
INSERT INTO customer_consents (id, customer_id, consent_type, consent_scope, granted_by_employee_id, synthetic)
VALUES
    ('88888888-8888-8888-8888-880000000901',
     '33333333-3333-3333-3333-333333333301', 'GENERAL_BUNDLE',
     '{"items": ["personal_info", "biometric", "transaction_history"]}'::jsonb,
     '22222222-2222-2222-2222-222222222201', true),
    ('88888888-8888-8888-8888-880000000902',
     '33333333-3333-3333-3333-333333333302', 'INFORMATION_USE',
     '{"purpose": "내부 분석"}'::jsonb,
     '22222222-2222-2222-2222-222222222201', true),
    ('88888888-8888-8888-8888-880000000903',
     '33333333-3333-3333-3333-333333333303', 'MARKETING_CONTACT',
     '{"channels": ["email", "sms"]}'::jsonb,
     '22222222-2222-2222-2222-222222222201', true),
    ('88888888-8888-8888-8888-880000000904',
     '33333333-3333-3333-3333-333333333304', 'DATA_SHARING_THIRD_PARTY',
     '{"third_party": "관계자 운용사"}'::jsonb,
     '22222222-2222-2222-2222-222222222201', true),
    ('88888888-8888-8888-8888-880000000905',
     '33333333-3333-3333-3333-333333333305', 'GENERAL_BUNDLE',
     '{"items": ["personal_info", "transaction_history"]}'::jsonb,
     '22222222-2222-2222-2222-222222222201', true),
    ('88888888-8888-8888-8888-880000000906',
     '33333333-3333-3333-3333-333333333301', 'MARKETING_CONTACT',
     '{"channels": ["app_push"]}'::jsonb,
     '22222222-2222-2222-2222-222222222201', true)
ON CONFLICT (id) DO NOTHING;

-- ─── info_access_requests (was 0) ────────────────────────────────────
INSERT INTO info_access_requests (id, customer_id, request_type, response_summary_redacted, employee_id, responded_at)
VALUES
    ('88888888-8888-8888-8888-880000001001',
     '33333333-3333-3333-3333-333333333301', 'ACCESS',
     '[SYN] 개인정보 처리내역 열람 응답 — 항목 N건 제공',
     '22222222-2222-2222-2222-222222222203', now() - interval '2 day'),
    ('88888888-8888-8888-8888-880000001002',
     '33333333-3333-3333-3333-333333333302', 'ACCESS',
     '[SYN] 거래내역 사본 제공 — 5년치 PDF',
     '22222222-2222-2222-2222-222222222203', now() - interval '5 day'),
    ('88888888-8888-8888-8888-880000001003',
     '33333333-3333-3333-3333-333333333303', 'CORRECTION',
     '[SYN] 주소 정정 처리 — 거주지 변경 반영',
     '22222222-2222-2222-2222-222222222203', now() - interval '1 day'),
    ('88888888-8888-8888-8888-880000001004',
     '33333333-3333-3333-3333-333333333304', 'CORRECTION',
     NULL,
     '22222222-2222-2222-2222-222222222203', NULL)
ON CONFLICT (id) DO NOTHING;

-- ─── data_purge_schedules (was 0) ────────────────────────────────────
INSERT INTO data_purge_schedules (id, target_table, target_row_id, purge_due_at, purge_reason)
VALUES
    ('88888888-8888-8888-8888-880000001101',
     'consultations', '66666666-6666-6666-6666-666666666301',
     now() + interval '5 year', '[SYN] 정기 retention 만료 일정'),
    ('88888888-8888-8888-8888-880000001102',
     'email_drafts', '6e2790fc-636e-433a-be1d-826783d4043f',
     now() + interval '3 year', '[SYN] 마케팅 자료 보관기간 만료'),
    ('88888888-8888-8888-8888-880000001103',
     'ai_outputs', '88888888-8888-8888-8888-888888888301',
     now() + interval '7 year', '[SYN] AI 출력 감사 보관기간 만료')
ON CONFLICT (id) DO NOTHING;

-- ─── dispute_cases (was 1) ───────────────────────────────────────────
INSERT INTO dispute_cases (id, customer_id, consultation_id, employee_id, dispute_type, status, response_due_at)
VALUES
    ('88888888-8888-8888-8888-880000001201',
     '33333333-3333-3333-3333-333333333301', '66666666-6666-6666-6666-666666666301',
     '22222222-2222-2222-2222-222222222201', '부당권유', 'OPEN', now() + interval '7 day'),
    ('88888888-8888-8888-8888-880000001202',
     '33333333-3333-3333-3333-333333333302', '66666666-6666-6666-6666-666666666302',
     '22222222-2222-2222-2222-222222222201', '광고', 'RESPONDED', now() + interval '14 day'),
    ('88888888-8888-8888-8888-880000001203',
     '33333333-3333-3333-3333-333333333303', '66666666-6666-6666-6666-666666666303',
     '22222222-2222-2222-2222-222222222201', '계약', 'OPEN', now() + interval '5 day'),
    ('88888888-8888-8888-8888-880000001204',
     '33333333-3333-3333-3333-333333333304', NULL,
     '22222222-2222-2222-2222-222222222201', '기타', 'RESOLVED', now() - interval '3 day')
ON CONFLICT (id) DO NOTHING;

UPDATE dispute_cases SET responded_at = now() - interval '1 day'
 WHERE id = '88888888-8888-8888-8888-880000001202' AND responded_at IS NULL;
UPDATE dispute_cases SET responded_at = now() - interval '6 day', resolved_at = now() - interval '3 day'
 WHERE id = '88888888-8888-8888-8888-880000001204' AND resolved_at IS NULL;

-- ─── marketing_reviews (was 1) ───────────────────────────────────────
INSERT INTO marketing_reviews (id, email_draft_id, classification, leading_block_text,
                                static_rule_pass, ai_compliance_pass, ai_reasoning_redacted,
                                decision, reviewed_by, reviewed_at)
VALUES
    ('88888888-8888-8888-8888-880000001301',
     '6e2790fc-636e-433a-be1d-826783d4043f', 'MARKETING',
     '[부적합 유형] 원금손실 가능, 적합하지 않은 투자자: 위험회피형',
     true, true,
     '[SYN] 부적합 유형 우선 표기 정합, 광고지침 통과',
     'MARKETING_REVIEW_PASS', '22222222-2222-2222-2222-222222222203',
     now() - interval '1 day'),
    ('88888888-8888-8888-8888-880000001302',
     '6b0157a2-95e8-437f-be0d-09618c1c52d9', 'OPERATIONAL',
     '운영성 안내문구 (마케팅 분류 아님)',
     true, NULL, NULL,
     'MARKETING_REVIEW_PASS', '22222222-2222-2222-2222-222222222203',
     now() - interval '2 day'),
    ('88888888-8888-8888-8888-880000001303',
     '8ceb22d9-f8b6-4593-a7e9-29f4faf81350', 'MARKETING',
     NULL,
     false, NULL, '[SYN] 부적합 유형 leading-block 누락 — 차단됨',
     'MARKETING_REVIEW_BLOCK', '22222222-2222-2222-2222-222222222203',
     now() - interval '3 day'),
    ('88888888-8888-8888-8888-880000001304',
     '1bc0b4dd-d96b-4b29-92e1-c934add6f7fb', 'MARKETING',
     '[부적합 유형] 손실 가능, 적합하지 않은 투자자: 안정형',
     true, false, '[SYN] AI 정합성 검사 미달',
     'MARKETING_REVIEW_BLOCK', '22222222-2222-2222-2222-222222222203',
     now() - interval '4 day')
ON CONFLICT (id) DO NOTHING;

-- ─── consultation_gates (was 1) ──────────────────────────────────────
-- 4 gates × 4 consultations = 16 rows. ON CONFLICT keyed by
-- (consultation_id, gate_name) so the existing row stays.
INSERT INTO consultation_gates (id, consultation_id, gate_name, gate_status, gate_evidence_json)
VALUES
    ('88888888-8888-8888-8888-880000001401', '66666666-6666-6666-6666-666666666301', 'suitability',  'PASSED',       '{"checked_at":"SYN"}'::jsonb),
    ('88888888-8888-8888-8888-880000001402', '66666666-6666-6666-6666-666666666301', 'explanation',  'PASSED',       '{"acknowledged":"SYN"}'::jsonb),
    ('88888888-8888-8888-8888-880000001403', '66666666-6666-6666-6666-666666666301', 'unfair_solicitation', 'PASSED','{"checked":"SYN"}'::jsonb),
    ('88888888-8888-8888-8888-880000001404', '66666666-6666-6666-6666-666666666301', 'marketing',    'ACKNOWLEDGED', '{"acknowledged":"SYN"}'::jsonb),
    ('88888888-8888-8888-8888-880000001405', '66666666-6666-6666-6666-666666666302', 'suitability',  'PASSED',       '{"checked_at":"SYN"}'::jsonb),
    ('88888888-8888-8888-8888-880000001406', '66666666-6666-6666-6666-666666666302', 'explanation',  'PASSED',       '{"acknowledged":"SYN"}'::jsonb),
    ('88888888-8888-8888-8888-880000001407', '66666666-6666-6666-6666-666666666302', 'unfair_solicitation', 'PASSED','{"checked":"SYN"}'::jsonb),
    ('88888888-8888-8888-8888-880000001408', '66666666-6666-6666-6666-666666666302', 'marketing',    'PENDING',      '{}'::jsonb),
    ('88888888-8888-8888-8888-880000001409', '66666666-6666-6666-6666-666666666303', 'suitability',  'PASSED',       '{"checked_at":"SYN"}'::jsonb),
    ('88888888-8888-8888-8888-880000001410', '66666666-6666-6666-6666-666666666303', 'explanation',  'BLOCKED',      '{"reason":"SYN-acknowledgement missing"}'::jsonb),
    ('88888888-8888-8888-8888-880000001411', '66666666-6666-6666-6666-666666666303', 'unfair_solicitation', 'PASSED','{"checked":"SYN"}'::jsonb),
    ('88888888-8888-8888-8888-880000001412', '66666666-6666-6666-6666-666666666303', 'marketing',    'PENDING',      '{}'::jsonb)
ON CONFLICT (consultation_id, gate_name) DO NOTHING;
