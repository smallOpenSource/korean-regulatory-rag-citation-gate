"""In-process AI job worker loop (UltraQA cycle 17 S35 fix).

The ai_job_runner CLI (``scripts/run_ai_job_runner.py``) keeps the standalone
deployment option open. This module replicates the same claim+dispatch
pipeline inside the FastAPI uvicorn process so the worker shares the
RealtimeConnectionManager singleton and can broadcast ``ai_job_done`` events
directly to active WebSocket subscribers.

Wired from ``apps.api.harness.main:lifespan`` as a ``asyncio.create_task``;
shutdown is coordinated through the same ``asyncio.Event`` mechanism the
``realtime.redis_fanout_loop`` already uses.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from apps.api.harness.services.consultation_briefing import run_consultation_briefing
from apps.api.harness.services.email_draft import run_email_draft
from apps.api.harness.services.nba_script import run_nba_script
from apps.api.harness.services.portfolio_analysis import run_portfolio_analysis

logger = logging.getLogger("ai_jobs_worker")

# ── Test-double dispatcher registry (DELTA-4 / G0a-1) ────────────────────────
# Job IDs enqueued for dry-run execution (populated by API endpoint handlers).
# The in-process worker shares memory with the API process, so this set is
# visible to both. Entries are consumed (discarded) once claimed.
_DRY_RUN_JOB_IDS: set[str] = set()

DRY_RUN_ENV_GATE = "WMAH_ENABLE_DRY_RUN_PROBE"
"""Environment variable gate that allows ``?dry_run=1`` to activate the
in-process test-double dispatcher (DELTA-4 / G0a-1). Set to ``"1"`` to
permit dry-run mode; any other value (or absence) makes the query parameter
inert. The previous Bearer-token shortcut (``v8-synthetic-traversal-token``)
was removed under Wave-Audit-Defect-Fix A2 — it bypassed auth-bypass-probe
checks (audit defect CR-3)."""

CLAIM_SQL = """
/* sql_id: claim_pending_ai_job_inproc */
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
/* sql_id: ai_job_mark_failed_inproc */
UPDATE ai_jobs
SET status_code = 'FAILED', error_code = $2, error_message = $3, finished_at = now()
WHERE id = $1::uuid AND status_code IN ('RUNNING', 'PENDING');
"""

MARK_SUCCEEDED_SQL = """
/* sql_id: ai_job_mark_succeeded_inproc */
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


async def _handle_unknown(_conn: Any, job: dict[str, Any]) -> str:
    raise NotImplementedError(
        f"no dispatcher registered for job_type_code={job['job_type_code']!r}"
    )


DISPATCHERS: dict[str, Callable[[Any, dict[str, Any]], Awaitable[str]]] = {
    "email_draft": run_email_draft,
    "consultation_briefing": run_consultation_briefing,
    "nba_script": run_nba_script,
    "portfolio_analysis": run_portfolio_analysis,
}


async def _handle_dispatch(
    conn: Any,
    job: dict[str, Any],
    dispatcher: Callable[[Any, dict[str, Any]], Awaitable[str]],
) -> str:
    """Dispatch a job, injecting dry_run=True for registered test-double jobs.

    Honest naming: this is the test-double dispatcher gate (DELTA-4 / G0a-1).
    When a job ID appears in ``_DRY_RUN_JOB_IDS`` (registered by the API
    endpoint handler), the dry_run flag is injected into the job dict before
    calling the downstream dispatcher. The registration is consumed here.
    Azure SDK calls are then bypassed at the dispatcher level; real DB writes
    and WS broadcast proceed normally via the caller (process_one).
    """
    job_id = str(job["id"])
    if job_id in _DRY_RUN_JOB_IDS:
        _DRY_RUN_JOB_IDS.discard(job_id)
        job = {**job, "dry_run": True}
        logger.info("dry_run dispatch job=%s type=%s", job_id, job["job_type_code"])
    return await dispatcher(conn, job)


async def _broadcast_done(manager: Any, job: dict[str, Any], status: str) -> None:
    if manager is None:
        return
    try:
        await manager.broadcast(
            {
                "event_type": "ai_job_done",
                "payload": {
                    "job_id": str(job["id"]),
                    "job_type": job["job_type_code"],
                    "resource_type": job.get("resource_type"),
                    "resource_id": str(job.get("resource_id") or ""),
                    "status": status,
                    # requested_by_id → event_visible_to_actor _target_employee_id
                    # 매칭에 필요 (PB는 본인 요청 job만 visible).
                    "employee_id": str(job.get("requested_by_id") or ""),
                },
            }
        )
    except Exception:  # noqa: BLE001 — WS broadcast must never block worker
        pass


async def process_one(pool: Any, *, manager: Any = None) -> bool:
    """Claim and process at most one PENDING job. Returns True if claimed."""
    async with pool.acquire() as claim_conn:
        async with claim_conn.transaction():
            row = await claim_conn.fetchrow(CLAIM_SQL)
    if row is None:
        return False

    job = dict(row)
    job_id = str(job["id"])
    job_type = job["job_type_code"]
    logger.info("claimed job=%s type=%s", job_id, job_type)

    dispatcher = DISPATCHERS.get(job_type, _handle_unknown)
    try:
        async with pool.acquire() as run_conn:
            async with run_conn.transaction():
                summary = await _handle_dispatch(run_conn, job, dispatcher)
                await run_conn.execute(MARK_SUCCEEDED_SQL, job_id, summary[:4000])
        logger.info("succeeded job=%s", job_id)
        await _broadcast_done(manager, job, "SUCCEEDED")
    except NotImplementedError as exc:
        async with pool.acquire() as fail_conn:
            await fail_conn.execute(MARK_FAILED_SQL, job_id, "no_dispatcher", str(exc)[:2000])
        logger.warning("no_dispatcher job=%s type=%s", job_id, job_type)
        await _broadcast_done(manager, job, "FAILED")
    except Exception as exc:  # noqa: BLE001 — boundary; details captured to DB
        async with pool.acquire() as fail_conn:
            await fail_conn.execute(
                MARK_FAILED_SQL, job_id, type(exc).__name__[:80], str(exc)[:2000]
            )
        logger.exception("failed job=%s", job_id)
        await _broadcast_done(manager, job, "FAILED")
    return True


async def worker_loop(
    pool: Any,
    *,
    manager: Any,
    stop_event: asyncio.Event,
    idle_sleep: float = 2.0,
) -> None:
    """Run the in-process ai_job worker until the stop event is set."""
    while not stop_event.is_set():
        try:
            claimed = await process_one(pool, manager=manager)
        except Exception:  # noqa: BLE001 — loop must never crash uvicorn
            logger.exception("worker_loop iteration failed")
            claimed = False
        if not claimed:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=idle_sleep)
            except asyncio.TimeoutError:
                pass
