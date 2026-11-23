/* sql_id: v084_drop_employees_role_code_check */
ALTER TABLE employees DROP CONSTRAINT IF EXISTS employees_role_code_check;

/* sql_id: v084_add_employees_role_code_check_compliance_officer */
ALTER TABLE employees
    ADD CONSTRAINT employees_role_code_check
    CHECK (role_code IN ('PB', 'WM', 'BRANCH_MANAGER', 'ADMIN', 'AUDIT_VIEWER', 'COMPLIANCE_OFFICER'));
