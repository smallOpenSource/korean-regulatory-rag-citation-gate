/* sql_id: house_view_single_live_index */
-- ADR-020 F1 — DB-level hardening of the single-global-live-view invariant.
--
-- The application guard (assert_single_live_house_view in
-- repositories/house_views.py) already enforces "at most one non-fixture live
-- house view at read" on both activation write paths. This partial UNIQUE index
-- is the DB-level backstop: it forbids a SECOND non-fixture live row regardless
-- of how it is written (direct SQL, a seed, a future code path that bypasses the
-- activation functions).
--
-- Idiom: a UNIQUE index keyed on the constant expression ((true)) — every
-- matching row produces the same key (t), so at most one matching row can exist.
-- Validated on the target PG: ((true)) is accepted, a 2nd matching row raises
-- "duplicate key value ... Key ((true))=(t) already exists", and a fixture live
-- row (excluded by the WHERE predicate) is allowed to coexist.
--
-- The WHERE predicate MIRRORS NON_FIXTURE_HOUSE_VIEW_PREDICATE +
-- LIVE_HOUSE_VIEW_STATUS_IN in repositories/house_views.py (the live-view readers
-- and the app guard use the same set). It excludes QA/golden/synthetic test
-- fixtures (by status_code / period_code / title / summary) so a fixture live row
-- never counts toward the single-live constraint — exactly what the readers do.
-- NOTE: this predicate is a frozen copy; if the Python NON_FIXTURE predicate
-- changes, this index WHERE must be updated in a follow-up migration (it cannot
-- reference the application constant). The app guard remains the primary SoT.

CREATE UNIQUE INDEX IF NOT EXISTS idx_house_views_single_live
    ON house_views ((true))
    WHERE status_code IN ('ACTIVE', 'ACTIVATED')
      AND status_code NOT IN (
          'GOLDEN_TEST', 'GOLDEN', 'RALPH', 'RALPH-QA', 'RALPH_QA',
          'SYNTHETIC_BOUNDARY', 'TEST', 'TEST_FIXTURE',
          'ULTRAQA', 'ULTRA_QA', 'ULTRA-QA', 'QA_DRAFT'
      )
      AND period_code NOT IN (
          'GOLDEN_TEST', 'GOLDEN', 'RALPH', 'RALPH-QA', 'RALPH_QA',
          'SYNTHETIC_BOUNDARY', 'TEST', 'TEST_FIXTURE',
          'ULTRAQA', 'ULTRA_QA', 'ULTRA-QA', 'QA_DRAFT', 'AUDIT'
      )
      AND title NOT LIKE 'AUDIT-%'
      AND title !~* '(golden[ _-]?test|ralph[ _-]?qa|synthetic[ _-]?(boundary|qa)|golden[ _-]?regression|test[ _-]?fixture|qa[ _-]?activation[ _-]?probe|ultra[ _-]?qa)'
      AND COALESCE(summary, '') !~* '(synthetic[ _-]?(boundary|qa)|golden[ _-]?regression|test[ _-]?fixture|qa[ _-]?activation[ _-]?probe|ralph[ _-]?qa|ultra[ _-]?qa)';
