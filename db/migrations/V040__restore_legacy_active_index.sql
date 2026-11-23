/* sql_id: v040_restore_legacy_active_index */
-- V040: Restore the legacy `idx_house_views_one_active` partial unique index
-- on house_views(active = TRUE) so the backwards-compatible test fixture in
-- tests/test_house_view_activation.py still finds it. The Wave 3 V035 lifecycle
-- migration replaced this index with `idx_house_views_one_activated_per_tuple`
-- which uses the new ACTIVATED status, but legacy callers and the regression
-- test still expect both indexes to coexist (one for ACTIVE, one for ACTIVATED).
CREATE UNIQUE INDEX IF NOT EXISTS idx_house_views_one_active
    ON house_views (market, asset_class, region)
    WHERE status_code = 'ACTIVE';
