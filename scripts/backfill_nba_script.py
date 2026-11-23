"""NBA AI-script backfill (W3-2, 2026-05-24).

Reads every nba_actions row whose ``script_text`` IS NULL or empty, then for
each row creates an ai_jobs lifecycle row (status RUNNING → SUCCEEDED /
FAILED) and dispatches the existing ``run_nba_script`` worker primitive
in-line. The worker performs the Azure call, the ADR-005 redact/safety
pass, and the actual UPDATE on nba_actions.script_text /
script_generated_at / script_model_name.

The ai_jobs row is necessary because ai_outputs.job_id has a FK to ai_jobs
and ``run_nba_script`` writes one ai_outputs row per dispatch. It mirrors
the same flow as the HTTP endpoint POST /nba-cards/{id}/generate-script
introduced in W2-2.

Concurrency is capped at 2 to stay under the gpt-5-mini deployment quota.

Idempotent: WHERE script_text IS NULL OR script_text = '' guards against
re-touching rows that already have a script (e.g., the one row populated
by the W2-2 smoke tests).

Usage:
    python scripts/backfill_nba_script.py --dry-run
    python scripts/backfill_nba_script.py --limit 5
    python scripts/backfill_nba_script.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.repositories import audit as audit_repo  # noqa: E402
from apps.api.harness.services.nba_script import run_nba_script  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill_nba_script")


# Canonical synthetic ADMIN ID used elsewhere as ``requested_by_id``.
ADMIN_EMPLOYEE_ID = "22222222-2222-2222-2222-222222222203"


SELECT_TARGETS_SQL = """
SELECT id, action_type_code, priority_code, status_code, trigger_code
FROM nba_actions
WHERE script_text IS NULL OR script_text = ''
ORDER BY created_at ASC
"""

INSERT_JOB_SQL = """
INSERT INTO ai_jobs (
    job_type_code, status_code, requested_by_id,
    resource_type, resource_id, started_at
)
VALUES ('nba_script', 'RUNNING', $1::uuid, 'nba_actions', $2::uuid, now())
RETURNING id
"""

FINISH_JOB_OK_SQL = """
UPDATE ai_jobs
SET status_code = 'SUCCEEDED', finished_at = now()
WHERE id = $1::uuid
"""

FINISH_JOB_FAIL_SQL = """
UPDATE ai_jobs
SET status_code = 'FAILED', error_message = $2, finished_at = now()
WHERE id = $1::uuid
"""


async def _process_one(
    pool: asyncpg.Pool,
    row: dict[str, Any],
    *,
    dry_run: bool,
    semaphore: asyncio.Semaphore,
) -> tuple[str, bool, str]:
    nba_id = str(row["id"])
    label = f"{row['action_type_code']}/{row['trigger_code']} ({nba_id[:8]})"
    if dry_run:
        return nba_id, True, f"[dry-run] would generate script for {label}"

    async with semaphore:
        async with pool.acquire() as connection:
            job_row = await connection.fetchrow(
                INSERT_JOB_SQL, ADMIN_EMPLOYEE_ID, nba_id,
            )
            job_id = str(job_row["id"])
            # AC23 / audit completeness: emit AI_CALL_STARTED the way the runtime
            # router does (resource_type='ai_job', resource_id=job_id) so this operator
            # backfill leaves the same audit trail and never creates an orphan terminal
            # ai_job. No wrapping transaction here, so it auto-commits like the enqueue
            # above — both the SUCCEEDED and FAILED terminal outcomes carry the trail.
            await audit_repo.insert_audit_log(
                connection,
                actor_id=ADMIN_EMPLOYEE_ID,
                action_code="AI_CALL_STARTED",
                resource_type="ai_job",
                resource_id=job_id,
                detail={"agent_id": "nba_script", "source": "backfill_nba_script"},
            )
            try:
                summary = await run_nba_script(
                    connection,
                    {
                        "id": job_id,
                        "resource_id": nba_id,
                        "resource_type": "nba_actions",
                        "dry_run": False,
                    },
                )
                await connection.execute(FINISH_JOB_OK_SQL, job_id)
                await asyncio.sleep(1.0)
                return nba_id, True, f"{label} → {summary}"
            except Exception as exc:  # noqa: BLE001
                error_msg = f"{type(exc).__name__}: {str(exc)[:200]}"
                await connection.execute(FINISH_JOB_FAIL_SQL, job_id, error_msg[:1000])
                return nba_id, False, f"{label} → ERROR {error_msg}"


async def main(*, dry_run: bool, limit: int | None) -> int:
    load_dotenv(PROJECT_ROOT / ".env", override=True)

    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        logger.error("DATABASE_URL not set after loading .env")
        return 2
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=4)
    try:
        rows = [dict(r) for r in await pool.fetch(SELECT_TARGETS_SQL)]
        if limit is not None:
            rows = rows[:limit]
        logger.info("targets: %d nba_actions (dry_run=%s)", len(rows), dry_run)
        if not rows:
            logger.info("nothing to do.")
            return 0

        started = datetime.now()
        semaphore = asyncio.Semaphore(2)
        tasks = [
            _process_one(pool, row, dry_run=dry_run, semaphore=semaphore)
            for row in rows
        ]
        done = 0
        ok = 0
        for coro in asyncio.as_completed(tasks):
            _nba_id, success, msg = await coro
            done += 1
            if success:
                ok += 1
            level = logging.INFO if success else logging.ERROR
            logger.log(level, "[%d/%d] %s", done, len(rows), msg)

        elapsed = (datetime.now() - started).total_seconds()
        logger.info(
            "done: %d/%d succeeded in %.1fs (%.1fs/row)",
            ok, len(rows), elapsed, elapsed / max(len(rows), 1),
        )
        return 0 if ok == len(rows) else 1
    finally:
        await pool.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill empty NBA AI scripts.")
    parser.add_argument("--dry-run", action="store_true", help="list targets without calling Azure")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of rows processed")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(dry_run=args.dry_run, limit=args.limit)))
