"""Operator-facing batch pipeline runner — entry point and orchestration.

Delegates to submodules:
  - runner_provider: provider lifecycle (KRX, ECOS, DART, BROKER, DATA_GO_KR)
  - runner_transform: transform and BGE embed stages
  - runner_derived: aftercare/NBA derived and house-view stages
  - runner_readiness: readiness helpers, post-conditions, and result aggregation

Key policy strings referenced in runner_provider and runner_readiness:
  env gate:       HARNESS_BATCH_KRX_SOURCE
  official KRX:   OFFICIAL_KRX_APPROVED
  skip status:    PROVIDER_SKIPPED_DISABLED
  source labels:  pykrx 비공식 보조 소스, KRX 공식 OpenAPI
"""

from __future__ import annotations

# ruff: noqa: E402,I001
# When invoked as __main__, Python prepends the script dir to sys.path.
# batch/types.py shadows the stdlib `types` module and causes a circular import.
# sys is a C built-in (safe); strip the script dir before any other imports.
import sys
import os as _os
_script_dir = _os.path.dirname(_os.path.abspath(__file__))
sys.path = [p for p in sys.path if _os.path.abspath(p or _os.getcwd()) != _script_dir]

import argparse
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.core.config import load_config
from apps.api.harness.core.db import create_pool
from apps.api.harness.core.logging import redact_secret_text
from apps.api.harness.core.redis_client import create_redis_client

from apps.api.harness.batch.types import (
    COUNT_ACTIVE_HOUSE_VIEWS_SQL,
    DEFAULT_BATCH_LOOKBACK_DAYS,
    DEFAULT_STAGES,
    EMBED_STAGE,
    GET_LATEST_KRX_TRADING_DAY_SQL,
    LIST_ACTIVE_DART_SECURITY_TARGETS_SQL,
    OFFICIAL_KRX_POLICY_CODE,
    OFFICIAL_KRX_SOURCE_CODE,
    POSTCONDITION_SQL,
    PROVIDER_STAGE,
    PROVIDER_STRICTNESS_REQUIRED,
    PROVIDER_STRICTNESS_VALUES,
    BatchRunSummary,
    KrxSourcePolicy,
    StageResult,
    compact_date,
    csv_values,
    env_bool,
    env_date,
    env_date_value,
    env_int,
    krx_lookback_days,
    latest_weekday_on_or_before,
    missing_env,
    normalize_provider_strictness,
    parse_dart_targets,
    parse_data_go_kr_targets,
    parse_ecos_targets,
    parse_broker_targets,
    parse_krx_official_targets,
    parse_krx_targets,
    parse_stage_list,
    provider_contract_matrix,
    provider_governance_matrix,
    resolve_krx_source_policy,
    utc_now,
)
from apps.api.harness.batch.runner_provider import (
    build_dart_targets,
    latest_krx_trading_day,
    pykrx_dependency_available,
    run_provider_stage,
)
from apps.api.harness.batch.runner_transform import (
    resolve_embedding_batch_size,
    run_embed_stage,
    run_transform_stage,
)
from apps.api.harness.batch.runner_derived import (
    run_derived_stage,
    run_house_view_stage,
)
from apps.api.harness.batch.runner_readiness import (
    collect_postconditions,
    create_skipped_stage_log,
    fatal_results,
    krx_official_target_report_window,
    krx_target_report_window,
    provider_strictness_failures,
    provider_window_report,
    resolve_provider_strictness,
    resolve_strict_external,
    run_local_stage,
    run_seed_stage,
    summarize_results,
)


async def run_pipeline(
    *,
    profile: str,
    stages: tuple[str, ...],
    report_path: Path,
    env_path: Path,
    embedding_batch_size: int | None,
    strict_external: bool | None = None,
    lookback_days: int = DEFAULT_BATCH_LOOKBACK_DAYS,
    as_of_date: date | None = None,
    provider_strictness: str | None = None,
) -> dict[str, Any]:
    """Execute selected stages and write the operator report."""

    started_at = utc_now()
    config = load_config(env_path)
    resolved_embedding_batch_size = resolve_embedding_batch_size(embedding_batch_size)
    resolved_lookback_days = max(int(lookback_days), 1)
    resolved_as_of_date = as_of_date or date.today()
    window_start = resolved_as_of_date - timedelta(days=resolved_lookback_days)
    window_end = resolved_as_of_date
    strict_external_resolved = resolve_strict_external(
        explicit=strict_external,
        app_env=config.runtime.app_env,
    )
    provider_strictness_resolved = resolve_provider_strictness(
        explicit=provider_strictness,
        strict_external=strict_external_resolved,
    )
    pool = await create_pool(config.database, min_size=1, max_size=1)
    redis_client = create_redis_client(config.redis)
    try:
        redis_client.ping()
        async with pool.acquire() as connection:
            results: list[StageResult] = []
            for stage in stages:
                if stage == "seed":
                    results.append(await run_seed_stage(connection, redis_client, profile=profile))
                elif stage == PROVIDER_STAGE:
                    results.extend(
                        await run_provider_stage(
                            connection,
                            redis_client,
                            as_of_date=resolved_as_of_date,
                            lookback_days=resolved_lookback_days,
                            provider_strictness=provider_strictness_resolved,
                        )
                    )
                elif stage == "transform":
                    results.append(await run_transform_stage(connection, redis_client))
                elif stage == EMBED_STAGE:
                    results.append(
                        await run_embed_stage(
                            connection,
                            redis_client,
                            config=config,
                            batch_size=resolved_embedding_batch_size,
                        )
                    )
                elif stage == "derived":
                    results.append(await run_derived_stage(connection, redis_client))
                elif stage == "house-view":
                    results.append(await run_house_view_stage(connection))
                else:  # pragma: no cover - guarded by parse_stage_list
                    raise ValueError(f"Unsupported batch stage: {stage}")

            postconditions = await collect_postconditions(
                connection,
                started_at,
                window_start=window_start,
                window_end=window_end,
            )
    finally:
        await pool.close()
        redis_client.close()

    finished_at = utc_now()
    summary = summarize_results(results)
    failures = fatal_results(results)
    exit_code = (
        1
        if failures
        else summary.exit_code(
            strict_external=strict_external_resolved,
            provider_strictness=provider_strictness_resolved,
        )
    )
    strictness_failures = provider_strictness_failures(
        results=results,
        postconditions=postconditions,
        stages=stages,
        provider_strictness=provider_strictness_resolved,
    )
    report = {
        "schema_version": "1.0",
        "profile": profile,
        "stages": list(stages),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "strict_external": strict_external_resolved,
        "provider_strictness": provider_strictness_resolved,
        "requested_lookback_days": resolved_lookback_days,
        "as_of_date": resolved_as_of_date.isoformat(),
        "provider_windows": provider_window_report(results),
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "provider_contracts": provider_contract_matrix(),
        "provider_governance": provider_governance_matrix(),
        **summary.as_dict(),
        "fatal_failures": [failure.as_dict() for failure in failures],
        "provider_strictness_failures": strictness_failures,
        "results": [result.as_dict() for result in results],
        "postconditions": postconditions,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    return report


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(description="Run the Harness batch pipeline.")
    parser.add_argument("--profile", default="full-mvp")
    parser.add_argument("--stages", help="Comma-separated subset of batch stages.")
    parser.add_argument("--all-stages", action="store_true", help="Run every supported stage.")
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / ".omx" / "reports" / "batch" / "latest.json",
    )
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env")
    parser.add_argument("--embedding-batch-size", type=int, default=None)
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_BATCH_LOOKBACK_DAYS,
        help="Requested recent-day provider window when provider-specific env dates are absent.",
    )
    parser.add_argument(
        "--as-of-date",
        type=lambda value: env_date_value(value, field_name="as_of_date"),
        default=None,
        help="Batch as-of date (YYYY-MM-DD or YYYYMMDD) used to resolve rolling windows.",
    )
    parser.add_argument(
        "--provider-strictness",
        choices=sorted(PROVIDER_STRICTNESS_VALUES),
        default=None,
        help=(
            "required accepts required providers only; "
            "all requires every configured provider result."
        ),
    )
    strict_group = parser.add_mutually_exclusive_group()
    strict_group.add_argument(
        "--strict-external",
        dest="strict_external",
        action="store_true",
        help="Exit 2 when provider evidence is SKIPPED/FAILED even if local stages pass.",
    )
    strict_group.add_argument(
        "--no-strict-external",
        dest="strict_external",
        action="store_false",
        help="Override APP_ENV=production or HARNESS_PROVIDER_STRICT for local break-glass runs.",
    )
    parser.set_defaults(strict_external=None)
    return parser.parse_args()


async def main_async() -> int:
    """CLI boundary with sanitized fatal messages."""

    args = parse_args()
    try:
        stages = parse_stage_list(args.stages, all_stages=args.all_stages)
        report = await run_pipeline(
            profile=args.profile,
            stages=stages,
            report_path=args.report,
            env_path=args.env_file,
            embedding_batch_size=args.embedding_batch_size,
            strict_external=args.strict_external,
            lookback_days=args.lookback_days,
            as_of_date=args.as_of_date,
            provider_strictness=args.provider_strictness,
        )
    except Exception as exc:  # noqa: BLE001 - CLI prints sanitized operator error
        print(f"batch_pipeline=failed reason={redact_secret_text(str(exc))}", file=sys.stderr)
        return 2

    print(json.dumps(report, ensure_ascii=False, default=str))
    return int(report["exit_code"])


def main() -> None:
    """Run the async CLI."""

    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
