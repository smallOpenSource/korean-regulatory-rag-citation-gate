/* sql_id: house_view_faithfulness */
-- P2-3: the house_view AI body (summary / asset_views / risks) is shown to
-- bankers as a market view, but unlike the portfolio/briefing/nba dispatchers it
-- carried no faithfulness signal — a synthetic, unverified AI market view could
-- read as a verified house view. Persist a deterministic faithfulness assessment
-- (computed at generate-content over the model output vs the market-data input)
-- so the row and GET /house-views expose it. Additive nullable JSONB; existing
-- rows stay NULL (the data-quality disclosure itself is static and attached at
-- the API layer, so no value column is needed for it).
ALTER TABLE house_views
    ADD COLUMN IF NOT EXISTS faithfulness_json JSONB;
