"""KRX batch collector functions — pykrx auxiliary + official KRX OpenAPI."""

from __future__ import annotations

import time as time_module
from collections.abc import Iterable
from datetime import date
from typing import Any

from apps.api.harness.batch.collectors import store_market_prices
from apps.api.harness.batch.jobs import BatchCounters, BatchProviderEvidence
from apps.api.harness.external.http import ExternalProviderError
from apps.api.harness.external.public_data import KrxOfficialClient
from apps.api.harness.repositories import batch as batch_repo

from apps.api.harness.batch.providers.krx import (
    KrxMarketTarget,
    KrxOfficialMarketTarget,
    KrxOfficialParseResult,
    _target_requires_multi_day_persistence,
    krx_official_target_detail,
    krx_official_target_ref,
    krx_target_ref,
    krx_target_window_detail,
    parse_krx_market_payload,
    parse_krx_official_basic_info_payload,
    parse_krx_official_market_payload,
    select_krx_top_market_cap_universe,
)
from apps.api.harness.batch.providers import _date


async def collect_krx_market_prices(
    *, connection: Any, targets: Iterable[KrxMarketTarget]
) -> BatchCounters:
    """Collect KRX OHLCV through optional pykrx when explicitly enabled."""

    try:
        from pykrx import stock  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ExternalProviderError("KRX collector requires optional pykrx package") from exc

    counters = {"rows_collected": 0, "rows_skipped": 0, "rows_failed": 0}
    evidences: list[BatchProviderEvidence] = []
    for target in targets:
        payload = stock.get_market_ohlcv_by_date(
            target.start_date,
            target.end_date,
            target.ticker,
        )
        rows = parse_krx_market_payload(payload=payload, target=target)
        target_counters = await store_market_prices(connection, rows)
        for key in counters:
            counters[key] += int(target_counters.get(key, 0))
        row_count = int(target_counters.get("rows_collected", 0))
        detail = krx_target_window_detail(target=target, rows=rows, row_count=row_count)
        if _target_requires_multi_day_persistence(target) and row_count <= 1:
            raise ExternalProviderError(
                "PROVIDER_NO_DATA: KRX/PYKRX persisted fewer than two trading-day rows "
                f"for requested window {target.start_date}-{target.end_date} "
                f"ticker={target.ticker}"
            )
        evidences.append(
            BatchProviderEvidence(
                provider_code="KRX",
                provider_status_code="PROVIDER_DONE" if row_count > 0 else "PROVIDER_NO_DATA",
                target_ref=krx_target_ref(target),
                rows_collected=row_count,
                rows_skipped=int(target_counters.get("rows_skipped", 0)),
                rows_failed=int(target_counters.get("rows_failed", 0)),
                reason_message=None
                if row_count > 0
                else "PYKRX 보조 출처가 적재 가능한 행을 반환하지 않았습니다.",
                provider_detail=detail,
            )
        )
    return BatchCounters(
        rows_collected=counters["rows_collected"],
        rows_skipped=counters["rows_skipped"],
        rows_failed=counters["rows_failed"],
        provider_evidence=tuple(evidences),
    )


async def _collect_krx_official_universe_market_prices(
    *,
    connection: Any,
    client: KrxOfficialClient,
    targets: tuple[KrxOfficialMarketTarget, ...],
    rate_limit_sleep_ms: int,
) -> BatchCounters:
    """Collect official KRX rows once per market/date and persist top-universe coverage."""

    counters = {"rows_collected": 0, "rows_skipped": 0, "rows_failed": 0}
    evidences: list[BatchProviderEvidence] = []
    sleep_seconds = max(rate_limit_sleep_ms, 0) / 1000
    parsed_by_target: list[tuple[KrxOfficialMarketTarget, KrxOfficialParseResult]] = []
    all_rows: list[dict[str, Any]] = []
    for target in targets:
        payload = client.daily_trading(market_code=target.market_code, bas_dd=target.bas_dd)
        parse_result = parse_krx_official_market_payload(payload=payload, target=target)
        parsed_by_target.append((target, parse_result))
        all_rows.extend(parse_result.rows)
        if sleep_seconds:
            time_module.sleep(sleep_seconds)

    if not all_rows:
        for target, parse_result in parsed_by_target:
            evidences.append(
                BatchProviderEvidence(
                    provider_code="KRX",
                    provider_status_code="PROVIDER_NO_DATA",
                    target_ref=krx_official_target_ref(target),
                    rows_collected=0,
                    rows_skipped=parse_result.rows_skipped,
                    rows_failed=parse_result.rows_failed,
                    reason_message="공식 KRX가 유니버스 종목 행을 반환하지 않았습니다.",
                    provider_detail=krx_official_target_detail(
                        target=target,
                        parse_result=parse_result,
                        row_count=0,
                        store_rows_skipped=0,
                        store_rows_failed=0,
                        basic_info_upserted=0,
                        rate_limit_sleep_ms=rate_limit_sleep_ms,
                    ),
                )
            )
        return BatchCounters(rows_failed=1, provider_evidence=tuple(evidences))

    resolved_trading_date = max(row["price_date"] for row in all_rows)
    universe_targets = [target for target in targets if target.universe_code]
    universe_code = universe_targets[0].universe_code or "DOMESTIC_TOP200_MARKET_CAP"
    universe_size = int(universe_targets[0].universe_size or 200)
    exclude_preferred = bool(universe_targets[0].universe_exclude_preferred)
    as_of_rows = [row for row in all_rows if row["price_date"] == resolved_trading_date]
    candidates, selected_members = select_krx_top_market_cap_universe(
        as_of_rows, target_size=universe_size, exclude_preferred=exclude_preferred,
    )
    snapshot = await batch_repo.upsert_market_universe_snapshot(
        connection,
        row={
            "universe_code": universe_code,
            "as_of_date": resolved_trading_date,
            "resolved_trading_date": resolved_trading_date,
            "source_code": "KRX",
            "source_policy_code": "OFFICIAL_KRX_APPROVED",
            "rank_method_code": "MARKET_CAP_DESC",
            "target_size": universe_size,
            "selected_count": len(selected_members),
            "raw_candidate_count": len(candidates),
            "excluded_count": max(len(candidates) - len(selected_members), 0),
            "coverage_status_code": "PENDING",
        },
    )
    snapshot_id = str(snapshot["id"])

    selected_tickers_by_market: dict[str, list[str]] = {}
    for member in selected_members:
        selected_tickers_by_market.setdefault(str(member["market_code"]), []).append(
            str(member["ticker"])
        )

    security_id_by_ticker: dict[str, str] = {}
    basic_info_upserted = 0
    for market_code, tickers in sorted(selected_tickers_by_market.items()):
        basic_payload = client.basic_info(
            market_code=market_code,
            bas_dd=resolved_trading_date.strftime("%Y%m%d"),
        )
        for security in parse_krx_official_basic_info_payload(
            payload=basic_payload,
            market_code=market_code,
            ticker_filter=tuple(sorted(tickers)),
        ):
            upserted = await batch_repo.upsert_krx_official_security(connection, row=security)
            security_id_by_ticker[str(upserted["ticker"])] = str(upserted["id"])
            basic_info_upserted += 1
        if sleep_seconds:
            time_module.sleep(sleep_seconds)

    selected_candidates_by_ticker = {
        str(candidate["ticker"]): candidate for candidate in candidates if candidate["included"]
    }
    for ticker, candidate in sorted(selected_candidates_by_ticker.items()):
        if ticker in security_id_by_ticker or not candidate.get("isin"):
            continue
        upserted = await batch_repo.upsert_krx_official_security(
            connection,
            row={
                "ticker": ticker,
                "isin": candidate["isin"],
                "security_name_kr": candidate["security_name_kr"],
                "market_code": candidate["market_code"],
                "listed_at": None,
            },
        )
        security_id_by_ticker[str(upserted["ticker"])] = str(upserted["id"])
        basic_info_upserted += 1

    for candidate in candidates:
        ticker = str(candidate["ticker"])
        await batch_repo.upsert_market_universe_candidate(
            connection,
            row={
                **candidate,
                "snapshot_id": snapshot_id,
                "security_id": security_id_by_ticker.get(ticker),
            },
        )

    persisted_members: list[dict[str, Any]] = []
    for member in selected_members:
        ticker = str(member["ticker"])
        security_id = security_id_by_ticker.get(ticker)
        if security_id is None:
            counters["rows_skipped"] += 1
            continue
        persisted = await batch_repo.upsert_market_universe_member(
            connection,
            row={**member, "snapshot_id": snapshot_id, "security_id": security_id},
        )
        persisted_members.append(
            {**member, "id": str(persisted["id"]), "security_id": security_id}
        )

    selected_tickers = {str(member["ticker"]) for member in persisted_members}
    bars_by_ticker_date: dict[tuple[str, date], dict[str, Any]] = {}
    target_store_counts: dict[str, dict[str, int]] = {}
    for target, parse_result in parsed_by_target:
        target_ref = krx_official_target_ref(target)
        target_counts = {"rows_collected": 0, "rows_skipped": 0, "rows_failed": 0}
        for row in parse_result.rows:
            if row["ticker"] not in selected_tickers:
                continue
            try:
                inserted = await batch_repo.upsert_market_price(connection, row=row)
            except Exception:  # noqa: BLE001 - per-row provider policy counts failures
                target_counts["rows_failed"] += 1
                counters["rows_failed"] += 1
                continue
            if inserted is None:
                target_counts["rows_skipped"] += 1
                counters["rows_skipped"] += 1
            else:
                target_counts["rows_collected"] += 1
                counters["rows_collected"] += 1
                bars_by_ticker_date[(str(row["ticker"]), row["price_date"])] = inserted
        target_store_counts[target_ref] = target_counts
    if counters["rows_collected"] > 0:
        await batch_repo.mark_price_bars_valid(connection)

    members_by_market: dict[str, list[dict[str, Any]]] = {}
    for member in persisted_members:
        members_by_market.setdefault(str(member["market_code"]), []).append(member)

    expected_member_days = 0
    valid_member_days = 0
    missing_member_days = 0
    for target, parse_result in parsed_by_target:
        calendar_date = _date(target.bas_dd, field_name="BAS_DD")
        expected = parse_result.raw_row_count > 0
        await batch_repo.upsert_market_trading_calendar_day(
            connection,
            row={
                "calendar_date": calendar_date,
                "market_code": target.market_code,
                "source_code": "KRX",
                "source_policy_code": "OFFICIAL_KRX_APPROVED",
                "is_expected_trading_day": expected,
                "is_observed_trading_day": expected,
                "no_trading_reason_code": None if expected else "MARKET_CLOSED_OR_NO_ROWS",
            },
        )
        for member in members_by_market.get(target.market_code, []):
            bar = bars_by_ticker_date.get((str(member["ticker"]), calendar_date))
            has_valid_bar = expected and bar is not None
            if expected:
                expected_member_days += 1
                if has_valid_bar:
                    valid_member_days += 1
                else:
                    missing_member_days += 1
            await batch_repo.upsert_market_universe_coverage_daily(
                connection,
                row={
                    "snapshot_id": snapshot_id,
                    "member_id": member["id"],
                    "security_id": member["security_id"],
                    "market_code": target.market_code,
                    "calendar_date": calendar_date,
                    "is_expected_trading_day": expected,
                    "has_valid_bar": has_valid_bar,
                    "market_price_bar_id": str(bar["id"]) if bar else None,
                    "missing_reason_code": None
                    if has_valid_bar
                    else "PROVIDER_NO_MEMBER_ROW"
                    if expected
                    else "MARKET_CLOSED_OR_NO_ROWS",
                    "quality_status_code": "VALID"
                    if has_valid_bar
                    else "MISSING"
                    if expected
                    else "NO_TRADING",
                },
            )

    coverage_status = (
        "READY"
        if len(persisted_members) >= universe_size
        and expected_member_days > 0
        and missing_member_days == 0
        else "DEGRADED"
        if persisted_members and valid_member_days > 0
        else "BLOCKED"
    )
    await batch_repo.upsert_market_universe_snapshot(
        connection,
        row={
            "universe_code": universe_code,
            "as_of_date": resolved_trading_date,
            "resolved_trading_date": resolved_trading_date,
            "source_code": "KRX",
            "source_policy_code": "OFFICIAL_KRX_APPROVED",
            "rank_method_code": "MARKET_CAP_DESC",
            "target_size": universe_size,
            "selected_count": len(persisted_members),
            "raw_candidate_count": len(candidates),
            "excluded_count": max(len(candidates) - len(persisted_members), 0),
            "coverage_status_code": coverage_status,
        },
    )

    for target, parse_result in parsed_by_target:
        target_ref = krx_official_target_ref(target)
        target_counts = target_store_counts.get(target_ref, {})
        row_count = int(target_counts.get("rows_collected", 0))
        detail = krx_official_target_detail(
            target=target,
            parse_result=parse_result,
            row_count=row_count,
            store_rows_skipped=int(target_counts.get("rows_skipped", 0)),
            store_rows_failed=int(target_counts.get("rows_failed", 0)),
            basic_info_upserted=basic_info_upserted,
            rate_limit_sleep_ms=rate_limit_sleep_ms,
        )
        detail.update(
            {
                "universe_code": universe_code,
                "universe_size": universe_size,
                "selected_count": len(persisted_members),
                "raw_candidate_count": len(candidates),
                "coverage_status_code": coverage_status,
                "expected_member_days": expected_member_days,
                "valid_member_days": valid_member_days,
                "missing_member_days": missing_member_days,
            }
        )
        evidences.append(
            BatchProviderEvidence(
                provider_code="KRX",
                provider_status_code="PROVIDER_DONE" if row_count > 0 else "PROVIDER_NO_DATA",
                target_ref=target_ref,
                rows_collected=row_count,
                rows_skipped=parse_result.rows_skipped
                + int(target_counts.get("rows_skipped", 0)),
                rows_failed=parse_result.rows_failed + int(target_counts.get("rows_failed", 0)),
                reason_message=None
                if row_count > 0
                else "공식 KRX가 유니버스 구성 종목 행을 반환하지 않았습니다.",
                provider_detail=detail,
            )
        )
    return BatchCounters(
        rows_collected=counters["rows_collected"],
        rows_skipped=counters["rows_skipped"],
        rows_failed=counters["rows_failed"],
        provider_evidence=tuple(evidences),
    )


async def collect_krx_official_market_prices(
    *,
    connection: Any,
    client: KrxOfficialClient,
    targets: Iterable[KrxOfficialMarketTarget],
    rate_limit_sleep_ms: int,
) -> BatchCounters:
    """Collect official KRX OpenAPI daily prices with fail-closed evidence."""

    target_tuple = tuple(targets)
    if any(target.universe_code for target in target_tuple):
        return await _collect_krx_official_universe_market_prices(
            connection=connection,
            client=client,
            targets=target_tuple,
            rate_limit_sleep_ms=rate_limit_sleep_ms,
        )

    counters = {"rows_collected": 0, "rows_skipped": 0, "rows_failed": 0}
    evidences: list[BatchProviderEvidence] = []
    sleep_seconds = max(rate_limit_sleep_ms, 0) / 1000
    for target in target_tuple:
        basic_info_upserted = 0
        basic_payload = client.basic_info(market_code=target.market_code, bas_dd=target.bas_dd)
        for security in parse_krx_official_basic_info_payload(
            payload=basic_payload,
            market_code=target.market_code,
            ticker_filter=target.ticker_filter,
        ):
            await batch_repo.upsert_krx_official_security(connection, row=security)
            basic_info_upserted += 1
        if sleep_seconds:
            time_module.sleep(sleep_seconds)

        payload = client.daily_trading(market_code=target.market_code, bas_dd=target.bas_dd)
        parse_result = parse_krx_official_market_payload(payload=payload, target=target)
        target_counters = await store_market_prices(connection, parse_result.rows)
        row_count = int(target_counters.get("rows_collected", 0))
        rows_skipped = parse_result.rows_skipped + int(target_counters.get("rows_skipped", 0))
        rows_failed = parse_result.rows_failed + int(target_counters.get("rows_failed", 0))
        counters["rows_collected"] += row_count
        counters["rows_skipped"] += rows_skipped
        counters["rows_failed"] += rows_failed
        detail = krx_official_target_detail(
            target=target,
            parse_result=parse_result,
            row_count=row_count,
            store_rows_skipped=int(target_counters.get("rows_skipped", 0)),
            store_rows_failed=int(target_counters.get("rows_failed", 0)),
            basic_info_upserted=basic_info_upserted,
            rate_limit_sleep_ms=rate_limit_sleep_ms,
        )
        evidences.append(
            BatchProviderEvidence(
                provider_code="KRX",
                provider_status_code="PROVIDER_DONE" if row_count > 0 else "PROVIDER_NO_DATA",
                target_ref=krx_official_target_ref(target),
                rows_collected=row_count,
                rows_skipped=rows_skipped,
                rows_failed=rows_failed,
                reason_message=None
                if row_count > 0
                else "공식 KRX가 적재 가능한 행을 반환하지 않았습니다.",
                provider_detail=detail,
            )
        )
        if sleep_seconds:
            time_module.sleep(sleep_seconds)
    return BatchCounters(
        rows_collected=counters["rows_collected"],
        rows_skipped=counters["rows_skipped"],
        rows_failed=counters["rows_failed"],
        provider_evidence=tuple(evidences),
    )
