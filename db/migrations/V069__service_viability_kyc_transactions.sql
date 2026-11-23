/* sql_id: kyc_transactions_v069 */
-- V069: Service Viability Follow-up — synthetic KYC transactions fixture
-- (2026-05-24, follow-up cycle svc-follow-up-v1 Wave 3 D4 / F7)
--
-- Predecessor: V068 (cycle svc-via-audit-v1) — F7 finding documented that
--   HP1 KYC evaluate body sends recent_transactions:[] → no
--   transaction-dependent rule fires → kyc_edd_triggered audit row 0건.
-- Plan SoT: .omc/plans/ralplan-wmah-follow-up-v1.md §3.3 Wave 3 D4.
--
-- Purpose: provide a single source of truth for synthetic per-customer
-- transaction rows so that:
--   (a) HP1 audit script SELECTs the canonical column list FROM
--       synthetic_customer_transactions WHERE customer_id = ... and passes
--       the result as recent_transactions[] to POST /kyc-edd/evaluate,
--       fulfilling F7 acceptance criterion (>=1 kyc_edd_triggered audit row
--       per HP1 KYC step).
--   (b) Future frontend can fetch via /customers/{id}/transactions when
--       that endpoint is added (out of D4 scope).
--
-- Trigger-rule coverage (apps/api/harness/services/kyc_edd.py:28-142):
--   - ASSET_CHANGE_PCT (>30% within 90d): row 1003 — SYN-CUST-001 purchase
--     420,000,000 KRW (32.94% of total_assets_krw=1,275,000,000) at 60d ago.
--   - OVERSEAS_TRANSFER (>10,000 USD cumulative in 30d): row 1001 —
--     SYN-CUST-001 overseas transfer 15,000 USD at 25d ago.
--   - HIGH_RISK_PRODUCT (purchase of risk_grade 5-6 product): row 1002 —
--     SYN-CUST-001 PURCHASE product 444...411 (risk_level_code 5).
--   - SYN-CUST-002 rows 2001/2002 (OVERSEAS_TRANSFER 12,000 USD +
--     HIGH_RISK_PRODUCT product 444...412) for cross-customer scenarios.
--
-- Memory rules applied:
--   [[v-sql-sql-id-validator]]      — every statement starts with /* sql_id: ... */
--   [[on-conflict-id-for-mutable-content]] — DETERMINISTIC id + ON CONFLICT (id) DO NOTHING
--   [[lifecycle-bug-hunting-pattern]] — rows allow lifecycle transition via
--                                       deletion / status-style metadata (DELETE-able fixture)
--
-- Synthetic prefix discipline: customer_id all reference V067/V068
-- SYN- prefixed customers (V037 CHECK constraint guarantees synthetic only).
-- All transactions explicitly tagged via note column for diagnostic clarity.

/* sql_id: kyc_transactions_v069 */
-- ─── Table definition (idempotent) ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS synthetic_customer_transactions (
    id                  UUID                       PRIMARY KEY,
    customer_id         UUID                       NOT NULL REFERENCES customers(id),
    transaction_date    TIMESTAMP WITH TIME ZONE   NOT NULL,
    transaction_type    VARCHAR(40)                NOT NULL,
    amount_krw          NUMERIC(20, 2),
    amount_usd          NUMERIC(20, 2),
    product_id          UUID                       REFERENCES products(id),
    product_risk_grade  INTEGER,
    note                TEXT,
    created_at          TIMESTAMP WITH TIME ZONE   NOT NULL DEFAULT now(),
    CONSTRAINT chk_synthetic_txn_type CHECK (
        transaction_type IN (
            'PURCHASE', 'BUY', 'SUBSCRIBE',
            'OVERSEAS_TRANSFER', 'FOREIGN_REMITTANCE',
            'SALE', 'REDEEM', 'DEPOSIT', 'WITHDRAWAL'
        )
    ),
    CONSTRAINT chk_synthetic_txn_risk_grade CHECK (
        product_risk_grade IS NULL OR product_risk_grade BETWEEN 1 AND 6
    )
);

/* sql_id: kyc_transactions_v069 */
CREATE INDEX IF NOT EXISTS idx_syn_txn_customer_date
    ON synthetic_customer_transactions (customer_id, transaction_date DESC);

/* sql_id: kyc_transactions_v069 */
-- ─── Seed rows (SYN-CUST-001 — fires all 3 transaction-dependent rules) ─
-- 1001: OVERSEAS_TRANSFER 15,000 USD at 25d ago → OVERSEAS_TRANSFER trigger
-- 1002: PURCHASE risk-5 product → HIGH_RISK_PRODUCT trigger
-- 1003: PURCHASE 420,000,000 KRW at 60d ago → ASSET_CHANGE_PCT trigger
--       (1,275,000,000 baseline_assets × 30% = 382,500,000; 420M > threshold)
INSERT INTO synthetic_customer_transactions (
    id, customer_id, transaction_date, transaction_type,
    amount_krw, amount_usd, product_id, product_risk_grade, note
)
VALUES
    ('99999999-9999-9999-9999-990000001001',
     '33333333-3333-3333-3333-333333333301',
     now() - interval '25 day',
     'OVERSEAS_TRANSFER',
     19500000.00,  20000.00,  NULL, NULL,
     '[SYN] V069 SYN-CUST-001 OVERSEAS_TRANSFER → expect KYC trigger fire'),
    ('99999999-9999-9999-9999-990000001002',
     '33333333-3333-3333-3333-333333333301',
     now() - interval '45 day',
     'PURCHASE',
     100000000.00, NULL,
     '44444444-4444-4444-4444-444444444411', 5,
     '[SYN] V069 SYN-CUST-001 high-risk product purchase → HIGH_RISK_PRODUCT trigger'),
    ('99999999-9999-9999-9999-990000001003',
     '33333333-3333-3333-3333-333333333301',
     now() - interval '60 day',
     'PURCHASE',
     420000000.00, NULL,
     NULL, NULL,
     '[SYN] V069 SYN-CUST-001 large asset transition 420M KRW (32.94%) → ASSET_CHANGE_PCT trigger')
ON CONFLICT (id) DO NOTHING;

/* sql_id: kyc_transactions_v069 */
-- ─── Seed rows (SYN-CUST-002 — secondary scenario coverage) ────────────
INSERT INTO synthetic_customer_transactions (
    id, customer_id, transaction_date, transaction_type,
    amount_krw, amount_usd, product_id, product_risk_grade, note
)
VALUES
    ('99999999-9999-9999-9999-990000002001',
     '33333333-3333-3333-3333-333333333302',
     now() - interval '20 day',
     'OVERSEAS_TRANSFER',
     15600000.00,  16000.00,  NULL, NULL,
     '[SYN] V069 SYN-CUST-002 OVERSEAS_TRANSFER 16k USD → trigger fire'),
    ('99999999-9999-9999-9999-990000002002',
     '33333333-3333-3333-3333-333333333302',
     now() - interval '40 day',
     'PURCHASE',
     80000000.00,  NULL,
     '44444444-4444-4444-4444-444444444412', 5,
     '[SYN] V069 SYN-CUST-002 high-risk ELS purchase → HIGH_RISK_PRODUCT trigger')
ON CONFLICT (id) DO NOTHING;
