/* sql_id: create_system_flags_table */
CREATE TABLE IF NOT EXISTS system_flags (
    flag_name TEXT PRIMARY KEY,
    flag_value JSONB NOT NULL,
    description TEXT,
    updated_by UUID REFERENCES employees(id),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    change_reason TEXT,
    ticket_id TEXT
);

/* sql_id: index_system_flags_updated_by */
CREATE INDEX IF NOT EXISTS idx_system_flags_updated_by ON system_flags(updated_by, updated_at DESC);

/* sql_id: seed_system_flags_demo_mode */
INSERT INTO system_flags (flag_name, flag_value, description) VALUES
    ('demo_mode', '{"enabled": false, "expires_at": null}'::jsonb, 'PoC_AUTO_APPROVAL demo gate; 8h auto-expire (ADR-004, REG-06)')
ON CONFLICT (flag_name) DO NOTHING;

/* sql_id: create_system_flags_update_trigger_fn */
CREATE OR REPLACE FUNCTION system_flags_require_admin_and_ticket()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.change_reason IS NULL OR LENGTH(NEW.change_reason) < 8 THEN
        RAISE EXCEPTION 'system_flags update requires change_reason (>=8 chars)';
    END IF;
    IF NEW.ticket_id IS NULL OR LENGTH(NEW.ticket_id) < 3 THEN
        RAISE EXCEPTION 'system_flags update requires ticket_id (>=3 chars)';
    END IF;
    IF NEW.updated_by IS NULL THEN
        RAISE EXCEPTION 'system_flags update requires updated_by';
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

/* sql_id: drop_system_flags_update_trigger */
DROP TRIGGER IF EXISTS trg_system_flags_admin_check ON system_flags;

/* sql_id: create_system_flags_update_trigger */
CREATE TRIGGER trg_system_flags_admin_check
BEFORE UPDATE ON system_flags
FOR EACH ROW EXECUTE FUNCTION system_flags_require_admin_and_ticket();
