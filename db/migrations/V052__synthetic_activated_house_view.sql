/* sql_id: v052_synthetic_activated_house_view */
-- FIXTURE: 대시보드 노출용 ACTIVATED 상태 합성 하우스뷰 1건
--
-- 목적: dashboard API가 status_code='ACTIVATED'/'ACTIVE' house_view를 조회.
--       DB에 해당 항목 0건이면 빈 객체 반환 → PB 화면 "최신 하우스뷰 요약" 미노출.
--       spec qa-audit-quality G6/G8 "house view summary card" assertion FAIL.
--
-- 설계 원칙:
--   - 결정성 UUID (ON CONFLICT idempotent)
--   - title/period_code/summary 모두 한국어 (BANNED_* 패턴 미포함)
--   - period_code: '2099Q4' (test fixture 차단 목록 미포함)
--   - empty_intent: 'by_design' (V048 컬럼)
--   - ai_model_name: 한국어 설명 (영문 내부 식별자 아님)

INSERT INTO house_views (
    id, version_no, period_code, title, status_code, summary,
    asset_views_json, model_portfolios_json, risks_json,
    created_by_id, activated_at, ai_generated_at, ai_model_name, empty_intent
)
VALUES (
    'a0000052-0000-0000-0000-000000000001'::uuid,
    9001,
    '2099Q4',
    '2099년 4분기 합성 하우스뷰 (대시보드 시연용)',
    'ACTIVATED',
    '대시보드 노출용 합성 데이터입니다. 실제 투자 권고가 아닙니다. 균형 배분 전략 기반 분기별 전망.',
    '{"primary_view": "균형 배분", "tilt": "방어적 포지셔닝"}'::jsonb,
    '{"core": "정기 분산 투자", "satellite": "선별적 동향 추종"}'::jsonb,
    '{"top_risks": ["유동성 변동성", "정책 불확실성", "환율 리스크"]}'::jsonb,
    (SELECT id FROM employees ORDER BY id LIMIT 1),
    now(),
    now(),
    '합성-데모-모델-v1',
    'by_design'
)
ON CONFLICT (id) DO UPDATE SET
    status_code      = EXCLUDED.status_code,
    activated_at     = COALESCE(house_views.activated_at, EXCLUDED.activated_at),
    summary          = EXCLUDED.summary,
    asset_views_json = EXCLUDED.asset_views_json,
    model_portfolios_json = EXCLUDED.model_portfolios_json,
    risks_json       = EXCLUDED.risks_json;
