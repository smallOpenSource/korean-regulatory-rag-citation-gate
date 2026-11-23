/* sql_id: create_market_prices_table */
CREATE TABLE IF NOT EXISTS market_prices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR(40) NOT NULL,
    source_code VARCHAR(30) NOT NULL CHECK (source_code IN ('BROKER', 'FDR', 'PYKRX', 'ECOS', 'DATA_GO_KR')),
    price_date DATE NOT NULL,
    open_price NUMERIC(20,4),
    high_price NUMERIC(20,4),
    low_price NUMERIC(20,4),
    close_price NUMERIC(20,4) NOT NULL,
    volume NUMERIC(24,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ticker, price_date, source_code)
);

/* sql_id: index_market_prices_ticker_date */
CREATE INDEX IF NOT EXISTS idx_market_prices_ticker_date ON market_prices(ticker, price_date DESC);

/* sql_id: create_financial_ratios_table */
CREATE TABLE IF NOT EXISTS financial_ratios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR(40) NOT NULL,
    source_code VARCHAR(30) NOT NULL,
    ratio_date DATE NOT NULL,
    per NUMERIC(20,6),
    pbr NUMERIC(20,6),
    roe NUMERIC(20,6),
    debt_ratio NUMERIC(20,6),
    eps NUMERIC(20,6),
    dividend_yield NUMERIC(20,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (ticker, ratio_date, source_code)
);

/* sql_id: index_financial_ratios_ticker_date */
CREATE INDEX IF NOT EXISTS idx_financial_ratios_ticker_date ON financial_ratios(ticker, ratio_date DESC);

/* sql_id: create_investor_flows_table */
CREATE TABLE IF NOT EXISTS investor_flows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fund_code VARCHAR(80) NOT NULL,
    fund_name VARCHAR(200) NOT NULL,
    fund_type_code VARCHAR(60) NOT NULL,
    flow_date DATE NOT NULL,
    net_flow_krw NUMERIC(20,2),
    aum_krw NUMERIC(20,2),
    source_code VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (fund_code, flow_date, source_code)
);

/* sql_id: index_investor_flows_fund_date */
CREATE INDEX IF NOT EXISTS idx_investor_flows_fund_date ON investor_flows(fund_code, flow_date DESC);

/* sql_id: create_macro_indicators_table */
CREATE TABLE IF NOT EXISTS macro_indicators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    indicator_code VARCHAR(80) NOT NULL,
    indicator_name VARCHAR(200) NOT NULL,
    reference_date DATE NOT NULL,
    value NUMERIC(24,8) NOT NULL,
    unit VARCHAR(40) NOT NULL,
    source_code VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (indicator_code, reference_date, source_code)
);

/* sql_id: index_macro_indicators_code_date */
CREATE INDEX IF NOT EXISTS idx_macro_indicators_code_date ON macro_indicators(indicator_code, reference_date DESC);

/* sql_id: create_raw_documents_table */
CREATE TABLE IF NOT EXISTS raw_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type_code VARCHAR(30) NOT NULL CHECK (source_type_code IN ('DART', 'REG_PAGE', 'RESEARCH', 'MANUAL', 'WEB_SEARCH')),
    source_url TEXT NOT NULL,
    content_hash VARCHAR(128) NOT NULL,
    raw_text TEXT,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_processed BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    UNIQUE (content_hash, source_url)
);

/* sql_id: index_raw_documents_processed */
CREATE INDEX IF NOT EXISTS idx_raw_documents_processed ON raw_documents(is_processed, collected_at);

/* sql_id: create_batch_job_logs_table */
CREATE TABLE IF NOT EXISTS batch_job_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name VARCHAR(120) NOT NULL,
    job_type_code VARCHAR(60) NOT NULL,
    status_code VARCHAR(30) NOT NULL CHECK (status_code IN ('RUNNING', 'DONE', 'FAILED', 'SKIPPED')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    rows_collected INTEGER NOT NULL DEFAULT 0 CHECK (rows_collected >= 0),
    rows_skipped INTEGER NOT NULL DEFAULT 0 CHECK (rows_skipped >= 0),
    rows_failed INTEGER NOT NULL DEFAULT 0 CHECK (rows_failed >= 0),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_batch_job_logs_name_created */
CREATE INDEX IF NOT EXISTS idx_batch_job_logs_name_created ON batch_job_logs(job_name, created_at DESC);

/* sql_id: index_batch_job_logs_status */
CREATE INDEX IF NOT EXISTS idx_batch_job_logs_status ON batch_job_logs(status_code, created_at DESC);
