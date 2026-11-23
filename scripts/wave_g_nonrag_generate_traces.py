#!/usr/bin/env python
"""P2-10 companion — generate live (Azure) non-RAG dispatcher traces.

The faithfulness baseline (``wave_g_nonrag_faithfulness_baseline.py``) scores
only ``ai_outputs`` rows that carry ``output_json._model_input`` — the PII-safe
grounding the deterministic gate needs. Only the LIVE dispatcher path persists
``_model_input`` (portfolio_analysis.py / nba_script.py / consultation_briefing.py);
the ``dry_run`` test-double fixtures deliberately omit it. So a real N>=target
baseline requires real generations, not dry_run fixtures.

This driver invokes the live ``run_*`` dispatcher functions (``dry_run=False``)
against synthetic-only resources, so each produces one ``ai_outputs`` row with
``_model_input`` + a faithfulness stamp. PII discipline is the dispatchers' own:
they build ``<USER_DATA>`` from structured codes + a UUID ref, never the customer
name. consultation_briefing is dual-LLM (2 Azure calls each).

Resources are cycled when the target exceeds the available count (e.g. 23
customers, target 55 -> each customer used ~2-3x); each generation is an
independent LLM call, which is the point of a faithfulness baseline.

Usage:
  /opt/conda/envs/wm_env/bin/python scripts/wave_g_nonrag_generate_traces.py \
      --count 55 --concurrency 4
  # smoke (~4 Azure calls): --count 1
  # top up a single dispatcher: --dispatchers nba_script --count 10
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
_ = load_dotenv(PROJECT_ROOT / ".env", override=True)

from apps.api.harness.core.config import load_config  # noqa: E402
from apps.api.harness.core.db import DatabaseUnavailableError, create_pool  # noqa: E402
from apps.api.harness.repositories import audit as audit_repo  # noqa: E402
from apps.api.harness.services.consultation_briefing import (  # noqa: E402
    run_consultation_briefing,
)
from apps.api.harness.services.nba_script import run_nba_script  # noqa: E402
from apps.api.harness.services.portfolio_analysis import run_portfolio_analysis  # noqa: E402

# agent_id -> (resource_type, run_* dispatcher coroutine). The resource_type is
# the canonical singular each dispatcher accepts AND the value recorded on the
# ai_jobs row, matching the existing ai_jobs data shape (customer / nba_actions /
# consultation).
DISPATCHERS: dict[str, tuple[str, object]] = {
    "portfolio_analysis": ("customer", run_portfolio_analysis),
    "nba_script": ("nba_actions", run_nba_script),
    "consultation_briefing": ("consultation", run_consultation_briefing),
}

# ai_outputs.job_id FKs to ai_jobs(id), so every generation needs a real ai_jobs
# row first (the worker normally claims one). We insert it RUNNING, run the
# dispatcher, then mark it SUCCEEDED — the worker's own lifecycle. requested_by_id
# FKs to employees(id); a baseline generate-run is operator/system-initiated, so
# the canonical ADMIN employee is the requester.
_ADMIN_EMPLOYEE_ID = "22222222-2222-2222-2222-222222222203"
ENQUEUE_JOB_SQL = (
    "/* sql_id: enqueue_baseline_gen_job */ "
    "INSERT INTO ai_jobs(job_type_code, status_code, requested_by_id, resource_type, "
    "resource_id, started_at) VALUES ($1, 'RUNNING', $2::uuid, $3, $4::uuid, now()) "
    "RETURNING id::text"
)
FINISH_JOB_SQL = (
    "/* sql_id: finish_baseline_gen_job */ "
    "UPDATE ai_jobs SET status_code = 'SUCCEEDED', finished_at = now(), "
    "result_summary = $2 WHERE id = $1::uuid"
)


async def _resource_ids(conn: Any, agent_id: str, count: int) -> list[str]:
    """Return ``count`` resource ids for the dispatcher, cycling if scarce."""
    if agent_id == "portfolio_analysis":
        rows = await conn.fetch(
            "SELECT id::text AS id FROM customers WHERE is_active IS TRUE ORDER BY created_at"
        )
    elif agent_id == "nba_script":
        rows = await conn.fetch("SELECT id::text AS id FROM nba_actions ORDER BY created_at")
    elif agent_id == "consultation_briefing":
        # Prefer consultations that have memos (they exercise the quarantine lane);
        # the rest fill the target.
        rows = await conn.fetch(
            "SELECT c.id::text AS id FROM consultations c "
            "LEFT JOIN (SELECT DISTINCT consultation_id FROM consultation_notes) n "
            "  ON n.consultation_id = c.id "
            "ORDER BY (n.consultation_id IS NOT NULL) DESC, c.created_at DESC "
            "LIMIT $1",
            max(count, 1),
        )
    else:
        raise ValueError(f"unknown dispatcher {agent_id!r}")
    ids = [r["id"] for r in rows]
    if not ids:
        return []
    return [ids[i % len(ids)] for i in range(count)]


async def _generate_one(
    pool: Any, agent_id: str, runner: Any, resource_type: str, resource_id: str
) -> tuple[bool, str]:
    async with pool.acquire() as conn:
        try:
            # ai_jobs row + dispatcher + mark-succeeded in one transaction: on any
            # failure (Azure error -> RuntimeError) the whole unit rolls back, so no
            # orphan RUNNING job and no partial ai_outputs row.
            async with conn.transaction():
                job_id = await conn.fetchval(
                    ENQUEUE_JOB_SQL, agent_id, _ADMIN_EMPLOYEE_ID, resource_type, resource_id
                )
                # AC23 / audit completeness: emit AI_CALL_STARTED the way the runtime
                # router does (resource_type='ai_job', resource_id=job_id), so a baseline
                # generate-run leaves the same audit trail and never creates an orphan
                # terminal ai_job. In-tx: rolls back with the job on dispatcher failure.
                await audit_repo.insert_audit_log(
                    conn,
                    actor_id=_ADMIN_EMPLOYEE_ID,
                    action_code="AI_CALL_STARTED",
                    resource_type="ai_job",
                    resource_id=job_id,
                    detail={"agent_id": agent_id, "source": "baseline_generate_run"},
                )
                job = {
                    "id": job_id,
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "dry_run": False,
                }
                msg = await runner(conn, job)
                await conn.execute(FINISH_JOB_SQL, job_id, str(msg)[:500])
            return (True, str(msg))
        except Exception as exc:  # noqa: BLE001 — per-item isolation (worker mark_failed parity)
            return (False, f"{type(exc).__name__}: {exc}")


async def _create_pool_resilient(config: Any, concurrency: int) -> Any:
    """create_pool with backoff retry on transient Patroni connect drops.

    Pre-warming `concurrency` connections at pool creation lets the per-task
    acquires reuse a pooled connection instead of opening a NEW connection
    mid-run (the HAProxy/Patroni endpoint can stall a burst of concurrent
    new-connection opens). create_pool re-wraps the transient asyncpg connect
    error as DatabaseUnavailableError, which the codebase's with_retry decorator
    does NOT catch, so we retry that exception here with the same backoff shape
    ([[pg-patroni-transient-drop]] — db.py with_retry is the read-path analogue).
    """
    delays = [1.0, 2.0, 4.0, 8.0]
    attempt = 0
    while True:
        try:
            return await create_pool(
                config.database, min_size=concurrency, max_size=max(concurrency + 1, 10)
            )
        except DatabaseUnavailableError as exc:
            if attempt >= len(delays):
                raise
            wait = delays[attempt]
            attempt += 1
            print(
                f"[generate] pool create transient failure (attempt {attempt}), "
                f"retry in {wait}s: {str(exc)[:120]}",
                flush=True,
            )
            await asyncio.sleep(wait)


async def _run(count: int, concurrency: int, dispatchers: list[str]) -> tuple[int, int]:
    config = load_config(PROJECT_ROOT / ".env")
    pool: Any = await _create_pool_resilient(config, concurrency)
    sem = asyncio.Semaphore(concurrency)
    overall_fail = 0
    try:
        async with pool.acquire() as conn:
            plan: dict[str, list[str]] = {
                a: await _resource_ids(conn, a, count) for a in dispatchers
            }
        # Actual scheduled total (NOT count*len(dispatchers)): a dispatcher with
        # zero eligible resources contributes 0 tasks, so the exit-code threshold
        # must compare against what was really scheduled, else a degenerate
        # no-eligible-resources run could mask an outage as success.
        total_tasks = sum(len(plan[a]) for a in dispatchers)

        async def _guarded(agent_id: str, resource_id: str) -> tuple[str, bool, str]:
            resource_type, runner = DISPATCHERS[agent_id]
            async with sem:
                ok, msg = await _generate_one(
                    pool, agent_id, runner, resource_type, resource_id
                )
            return (agent_id, ok, msg)

        tasks = [
            _guarded(a, rid) for a in dispatchers for rid in plan[a]
        ]
        results = await asyncio.gather(*tasks)

        for agent_id in dispatchers:
            ag = [r for r in results if r[0] == agent_id]
            ok = sum(1 for r in ag if r[1])
            fail = len(ag) - ok
            overall_fail += fail
            print(
                f"[generate] {agent_id}: requested {len(ag)} ok {ok} fail {fail}",
                flush=True,
            )
            for r in ag:
                if not r[1]:
                    print(f"[generate]   FAIL {agent_id}: {r[2][:160]}", flush=True)
    finally:
        await pool.close()  # type: ignore[attr-defined]
    return overall_fail, total_tasks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=55, help="generations per dispatcher")
    ap.add_argument("--concurrency", type=int, default=4, help="max concurrent Azure calls")
    ap.add_argument(
        "--dispatchers",
        default=",".join(DISPATCHERS),
        help="comma-separated subset of dispatchers to generate",
    )
    args = ap.parse_args()
    dispatchers = [d.strip() for d in args.dispatchers.split(",") if d.strip()]
    unknown = [d for d in dispatchers if d not in DISPATCHERS]
    if unknown:
        raise SystemExit(f"unknown dispatcher(s): {unknown}; allowed: {list(DISPATCHERS)}")
    print(
        f"[generate] count={args.count} concurrency={args.concurrency} "
        f"dispatchers={dispatchers} (live Azure, dry_run=False)",
        flush=True,
    )
    fail, total = asyncio.run(_run(args.count, args.concurrency, dispatchers))
    # Compare against the ACTUAL scheduled total, not count*len(dispatchers): a
    # dispatcher with zero eligible resources schedules 0 tasks, so the requested
    # product would let a near-total Azure outage on the rest still pass. An empty
    # plan (total==0) is itself an ERROR (exit 1) so a degenerate no-eligible-
    # resources run is surfaced, not masked. Non-zero exit only if EVERYTHING
    # failed (signals a config/Azure outage, not a few transient 429s).
    return 0 if (fail < total and total > 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
