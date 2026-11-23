/* sql_id: v054_v8_audit_action_codes_and_cleanup */
-- V054: v8 state-graph traversal — audit_action_codes 추가 + archive table 생성
--
-- 목적:
--   1. v8 BFS 셀 방문 로그용 action_code 2개 등록
--   2. audit_logs_v8_archive 별도 테이블 생성 (90d 이전 v8_cell_visited row 복제 대상)
--
-- CRITICAL 제약:
--   - audit_logs 자체 UPDATE / DELETE / TRUNCATE 절대 금지
--     (V008 trg_audit_logs_no_update / trg_audit_logs_no_delete,
--      V019 trg_audit_logs_no_truncate 존재)
--   - audit_logs_v8_archive 는 별도 테이블 — INSERT only from audit_logs
--   - audit_logs row 는 영원히 보존 (append-only invariant)

-- ─── 1. v8 audit_action_codes 추가 ─────────────────────────────────────────

/* sql_id: v054_seed_v8_action_codes */
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('v8_cell_visited',       'v8 BFS visitor — 상태 셀 방문 로그 (90d 보존 후 archive 복제)'),
    ('v8_unreachable_marked', 'v8 BFS visitor — 도달 불가 셀 manifest 마킹 로그')
ON CONFLICT (action_code) DO NOTHING;

/* sql_id: v054_create_audit_logs_v8_archive */
-- ─── 2. audit_logs_v8_archive 테이블 생성 ──────────────────────────────────
-- audit_logs 와 동일 컬럼 구조 (FK 제약 없음 — archive 독립성 보장).
-- 트리거 없음 — archive 테이블은 INSERT-only 아카이브이며
-- append-only 보장은 운영 정책으로 관리.
-- audit_logs row 는 절대 삭제 안 함 — archive 는 복제(copy)일 뿐.
CREATE TABLE IF NOT EXISTS audit_logs_v8_archive (
    id            UUID         NOT NULL DEFAULT gen_random_uuid(),
    actor_id      UUID,                                    -- no FK: archive 독립
    action_code   VARCHAR(80)  NOT NULL,                   -- no FK: archive 독립
    resource_type VARCHAR(80)  NOT NULL,
    resource_id   UUID,
    ip_address    INET,
    user_agent    TEXT,
    detail_json   JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),     -- 원본 audit_logs.created_at
    archived_at   TIMESTAMPTZ  NOT NULL DEFAULT now()      -- archive 복제 시각
);

/* sql_id: v054_pk_audit_logs_v8_archive */
ALTER TABLE audit_logs_v8_archive
    ADD CONSTRAINT audit_logs_v8_archive_pkey
    PRIMARY KEY (id);

/* sql_id: v054_index_archive_action_created */
CREATE INDEX IF NOT EXISTS idx_v8_archive_action_created
    ON audit_logs_v8_archive (action_code, created_at DESC);

/* sql_id: v054_index_archive_archived_at */
CREATE INDEX IF NOT EXISTS idx_v8_archive_archived_at
    ON audit_logs_v8_archive (archived_at DESC);
