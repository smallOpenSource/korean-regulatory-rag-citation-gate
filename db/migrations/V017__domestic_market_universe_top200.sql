/* sql_id: create_market_universe_snapshots_table */
CREATE TABLE IF NOT EXISTS market_universe_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    universe_code VARCHAR(80) NOT NULL CHECK (universe_code <> ''),
    as_of_date DATE NOT NULL,
    resolved_trading_date DATE NOT NULL,
    source_code VARCHAR(30) NOT NULL REFERENCES source_licenses(source_code),
    source_policy_code VARCHAR(80) NOT NULL CHECK (source_policy_code <> ''),
    rank_method_code VARCHAR(80) NOT NULL DEFAULT 'MARKET_CAP_DESC' CHECK (rank_method_code <> ''),
    target_size INTEGER NOT NULL CHECK (target_size > 0),
    selected_count INTEGER NOT NULL DEFAULT 0 CHECK (selected_count >= 0),
    raw_candidate_count INTEGER NOT NULL DEFAULT 0 CHECK (raw_candidate_count >= 0),
    excluded_count INTEGER NOT NULL DEFAULT 0 CHECK (excluded_count >= 0),
    coverage_status_code VARCHAR(30) NOT NULL DEFAULT 'PENDING'
        CHECK (coverage_status_code IN ('PENDING', 'READY', 'DEGRADED', 'BLOCKED')),
    provider_evidence_id UUID REFERENCES batch_provider_evidence(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (universe_code, as_of_date, source_code, source_policy_code),
    CONSTRAINT market_universe_snapshots_counts CHECK (
        raw_candidate_count >= selected_count
        AND raw_candidate_count >= excluded_count
        AND selected_count <= target_size
    )
);

/* sql_id: create_market_universe_candidates_table */
CREATE TABLE IF NOT EXISTS market_universe_candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id UUID NOT NULL REFERENCES market_universe_snapshots(id) ON DELETE CASCADE,
    security_id UUID REFERENCES securities(id),
    ticker VARCHAR(6) NOT NULL CHECK (ticker ~ '^[0-9]{6}$'),
    isin VARCHAR(12) CHECK (isin IS NULL OR isin ~ '^KR[0-9A-Z]{10}$'),
    security_name_kr VARCHAR(160) NOT NULL CHECK (security_name_kr <> ''),
    market_code VARCHAR(20) NOT NULL CHECK (market_code IN ('KOSPI', 'KOSDAQ')),
    rank_before_filter INTEGER NOT NULL CHECK (rank_before_filter > 0),
    rank_after_filter INTEGER CHECK (rank_after_filter IS NULL OR rank_after_filter > 0),
    market_cap_krw NUMERIC(24,0) NOT NULL CHECK (market_cap_krw >= 0),
    listed_shares NUMERIC(24,0) CHECK (listed_shares IS NULL OR listed_shares >= 0),
    close_price NUMERIC(20,4) CHECK (close_price IS NULL OR close_price > 0),
    section_type_name VARCHAR(120),
    company_key VARCHAR(120) NOT NULL CHECK (company_key <> ''),
    company_key_source_code VARCHAR(40) NOT NULL CHECK (company_key_source_code <> ''),
    raw_payload_hash VARCHAR(128) NOT NULL CHECK (length(raw_payload_hash) >= 12),
    included BOOLEAN NOT NULL DEFAULT FALSE,
    exclusion_reason_code VARCHAR(80),
    provider_evidence_id UUID REFERENCES batch_provider_evidence(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, ticker),
    CONSTRAINT market_universe_candidates_inclusion_state CHECK (
        (included IS TRUE AND rank_after_filter IS NOT NULL AND exclusion_reason_code IS NULL)
        OR (included IS FALSE)
    )
);

/* sql_id: create_market_universe_members_table */
CREATE TABLE IF NOT EXISTS market_universe_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id UUID NOT NULL REFERENCES market_universe_snapshots(id) ON DELETE CASCADE,
    security_id UUID NOT NULL REFERENCES securities(id),
    ticker VARCHAR(6) NOT NULL CHECK (ticker ~ '^[0-9]{6}$'),
    company_key VARCHAR(120) NOT NULL CHECK (company_key <> ''),
    rank_no INTEGER NOT NULL CHECK (rank_no > 0),
    market_code VARCHAR(20) NOT NULL CHECK (market_code IN ('KOSPI', 'KOSDAQ')),
    market_cap_krw NUMERIC(24,0) NOT NULL CHECK (market_cap_krw >= 0),
    listed_shares NUMERIC(24,0) CHECK (listed_shares IS NULL OR listed_shares >= 0),
    close_price NUMERIC(20,4) CHECK (close_price IS NULL OR close_price > 0),
    included_reason_code VARCHAR(80) NOT NULL DEFAULT 'TOP_MARKET_CAP_COMMON_EQUITY',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, ticker),
    UNIQUE (snapshot_id, rank_no),
    UNIQUE (snapshot_id, security_id)
);

/* sql_id: create_market_trading_calendar_table */
CREATE TABLE IF NOT EXISTS market_trading_calendar (
    calendar_date DATE NOT NULL,
    market_code VARCHAR(20) NOT NULL CHECK (market_code IN ('KOSPI', 'KOSDAQ')),
    source_code VARCHAR(30) NOT NULL REFERENCES source_licenses(source_code),
    source_policy_code VARCHAR(80) NOT NULL CHECK (source_policy_code <> ''),
    is_expected_trading_day BOOLEAN NOT NULL,
    is_observed_trading_day BOOLEAN NOT NULL DEFAULT FALSE,
    no_trading_reason_code VARCHAR(80),
    batch_provider_evidence_id UUID REFERENCES batch_provider_evidence(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (market_code, calendar_date, source_code, source_policy_code),
    CONSTRAINT market_trading_calendar_reason CHECK (
        is_expected_trading_day IS TRUE OR no_trading_reason_code IS NOT NULL
    ),
    CONSTRAINT market_trading_calendar_observed_expected CHECK (
        is_observed_trading_day IS FALSE OR is_expected_trading_day IS TRUE
    )
);

/* sql_id: create_market_universe_coverage_daily_table */
CREATE TABLE IF NOT EXISTS market_universe_coverage_daily (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id UUID NOT NULL REFERENCES market_universe_snapshots(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES market_universe_members(id) ON DELETE CASCADE,
    security_id UUID NOT NULL REFERENCES securities(id),
    market_code VARCHAR(20) NOT NULL CHECK (market_code IN ('KOSPI', 'KOSDAQ')),
    calendar_date DATE NOT NULL,
    is_expected_trading_day BOOLEAN NOT NULL,
    has_valid_bar BOOLEAN NOT NULL DEFAULT FALSE,
    market_price_bar_id UUID REFERENCES market_price_bars(id) ON DELETE SET NULL,
    missing_reason_code VARCHAR(80),
    quality_status_code VARCHAR(30) NOT NULL DEFAULT 'MISSING'
        CHECK (quality_status_code IN ('RAW', 'VALID', 'WARN', 'REJECTED', 'RECONCILED', 'MISSING', 'NO_TRADING')),
    batch_provider_evidence_id UUID REFERENCES batch_provider_evidence(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (snapshot_id, member_id, calendar_date),
    CONSTRAINT market_universe_coverage_valid_bar_link CHECK (
        (has_valid_bar IS TRUE AND market_price_bar_id IS NOT NULL AND missing_reason_code IS NULL)
        OR (has_valid_bar IS FALSE)
    ),
    CONSTRAINT market_universe_coverage_expected_reason CHECK (
        is_expected_trading_day IS FALSE OR has_valid_bar IS TRUE OR missing_reason_code IS NOT NULL
    )
);

/* sql_id: add_market_price_bars_trading_value */
ALTER TABLE market_price_bars
    ADD COLUMN IF NOT EXISTS trading_value_krw NUMERIC(24,0)
        CHECK (trading_value_krw IS NULL OR trading_value_krw >= 0);

/* sql_id: add_market_price_bars_market_cap */
ALTER TABLE market_price_bars
    ADD COLUMN IF NOT EXISTS market_cap_krw NUMERIC(24,0)
        CHECK (market_cap_krw IS NULL OR market_cap_krw >= 0);

/* sql_id: add_market_price_bars_listed_shares */
ALTER TABLE market_price_bars
    ADD COLUMN IF NOT EXISTS listed_shares NUMERIC(24,0)
        CHECK (listed_shares IS NULL OR listed_shares >= 0);

/* sql_id: add_market_price_bars_change_price */
ALTER TABLE market_price_bars
    ADD COLUMN IF NOT EXISTS change_price NUMERIC(20,4);

/* sql_id: add_market_price_bars_change_rate_pct */
ALTER TABLE market_price_bars
    ADD COLUMN IF NOT EXISTS change_rate_pct NUMERIC(12,6);

/* sql_id: index_market_universe_snapshots_code_asof */
CREATE INDEX IF NOT EXISTS idx_market_universe_snapshots_code_asof
    ON market_universe_snapshots(universe_code, as_of_date DESC);

/* sql_id: index_market_universe_candidates_snapshot_rank */
CREATE INDEX IF NOT EXISTS idx_market_universe_candidates_snapshot_rank
    ON market_universe_candidates(snapshot_id, rank_before_filter);

/* sql_id: index_market_universe_members_snapshot_rank */
CREATE INDEX IF NOT EXISTS idx_market_universe_members_snapshot_rank
    ON market_universe_members(snapshot_id, rank_no);

/* sql_id: index_market_trading_calendar_market_date */
CREATE INDEX IF NOT EXISTS idx_market_trading_calendar_market_date
    ON market_trading_calendar(market_code, calendar_date);

/* sql_id: index_market_universe_coverage_snapshot_date */
CREATE INDEX IF NOT EXISTS idx_market_universe_coverage_snapshot_date
    ON market_universe_coverage_daily(snapshot_id, calendar_date, has_valid_bar);

/* sql_id: index_market_price_bars_security_date_source */
CREATE INDEX IF NOT EXISTS idx_market_price_bars_security_date_source
    ON market_price_bars(security_id, price_date DESC, source_code);
