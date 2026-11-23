#!/usr/bin/env python
"""Backfill AI_CALL_STARTED audit rows for terminal ai_jobs that lack one.

AC23 (tests/test_audit_emission_completeness.py::test_every_terminal_ai_job_has_audit_call_started)
requires every terminal (SUCCEEDED/FAILED, non-ffffffff fixture) ai_jobs row to have an
AI_CALL_STARTED audit_logs row linked via resource_type='ai_job' AND resource_id=ai_jobs.id
(or detail_json->>'job_id'). The wave_g_nonrag_generate_traces baseline generate-run (P2-10)
enqueued real Azure-backed ai_jobs directly (RUNNING -> SUCCEEDED) WITHOUT emitting the audit
row the router normally writes, leaving terminal "orphan" jobs. Those were real AI calls, so
per AC23 they should carry an AI_CALL_STARTED trail.

This backfill is an append-only INSERT (audit_logs forbids UPDATE/DELETE/TRUNCATE, not INSERT)
that is IDEMPOTENT (WHERE NOT EXISTS), so it is safe to re-run. The audit row mirrors the
canonical router emit shape (routers/house_views.py: AI_CALL_STARTED, resource_type='ai_job',
resource_id=<job_id>, detail={agent_id,...}); created_at is set to the job's started_at so the
trail timestamp is faithful to when the AI call actually ran. Going forward,
scripts/wave_g_nonrag_generate_traces.py emits AI_CALL_STARTED itself, so no new orphans appear.

Run: /opt/conda/envs/wm_env/bin/python scripts/backfill_ai_call_started_for_orphan_jobs.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)
# 형제 backfill 스크립트와 동일하게 가드된 읽기를 사용합니다(bare KeyError 회피).
DSN = os.environ.get("DATABASE_URL", "").strip()
if not DSN:
    print("[backfill] ERROR: DATABASE_URL not set after loading .env")
    sys.exit(2)

ORPHAN_PREDICATE = """
  FROM ai_jobs aj
  WHERE aj.status_code IN ('SUCCEEDED', 'FAILED')
    AND aj.id::text NOT LIKE 'ffffffff-%'
    AND NOT EXISTS (
      SELECT 1 FROM audit_logs al
      WHERE al.action_code = 'AI_CALL_STARTED'
        AND (al.detail_json->>'job_id' = aj.id::text
             OR (al.resource_type = 'ai_job' AND al.resource_id = aj.id))
    )
"""

BACKFILL_SQL = f"""
/* sql_id: backfill_ai_call_started_for_orphan_jobs */
INSERT INTO audit_logs (actor_id, action_code, resource_type, resource_id, detail_json, created_at)
SELECT aj.requested_by_id, 'AI_CALL_STARTED', 'ai_job', aj.id,
       jsonb_build_object('agent_id', aj.job_type_code, 'source', 'baseline_generate_run_backfill'),
       COALESCE(aj.started_at, now())
{ORPHAN_PREDICATE};
"""

COUNT_SQL = f"SELECT count(*) {ORPHAN_PREDICATE};"


def main() -> int:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(COUNT_SQL)
        before = cur.fetchone()[0]
        print(f"[backfill] terminal ai_jobs missing AI_CALL_STARTED (before): {before}")
        cur.execute(BACKFILL_SQL)
        inserted = cur.rowcount
        conn.commit()
        cur.execute(COUNT_SQL)
        after = cur.fetchone()[0]
        print(f"[backfill] inserted AI_CALL_STARTED rows: {inserted}")
        print(f"[backfill] remaining orphans (after): {after}")
    return 0 if after == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
