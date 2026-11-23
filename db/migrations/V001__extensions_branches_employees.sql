/* sql_id: require_postgres17 */
DO $$
BEGIN
    IF current_setting('server_version_num')::INTEGER < 170000 THEN
        RAISE EXCEPTION 'Harness requires PostgreSQL 17 or newer';
    END IF;
END
$$;

/* sql_id: create_pgcrypto_extension */
CREATE EXTENSION IF NOT EXISTS pgcrypto;

/* sql_id: create_vector_extension */
CREATE EXTENSION IF NOT EXISTS vector;

/* sql_id: create_branches_table */
CREATE TABLE IF NOT EXISTS branches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_code VARCHAR(30) NOT NULL UNIQUE,
    branch_name VARCHAR(120) NOT NULL,
    region_code VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: create_employees_table */
CREATE TABLE IF NOT EXISTS employees (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_no VARCHAR(40) NOT NULL UNIQUE,
    name VARCHAR(120) NOT NULL,
    role_code VARCHAR(30) NOT NULL CHECK (role_code IN ('PB', 'WM', 'BRANCH_MANAGER', 'ADMIN', 'AUDIT_VIEWER')),
    branch_id UUID REFERENCES branches(id),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_employees_branch */
CREATE INDEX IF NOT EXISTS idx_employees_branch ON employees(branch_id);

/* sql_id: index_employees_role */
CREATE INDEX IF NOT EXISTS idx_employees_role ON employees(role_code);
