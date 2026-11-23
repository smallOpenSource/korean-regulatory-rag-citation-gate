/* sql_id: v079_house_view_leading_block */
-- REG-02 leading-block markers (loss_warning / unsuitable_types /
-- uncertainty_disclaimer) are produced by services/house_view.py but were
-- discarded on persist (no column on house_views), so an activated house view
-- could not be shown to carry its mandatory markers. Add an additive nullable
-- JSONB column so generate-content persists them and the row/API exposes them
-- for positive assertion. Existing rows stay NULL (back-compatible).
ALTER TABLE house_views
    ADD COLUMN IF NOT EXISTS leading_block_json JSONB;
