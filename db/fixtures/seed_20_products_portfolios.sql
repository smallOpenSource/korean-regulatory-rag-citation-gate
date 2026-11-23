/* sql_id: seed_full_mvp_products */
WITH product_seed(id, product_code, product_name, product_type_code, risk_level_code, maturity_offset_days, has_knock_in, knock_in_barrier_pct, issuer_name, fee_pct, currency) AS (
    VALUES
        ('44444444-4444-4444-4444-444444444401'::uuid, 'SYN-FUND-001', '원화 유동성 관리 랩', 'WRAP', '1', NULL::integer, FALSE, NULL::numeric, '교육용자산운용', 0.2500::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444402'::uuid, 'SYN-ELS-001', '6개월 만기 정기예금', 'DEPOSIT', '1', 90, FALSE, NULL::numeric, '교육용은행', 0.0000::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444403'::uuid, 'SYN-BOND-001', '국공채 단기채권', 'BOND', '1', 180, FALSE, NULL::numeric, '교육용증권', 0.1200::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444404'::uuid, 'SYN-WRAP-001', '우량 회사채 인컴', 'BOND', '2', 360, FALSE, NULL::numeric, '교육용채권데스크', 0.1800::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444405'::uuid, 'SYN-TRUST-001', '배당주 혼합형 펀드', 'FUND', '3', NULL::integer, FALSE, NULL::numeric, '교육용자산운용', 0.7000::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444406'::uuid, 'SYN-DEP-001', '상속증여 현금흐름 신탁', 'TRUST', '2', 365, FALSE, NULL::numeric, '교육용신탁', 0.5500::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444407'::uuid, 'SYN-FUND-002', '멀티에셋 안정성장 랩', 'WRAP', '3', NULL::integer, FALSE, NULL::numeric, '교육용랩어드바이저리', 0.9000::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444408'::uuid, 'SYN-BOND-002', '글로벌 분산 성장 펀드', 'FUND', '4', NULL::integer, FALSE, NULL::numeric, '교육용글로벌운용', 1.0500::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444409'::uuid, 'SYN-ELS-002', '지수연계 스텝다운 ELS', 'ELS_DLS', '4', 25, TRUE, 55.0000::numeric, '교육용증권', 1.2000::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444410'::uuid, 'SYN-WRAP-002', '리츠·인프라 인컴 신탁', 'TRUST', '4', NULL::integer, FALSE, NULL::numeric, '교육용신탁', 0.6500::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444411'::uuid, 'SYN-TRUST-002', '테크 성장주 집중 랩', 'WRAP', '5', NULL::integer, FALSE, NULL::numeric, '교육용랩어드바이저리', 1.5000::numeric, 'KRW'),
        ('44444444-4444-4444-4444-444444444412'::uuid, 'SYN-DEP-002', '월지급식 고위험 ELS', 'ELS_DLS', '5', 730, TRUE, 45.0000::numeric, '교육용증권', 1.4500::numeric, 'KRW')
)
INSERT INTO products(
    id, product_code, product_name, product_type_code, risk_level_code, maturity_date,
    has_knock_in, knock_in_barrier_pct, issuer_name, fee_pct, currency
)
SELECT id, product_code, product_name, product_type_code, risk_level_code,
       CASE WHEN maturity_offset_days IS NULL THEN NULL ELSE current_date + maturity_offset_days END,
       has_knock_in, knock_in_barrier_pct, issuer_name, fee_pct, currency
FROM product_seed
ON CONFLICT (product_code) DO UPDATE SET
    product_name = EXCLUDED.product_name,
    product_type_code = EXCLUDED.product_type_code,
    risk_level_code = EXCLUDED.risk_level_code,
    maturity_date = EXCLUDED.maturity_date,
    has_knock_in = EXCLUDED.has_knock_in,
    knock_in_barrier_pct = EXCLUDED.knock_in_barrier_pct,
    issuer_name = EXCLUDED.issuer_name,
    fee_pct = EXCLUDED.fee_pct,
    currency = EXCLUDED.currency,
    is_active = TRUE;

/* sql_id: seed_full_mvp_product_underlyings */
WITH underlying_seed(product_code, ticker, underlying_role_code, weight_pct) AS (
    VALUES
        ('SYN-FUND-001', '005930', 'PRIMARY', 100.0000::numeric),
        ('SYN-BOND-001', '000660', 'PRIMARY', 100.0000::numeric),
        ('SYN-WRAP-001', '005930', 'PRIMARY', 100.0000::numeric),
        ('SYN-TRUST-001', '005380', 'PRIMARY', 100.0000::numeric),
        ('SYN-FUND-002', '035420', 'PRIMARY', 100.0000::numeric),
        ('SYN-BOND-002', '068270', 'PRIMARY', 100.0000::numeric),
        ('SYN-ELS-002', '005930', 'BASKET', 50.0000::numeric),
        ('SYN-ELS-002', '000660', 'BASKET', 50.0000::numeric),
        ('SYN-WRAP-002', '005380', 'PRIMARY', 100.0000::numeric),
        ('SYN-TRUST-002', '035420', 'PRIMARY', 100.0000::numeric),
        ('SYN-DEP-002', '005930', 'BASKET', 50.0000::numeric),
        ('SYN-DEP-002', '068270', 'BASKET', 50.0000::numeric)
)
INSERT INTO product_underlyings(product_id, security_id, underlying_role_code, weight_pct)
SELECT p.id, s.id, underlying_seed.underlying_role_code, underlying_seed.weight_pct
FROM underlying_seed
JOIN products p ON p.product_code = underlying_seed.product_code
JOIN securities s ON s.ticker = underlying_seed.ticker
ON CONFLICT (product_id, security_id, underlying_role_code) DO UPDATE SET
    weight_pct = EXCLUDED.weight_pct;

/* sql_id: seed_full_mvp_prune_legacy_minimal_holdings */
DELETE FROM portfolio_holdings
WHERE portfolio_id = '55555555-5555-5555-5555-555555555501'::uuid;

/* sql_id: seed_full_mvp_prune_legacy_minimal_portfolio */
DELETE FROM portfolios
WHERE id = '55555555-5555-5555-5555-555555555501'::uuid;

/* sql_id: seed_full_mvp_portfolios */
WITH portfolio_seed(portfolio_no, customer_id, id, portfolio_name) AS (
    SELECT series_no,
           c.id,
           ('55555555-5555-5555-5555-' || lpad((555555555300 + series_no)::text, 12, '0'))::uuid,
           CASE series_no
               WHEN 1 THEN '은퇴소득 방어형 현금흐름 포트폴리오'
               WHEN 2 THEN '채권 사다리 안정수익 포트폴리오'
               WHEN 3 THEN '배당·멀티에셋 균형성장 포트폴리오'
               WHEN 4 THEN '글로벌 성장·인컴 분산 포트폴리오'
               WHEN 5 THEN '테크 성장·ELS 위험점검 포트폴리오'
               WHEN 6 THEN '법인 유동성 초단기 방어 포트폴리오'
               WHEN 7 THEN '상속증여 유동성 보전 포트폴리오'
               WHEN 8 THEN '교육자금 중기 균형 포트폴리오'
               WHEN 9 THEN '해외분산 리밸런싱 성장 포트폴리오'
               WHEN 10 THEN '고위험 ELS 사후관리 포트폴리오'
               WHEN 11 THEN '현금성자산 방어형 포트폴리오'
               WHEN 12 THEN '절세채권 만기분산 포트폴리오'
               WHEN 13 THEN '배당형 균형수익 포트폴리오'
               WHEN 14 THEN '글로벌 인컴 성장 포트폴리오'
               WHEN 15 THEN '성장주 위성투자 점검 포트폴리오'
               WHEN 16 THEN '은퇴 현금흐름 보전 포트폴리오'
               WHEN 17 THEN '절세채권 사다리 포트폴리오'
               WHEN 18 THEN '균형성장 재점검 포트폴리오'
               WHEN 19 THEN '해외 ETF 리밸런싱 포트폴리오'
               ELSE '월지급 ELS 사후관리 포트폴리오'
           END
    FROM generate_series(1, 20) AS series(series_no)
    JOIN customers c ON c.id = ('33333333-3333-3333-3333-' || lpad((333333333300 + series_no)::text, 12, '0'))::uuid
)
INSERT INTO portfolios(id, customer_id, portfolio_name, base_currency, valuation_date)
SELECT id, customer_id, portfolio_name, 'KRW', current_date
FROM portfolio_seed
ON CONFLICT (id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    portfolio_name = EXCLUDED.portfolio_name,
    base_currency = EXCLUDED.base_currency,
    valuation_date = EXCLUDED.valuation_date,
    updated_at = now();

/* sql_id: seed_full_mvp_prune_obsolete_holdings */
WITH expected_holdings AS (
    SELECT ('56565656-5656-5656-5656-' || lpad((565656560000 + portfolio_no * 10 + holding_slot)::text, 12, '0'))::uuid AS id
    FROM generate_series(1, 20) AS portfolio(portfolio_no)
    CROSS JOIN generate_series(1, 3) AS holding(holding_slot)
), seed_portfolios AS (
    SELECT ('55555555-5555-5555-5555-' || lpad((555555555300 + portfolio_no)::text, 12, '0'))::uuid AS id
    FROM generate_series(1, 20) AS portfolio(portfolio_no)
)
DELETE FROM portfolio_holdings ph
USING seed_portfolios sp
WHERE ph.portfolio_id = sp.id
  AND NOT EXISTS (
      SELECT 1
      FROM expected_holdings eh
      WHERE eh.id = ph.id
  );

/* sql_id: seed_full_mvp_portfolio_holdings */
WITH holding_seed(portfolio_no, holding_slot) AS (
    SELECT portfolio_no, holding_slot
    FROM generate_series(1, 20) AS portfolio(portfolio_no)
    CROSS JOIN generate_series(1, 3) AS holding(holding_slot)
), holding_rows AS (
    SELECT
        ('56565656-5656-5656-5656-' || lpad((565656560000 + portfolio_no * 10 + holding_slot)::text, 12, '0'))::uuid AS id,
        ('55555555-5555-5555-5555-' || lpad((555555555300 + portfolio_no)::text, 12, '0'))::uuid AS portfolio_id,
        CASE c.risk_grade_code
            WHEN '1' THEN CASE holding_slot WHEN 1 THEN '44444444-4444-4444-4444-444444444402'::uuid WHEN 2 THEN '44444444-4444-4444-4444-444444444401'::uuid ELSE '44444444-4444-4444-4444-444444444403'::uuid END
            WHEN '2' THEN CASE holding_slot WHEN 1 THEN '44444444-4444-4444-4444-444444444404'::uuid WHEN 2 THEN '44444444-4444-4444-4444-444444444406'::uuid ELSE '44444444-4444-4444-4444-444444444401'::uuid END
            WHEN '3' THEN CASE holding_slot WHEN 1 THEN '44444444-4444-4444-4444-444444444407'::uuid WHEN 2 THEN '44444444-4444-4444-4444-444444444405'::uuid ELSE '44444444-4444-4444-4444-444444444404'::uuid END
            WHEN '4' THEN CASE holding_slot WHEN 1 THEN '44444444-4444-4444-4444-444444444408'::uuid WHEN 2 THEN '44444444-4444-4444-4444-444444444410'::uuid ELSE '44444444-4444-4444-4444-444444444409'::uuid END
            ELSE CASE holding_slot WHEN 1 THEN '44444444-4444-4444-4444-444444444411'::uuid WHEN 2 THEN '44444444-4444-4444-4444-444444444412'::uuid ELSE '44444444-4444-4444-4444-444444444408'::uuid END
        END AS product_id,
        CASE c.risk_grade_code
            WHEN '1' THEN CASE holding_slot WHEN 1 THEN 50.0000 WHEN 2 THEN 30.0000 ELSE 20.0000 END::numeric(8,4)
            WHEN '2' THEN CASE holding_slot WHEN 1 THEN 45.0000 WHEN 2 THEN 35.0000 ELSE 20.0000 END::numeric(8,4)
            WHEN '3' THEN CASE holding_slot WHEN 1 THEN 40.0000 WHEN 2 THEN 35.0000 ELSE 25.0000 END::numeric(8,4)
            WHEN '4' THEN CASE holding_slot WHEN 1 THEN 35.0000 WHEN 2 THEN 35.0000 ELSE 30.0000 END::numeric(8,4)
            ELSE CASE holding_slot WHEN 1 THEN 35.0000 WHEN 2 THEN 30.0000 ELSE 35.0000 END::numeric(8,4)
        END AS weight_pct,
        c.total_assets_krw
    FROM holding_seed
    JOIN customers c ON c.id = ('33333333-3333-3333-3333-' || lpad((333333333300 + portfolio_no)::text, 12, '0'))::uuid
)
INSERT INTO portfolio_holdings(id, portfolio_id, product_id, quantity, market_value_krw, weight_pct, as_of_date)
SELECT id,
       portfolio_id,
       product_id,
       round((total_assets_krw * weight_pct / 100.0) / 1000000.0, 6),
       round(total_assets_krw * weight_pct / 100.0, 2),
       weight_pct,
       current_date
FROM holding_rows
ON CONFLICT (id) DO UPDATE SET
    portfolio_id = EXCLUDED.portfolio_id,
    product_id = EXCLUDED.product_id,
    quantity = EXCLUDED.quantity,
    market_value_krw = EXCLUDED.market_value_krw,
    weight_pct = EXCLUDED.weight_pct,
    as_of_date = EXCLUDED.as_of_date;
