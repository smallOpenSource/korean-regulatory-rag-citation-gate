/* sql_id: create_products_table */
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_code VARCHAR(60) NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    product_type_code VARCHAR(30) NOT NULL CHECK (product_type_code IN ('FUND', 'BOND', 'ELS_DLS', 'WRAP', 'TRUST', 'DEPOSIT')),
    risk_level_code VARCHAR(1) NOT NULL CHECK (risk_level_code IN ('1', '2', '3', '4', '5')),
    maturity_date DATE,
    has_knock_in BOOLEAN NOT NULL DEFAULT FALSE,
    knock_in_barrier_pct NUMERIC(8,4),
    issuer_name VARCHAR(160),
    fee_pct NUMERIC(8,4) CHECK (fee_pct IS NULL OR fee_pct >= 0),
    currency VARCHAR(10) NOT NULL DEFAULT 'KRW',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_products_type_risk */
CREATE INDEX IF NOT EXISTS idx_products_type_risk ON products(product_type_code, risk_level_code);

/* sql_id: create_portfolios_table */
CREATE TABLE IF NOT EXISTS portfolios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id),
    portfolio_name VARCHAR(120) NOT NULL,
    base_currency VARCHAR(10) NOT NULL DEFAULT 'KRW',
    valuation_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_portfolios_customer */
CREATE INDEX IF NOT EXISTS idx_portfolios_customer ON portfolios(customer_id);

/* sql_id: create_portfolio_holdings_table */
CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    portfolio_id UUID NOT NULL REFERENCES portfolios(id),
    product_id UUID NOT NULL REFERENCES products(id),
    quantity NUMERIC(20,6) NOT NULL CHECK (quantity >= 0),
    market_value_krw NUMERIC(20,2) NOT NULL CHECK (market_value_krw >= 0),
    weight_pct NUMERIC(8,4) NOT NULL CHECK (weight_pct >= 0),
    as_of_date DATE NOT NULL
);

/* sql_id: index_portfolio_holdings_portfolio */
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_portfolio ON portfolio_holdings(portfolio_id);
