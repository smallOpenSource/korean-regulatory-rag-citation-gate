/* sql_id: seed_branch */
INSERT INTO branches(id, branch_code, branch_name, region_code)
VALUES ('11111111-1111-1111-1111-111111111111', 'SYN-GANGNAM', 'SYN 강남센터', 'SEOUL')
ON CONFLICT (branch_code) DO UPDATE SET
    branch_name = EXCLUDED.branch_name,
    region_code = EXCLUDED.region_code;

/* sql_id: seed_employees */
INSERT INTO employees(id, employee_no, name, role_code, branch_id, email, password_hash)
VALUES
    ('22222222-2222-2222-2222-222222222201', 'SYN-PB-001', '김하준 PB', 'PB', '11111111-1111-1111-1111-111111111111', 'synthetic.pb1@example.invalid', 'pbkdf2_sha256$210000$aGFybmVzcy1zeW50aGV0aWMtbG9naW4tdjE$TnRigzGjhHIQulN42spefAn-WD52ORQD3cVOArd2-sc'),
    ('22222222-2222-2222-2222-222222222202', 'SYN-WM-001', '이서연 WM', 'WM', '11111111-1111-1111-1111-111111111111', 'synthetic.wm1@example.invalid', 'pbkdf2_sha256$210000$aGFybmVzcy1zeW50aGV0aWMtbG9naW4tdjE$TnRigzGjhHIQulN42spefAn-WD52ORQD3cVOArd2-sc'),
    ('22222222-2222-2222-2222-222222222203', 'SYN-ADMIN-001', '박도윤 관리자', 'ADMIN', '11111111-1111-1111-1111-111111111111', 'synthetic.admin@example.invalid', 'pbkdf2_sha256$210000$aGFybmVzcy1zeW50aGV0aWMtbG9naW4tdjE$TnRigzGjhHIQulN42spefAn-WD52ORQD3cVOArd2-sc')
ON CONFLICT (employee_no) DO UPDATE SET
    name = EXCLUDED.name,
    role_code = EXCLUDED.role_code,
    branch_id = EXCLUDED.branch_id,
    email = EXCLUDED.email,
    password_hash = EXCLUDED.password_hash,
    is_active = TRUE;

/* sql_id: seed_customers */
INSERT INTO customers(id, customer_no, customer_name, assigned_pb_id, branch_id, risk_grade_code, segment_code, total_assets_krw, last_contacted_at)
VALUES
    ('33333333-3333-3333-3333-333333333301', 'SYN-CUST-001', '강남 배당·멀티에셋 균형성장', '22222222-2222-2222-2222-222222222201', '11111111-1111-1111-1111-111111111111', '3', 'HNWI_CORE', 2500000000.00, now() - interval '15 days'),
    ('33333333-3333-3333-3333-333333333302', 'SYN-CUST-002', '강남 글로벌분산 성장 자산관리', '22222222-2222-2222-2222-222222222201', '11111111-1111-1111-1111-111111111111', '4', 'HNWI_ULTRA', 8700000000.00, now() - interval '40 days')
ON CONFLICT (customer_no) DO UPDATE SET
    customer_name = EXCLUDED.customer_name,
    assigned_pb_id = EXCLUDED.assigned_pb_id,
    branch_id = EXCLUDED.branch_id,
    risk_grade_code = EXCLUDED.risk_grade_code,
    segment_code = EXCLUDED.segment_code,
    total_assets_krw = EXCLUDED.total_assets_krw,
    last_contacted_at = EXCLUDED.last_contacted_at,
    is_active = TRUE,
    updated_at = now();

/* sql_id: seed_products */
INSERT INTO products(id, product_code, product_name, product_type_code, risk_level_code, maturity_date, has_knock_in, knock_in_barrier_pct, issuer_name, fee_pct, currency)
VALUES
    ('44444444-4444-4444-4444-444444444401', 'SYN-FUND-001', '배당주 혼합형 펀드', 'FUND', '3', NULL, FALSE, NULL, '교육용자산운용', 0.8500, 'KRW'),
    ('44444444-4444-4444-4444-444444444402', 'SYN-ELS-001', '지수연계 스텝다운 ELS', 'ELS_DLS', '4', current_date + 25, TRUE, 55.0000, '교육용증권', 1.2000, 'KRW')
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

/* sql_id: seed_portfolio */
INSERT INTO portfolios(id, customer_id, portfolio_name, base_currency, valuation_date)
VALUES ('55555555-5555-5555-5555-555555555501', '33333333-3333-3333-3333-333333333301', '배당·멀티에셋 균형성장 포트폴리오', 'KRW', current_date)
ON CONFLICT (id) DO UPDATE SET
    customer_id = EXCLUDED.customer_id,
    portfolio_name = EXCLUDED.portfolio_name,
    base_currency = EXCLUDED.base_currency,
    valuation_date = EXCLUDED.valuation_date,
    updated_at = now();

/* sql_id: seed_portfolio_holdings */
INSERT INTO portfolio_holdings(id, portfolio_id, product_id, quantity, market_value_krw, weight_pct, as_of_date)
VALUES
    ('56565656-5656-5656-5656-565656565501', '55555555-5555-5555-5555-555555555501', '44444444-4444-4444-4444-444444444401', 1500.000000, 1500000000.00, 60.0000, current_date),
    ('56565656-5656-5656-5656-565656565502', '55555555-5555-5555-5555-555555555501', '44444444-4444-4444-4444-444444444402', 1000.000000, 1000000000.00, 40.0000, current_date)
ON CONFLICT (id) DO UPDATE SET
    portfolio_id = EXCLUDED.portfolio_id,
    product_id = EXCLUDED.product_id,
    quantity = EXCLUDED.quantity,
    market_value_krw = EXCLUDED.market_value_krw,
    weight_pct = EXCLUDED.weight_pct,
    as_of_date = EXCLUDED.as_of_date;
