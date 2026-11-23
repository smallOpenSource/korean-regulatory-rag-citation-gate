/* sql_id: add_customer_display_name */
ALTER TABLE customers
ADD COLUMN IF NOT EXISTS customer_name VARCHAR(120);

/* sql_id: backfill_customer_display_name */
UPDATE customers
SET customer_name = customer_no
WHERE customer_name IS NULL;

/* sql_id: require_customer_display_name */
ALTER TABLE customers
ALTER COLUMN customer_name SET NOT NULL;

/* sql_id: index_customers_display_name */
CREATE INDEX IF NOT EXISTS idx_customers_customer_name ON customers(customer_name);
