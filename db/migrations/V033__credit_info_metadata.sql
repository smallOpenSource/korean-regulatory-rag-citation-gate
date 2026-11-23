/* sql_id: v033_house_views_pseudonym_label */
ALTER TABLE house_views
    ADD COLUMN IF NOT EXISTS pseudonym_label TEXT NOT NULL DEFAULT '가명/재식별금지';

/* sql_id: v033_nba_actions_pseudonym_label */
ALTER TABLE nba_actions
    ADD COLUMN IF NOT EXISTS pseudonym_label TEXT NOT NULL DEFAULT '가명/재식별금지';

/* sql_id: v033_create_data_purge_schedules */
CREATE TABLE IF NOT EXISTS data_purge_schedules (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    target_table TEXT        NOT NULL,
    target_row_id UUID       NOT NULL,
    purge_due_at TIMESTAMPTZ NOT NULL,
    executed_at  TIMESTAMPTZ NULL,
    purge_reason TEXT        NOT NULL
);

/* sql_id: v033_data_purge_schedules_comment */
COMMENT ON TABLE data_purge_schedules IS
    'REG-01 신용정보법 §20-2 파기 schedule placeholder. '
    'purge_due_at = 상거래 종료일 + 5년. '
    'executed_at NULL = 미실행(Stage 7 runbook 실행 범위). PoC 합성 데이터 전용.';

/* sql_id: v033_seed_purge_action_code */
INSERT INTO audit_action_codes (action_code, description) VALUES
    ('credit_info_purge_simulated',
     'REG-01 신용정보법 §20-2: purge schedule recorded (Stage 7 runbook executes actual deletion)')
ON CONFLICT (action_code) DO NOTHING;
