-- db/setup/roles.sql
-- REG-05 T290 / ADR-006 / SEC-04 — Harness PoC RBAC role provisioning.
--
-- NOT a migration. Run manually by a DBA (superuser) once per environment:
--
--     psql "$DATABASE_URL_SUPERUSER" \
--         -v HARNESS_APP_PWD="$HARNESS_APP_PWD" \
--         -v HARNESS_BATCH_PWD="$HARNESS_BATCH_PWD" \
--         -v HARNESS_AUDIT_PWD="$HARNESS_AUDIT_PWD" \
--         -v HARNESS_ADMIN_PWD="$HARNESS_ADMIN_PWD" \
--         -f db/setup/roles.sql
--
-- Idempotent — re-running only updates passwords / connection limits.
-- The 4 roles created here are the GRANT targets in V019; the migration
-- itself wraps GRANT in pg_roles existence checks so it stays green even
-- if this file has not been applied yet.
--
-- Cross-refs: ADR-006 (audit append-only), RUN-05 (PG hardening), SEC-04.

\set ON_ERROR_STOP on

/* sql_id: setup_create_harness_app */
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'harness_app') THEN
        EXECUTE format('CREATE ROLE harness_app LOGIN NOINHERIT PASSWORD %L', :'HARNESS_APP_PWD');
    ELSE
        EXECUTE format('ALTER ROLE harness_app WITH LOGIN NOINHERIT PASSWORD %L', :'HARNESS_APP_PWD');
    END IF;
END $$;

/* sql_id: setup_create_harness_batch */
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'harness_batch') THEN
        EXECUTE format('CREATE ROLE harness_batch LOGIN NOINHERIT PASSWORD %L', :'HARNESS_BATCH_PWD');
    ELSE
        EXECUTE format('ALTER ROLE harness_batch WITH LOGIN NOINHERIT PASSWORD %L', :'HARNESS_BATCH_PWD');
    END IF;
END $$;

/* sql_id: setup_create_harness_audit */
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'harness_audit') THEN
        EXECUTE format('CREATE ROLE harness_audit LOGIN NOINHERIT PASSWORD %L', :'HARNESS_AUDIT_PWD');
    ELSE
        EXECUTE format('ALTER ROLE harness_audit WITH LOGIN NOINHERIT PASSWORD %L', :'HARNESS_AUDIT_PWD');
    END IF;
END $$;

/* sql_id: setup_create_harness_admin */
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'harness_admin') THEN
        EXECUTE format('CREATE ROLE harness_admin LOGIN NOINHERIT CREATEROLE PASSWORD %L', :'HARNESS_ADMIN_PWD');
    ELSE
        EXECUTE format('ALTER ROLE harness_admin WITH LOGIN NOINHERIT CREATEROLE PASSWORD %L', :'HARNESS_ADMIN_PWD');
    END IF;
END $$;

/* sql_id: setup_connection_limits */
ALTER ROLE harness_app    CONNECTION LIMIT 50;
ALTER ROLE harness_batch  CONNECTION LIMIT 10;
ALTER ROLE harness_audit  CONNECTION LIMIT 5;
ALTER ROLE harness_admin  CONNECTION LIMIT 2;

-- Default privileges so future tables get the right grants automatically.
-- audit_logs grants are owned by V019 — don't duplicate them here.

/* sql_id: setup_grant_db_connect */
DO $$
DECLARE
    db_name TEXT := current_database();
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO harness_app, harness_batch, harness_audit, harness_admin', db_name);
END $$;

/* sql_id: setup_grant_schema_usage */
GRANT USAGE ON SCHEMA public TO harness_app, harness_batch, harness_audit, harness_admin;

-- App / batch baseline: SELECT/INSERT/UPDATE/DELETE on existing app+batch tables (audit_logs is
-- handled exclusively by V019 — REVOKE then narrow GRANT).
/* sql_id: setup_grant_app_default */
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO harness_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO harness_app;

/* sql_id: setup_grant_batch_default */
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO harness_batch;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO harness_batch;

-- Audit role: read-only baseline (V019 narrows further on audit_logs).
/* sql_id: setup_grant_audit_default */
GRANT SELECT ON ALL TABLES IN SCHEMA public TO harness_audit;

-- Admin: read access; DDL via direct CREATE/ALTER privileges as table owner.
/* sql_id: setup_grant_admin_default */
GRANT SELECT ON ALL TABLES IN SCHEMA public TO harness_admin;

-- After V019 re-applies REVOKE UPDATE/DELETE/TRUNCATE on audit_logs FROM PUBLIC, the
-- broad GRANTs above are narrowed for audit_logs only. INSERT is preserved for app/batch,
-- and UPDATE/DELETE/TRUNCATE are not inheritable from PUBLIC because PUBLIC no longer has them.

/* sql_id: setup_revoke_public_audit_post */
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM harness_app, harness_batch, harness_audit, harness_admin;
GRANT INSERT ON audit_logs TO harness_app, harness_batch;
GRANT SELECT ON audit_logs TO harness_audit, harness_admin;
