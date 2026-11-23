"""Readiness, result aggregation, and post-condition helpers.

Provides shared stage runners (run_local_stage, create_skipped_stage_log,
run_seed_stage), result summarisation, provider-window report helpers, and
post-condition collection used by runner.py and the stage submodules.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from apps.api.harness.batch.jobs import (
    BatchCounters,
    persist_batch_log_provider_evidence,
    run_locked_batch_job,
)
from apps.api.harness.batch.providers import (
    DartFilingTarget,
    KrxMarketTarget,
    KrxOfficialMarketTarget,
    krx_official_target_ref,
)
from apps.api.harness.batch.documents import rag_readiness_snapshot
from apps.api.harness.core.db import fetch_one
from apps.api.harness.core.logging import redact_secret_text
from apps.api.harness.repositories import batch as batch_repo
from db.seed import apply_profile

from .types import (
    DEFAULT_LOCK_TTL_SECONDS,
    EMBED_STAGE,
    MANDATORY_LOCAL_STAGES,
    OFFICIAL_KRX_POLICY_CODE,
    OFFICIAL_KRX_SOURCE_CODE,
    POSTCONDITION_SQL,
    PROVIDER_STAGE,
    PROVIDER_STRICTNESS_ALL,
    PROVIDER_STRICTNESS_REQUIRED,
    PYKRX_SOURCE_CODE,
    REQUIRED_PROVIDER_JOB_TYPE_CODES,
    BatchRunSummary,
    StageResult,
    env_date_value,
    env_bool,
    normalize_provider_strictness,
)

# ---------------------------------------------------------------------------
# Shared stage primitives
# ---------------------------------------------------------------------------


async def create_skipped_stage_log(
    connection: Any,
    *,
    stage: str,
    job_name: str,
    job_type_code: str,
    reason: str,
    detail: dict[str, Any] | None = None,
) -> StageResult:
    """Persist explicit SKIPPED evidence for unavailable optional stages."""

    log = await batch_repo.create_skipped_batch_log(
        connection,
        job_name=job_name,
        job_type_code=job_type_code,
        reason=redact_secret_text(reason),
    )
    if job_type_code.startswith("PROVIDER_"):
        evidence = await persist_batch_log_provider_evidence(
            connection, batch_log=log, detail=detail
        )
        if evidence is not None:
            log["provider_evidence"] = [evidence]
    return StageResult.from_batch_log(stage=stage, batch_log=log, detail=detail)


async def run_local_stage(
    connection: Any,
    redis_client: Any,
    *,
    stage: str,
    job_name: str,
    job_type_code: str,
    work: Callable[[], Awaitable[dict[str, int]]],
    detail: dict[str, Any] | None = None,
) -> StageResult:
    """Run one local stage under the existing Redis lock + job-log boundary."""

    async def wrapped_work() -> BatchCounters:
        rows = await work()
        return BatchCounters(
            rows_collected=rows.get("rows_collected", 0),
            rows_skipped=rows.get("rows_skipped", 0),
            rows_failed=rows.get("rows_failed", 0),
        )

    log = await run_locked_batch_job(
        connection=connection,
        redis_client=redis_client,
        job_name=job_name,
        job_type_code=job_type_code,
        ttl_seconds=DEFAULT_LOCK_TTL_SECONDS,
        work=wrapped_work,
    )
    return StageResult.from_batch_log(stage=stage, batch_log=log, detail=detail)


async def run_seed_stage(
    connection: Any,
    redis_client: Any,
    *,
    profile: str,
) -> StageResult:
    """Run deterministic seed fixtures and record executable evidence."""

    detail: dict[str, Any] = {}

    async def work() -> dict[str, int]:
        seed_result = await apply_profile(connection, profile)
        detail.update(
            {
                "profile": seed_result["profile"],
                "fixture_files": seed_result["fixture_files"],
                "readiness_ready": seed_result["readiness"]["ready"],
            }
        )
        return {"rows_collected": int(seed_result["statements_executed"])}

    return await run_local_stage(
        connection,
        redis_client,
        stage="seed",
        job_name="seed_full_mvp",
        job_type_code="SEED_FULL_MVP",
        work=work,
        detail=detail,
    )


# ---------------------------------------------------------------------------
# Provider strictness resolution
# ---------------------------------------------------------------------------


def resolve_strict_external(*, explicit: bool | None, app_env: str) -> bool:
    """Resolve legacy all-provider strict mode from CLI/env."""

    if explicit is not None:
        return explicit
    if app_env.strip().lower() == "production":
        return True
    if os.getenv("HARNESS_PROVIDER_STRICT", "").strip():
        return env_bool("HARNESS_PROVIDER_STRICT")
    return False


def resolve_provider_strictness(*, explicit: str | None, strict_external: bool) -> str:
    """Resolve required-provider vs all-provider batch acceptance mode."""

    if explicit:
        return normalize_provider_strictness(explicit)
    env_value = os.getenv("HARNESS_PROVIDER_STRICTNESS", "").strip()
    if env_value:  # noqa: RET505
        return normalize_provider_strictness(env_value)
    if strict_external:
        return PROVIDER_STRICTNESS_ALL
    return PROVIDER_STRICTNESS_REQUIRED


# ---------------------------------------------------------------------------
# Result aggregation
# ---------------------------------------------------------------------------


def _aggregate_status(results: list[StageResult]) -> str:
    if not results:
        return "NOT_RUN"
    statuses = {result.status_code for result in results}
    if "FAILED" in statuses:
        return "FAILED"
    if "SKIPPED" in statuses:
        return "SKIPPED"
    if statuses == {"DONE"}:
        return "DONE"
    return "DEGRADED"


def summarize_results(results: list[StageResult]) -> BatchRunSummary:
    """Summarize local success separately from external provider evidence."""

    local_results = [
        result
        for result in results
        if result.local_mandatory or result.stage in MANDATORY_LOCAL_STAGES
    ]
    provider_results = [
        result
        for result in results
        if result.provider_evidence
        or result.stage == PROVIDER_STAGE
        or result.job_type_code.startswith("PROVIDER_")
    ]
    required_provider_results = [
        result
        for result in provider_results
        if result.job_type_code in REQUIRED_PROVIDER_JOB_TYPE_CODES
    ]

    local_status = _aggregate_status(local_results)
    provider_status = _aggregate_status(provider_results)
    required_provider_status = _aggregate_status(required_provider_results)
    local_ok = local_status in {"DONE", "NOT_RUN"}
    provider_ok = provider_status in {"DONE", "NOT_RUN"}
    required_provider_ok = required_provider_status in {"DONE", "NOT_RUN"}
    status = "DONE"
    if not local_ok or not required_provider_ok:
        status = "FAILED"
    elif not provider_ok:
        status = "DEGRADED"

    return BatchRunSummary(
        status_code=status,
        local_status_code=local_status,
        provider_status_code=provider_status,
        provider_required_status_code=required_provider_status,
        local_ok=local_ok,
        provider_evidence_ok=provider_ok,
        provider_required_ok=required_provider_ok,
    )


# ---------------------------------------------------------------------------
# Provider-window report helpers
# ---------------------------------------------------------------------------


def _compact_report_date(value: str) -> str:
    return env_date_value(value, field_name="date").isoformat()


def krx_target_report_window(target: KrxMarketTarget | KrxOfficialMarketTarget) -> dict[str, Any]:
    if isinstance(target, KrxOfficialMarketTarget):
        return {
            "target_ref": krx_official_target_ref(target),
            "market_code": target.market_code,
            "bas_dd": target.bas_dd,
            "ticker_filter_count": len(target.ticker_filter),
            "universe_code": target.universe_code,
            "universe_size": target.universe_size,
            "requested_window_start": _compact_report_date(target.bas_dd),
            "requested_window_end": _compact_report_date(target.bas_dd),
            "source_policy": "HISTORICAL_DAILY_PRICE",
            "source_policy_code": OFFICIAL_KRX_POLICY_CODE,
            "source_code": OFFICIAL_KRX_SOURCE_CODE,
            "precedence_rank": 1,
        }
    return {
        "target_ref": f"PYKRX:{target.ticker}:{target.start_date}-{target.end_date}",
        "ticker": target.ticker,
        "requested_window_start": _compact_report_date(target.start_date),
        "requested_window_end": _compact_report_date(target.end_date),
        "source_policy": "AUXILIARY_HISTORICAL_DAILY_PRICE",
        "source_code": PYKRX_SOURCE_CODE,
        "precedence_rank": 2,
    }


def krx_official_target_report_window(target: KrxOfficialMarketTarget) -> dict[str, Any]:
    return {
        "target_ref": krx_official_target_ref(target),
        "market": target.market_code,
        "bas_dd": target.bas_dd,
        "requested_window_start": _compact_report_date(target.requested_window_start),
        "requested_window_end": _compact_report_date(target.requested_window_end),
        "ticker_filter_count": len(target.ticker_filter),
        "universe_code": target.universe_code,
        "universe_size": target.universe_size,
        "source_policy": "OFFICIAL_DAILY_TRADING_PRICE",
        "source_policy_code": OFFICIAL_KRX_POLICY_CODE,
        "source_code": OFFICIAL_KRX_SOURCE_CODE,
        "redacted_auth": True,
        "precedence_rank": 1,
    }


def dart_target_report_window(target: DartFilingTarget) -> dict[str, Any]:
    target_ref = (
        f"DART:{target.corp_code or target.stock_code}:"
        f"{target.begin_date}-{target.end_date}:{target.report_type or 'all'}"
    )
    return {
        "target_ref": target_ref,
        "corp_code": target.corp_code,
        "stock_code": target.stock_code,
        "requested_window_start": _compact_report_date(target.begin_date),
        "requested_window_end": _compact_report_date(target.end_date),
        "source_policy": "DISCLOSURE_DOCUMENT_WINDOW",
        "page_count": target.page_count,
        "report_type": target.report_type,
    }


def provider_window_report(results: list[StageResult]) -> list[dict[str, Any]]:
    """Collect per-provider window metadata already present in stage details."""

    windows: list[dict[str, Any]] = []
    for result in results:
        detail = result.detail or {}
        provider = detail.get("provider") or result.job_type_code.replace("PROVIDER_", "")
        detail_windows = detail.get("windows")
        if isinstance(detail_windows, list):
            for window in detail_windows:
                if isinstance(window, dict):
                    windows.append({"provider": provider, **window})
            continue
        if "as_of_date" in detail:
            windows.append(
                {
                    "provider": provider,
                    "source_policy": detail.get("source_policy", "CURRENT_OR_REFERENCE"),
                    "requested_window_start": detail.get("as_of_date"),
                    "requested_window_end": detail.get("as_of_date"),
                }
            )
    return windows


# ---------------------------------------------------------------------------
# Post-condition collection
# ---------------------------------------------------------------------------


async def collect_postconditions(
    connection: Any,
    started_at: Any,
    *,
    window_start: date,
    window_end: date,
) -> dict[str, Any]:
    """Collect postcondition evidence with SQL_ID-protected statements."""

    status_rows = await connection.fetch(POSTCONDITION_SQL["batch_job_logs"], started_at)
    readiness = await fetch_one(connection, POSTCONDITION_SQL["readiness"], started_at)
    provider_window = await fetch_one(
        connection,
        POSTCONDITION_SQL["provider_window"],
        window_start,
        window_end,
    )
    rag_readiness = await rag_readiness_snapshot(connection=connection)
    return {
        "batch_job_logs": [dict(row) for row in status_rows],
        "readiness": dict(readiness) if readiness is not None else {},
        "provider_window": dict(provider_window) if provider_window is not None else {},
        "rag_readiness": rag_readiness,
    }


# ---------------------------------------------------------------------------
# Report post-condition checks
# ---------------------------------------------------------------------------


def fatal_results(results: list[StageResult]) -> list[StageResult]:
    """Return stage results that should make the CLI exit nonzero."""

    fatal: list[StageResult] = []
    for result in results:
        if result.stage in MANDATORY_LOCAL_STAGES and result.status_code != "DONE":
            fatal.append(result)
        if result.stage == EMBED_STAGE and result.status_code == "FAILED":
            fatal.append(result)
    return fatal


def provider_strictness_failures(
    *,
    results: list[StageResult],
    postconditions: dict[str, Any],
    stages: tuple[str, ...],
    provider_strictness: str,
) -> list[dict[str, Any]]:
    """Return explicit failures for required/all provider acceptance."""

    failures: list[dict[str, Any]] = []
    provider_results = [
        result
        for result in results
        if result.stage == PROVIDER_STAGE or result.job_type_code.startswith("PROVIDER_")
    ]
    if provider_strictness == PROVIDER_STRICTNESS_ALL:
        for result in provider_results:
            if result.status_code != "DONE":
                failures.append(
                    {
                        "scope": "provider_all",
                        "job_type_code": result.job_type_code,
                        "status_code": result.status_code,
                        "message": "all-provider diagnostic strictness requires DONE evidence",
                    }
                )
        return failures

    if PROVIDER_STAGE in stages:
        by_job_type = {result.job_type_code: result for result in provider_results}
        for job_type_code in sorted(REQUIRED_PROVIDER_JOB_TYPE_CODES):
            result = by_job_type.get(job_type_code)
            if result is None:
                failures.append(
                    {
                        "scope": "provider_required",
                        "job_type_code": job_type_code,
                        "status_code": "NOT_RUN",
                        "message": "required-provider acceptance did not run this provider",
                    }
                )
            elif result.status_code != "DONE":
                failures.append(
                    {
                        "scope": "provider_required",
                        "job_type_code": job_type_code,
                        "status_code": result.status_code,
                        "message": "required-provider acceptance requires DONE provider evidence",
                    }
                )

        provider_window = postconditions.get("provider_window") or {}
        price_days = int(provider_window.get("historical_price_trading_day_count") or 0)
        ecos_rows = int(provider_window.get("ecos_observation_count") or 0)
        dart_sources = int(provider_window.get("dart_document_source_count") or 0)
        if price_days <= 1:
            failures.append(
                {
                    "scope": "provider_required",
                    "job_type_code": "PROVIDER_KRX",
                    "observed_count": price_days,
                    "message": (
                        "required acceptance needs >1 persisted PYKRX/KRX trading day in "
                        "the requested window"
                    ),
                }
            )
        if ecos_rows <= 0:
            failures.append(
                {
                    "scope": "provider_required",
                    "job_type_code": "PROVIDER_ECOS",
                    "observed_count": ecos_rows,
                    "message": "required acceptance needs real ECOS observations in the window",
                }
            )
        if dart_sources <= 0:
            failures.append(
                {
                    "scope": "provider_required",
                    "job_type_code": "PROVIDER_DART",
                    "observed_count": dart_sources,
                    "message": "required acceptance needs real OpenDART document lineage",
                }
            )

    if EMBED_STAGE in stages:
        embed_results = [result for result in results if result.stage == EMBED_STAGE]
        if not embed_results or any(result.status_code != "DONE" for result in embed_results):
            failures.append(
                {
                    "scope": "provider_required",
                    "job_type_code": "EMBEDDING_REFRESH",
                    "status_code": ",".join(result.status_code for result in embed_results)
                    or "NOT_RUN",
                    "message": "required acceptance needs BGE embedding refresh to finish DONE",
                }
            )
    return failures
