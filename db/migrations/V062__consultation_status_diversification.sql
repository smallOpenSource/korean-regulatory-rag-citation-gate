/* sql_id: v062_extend_consultation_status_check */
-- V062: Wave-Audit-Defect-Fix A.3 — extend consultations.status_code domain
-- with 4 lifecycle codes (CANCELLED/REJECTED/DISMISSED/EXPIRED) and seed one
-- synthetic row per code so the audit fixture has ≥7 distinct status codes.
--
-- Pre-V062 domain: {DRAFT, SAVED, COMPLETED}. Strictly broader extension —
-- every existing row remains valid. Idempotent via DROP CONSTRAINT IF EXISTS.
ALTER TABLE consultations
    DROP CONSTRAINT IF EXISTS consultations_status_code_check;

/* sql_id: v062_add_extended_consultation_status_check */
ALTER TABLE consultations
    ADD CONSTRAINT consultations_status_code_check
    CHECK (status_code IN (
        'DRAFT', 'SAVED', 'COMPLETED',
        'CANCELLED', 'REJECTED', 'DISMISSED', 'EXPIRED'
    ));

/* sql_id: v062_seed_consultation_cancelled */
INSERT INTO consultations(
    id, customer_id, employee_id, consultation_at,
    channel_code, status_code, summary,
    suitability_checked, explanation_checked,
    created_at, updated_at
) VALUES (
    'cccccccc-cccc-cccc-cccc-cccccccccc01'::uuid,
    '33333333-3333-3333-3333-333333333301'::uuid,
    '22222222-2222-2222-2222-222222222201'::uuid,
    '2026-05-15 10:00:00+09'::timestamptz,
    'PHONE', 'CANCELLED',
    '[합성] 고객 일정 변경으로 상담 취소 — 재예약 안내.',
    FALSE, FALSE, now(), now()
) ON CONFLICT (id) DO UPDATE SET
    status_code = EXCLUDED.status_code,
    summary = EXCLUDED.summary,
    updated_at = now();

/* sql_id: v062_seed_consultation_rejected */
INSERT INTO consultations(
    id, customer_id, employee_id, consultation_at,
    channel_code, status_code, summary,
    suitability_checked, explanation_checked,
    created_at, updated_at
) VALUES (
    'cccccccc-cccc-cccc-cccc-cccccccccc02'::uuid,
    '33333333-3333-3333-3333-333333333302'::uuid,
    '22222222-2222-2222-2222-222222222201'::uuid,
    '2026-05-16 11:30:00+09'::timestamptz,
    'WRITTEN', 'REJECTED',
    '[합성] 적합성 검토 결과 권유 거절 — 위험성향 불일치.',
    FALSE, FALSE, now(), now()
) ON CONFLICT (id) DO UPDATE SET
    status_code = EXCLUDED.status_code,
    summary = EXCLUDED.summary,
    updated_at = now();

/* sql_id: v062_seed_consultation_dismissed */
INSERT INTO consultations(
    id, customer_id, employee_id, consultation_at,
    channel_code, status_code, summary,
    suitability_checked, explanation_checked,
    created_at, updated_at
) VALUES (
    'cccccccc-cccc-cccc-cccc-cccccccccc03'::uuid,
    '33333333-3333-3333-3333-333333333303'::uuid,
    '22222222-2222-2222-2222-222222222202'::uuid,
    '2026-05-17 09:15:00+09'::timestamptz,
    'VIDEO', 'DISMISSED',
    '[합성] 고객 부재 3회 — 상담 회차 종결 처리.',
    FALSE, FALSE, now(), now()
) ON CONFLICT (id) DO UPDATE SET
    status_code = EXCLUDED.status_code,
    summary = EXCLUDED.summary,
    updated_at = now();

/* sql_id: v062_seed_consultation_expired */
INSERT INTO consultations(
    id, customer_id, employee_id, consultation_at,
    channel_code, status_code, summary,
    suitability_checked, explanation_checked,
    created_at, updated_at
) VALUES (
    'cccccccc-cccc-cccc-cccc-cccccccccc04'::uuid,
    '33333333-3333-3333-3333-333333333304'::uuid,
    '22222222-2222-2222-2222-222222222202'::uuid,
    '2026-05-10 14:00:00+09'::timestamptz,
    'FACE_TO_FACE', 'EXPIRED',
    '[합성] DRAFT 상태 30일 초과 — 자동 만료 처리.',
    FALSE, FALSE, now(), now()
) ON CONFLICT (id) DO UPDATE SET
    status_code = EXCLUDED.status_code,
    summary = EXCLUDED.summary,
    updated_at = now();
