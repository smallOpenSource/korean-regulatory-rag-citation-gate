/* sql_id: replace_market_price_bars_source_check */
DO $$
DECLARE
    constraint_record record;
BEGIN
    FOR constraint_record IN
        SELECT pg_constraint.conname
        FROM pg_constraint
        WHERE pg_constraint.conrelid = 'public.market_price_bars'::regclass
          AND pg_constraint.contype = 'c'
          AND pg_get_constraintdef(pg_constraint.oid) ILIKE '%source_code%'
          AND pg_get_constraintdef(pg_constraint.oid) ILIKE '%PYKRX%'
    LOOP
        EXECUTE format(
            'ALTER TABLE public.market_price_bars DROP CONSTRAINT IF EXISTS %I',
            constraint_record.conname
        );
    END LOOP;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE pg_constraint.conrelid = 'public.market_price_bars'::regclass
          AND pg_constraint.conname = 'chk_market_price_bars_source_code'
    ) THEN
        ALTER TABLE public.market_price_bars
            ADD CONSTRAINT chk_market_price_bars_source_code
            CHECK (source_code IN ('KRX', 'BROKER', 'DATA_GO_KR', 'PYKRX'));
    END IF;
END $$;

/* sql_id: update_krx_source_license_contract */
INSERT INTO source_licenses(source_code, source_name, license_status_code, terms_url, notes)
VALUES (
    'KRX',
    'Korea Exchange official OpenAPI/Data Marketplace',
    'ACTIVE',
    'https://data.krx.co.kr',
    'Official KRX OpenAPI source for domestic Korea listed equity daily trading rows; AUTH_KEY is supplied from KRX_API_KEY and never persisted.'
)
ON CONFLICT (source_code) DO UPDATE SET
    source_name = EXCLUDED.source_name,
    license_status_code = EXCLUDED.license_status_code,
    terms_url = EXCLUDED.terms_url,
    notes = EXCLUDED.notes;
