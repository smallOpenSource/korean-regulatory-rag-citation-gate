"""Derived and house-view batch pipeline stages."""

from __future__ import annotations

from typing import Any

from apps.api.harness.batch.documents import refresh_aftercare_and_nba
from apps.api.harness.repositories import batch as batch_repo
from apps.api.harness.repositories import house_views as house_view_repo

from .runner_readiness import create_skipped_stage_log, run_local_stage
from .types import StageResult


async def run_derived_stage(connection: Any, redis_client: Any) -> StageResult:
    """Refresh derived aftercare/NBA rows from persisted data."""

    return await run_local_stage(
        connection,
        redis_client,
        stage="derived",
        job_name="aftercare_nba_derived_refresh",
        job_type_code="DERIVED_REFRESH",
        work=lambda: refresh_aftercare_and_nba(connection=connection),
    )


async def run_house_view_stage(connection: Any) -> StageResult:
    """Record current deterministic/manual house-view readiness evidence."""

    active = await house_view_repo.get_active_house_view(connection)
    if active is None:
        return await create_skipped_stage_log(
            connection,
            stage="house-view",
            job_name="house_view_readiness_snapshot",
            job_type_code="HOUSE_VIEW_REFRESH",
            reason="No ACTIVE house view exists after selected stages",
            detail={"active_house_view": False},
        )
    log = await batch_repo.create_batch_log(
        connection,
        job_name="house_view_readiness_snapshot",
        job_type_code="HOUSE_VIEW_REFRESH",
    )
    done = await batch_repo.mark_batch_done(
        connection,
        log_id=str(log["id"]),
        rows={"rows_collected": 1, "rows_skipped": 0, "rows_failed": 0},
    )
    return StageResult.from_batch_log(
        stage="house-view",
        batch_log=done,
        detail={
            "active_house_view": True,
            "house_view_id": str(active["id"]),
            "title": active["title"],
            "status_code": active["status_code"],
        },
    )
