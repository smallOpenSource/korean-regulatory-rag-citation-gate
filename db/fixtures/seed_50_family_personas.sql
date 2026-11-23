/* sql_id: seed_family_personas_t256 */
-- T256 — 합성 페르소나 6종 (가족 단위) seed.
-- Each row is the family HEAD; dependent accounts are out of scope for this
-- seed (added incrementally as Stage 4 demo scenarios call them).
-- All customer_no entries satisfy V037 chk_customer_no_syn_prefix (CHECK SYN-%).

-- Required preconditions:
--   - assigned_pb_id must reference a synthetic employee already seeded by
--     seed_00_identity.sql (ids: ...201, ...202, ...203).
--   - branch_id is the SYN-BR-001 synthetic branch from seed_00_identity.sql
--     (id = '11111111-1111-1111-1111-111111111111').
-- AC11: customer_name carries [교육용] prefix (PB-perspective self-check, UI display marker).
-- AC14: surveyed_by_id distributes across 3 PBs (2/2/2 split).

INSERT INTO customers(
    id, customer_no, customer_name, assigned_pb_id, branch_id,
    risk_grade_code, segment_code, total_assets_krw, last_contacted_at
)
VALUES
    -- SYN-FAM-001: 4인 가족, 핵심 PB-WM 고객, 위험 5등급, HIGH 세그먼트 (PB 1)
    ('33333333-3333-3333-3333-333333333f01', 'SYN-FAM-001', '[교육용] 김가족 (4인 가구)',
     '22222222-2222-2222-2222-222222222201', '11111111-1111-1111-1111-111111111111',
     '5', 'HNWI_CORE', 8500000000, current_date - interval '12 days'),

    -- SYN-FAM-002: 노부부 + 자녀, 안정 추구, 위험 3, MEDIUM (PB 1)
    ('33333333-3333-3333-3333-333333333f02', 'SYN-FAM-002', '[교육용] 박가족 (노부부+자녀)',
     '22222222-2222-2222-2222-222222222201', '11111111-1111-1111-1111-111111111111',
     '3', 'EMERGING_HNWI', 3200000000, current_date - interval '23 days'),

    -- SYN-FAM-003: 단독 30대 직장인, 적극 투자, 위험 7, LOW(자산 기준) (PB 2)
    ('33333333-3333-3333-3333-333333333f03', 'SYN-FAM-003', '[교육용] 이가족 (단독세대)',
     '22222222-2222-2222-2222-222222222202', '11111111-1111-1111-1111-111111111111',
     '6', 'EMERGING_HNWI', 480000000, current_date - interval '7 days'),

    -- SYN-FAM-004: 다세대 가구 (조부모/부모/자녀), VVIP, 위험 2 (보수) (PB 2)
    ('33333333-3333-3333-3333-333333333f04', 'SYN-FAM-004', '[교육용] 최가족 (3대 가구)',
     '22222222-2222-2222-2222-222222222202', '11111111-1111-1111-1111-111111111111',
     '2', 'HNWI_ULTRA', 21500000000, current_date - interval '3 days'),

    -- SYN-FAM-005: 한부모 가정, 자녀 교육비 목표, 위험 4, MEDIUM (PB 3)
    ('33333333-3333-3333-3333-333333333f05', 'SYN-FAM-005', '[교육용] 정가족 (한부모)',
     '22222222-2222-2222-2222-222222222203', '11111111-1111-1111-1111-111111111111',
     '4', 'EMERGING_HNWI', 1800000000, current_date - interval '34 days'),

    -- SYN-FAM-006: 신혼부부 (자녀 미정), 자산 형성기, 위험 6, MASS (PB 3)
    ('33333333-3333-3333-3333-333333333f06', 'SYN-FAM-006', '[교육용] 강가족 (신혼)',
     '22222222-2222-2222-2222-222222222203', '11111111-1111-1111-1111-111111111111',
     '6', 'EMERGING_HNWI', 320000000, current_date - interval '5 days')
ON CONFLICT (customer_no) DO UPDATE SET
    customer_name = EXCLUDED.customer_name,
    assigned_pb_id = EXCLUDED.assigned_pb_id,
    branch_id = EXCLUDED.branch_id,
    risk_grade_code = EXCLUDED.risk_grade_code,
    segment_code = EXCLUDED.segment_code,
    total_assets_krw = EXCLUDED.total_assets_krw,
    last_contacted_at = EXCLUDED.last_contacted_at,
    is_active = TRUE,
    updated_at = now();

/* sql_id: seed_family_personas_risk_assessments_t256 */
-- Pair each family head with a recent risk assessment so the suitability
-- gate doesn't immediately block on a missing score.
-- AC14: surveyed_by_id distributed across 3 employees (2/2/2 split):
--   personas 1-2 → ...201, personas 3-4 → ...202, personas 5-6 → ...203.
INSERT INTO risk_assessments(id, customer_id, score, risk_grade_code, surveyed_at, surveyed_by_id)
VALUES
    ('33333333-3333-3333-4444-33333333ff01', '33333333-3333-3333-3333-333333333f01',
     58, '5', current_date - interval '12 days', '22222222-2222-2222-2222-222222222201'),
    ('33333333-3333-3333-4444-33333333ff02', '33333333-3333-3333-3333-333333333f02',
     32, '3', current_date - interval '23 days', '22222222-2222-2222-2222-222222222201'),
    ('33333333-3333-3333-4444-33333333ff03', '33333333-3333-3333-3333-333333333f03',
     74, '6', current_date - interval '7 days',  '22222222-2222-2222-2222-222222222202'),
    ('33333333-3333-3333-4444-33333333ff04', '33333333-3333-3333-3333-333333333f04',
     22, '2', current_date - interval '3 days',  '22222222-2222-2222-2222-222222222202'),
    ('33333333-3333-3333-4444-33333333ff05', '33333333-3333-3333-3333-333333333f05',
     45, '4', current_date - interval '34 days', '22222222-2222-2222-2222-222222222203'),
    ('33333333-3333-3333-4444-33333333ff06', '33333333-3333-3333-3333-333333333f06',
     61, '6', current_date - interval '5 days',  '22222222-2222-2222-2222-222222222203')
ON CONFLICT (id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    score = EXCLUDED.score,
    risk_grade_code = EXCLUDED.risk_grade_code,
    surveyed_at = EXCLUDED.surveyed_at,
    surveyed_by_id = EXCLUDED.surveyed_by_id;
