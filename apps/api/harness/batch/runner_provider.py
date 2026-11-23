"""Provider lifecycle stage for the batch pipeline.

Handles KRX/PYKRX source policy, DART target discovery, and the provider
stage orchestration (BROKER, ECOS, DATA_GO_KR, KRX, DART).
"""

from __future__ import annotations

import importlib.util
import os
from datetime import date, timedelta
from typing import Any

from apps.api.harness.batch.jobs import (
    BatchCounters,
    persist_batch_log_provider_evidence,
)
from apps.api.harness.batch.providers import (
    collect_dart_raw_documents,
    collect_data_go_kr_market_prices,
    collect_ecos_macro_indicators,
    collect_broker_market_prices,
    run_provider_job,
)
from apps.api.harness.batch.providers.krx_collector import (
    collect_krx_market_prices,
    collect_krx_official_market_prices,
)
from apps.api.harness.core.db import fetch_all, fetch_one
from apps.api.harness.external.broker import BrokerConfig, BrokerReadOnlyClient
from apps.api.harness.external.public_data import (
    DartClient,
    DataGoKrClient,
    EcosClient,
    KrxOfficialClient,
)

from .runner_readiness import (
    create_skipped_stage_log,
    dart_target_report_window,
    krx_official_target_report_window,
    krx_target_report_window,
)
from .types import (
    DEFAULT_LOCK_TTL_SECONDS,
    GET_LATEST_KRX_TRADING_DAY_SQL,
    LIST_ACTIVE_DART_SECURITY_TARGETS_SQL,
    OFFICIAL_KRX_SOURCE_CODE,
    StageResult,
    dart_explicit_target_env_set,
    dart_target_dates,
    compact_date,
    env_bool,
    env_int,
    missing_env,
    parse_dart_targets,
    parse_data_go_kr_targets,
    parse_ecos_targets,
    parse_broker_targets,
    parse_krx_official_targets,
    parse_krx_targets,
)


def pykrx_dependency_available() -> bool:
    """Return whether optional pykrx is importable without importing provider code."""

    return importlib.util.find_spec("pykrx") is not None


async def build_dart_targets(
    connection: Any, today: date | None = None, *, default_lookback_days: int | None = None
) -> tuple[Any, ...]:
    """Build DART targets, preferring active securities plus corpCode discovery."""

    if dart_explicit_target_env_set():
        return parse_dart_targets(
            today, include_default=True, default_lookback_days=default_lookback_days
        )

    begin_date, end_date = dart_target_dates(today, default_lookback_days=default_lookback_days)
    page_count = env_int("HARNESS_BATCH_DART_PAGE_COUNT", default=100, minimum=1, maximum=100)
    rows = await fetch_all(connection, LIST_ACTIVE_DART_SECURITY_TARGETS_SQL, 20)
    stock_codes = tuple(str(row["ticker"]) for row in rows if str(row["ticker"]).strip())
    if not stock_codes:
        return parse_dart_targets(
            today, include_default=True, default_lookback_days=default_lookback_days
        )
    from apps.api.harness.batch.providers import DartFilingTarget

    return tuple(
        DartFilingTarget(
            corp_code=None,
            stock_code=stock_code,
            begin_date=begin_date,
            end_date=end_date,
            page_count=page_count,
        )
        for stock_code in stock_codes
    )


async def latest_krx_trading_day(connection: Any, today: date) -> date:
    """Resolve the latest known KRX trading day, falling back to last weekday."""

    from .types import latest_weekday_on_or_before

    row = await fetch_one(connection, GET_LATEST_KRX_TRADING_DAY_SQL, today)
    if row is not None and row["calendar_date"] is not None:
        return row["calendar_date"]
    return latest_weekday_on_or_before(today)


async def run_provider_stage(
    connection: Any,
    redis_client: Any,
    *,
    as_of_date: date,
    lookback_days: int,
    provider_strictness: str,
) -> list[StageResult]:
    """Run configured real providers or persist SKIPPED evidence."""

    today = as_of_date
    window_start = today - timedelta(days=max(int(lookback_days), 1))
    window_end = today
    results: list[StageResult] = []

    broker_missing = missing_env(("BROKER_BASE_URL", "BROKER_APP_KEY", "BROKER_APP_SECRET"))
    if broker_missing:
        results.append(
            await create_skipped_stage_log(
                connection,
                stage="provider",
                job_name="broker_market_collector",
                job_type_code="PROVIDER_BROKER",
                reason=f"Provider collector requires configured BROKER credentials: {broker_missing}",
                detail={
                    "provider": "BROKER",
                    "configured": False,
                    "source_policy": "CURRENT_SNAPSHOT",
                    "as_of_date": today.isoformat(),
                    "provider_strictness": provider_strictness,
                },
            )
        )
    else:
        broker_client = BrokerReadOnlyClient(BrokerConfig.from_env(), redis_client=redis_client)
        broker_log = await run_provider_job(
            connection=connection,
            redis_client=redis_client,
            job_name="broker_market_collector",
            job_type_code="PROVIDER_BROKER",
            ttl_seconds=DEFAULT_LOCK_TTL_SECONDS,
            work=lambda: collect_broker_market_prices(
                connection=connection,
                client=broker_client,
                targets=parse_broker_targets(),
                fallback_date=today,
            ),
        )
        results.append(
            StageResult.from_batch_log(
                stage="provider",
                batch_log=broker_log,
                detail={
                    "provider": "BROKER",
                    "configured": True,
                    "source_policy": "CURRENT_SNAPSHOT",
                    "as_of_date": today.isoformat(),
                    "snapshot_count": int(broker_log.get("rows_collected") or 0),
                    "not_historical_reason": "BROKER quote endpoint is current/as-of snapshot only",
                    "provider_strictness": provider_strictness,
                },
            )
        )

    ecos_missing = missing_env(("ECOS_API_BASE_URL", "ECOS_API_KEY"))
    if ecos_missing:
        results.append(
            await create_skipped_stage_log(
                connection,
                stage="provider",
                job_name="ecos_macro_collector",
                job_type_code="PROVIDER_ECOS",
                reason=f"Provider collector requires configured ECOS credentials: {ecos_missing}",
                detail={
                    "provider": "ECOS",
                    "configured": False,
                    "requested_lookback_days": lookback_days,
                    "as_of_date": today.isoformat(),
                    "provider_strictness": provider_strictness,
                },
            )
        )
    else:
        ecos_client = EcosClient.from_env()
        ecos_log = await run_provider_job(
            connection=connection,
            redis_client=redis_client,
            job_name="ecos_macro_collector",
            job_type_code="PROVIDER_ECOS",
            ttl_seconds=DEFAULT_LOCK_TTL_SECONDS,
            work=lambda: collect_ecos_macro_indicators(
                connection=connection,
                client=ecos_client,
                targets=parse_ecos_targets(today, default_lookback_days=lookback_days),
            ),
        )
        results.append(
            StageResult.from_batch_log(
                stage="provider",
                batch_log=ecos_log,
                detail={
                    "provider": "ECOS",
                    "configured": True,
                    "requested_lookback_days": lookback_days,
                    "as_of_date": today.isoformat(),
                    "provider_strictness": provider_strictness,
                },
            )
        )

    data_go_missing = missing_env(
        (
            "DATA_GO_KR_API_BASE_URL",
            "DATA_GO_KR_SERVICE_KEY_ENCODING",
        )
    )
    if not os.getenv("HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON", "").strip():
        data_go_missing.extend(
            missing_env(
                (
                    "DATA_GO_KR_MARKET_PATH",
                    "DATA_GO_KR_TICKER_FIELD",
                    "DATA_GO_KR_DATE_FIELD",
                    "DATA_GO_KR_CLOSE_FIELD",
                )
            )
        )
    data_go_targets = parse_data_go_kr_targets() if not data_go_missing else ()
    if data_go_missing or not data_go_targets:
        missing_reason = data_go_missing or ["HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON"]
        results.append(
            await create_skipped_stage_log(
                connection,
                stage="provider",
                job_name="data_go_kr_market_collector",
                job_type_code="PROVIDER_DATA_GO_KR",
                reason=(
                    "Provider collector requires configured DATA_GO_KR endpoint, key, "
                    f"and field mapping: {missing_reason}"
                ),
                detail={
                    "provider": "DATA_GO_KR",
                    "configured": False,
                    "source_policy": "AS_OF_REFERENCE",
                    "as_of_date": today.isoformat(),
                    "provider_strictness": provider_strictness,
                },
            )
        )
    else:
        data_go_client = DataGoKrClient.from_env()
        data_go_log = await run_provider_job(
            connection=connection,
            redis_client=redis_client,
            job_name="data_go_kr_market_collector",
            job_type_code="PROVIDER_DATA_GO_KR",
            ttl_seconds=DEFAULT_LOCK_TTL_SECONDS,
            work=lambda: collect_data_go_kr_market_prices(
                connection=connection,
                client=data_go_client,
                targets=data_go_targets,
            ),
        )
        results.append(
            StageResult.from_batch_log(
                stage="provider",
                batch_log=data_go_log,
                detail={
                    "provider": "DATA_GO_KR",
                    "configured": True,
                    "source_policy": "AS_OF_REFERENCE",
                    "as_of_date": today.isoformat(),
                    "reference_count": int(data_go_log.get("rows_collected") or 0),
                    "not_historical_reason": (
                        "Data.go.kr listed-stock endpoint is base-date/reference oriented"
                    ),
                    "provider_strictness": provider_strictness,
                },
            )
        )

    from .types import resolve_krx_source_policy

    krx_policy = resolve_krx_source_policy(
        enabled=env_bool("HARNESS_BATCH_KRX_ENABLED", default=False),
        requested_source=os.getenv("HARNESS_BATCH_KRX_SOURCE"),
        policy_code=os.getenv("HARNESS_BATCH_KRX_POLICY"),
        pykrx_available=pykrx_dependency_available(),
        official_env_missing=missing_env(("KRX_API_BASE_URL", "KRX_API_KEY")),
    )
    if not krx_policy.runnable:
        results.append(
            await create_skipped_stage_log(
                connection,
                stage="provider",
                job_name="krx_market_collector",
                job_type_code="PROVIDER_KRX",
                reason=krx_policy.reason or "KRX/PYKRX source policy is disabled",
                detail={
                    **krx_policy.detail(),
                    "configured": False,
                    "source_policy": (
                        "HISTORICAL_DAILY_PRICE"
                        if krx_policy.requested_source == OFFICIAL_KRX_SOURCE_CODE
                        else "AUXILIARY_HISTORICAL_DAILY_PRICE"
                    ),
                    "requested_lookback_days": lookback_days,
                    "as_of_date": as_of_date.isoformat(),
                    "requested_window_start": window_start.isoformat(),
                    "requested_window_end": window_end.isoformat(),
                },
            )
        )
    else:
        krx_trading_day = await latest_krx_trading_day(connection, today)
        official_targets: tuple[Any, ...] = ()
        if krx_policy.requested_source == OFFICIAL_KRX_SOURCE_CODE:
            official_targets = parse_krx_official_targets(
                today,
                default_trading_day=krx_trading_day,
                lookback_days=lookback_days,
            )
            krx_targets = ()
            official_client = KrxOfficialClient.from_env()

            async def work() -> BatchCounters:
                return await collect_krx_official_market_prices(
                    connection=connection,
                    client=official_client,
                    targets=official_targets,
                    rate_limit_sleep_ms=env_int(
                        "KRX_API_RATE_LIMIT_SLEEP_MS", default=200, minimum=0, maximum=60000
                    ),
                )

        else:
            krx_targets = parse_krx_targets(
                today,
                default_trading_day=krx_trading_day,
                lookback_days=lookback_days,
            )

            async def work() -> BatchCounters:
                return await collect_krx_market_prices(
                    connection=connection,
                    targets=krx_targets,
                )

        krx_log = await run_provider_job(
            connection=connection,
            redis_client=redis_client,
            job_name="krx_market_collector",
            job_type_code="PROVIDER_KRX",
            ttl_seconds=DEFAULT_LOCK_TTL_SECONDS,
            work=work,
        )
        krx_detail = {
            **krx_policy.detail(),
            "configured": True,
            "default_trading_day": compact_date(krx_trading_day),
            "target_count": (
                len(official_targets)
                if krx_policy.requested_source == OFFICIAL_KRX_SOURCE_CODE
                else len(krx_targets)
            ),
            "requested_lookback_days": lookback_days,
            "as_of_date": today.isoformat(),
            "provider_strictness": provider_strictness,
            "windows": (
                [krx_official_target_report_window(target) for target in official_targets]
                if krx_policy.requested_source == OFFICIAL_KRX_SOURCE_CODE
                else [krx_target_report_window(target) for target in krx_targets]
            ),
        }
        if krx_log["status_code"] != "DONE":
            krx_detail["provider_status_code"] = "PROVIDER_FAILED_NETWORK"
        krx_evidence = await persist_batch_log_provider_evidence(
            connection,
            batch_log=krx_log,
            detail=krx_detail,
        )
        if krx_evidence is not None:
            krx_log["provider_evidence"] = [krx_evidence]
        results.append(
            StageResult.from_batch_log(
                stage="provider",
                batch_log=krx_log,
                detail=krx_detail,
            )
        )

    dart_missing = missing_env(("DART_API_BASE_URL", "DART_API_KEY"))
    if dart_missing:
        results.append(
            await create_skipped_stage_log(
                connection,
                stage="provider",
                job_name="dart_disclosure_collector",
                job_type_code="PROVIDER_DART",
                reason=f"Provider collector requires configured DART credentials: {dart_missing}",
                detail={
                    "provider": "DART",
                    "configured": False,
                    "source_policy": "DISCLOSURE_WINDOW",
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                },
            )
        )
    else:
        dart_client = DartClient.from_env()
        dart_evidence: list[dict[str, Any]] = []
        dart_targets = await build_dart_targets(
            connection, today, default_lookback_days=lookback_days
        )
        dart_log = await run_provider_job(
            connection=connection,
            redis_client=redis_client,
            job_name="dart_disclosure_collector",
            job_type_code="PROVIDER_DART",
            ttl_seconds=DEFAULT_LOCK_TTL_SECONDS,
            work=lambda: collect_dart_raw_documents(
                connection=connection,
                client=dart_client,
                targets=dart_targets,
                evidence=dart_evidence,
            ),
        )
        results.append(
            StageResult.from_batch_log(
                stage="provider",
                batch_log=dart_log,
                detail={
                    "provider": "DART",
                    "configured": True,
                    "source_policy": "DISCLOSURE_WINDOW",
                    "window_start": window_start.isoformat(),
                    "window_end": window_end.isoformat(),
                    "target_count": len(dart_targets),
                    "requested_lookback_days": lookback_days,
                    "as_of_date": today.isoformat(),
                    "provider_strictness": provider_strictness,
                    "windows": [dart_target_report_window(target) for target in dart_targets],
                    "provider_evidence": dart_evidence,
                },
            )
        )

    return results
