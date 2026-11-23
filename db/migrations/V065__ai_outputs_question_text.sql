/* sql_id: v065_add_question_text_column */
-- V065: Wave-Audit-Defect-Fix v5 residual closure — add nullable
-- `question_text` column to ai_outputs so the G1 RAGAS AnswerRelevancy
-- metric (scripts/wave_g_ragas.py) can use the canonical user-input
-- instead of substituting a synthetic placeholder ("Q for
-- resource_type=…").
--
-- Per ADR-005 §"ai_outputs Mutability" amend (2026-05-23 in
-- commit 860d992): ai_outputs is NOT append-only. Only audit_logs is
-- trigger-locked (V008+V019). The mutable-column allowlist now
-- includes question_text.
ALTER TABLE ai_outputs ADD COLUMN IF NOT EXISTS question_text TEXT;

/* sql_id: v065_backfill_question_text_from_output_json */
-- Pre-flight grep (Wave v5 ralplan Pre-mortem Scenario 1 mitigation):
-- the 5 INSERT call sites (repositories/ai.py:65 +
-- services/{email_draft,nba_script,portfolio_analysis,consultation_briefing}.py)
-- do NOT historically emit a uniform "question"/"query"/"user_input"
-- key into output_json. The grep returned 0 hits across all four
-- service files. Backfill therefore uses the broadest JSON path set
-- to capture whatever the rows happen to carry; rows with no
-- recognisable question key remain NULL and are handled by the G1
-- script's "extracted vs placeholder" classification.
UPDATE ai_outputs
SET question_text = COALESCE(
    output_json->>'question',
    output_json->>'query',
    output_json->>'user_input',
    output_json->>'prompt',
    output_json->>'customer_concern',
    output_json->>'briefing_question'
)
WHERE question_text IS NULL
  AND output_json IS NOT NULL
  AND (
    output_json ? 'question'
    OR output_json ? 'query'
    OR output_json ? 'user_input'
    OR output_json ? 'prompt'
    OR output_json ? 'customer_concern'
    OR output_json ? 'briefing_question'
  );

/* sql_id: v065_index_question_text */
-- Used by the G1 script's per-row WHERE filter when N=30 sample
-- requires `question_text IS NOT NULL`.
CREATE INDEX IF NOT EXISTS ai_outputs_question_text_idx
  ON ai_outputs (question_text)
  WHERE question_text IS NOT NULL;
