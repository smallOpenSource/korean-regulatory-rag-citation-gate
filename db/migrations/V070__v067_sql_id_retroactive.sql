/* sql_id: v070_v067_retroactive_fix */
-- V070: Retroactive sql_id convention fix for V067 (2026-05-24)
--
-- V067 (service_readiness_fixture_seeds) was written before the
-- per-statement /* sql_id: short_name */ convention was enforced by
-- tests/test_sql_contracts.py. V067 has a file-level sql_id comment on
-- statement 1 but statements 2-11 (rights_notices, conflict_disclosures,
-- customer_consents, info_access_requests, data_purge_schedules,
-- dispute_cases ×3 INSERT+UPDATE+UPDATE, marketing_reviews,
-- consultation_gates) lack individual headers.
--
-- Fix strategy (Option B — V067 변경 금지):
--   This migration file serves as the canonical record of the retroactive
--   fix. The test (test_sql_contracts.py) grandfathers V067 via
--   GRANDFATHERED_MIGRATIONS set, recognising that statement 1 carries
--   a valid file-level sql_id. No schema or data changes are made here.
--
-- Tracking: svc-follow-up-v1 Wave 4 Q3 / task #11
--           .omc/handoffs/svc-via-audit-v1__step0-ops-pause.md §4 Follow-up 1

DO $$ BEGIN NULL; END $$;
