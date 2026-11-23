/* sql_id: drop_securities_isin_kr7_constraint */
ALTER TABLE securities
    DROP CONSTRAINT IF EXISTS securities_isin_check;

/* sql_id: add_securities_isin_kr_constraint */
ALTER TABLE securities
    ADD CONSTRAINT securities_isin_check CHECK (isin ~ '^KR[0-9A-Z]{10}$');

/* sql_id: drop_security_identifiers_value_constraint */
ALTER TABLE security_identifiers
    DROP CONSTRAINT IF EXISTS security_identifiers_value_format;

/* sql_id: add_security_identifiers_value_constraint */
ALTER TABLE security_identifiers
    ADD CONSTRAINT security_identifiers_value_format CHECK (
        (identifier_type_code IN ('TICKER', 'KRX_SHORT_CODE') AND identifier_value ~ '^[0-9]{6}$')
        OR (identifier_type_code = 'ISIN' AND identifier_value ~ '^KR[0-9A-Z]{10}$')
    );

/* sql_id: drop_market_universe_candidates_isin_constraint */
ALTER TABLE market_universe_candidates
    DROP CONSTRAINT IF EXISTS market_universe_candidates_isin_check;

/* sql_id: add_market_universe_candidates_isin_constraint */
ALTER TABLE market_universe_candidates
    ADD CONSTRAINT market_universe_candidates_isin_check CHECK (
        isin IS NULL OR isin ~ '^KR[0-9A-Z]{10}$'
    );
