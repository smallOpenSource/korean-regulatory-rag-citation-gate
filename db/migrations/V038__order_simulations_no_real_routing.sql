/* sql_id: add_routed_to_exchange_column */
-- T311: PoC invariant (REG-06 §8) — order_simulations rows must never represent real
-- exchange routing. The column defaults to FALSE and the accompanying CHECK constraint
-- prevents any code path from flipping it to TRUE.
ALTER TABLE order_simulations
    ADD COLUMN IF NOT EXISTS routed_to_exchange BOOLEAN NOT NULL DEFAULT FALSE;

/* sql_id: drop_routed_to_exchange_check_if_exists */
ALTER TABLE order_simulations DROP CONSTRAINT IF EXISTS chk_order_sim_no_real_routing;

/* sql_id: add_routed_to_exchange_check */
ALTER TABLE order_simulations ADD CONSTRAINT chk_order_sim_no_real_routing
    CHECK (routed_to_exchange = FALSE);
