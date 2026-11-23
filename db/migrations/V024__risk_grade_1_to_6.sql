/* sql_id: expand_customers_risk_grade_to_6 */
DO $$
BEGIN
    ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_risk_grade_code_check;
    ALTER TABLE customers
        ADD CONSTRAINT customers_risk_grade_code_check
        CHECK (risk_grade_code IN ('1', '2', '3', '4', '5', '6'));
END
$$;

/* sql_id: expand_risk_assessments_risk_grade_to_6 */
DO $$
BEGIN
    ALTER TABLE risk_assessments DROP CONSTRAINT IF EXISTS risk_assessments_risk_grade_code_check;
    ALTER TABLE risk_assessments
        ADD CONSTRAINT risk_assessments_risk_grade_code_check
        CHECK (risk_grade_code IN ('1', '2', '3', '4', '5', '6'));
END
$$;

/* sql_id: add_products_risk_grade_code */
ALTER TABLE products
    ADD COLUMN IF NOT EXISTS risk_grade_code VARCHAR(1)
        CHECK (risk_grade_code IN ('1', '2', '3', '4', '5', '6'));

/* sql_id: migrate_products_risk_grade_from_risk_level */
UPDATE products
    SET risk_grade_code = risk_level_code
    WHERE risk_grade_code IS NULL;

/* sql_id: add_products_volatility_meta */
ALTER TABLE products
    ADD COLUMN IF NOT EXISTS volatility_meta JSONB NOT NULL DEFAULT '{}';

/* sql_id: seed_products_volatility_meta_defaults */
-- Volatility meta schema: {exchange_rate_risk, credit_risk, liquidity_risk,
--                          market_risk, is_complex_product}
-- Default empty JSONB already applied; product-specific values are set by
-- the product data seeding pipeline (real market provider data).
-- High-complexity ELS/DLS products receive risk_grade_code '5' or '6'.
UPDATE products
    SET risk_grade_code = '5',
        volatility_meta = jsonb_build_object(
            'is_complex_product', true,
            'market_risk', 'HIGH',
            'credit_risk', 'MEDIUM',
            'liquidity_risk', 'HIGH',
            'exchange_rate_risk', 'LOW'
        )
    WHERE product_type_code = 'ELS_DLS'
      AND has_knock_in IS TRUE
      AND risk_grade_code < '5';
