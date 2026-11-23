/* sql_id: drop_syn_prefix_check_if_exists */
ALTER TABLE customers DROP CONSTRAINT IF EXISTS chk_customer_no_syn_prefix;

/* sql_id: add_syn_prefix_check */
-- T310: synthetic customer enforcement (REG-06 §8) — every customer_no must start with SYN-
-- prefix so accidental seeding of non-synthetic identifiers fails at the database level.
ALTER TABLE customers ADD CONSTRAINT chk_customer_no_syn_prefix
    CHECK (customer_no LIKE 'SYN-%');
