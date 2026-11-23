/* sql_id: v035_house_view_lifecycle_migration */
-- V035: Extend house_views for T16 lifecycle (DRAFT→GENERATED→REVIEWED→ACTIVATED→ARCHIVED)
-- Adds market/asset_class/region partitioning + generation metadata columns.

-- 1. Add market-tuple columns for per-(market, asset_class, region) uniqueness
ALTER TABLE house_views
    ADD COLUMN IF NOT EXISTS market       VARCHAR(60),
    ADD COLUMN IF NOT EXISTS asset_class  VARCHAR(60),
    ADD COLUMN IF NOT EXISTS region       VARCHAR(60);

/* sql_id: v024_add_gen_metadata_columns */
-- 2. Add generation metadata columns
ALTER TABLE house_views
    ADD COLUMN IF NOT EXISTS prompt_tokens      INTEGER,
    ADD COLUMN IF NOT EXISTS completion_tokens  INTEGER,
    ADD COLUMN IF NOT EXISTS inputs_hash        VARCHAR(64);

/* sql_id: v024_drop_old_status_check */
-- 3. Drop existing CHECK constraint (inline auto-name) and widen allowed states
ALTER TABLE house_views DROP CONSTRAINT IF EXISTS house_views_status_code_check;

/* sql_id: v024_add_new_status_check */
ALTER TABLE house_views ADD CONSTRAINT house_views_status_code_check_v2
    CHECK (status_code IN (
        'DRAFT', 'PENDING_REVIEW', 'ACTIVE', 'SUPERSEDED',   -- legacy states kept for existing rows
        'GENERATED', 'REVIEWED', 'ACTIVATED', 'ARCHIVED'      -- T16 lifecycle states
    ));

/* sql_id: v024_drop_old_one_active_index */
-- 4. Drop global one-active index; replace with per-(market, asset_class, region) uniqueness
DROP INDEX IF EXISTS idx_house_views_one_active;

/* sql_id: v024_one_activated_per_tuple */
-- Partial unique: at most one ACTIVATED view per (market, asset_class, region).
-- NULLs are allowed (not enforced) for legacy/global views.
CREATE UNIQUE INDEX IF NOT EXISTS idx_house_views_one_activated_per_tuple
    ON house_views (market, asset_class, region)
    WHERE status_code = 'ACTIVATED' AND market IS NOT NULL;

/* sql_id: v024_index_house_views_lifecycle */
CREATE INDEX IF NOT EXISTS idx_house_views_lifecycle
    ON house_views (status_code, market, asset_class, region, version_no DESC);
