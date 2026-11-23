#!/usr/bin/env python
"""ai_jobs PENDING worker daemon entry script (Wave 6 US-W6-3, R3+R39).

Polls ``ai_jobs`` for PENDING rows using ``FOR UPDATE SKIP LOCKED`` so that
multiple worker instances can safely run in parallel. Each claim is followed
by a job_type_code-specific dispatcher invocation; the dispatcher's return
value is recorded as ``result_summary`` on success.

Dispatchers are intentionally not pre-populated here — wiring the real
agent services is scope of US-W6-2 (R36 dual-LLM 6 agent expansion). Until
those services exist, every job routes to ``handle_unknown`` which raises
``NotImplementedError`` and is recorded as ``FAILED`` with
``error_code='no_dispatcher'``. That fail-closed behavior keeps the job
backlog observable rather than silently consuming PENDING rows.

Deployment (systemd / cron) is a separate operational decision and is not
configured by this script. Run the script manually or wire it into the
operator's preferred process supervisor.

Usage::

    scripts/run_ai_job_runner.py                       # foreground loop
    scripts/run_ai_job_runner.py --dry-run             # observe pending count only
    scripts/run_ai_job_runner.py --once                # claim+process one job, exit
    scripts/run_ai_job_runner.py --backoff-base 2.0    # exponential idle backoff
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.core.config import load_config  # noqa: E402
from apps.api.harness.core.db import create_pool  # noqa: E402
from apps.api.harness.services.consultation_briefing import run_consultation_briefing  # noqa: E402
from apps.api.harness.services.email_draft import run_email_draft  # noqa: E402
from apps.api.harness.services.nba_script import run_nba_script  # noqa: E402
from apps.api.harness.services.portfolio_analysis import run_portfolio_analysis  # noqa: E402

CLAIM_SQL = """
/* sql_id: claim_pending_ai_job */
WITH next_job AS (
    SELECT id FROM ai_jobs
    WHERE status_code = 'PENDING'
    ORDER BY created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE ai_jobs
SET status_code = 'RUNNING', started_at = COALESCE(started_at, now())
FROM next_job
WHERE ai_jobs.id = next_job.id
RETURNING ai_jobs.id, ai_jobs.job_type_code, ai_jobs.requested_by_id,
          ai_jobs.resource_type, ai_jobs.resource_id, ai_jobs.created_at;
"""

MARK_FAILED_SQL = """
/* sql_id: ai_job_mark_failed_by_runner */
UPDATE ai_jobs
SET status_code = 'FAILED', error_code = $2, error_message = $3, finished_at = now()
WHERE id = $1::uuid AND status_code IN ('RUNNING', 'PENDING');
"""

MARK_SUCCEEDED_SQL = """
/* sql_id: ai_job_mark_succeeded_by_runner */
UPDATE ai_jobs
SET status_code = 'SUCCEEDED',
    result_summary = $2,
    result_resource_id = (
        SELECT ao.id FROM ai_outputs ao
        WHERE ao.job_id = $1::uuid
        ORDER BY ao.created_at DESC
        LIMIT 1
    ),
    result_resource_type = CASE
        WHEN EXISTS (SELECT 1 FROM ai_outputs ao WHERE ao.job_id = $1::uuid)
        THEN 'ai_output' ELSE result_resource_type END,
    finished_at = now()
WHERE id = $1::uuid AND status_code = 'RUNNING';
"""

COUNT_PENDING_SQL = """
/* sql_id: count_pending_ai_jobs */
SELECT COUNT(*) FROM ai_jobs WHERE status_code = 'PENDING';
"""

logger = logging.getLogger("ai_job_runner")


async def handle_unknown(_conn: Any, job: dict[str, Any]) -> str:
    """Default dispatcher — every unknown ``job_type_code`` fails closed.

    Wiring real agent services is scope of Wave 6 US-W6-2 (R36).
    """
    raise NotImplementedError(
        f"no dispatcher registered for job_type_code={job['job_type_code']!r}"
    )


DISPATCHERS: dict[str, Callable[[Any, dict[str, Any]], Awaitable[str]]] = {
    # ADR-005 §Status dual-LLM (Wave 6.3):
    "email_draft": run_email_draft,
    "consultation_briefing": run_consultation_briefing,
    # ADR-005 §Status T265 single-LLM + spotlighting + sanitize (Wave 6.4 + 6.5):
    "nba_script": run_nba_script,
    "portfolio_analysis": run_portfolio_analysis,
    # compliance_check is invoked SYNCHRONOUSLY from
    # routers/consultations.py (BLOCKING fourth gate), not via the worker.
    # house_view_generation is invoked from house_view router activation;
    # both attach T265 via their own modules — see services/house_view.py
    # and services/compliance_check.py.
}


async def claim_one(conn: Any) -> dict[str, Any] | None:
    row = await conn.fetchrow(CLAIM_SQL)
    return dict(row) if row else None


async def mark_failed(conn: Any, job_id: str, error_code: str, message: str) -> None:
    await conn.execute(MARK_FAILED_SQL, job_id, error_code[:80], message[:2000])


async def mark_succeeded(conn: Any, job_id: str, summary: str) -> None:
    await conn.execute(MARK_SUCCEEDED_SQL, job_id, summary[:4000])


async def process_one(pool: Any, *, dry_run: bool = False) -> bool:
    """Claim and process at most one PENDING job.

    Returns True when a job was claimed (regardless of dispatcher outcome).
    Returns False when the table had no PENDING rows or ``dry_run`` was set.
    """

    if dry_run:
        async with pool.acquire() as conn:
            pending = await conn.fetchval(COUNT_PENDING_SQL)
        logger.info("[dry-run] pending=%s", pending)
        return False

    async with pool.acquire() as claim_conn:
        async with claim_conn.transaction():
            job = await claim_one(claim_conn)
    if job is None:
        return False

    job_id = str(job["id"])
    job_type = job["job_type_code"]
    logger.info("claimed job=%s type=%s", job_id, job_type)

    dispatcher = DISPATCHERS.get(job_type, handle_unknown)
    try:
        async with pool.acquire() as run_conn:
            async with run_conn.transaction():
                summary = await dispatcher(run_conn, job)
                await mark_succeeded(run_conn, job_id, summary)
        logger.info("succeeded job=%s", job_id)
    except NotImplementedError as exc:
        async with pool.acquire() as fail_conn:
            await mark_failed(fail_conn, job_id, "no_dispatcher", str(exc))
        logger.warning("no_dispatcher job=%s type=%s", job_id, job_type)
    except Exception as exc:  # noqa: BLE001 - boundary; details captured to DB
        async with pool.acquire() as fail_conn:
            await mark_failed(fail_conn, job_id, type(exc).__name__, str(exc))
        logger.exception("failed job=%s", job_id)

    return True


async def runner_loop(
    *,
    once: bool,
    dry_run: bool,
    idle_sleep: float,
    backoff_base: float,
    max_idle_retries: int,
) -> int:
    config = load_config(PROJECT_ROOT / ".env")
    pool = await create_pool(config.database)
    try:
        idle_retries = 0
        processed = 0
        while True:
            claimed = await process_one(pool, dry_run=dry_run)
            if claimed:
                processed += 1
                idle_retries = 0
                if once:
                    break
                continue

            if once or dry_run:
                break
            idle_retries += 1
            if idle_retries >= max_idle_retries:
                break
            sleep_s = min(idle_sleep * (backoff_base ** (idle_retries - 1)), 60.0)
            await asyncio.sleep(sleep_s)
    finally:
        await pool.close()
    return processed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ai_jobs PENDING worker daemon entry (Wave 6 US-W6-3)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="report pending count without claiming",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="claim+process one job then exit (or exit immediately if none pending)",
    )
    parser.add_argument("--idle-sleep", type=float, default=2.0)
    parser.add_argument("--backoff-base", type=float, default=1.5)
    parser.add_argument(
        "--max-idle-retries", type=int, default=30,
        help="exit after this many empty polls (foreground-loop bound)",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("AI_JOB_RUNNER_LOG_LEVEL", "INFO"),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)sZ ai_job_runner %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    processed = asyncio.run(
        runner_loop(
            once=args.once,
            dry_run=args.dry_run,
            idle_sleep=args.idle_sleep,
            backoff_base=args.backoff_base,
            max_idle_retries=args.max_idle_retries,
        )
    )
    logger.info("done processed=%d", processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
