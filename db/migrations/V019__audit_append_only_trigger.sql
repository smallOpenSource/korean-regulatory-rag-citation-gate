/* sql_id: create_audit_no_truncate_fn */
CREATE OR REPLACE FUNCTION prevent_audit_log_truncate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs TRUNCATE denied (PoC append-only invariant)';
END;
$$;

/* sql_id: drop_audit_no_truncate_trigger */
DROP TRIGGER IF EXISTS trg_audit_logs_no_truncate ON audit_logs;

/* sql_id: create_audit_no_truncate_trigger */
CREATE TRIGGER trg_audit_logs_no_truncate
BEFORE TRUNCATE ON audit_logs
FOR EACH STATEMENT EXECUTE FUNCTION prevent_audit_log_truncate();

/* sql_id: audit_logs_revoke_public_mutation */
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC;

/* sql_id: audit_logs_grant_insert_app */
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'harness_app') THEN
        EXECUTE 'GRANT INSERT ON audit_logs TO harness_app';
    END IF;
END $$;

/* sql_id: audit_logs_grant_insert_batch */
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'harness_batch') THEN
        EXECUTE 'GRANT INSERT ON audit_logs TO harness_batch';
    END IF;
END $$;

/* sql_id: audit_logs_grant_select_audit */
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'harness_audit') THEN
        EXECUTE 'GRANT SELECT ON audit_logs TO harness_audit';
    END IF;
END $$;

/* sql_id: audit_logs_grant_select_admin */
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'harness_admin') THEN
        EXECUTE 'GRANT SELECT ON audit_logs TO harness_admin';
    END IF;
END $$;
