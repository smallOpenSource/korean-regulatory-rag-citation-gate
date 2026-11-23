/* sql_id: v029_kyc_edd_migration */
-- V029: KYC/EDD trigger table + reassessment tasks (T248)

/* sql_id: v029_create_kyc_edd_triggers_table */
CREATE TABLE IF NOT EXISTS kyc_edd_triggers (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id             UUID        NOT NULL REFERENCES customers(id),
    trigger_type            VARCHAR(30) NOT NULL
        CHECK (trigger_type IN ('ASSET_CHANGE_PCT', 'OVERSEAS_TRANSFER', 'PEP_FLAG', 'HIGH_RISK_PRODUCT')),
    trigger_value           JSONB       NOT NULL DEFAULT '{}',
    triggered_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    status                  VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'IN_PROGRESS', 'CLOSED')),
    reason_text             TEXT,
    reassessed_at           TIMESTAMPTZ,
    reassessor_employee_id  UUID        REFERENCES employees(id),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: v029_index_kyc_edd_customer */
CREATE INDEX IF NOT EXISTS idx_kyc_edd_customer
    ON kyc_edd_triggers (customer_id, status, triggered_at DESC);

/* sql_id: v029_index_kyc_edd_type_status */
CREATE INDEX IF NOT EXISTS idx_kyc_edd_type_status
    ON kyc_edd_triggers (trigger_type, status);
