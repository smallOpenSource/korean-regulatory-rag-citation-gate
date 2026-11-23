/* sql_id: v043_backfill_aftercare_quarter_code */
-- V043 — backfill aftercare_events.quarter_code (UltraQA cycle 5 S21 fix, 2026-05-19)
--
-- UltraQA cycle 5 sweep discovered that the 사후관리(분기) UI shows
-- 0건/0건/0건/0건 even though aftercare_events has 38 rows. Root cause:
-- the quarterly UI calls GET /aftercare/quarterly?quarter=YYYYQQ, the
-- repository filters on a.quarter_code = $X, but the column is NULL on
-- every existing row (seed scripts never populated it).
--
-- This migration derives quarter_code from event_date and writes it once
-- per row. Idempotent: the WHERE clause skips already-populated rows.

UPDATE aftercare_events
   SET quarter_code = format(
                        '%sQ%s',
                        date_part('year', event_date)::int,
                        CASE
                          WHEN event_date IS NULL THEN NULL
                          ELSE ceil(date_part('month', event_date) / 3.0)::int
                        END
                      )
 WHERE quarter_code IS NULL
   AND event_date IS NOT NULL;
