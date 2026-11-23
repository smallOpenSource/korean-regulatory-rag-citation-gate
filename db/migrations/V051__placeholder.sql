/* sql_id: v051_placeholder */
-- Placeholder migration for V051 numbering gap (V050 → V052 leap during
-- T-Stage rapid iteration). Restores ascending sequence required by
-- db/migrator.py:165-167 (discover_migrations) and
-- tests/test_sql_contracts.py::test_migration_versions_are_sequential.
-- No schema change: emits SELECT 1 to satisfy validate_statement contract.
SELECT 1;
