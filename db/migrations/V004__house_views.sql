/* sql_id: create_house_views_table */
CREATE TABLE IF NOT EXISTS house_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_no INTEGER NOT NULL UNIQUE,
    period_code VARCHAR(30) NOT NULL,
    title VARCHAR(200) NOT NULL,
    status_code VARCHAR(30) NOT NULL CHECK (status_code IN ('DRAFT', 'PENDING_REVIEW', 'ACTIVE', 'SUPERSEDED', 'ARCHIVED')),
    summary TEXT NOT NULL,
    asset_views_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    model_portfolios_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    risks_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by_id UUID NOT NULL REFERENCES employees(id),
    activated_at TIMESTAMPTZ,
    superseded_at TIMESTAMPTZ,
    ai_generated_at TIMESTAMPTZ,
    ai_model_name VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_house_views_status */
CREATE INDEX IF NOT EXISTS idx_house_views_status ON house_views(status_code, created_at DESC);

/* sql_id: index_house_views_one_active */
CREATE UNIQUE INDEX IF NOT EXISTS idx_house_views_one_active ON house_views(status_code) WHERE status_code = 'ACTIVE';

/* sql_id: create_house_view_applications_table */
CREATE TABLE IF NOT EXISTS house_view_applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    house_view_id UUID NOT NULL REFERENCES house_views(id),
    consultation_id UUID,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

/* sql_id: index_house_view_applications_house_view */
CREATE INDEX IF NOT EXISTS idx_house_view_applications_house_view ON house_view_applications(house_view_id);
