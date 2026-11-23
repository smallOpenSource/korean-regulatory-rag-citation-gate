/* sql_id: create_source_licenses_table */
CREATE TABLE IF NOT EXISTS source_licenses (
    source_code VARCHAR(30) PRIMARY KEY CHECK (source_code IN ('KRX', 'BROKER', 'DATA_GO_KR', 'PYKRX')),
    source_name VARCHAR(120) NOT NULL,
    license_status_code VARCHAR(30) NOT NULL CHECK (license_status_code IN ('ACTIVE', 'CONFIG_REQUIRED', 'DISABLED')),
    domestic_equity_only BOOLEAN NOT NULL DEFAULT TRUE CHECK (domestic_equity_only IS TRUE),
    terms_url TEXT,
    notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: seed_domestic_source_licenses */
INSERT INTO source_licenses(source_code, source_name, license_status_code, terms_url, notes)
VALUES
    ('KRX', 'Korea Exchange reference master', 'ACTIVE', 'https://kind.krx.co.kr', 'Reference-only domestic Korea listed equity master.'),
    ('BROKER', 'Brokerage read-only quote API', 'CONFIG_REQUIRED', 'urn:harness:source:broker-open-api', 'Runtime credentials required; domestic stock quotation only.'),
    ('DATA_GO_KR', 'Korea public data portal market endpoint', 'CONFIG_REQUIRED', 'https://www.data.go.kr', 'Endpoint and field mapping must be scoped to Korea listed equities.'),
    ('PYKRX', 'pykrx domestic market data library', 'DISABLED', 'https://github.com/sharebook-kr/pykrx', 'Reserved for Korea-only offline backfill when explicitly enabled.')
ON CONFLICT (source_code) DO UPDATE SET
    source_name = EXCLUDED.source_name,
    license_status_code = EXCLUDED.license_status_code,
    terms_url = EXCLUDED.terms_url,
    notes = EXCLUDED.notes,
    updated_at = now();

/* sql_id: create_securities_table */
CREATE TABLE IF NOT EXISTS securities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker VARCHAR(6) NOT NULL UNIQUE CHECK (ticker ~ '^[0-9]{6}$'),
    isin VARCHAR(12) NOT NULL UNIQUE CHECK (isin ~ '^KR[0-9A-Z]{10}$'),
    security_name_kr VARCHAR(160) NOT NULL,
    market_code VARCHAR(20) NOT NULL CHECK (market_code IN ('KOSPI', 'KOSDAQ', 'KONEX')),
    country_code CHAR(2) NOT NULL DEFAULT 'KR' CHECK (country_code = 'KR'),
    security_type_code VARCHAR(30) NOT NULL DEFAULT 'EQUITY' CHECK (security_type_code = 'EQUITY'),
    currency VARCHAR(10) NOT NULL DEFAULT 'KRW' CHECK (currency = 'KRW'),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    listed_at DATE,
    delisted_at DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT securities_domestic_active_dates CHECK (delisted_at IS NULL OR listed_at IS NULL OR delisted_at >= listed_at)
);

/* sql_id: index_securities_market_active */
CREATE INDEX IF NOT EXISTS idx_securities_market_active ON securities(market_code, is_active, ticker);

/* sql_id: seed_domestic_security_master */
INSERT INTO securities(id, ticker, isin, security_name_kr, market_code, listed_at)
VALUES
    ('77777777-7777-7777-7777-000000005930'::uuid, '005930', 'KR7005930003', '삼성전자', 'KOSPI', '1975-06-11'::date),
    ('77777777-7777-7777-7777-000000000660'::uuid, '000660', 'KR7000660001', 'SK하이닉스', 'KOSPI', '1996-12-26'::date),
    ('77777777-7777-7777-7777-000000035420'::uuid, '035420', 'KR7035420009', 'NAVER', 'KOSPI', '2008-11-28'::date),
    ('77777777-7777-7777-7777-000000005380'::uuid, '005380', 'KR7005380001', '현대차', 'KOSPI', '1974-06-28'::date),
    ('77777777-7777-7777-7777-000000068270'::uuid, '068270', 'KR7068270008', '셀트리온', 'KOSPI', '2018-02-09'::date)
ON CONFLICT (ticker) DO UPDATE SET
    isin = EXCLUDED.isin,
    security_name_kr = EXCLUDED.security_name_kr,
    market_code = EXCLUDED.market_code,
    country_code = 'KR',
    security_type_code = 'EQUITY',
    currency = 'KRW',
    is_active = TRUE,
    listed_at = EXCLUDED.listed_at,
    updated_at = now();

/* sql_id: create_security_identifiers_table */
CREATE TABLE IF NOT EXISTS security_identifiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES securities(id),
    identifier_type_code VARCHAR(30) NOT NULL CHECK (identifier_type_code IN ('TICKER', 'ISIN', 'KRX_SHORT_CODE')),
    identifier_value VARCHAR(40) NOT NULL,
    source_code VARCHAR(30) NOT NULL REFERENCES source_licenses(source_code),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    valid_from DATE NOT NULL DEFAULT current_date,
    valid_to DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT security_identifiers_value_format CHECK (
        (identifier_type_code IN ('TICKER', 'KRX_SHORT_CODE') AND identifier_value ~ '^[0-9]{6}$')
        OR (identifier_type_code = 'ISIN' AND identifier_value ~ '^KR[0-9A-Z]{10}$')
    ),
    CONSTRAINT security_identifiers_valid_dates CHECK (valid_to IS NULL OR valid_to >= valid_from),
    UNIQUE (identifier_type_code, identifier_value, source_code)
);

/* sql_id: index_security_identifiers_security */
CREATE INDEX IF NOT EXISTS idx_security_identifiers_security ON security_identifiers(security_id, identifier_type_code);

/* sql_id: seed_domestic_security_identifiers */
WITH seeded_security AS (
    SELECT id, ticker, isin
    FROM securities
    WHERE ticker IN ('005930', '000660', '035420', '005380', '068270')
), identifier_seed AS (
    SELECT id AS security_id, 'TICKER'::varchar AS identifier_type_code, ticker AS identifier_value, TRUE AS is_primary
    FROM seeded_security
    UNION ALL
    SELECT id AS security_id, 'KRX_SHORT_CODE'::varchar AS identifier_type_code, ticker AS identifier_value, FALSE AS is_primary
    FROM seeded_security
    UNION ALL
    SELECT id AS security_id, 'ISIN'::varchar AS identifier_type_code, isin AS identifier_value, TRUE AS is_primary
    FROM seeded_security
)
INSERT INTO security_identifiers(security_id, identifier_type_code, identifier_value, source_code, is_primary)
SELECT security_id, identifier_type_code, identifier_value, 'KRX', is_primary
FROM identifier_seed
ON CONFLICT (identifier_type_code, identifier_value, source_code) DO UPDATE SET
    security_id = EXCLUDED.security_id,
    is_primary = EXCLUDED.is_primary;

/* sql_id: create_product_underlyings_table */
CREATE TABLE IF NOT EXISTS product_underlyings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id),
    security_id UUID NOT NULL REFERENCES securities(id),
    underlying_role_code VARCHAR(30) NOT NULL DEFAULT 'PRIMARY' CHECK (underlying_role_code IN ('PRIMARY', 'BASKET', 'HEDGE')),
    weight_pct NUMERIC(8,4) CHECK (weight_pct IS NULL OR (weight_pct >= 0 AND weight_pct <= 100)),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (product_id, security_id, underlying_role_code)
);

/* sql_id: index_product_underlyings_security */
CREATE INDEX IF NOT EXISTS idx_product_underlyings_security ON product_underlyings(security_id, product_id);

/* sql_id: create_trading_calendar_table */
CREATE TABLE IF NOT EXISTS trading_calendar (
    market_code VARCHAR(20) NOT NULL CHECK (market_code IN ('KOSPI', 'KOSDAQ', 'KONEX')),
    calendar_date DATE NOT NULL,
    is_trading_day BOOLEAN NOT NULL,
    holiday_name VARCHAR(120),
    source_code VARCHAR(30) NOT NULL REFERENCES source_licenses(source_code),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (market_code, calendar_date),
    CONSTRAINT trading_calendar_holiday_name CHECK (is_trading_day IS TRUE OR holiday_name IS NOT NULL)
);

/* sql_id: index_trading_calendar_date */
CREATE INDEX IF NOT EXISTS idx_trading_calendar_date ON trading_calendar(calendar_date, is_trading_day);

/* sql_id: create_market_data_evidence_table */
CREATE TABLE IF NOT EXISTS market_data_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_code VARCHAR(30) NOT NULL REFERENCES source_licenses(source_code),
    evidence_type_code VARCHAR(30) NOT NULL CHECK (evidence_type_code IN ('RAW_PAYLOAD', 'API_RESPONSE', 'BACKFILL', 'RECONCILIATION', 'QUALITY_CHECK')),
    provider_reference TEXT,
    payload_hash VARCHAR(128) NOT NULL,
    source_as_of TIMESTAMPTZ NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source_code, evidence_type_code, payload_hash)
);

/* sql_id: index_market_data_evidence_source */
CREATE INDEX IF NOT EXISTS idx_market_data_evidence_source ON market_data_evidence(source_code, source_as_of DESC);

/* sql_id: create_market_price_bars_table */
CREATE TABLE IF NOT EXISTS market_price_bars (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES securities(id),
    source_code VARCHAR(30) NOT NULL REFERENCES source_licenses(source_code) CHECK (source_code IN ('BROKER', 'DATA_GO_KR', 'PYKRX')),
    price_date DATE NOT NULL,
    timeframe_code VARCHAR(10) NOT NULL DEFAULT '1D' CHECK (timeframe_code = '1D'),
    open_price NUMERIC(20,4) CHECK (open_price IS NULL OR open_price > 0),
    high_price NUMERIC(20,4) CHECK (high_price IS NULL OR high_price > 0),
    low_price NUMERIC(20,4) CHECK (low_price IS NULL OR low_price > 0),
    close_price NUMERIC(20,4) NOT NULL CHECK (close_price > 0),
    adjusted_close_price NUMERIC(20,4) CHECK (adjusted_close_price IS NULL OR adjusted_close_price > 0),
    volume NUMERIC(24,4) CHECK (volume IS NULL OR volume >= 0),
    source_as_of TIMESTAMPTZ NOT NULL,
    evidence_id UUID REFERENCES market_data_evidence(id),
    quality_status_code VARCHAR(30) NOT NULL DEFAULT 'RAW' CHECK (quality_status_code IN ('RAW', 'VALID', 'WARN', 'REJECTED', 'RECONCILED')),
    quality_message TEXT,
    is_synthetic BOOLEAN NOT NULL DEFAULT FALSE CHECK (is_synthetic IS FALSE),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT market_price_bars_ohlc_range CHECK (
        high_price IS NULL
        OR low_price IS NULL
        OR high_price >= low_price
    ),
    CONSTRAINT market_price_bars_close_range CHECK (
        high_price IS NULL
        OR low_price IS NULL
        OR (close_price <= high_price AND close_price >= low_price)
    ),
    UNIQUE (security_id, price_date, source_code, timeframe_code)
);

/* sql_id: index_market_price_bars_security_date */
CREATE INDEX IF NOT EXISTS idx_market_price_bars_security_date ON market_price_bars(security_id, price_date DESC);

/* sql_id: index_market_price_bars_source_asof */
CREATE INDEX IF NOT EXISTS idx_market_price_bars_source_asof ON market_price_bars(source_code, source_as_of DESC);

/* sql_id: backfill_price_bars_from_legacy */
INSERT INTO market_price_bars(
    security_id, source_code, price_date, open_price, high_price, low_price, close_price,
    adjusted_close_price, volume, source_as_of, quality_status_code, quality_message
)
SELECT s.id, mp.source_code, mp.price_date, mp.open_price, mp.high_price, mp.low_price,
       mp.close_price, mp.close_price, mp.volume, mp.created_at, 'RAW',
       'Backfilled from deprecated market_prices before legacy write guard activation.'
FROM market_prices mp
JOIN securities s ON s.ticker = mp.ticker
WHERE mp.source_code IN ('BROKER', 'DATA_GO_KR', 'PYKRX')
  AND s.country_code = 'KR'
  AND s.security_type_code = 'EQUITY'
  AND s.currency = 'KRW'
ON CONFLICT (security_id, price_date, source_code, timeframe_code) DO NOTHING;

/* sql_id: create_corporate_actions_table */
CREATE TABLE IF NOT EXISTS corporate_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    security_id UUID NOT NULL REFERENCES securities(id),
    source_code VARCHAR(30) NOT NULL REFERENCES source_licenses(source_code),
    action_type_code VARCHAR(30) NOT NULL CHECK (action_type_code IN ('DIVIDEND', 'SPLIT', 'MERGER', 'SPINOFF')),
    effective_date DATE NOT NULL,
    announced_at TIMESTAMPTZ,
    cash_amount_krw NUMERIC(20,4) CHECK (cash_amount_krw IS NULL OR cash_amount_krw >= 0),
    split_ratio NUMERIC(20,8) CHECK (split_ratio IS NULL OR split_ratio > 0),
    evidence_id UUID REFERENCES market_data_evidence(id),
    quality_status_code VARCHAR(30) NOT NULL DEFAULT 'RAW' CHECK (quality_status_code IN ('RAW', 'VALID', 'WARN', 'REJECTED', 'RECONCILED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (security_id, source_code, action_type_code, effective_date)
);

/* sql_id: index_corporate_actions_security_date */
CREATE INDEX IF NOT EXISTS idx_corporate_actions_security_date ON corporate_actions(security_id, effective_date DESC);

/* sql_id: create_market_data_quality_checks_table */
CREATE TABLE IF NOT EXISTS market_data_quality_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    check_code VARCHAR(80) NOT NULL,
    security_id UUID REFERENCES securities(id),
    source_code VARCHAR(30) REFERENCES source_licenses(source_code),
    price_date DATE,
    status_code VARCHAR(30) NOT NULL CHECK (status_code IN ('PASS', 'WARN', 'FAIL')),
    severity_code VARCHAR(30) NOT NULL CHECK (severity_code IN ('INFO', 'WARN', 'ERROR')),
    observed_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_id UUID REFERENCES market_data_evidence(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_market_quality_recent */
CREATE INDEX IF NOT EXISTS idx_market_quality_recent ON market_data_quality_checks(status_code, created_at DESC);

/* sql_id: create_legacy_market_prices_guard_fn */
CREATE OR REPLACE FUNCTION reject_legacy_market_prices_write()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'legacy market_prices is deprecated; write domestic Korea equity bars to market_price_bars';
END;
$$;

/* sql_id: drop_legacy_market_prices_guard */
DROP TRIGGER IF EXISTS trg_reject_legacy_market_prices_write ON market_prices;

/* sql_id: create_legacy_market_prices_guard */
CREATE TRIGGER trg_reject_legacy_market_prices_write
BEFORE INSERT OR UPDATE OR DELETE ON market_prices
FOR EACH ROW
EXECUTE FUNCTION reject_legacy_market_prices_write();
