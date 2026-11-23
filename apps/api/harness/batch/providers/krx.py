"""KRX batch provider parsers — pykrx auxiliary + official KRX OpenAPI."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.api.harness.external.http import ExternalProviderError
from apps.api.harness.external.public_data import KrxOfficialClient

# Shared field-parsing utilities defined in package __init__ (safe: __init__
# defines these before executing `from .krx import *`).
from apps.api.harness.batch.providers import (  # noqa: E402
    _date,
    _decimal,
    _domestic_equity_identifier,
    _optional_decimal,
)


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KrxMarketTarget:
    ticker: str
    start_date: str
    end_date: str


@dataclass(frozen=True)
class KrxOfficialMarketTarget:
    market_code: str
    bas_dd: str
    ticker_filter: tuple[str, ...]
    requested_window_start: str
    requested_window_end: str
    universe_code: str | None = None
    universe_size: int | None = None
    universe_exclude_preferred: bool = True


@dataclass(frozen=True)
class KrxOfficialParseResult:
    rows: list[dict[str, Any]]
    rows_skipped: int
    rows_failed: int
    raw_row_count: int
    ticker_filter_count: int


def _market_rows(payload: Any) -> list[tuple[Mapping[str, Any], str | None]]:
    """Return all rows from a dict-like or pandas-like KRX market payload."""

    if isinstance(payload, Mapping):
        return [(payload, None)]
    if bool(getattr(payload, "empty", False)):
        raise ExternalProviderError("KRX response contains no market rows")
    if hasattr(payload, "iterrows"):
        rows: list[tuple[Mapping[str, Any], str | None]] = []
        for index_value, row in payload.iterrows():
            if not hasattr(row, "to_dict"):
                raise ExternalProviderError("KRX response row is not dict-like")
            rows.append((row.to_dict(), str(index_value)[:10]))
        if rows:
            return rows
    if hasattr(payload, "to_dict"):
        records = payload.to_dict("records")
        if isinstance(records, list) and all(isinstance(row, Mapping) for row in records):
            return [(row, None) for row in records]
    raise ExternalProviderError("KRX response missing tabular market rows")


def parse_krx_market_payload(*, payload: Any, target: KrxMarketTarget) -> list[dict[str, Any]]:
    """Convert a KRX/pykrx OHLCV payload into market_price_bars rows.

    PyKRX returns a pandas DataFrame for date ranges. Each trading-day row must
    be persisted independently so a recent-30-day request cannot collapse into a
    single latest-row false green.
    """

    parsed: list[dict[str, Any]] = []
    for row, index_date in _market_rows(payload):
        price_date = row.get("날짜") or row.get("date") or index_date or target.end_date
        parsed.append(
            {
                "ticker": _domestic_equity_identifier(target.ticker, field_name="ticker"),
                "source_code": "PYKRX",
                "price_date": _date(price_date, field_name="date"),
                "open_price": _optional_decimal(row.get("시가") or row.get("open")),
                "high_price": _optional_decimal(row.get("고가") or row.get("high")),
                "low_price": _optional_decimal(row.get("저가") or row.get("low")),
                "close_price": _decimal(row.get("종가") or row.get("close"), field_name="close"),
                "volume": _optional_decimal(row.get("거래량") or row.get("volume")),
            }
        )
    return parsed


def _official_outblock_rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = payload.get("OutBlock_1")
    if rows is None:
        rows = payload.get("outBlock_1") or payload.get("output") or payload.get("rows")
    if rows is None:
        result = payload.get("RESULT") or payload.get("result")
        if isinstance(result, Mapping):
            code = str(result.get("CODE") or result.get("code") or "").upper()
            message = str(result.get("MESSAGE") or result.get("message") or "")
            if code and code not in {"INFO-000", "000", "SUCCESS"}:
                raise ExternalProviderError(
                    f"PROVIDER_FAILED_SCHEMA: KRX official payload result={code} {message}"
                )
        raise ExternalProviderError(
            "PROVIDER_FAILED_SCHEMA: KRX official payload missing OutBlock_1"
        )
    if isinstance(rows, Mapping):
        rows = [rows]
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ExternalProviderError("PROVIDER_FAILED_SCHEMA: KRX official OutBlock_1 is not rows")
    return list(rows)


def _krx_decimal_or_none(value: Any, *, zero_as_none: bool) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-"}:
        return None
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError) as exc:
        raise ExternalProviderError(
            "PROVIDER_FAILED_SCHEMA: KRX official numeric field invalid"
        ) from exc
    if zero_as_none and number == 0:
        return None
    return number


def _krx_short_code(row: Mapping[str, Any]) -> str:
    short_code = str(row.get("ISU_SRT_CD") or row.get("isuSrtCd") or "").strip()
    if short_code:
        return _domestic_equity_identifier(short_code, field_name="ISU_SRT_CD")
    return _domestic_equity_identifier(
        row.get("ISU_CD") or row.get("ISU_SRT_CD") or row.get("isuCd"),
        field_name="ISU_CD",
    )


def _krx_isin_code(row: Mapping[str, Any]) -> str | None:
    value = str(row.get("ISU_CD") or row.get("ISIN_CODE") or row.get("ISIN_CD") or "").strip()
    return value if re.match(r"^KR[0-9A-Z]{10}$", value) else None


def _krx_security_name(row: Mapping[str, Any]) -> str:
    return str(
        row.get("ISU_ABBRV")
        or row.get("ISU_NM")
        or row.get("ISU_KOR_NM")
        or row.get("SECUGRP_NM")
        or ""
    ).strip()


def _krx_section_type_name(row: Mapping[str, Any]) -> str | None:
    value = str(
        row.get("MKT_NM")
        or row.get("SECT_TP_NM")
        or row.get("ISU_TYPE")
        or row.get("SECUGRP_NM")
        or ""
    ).strip()
    return value or None


def _krx_raw_payload_hash(row: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _krx_company_key(security_name_kr: str, ticker: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", "", security_name_kr).upper()
    normalized = re.sub(r"(우B|우C|우\(전환\)|우선주|우)$", "", normalized)
    normalized = normalized or ticker
    return normalized, "SECURITY_NAME_NORMALIZED" if security_name_kr else "TICKER"


_KRX_BLOCKED_SECTION_TOKENS = (
    "ETF", "ETN", "ELW", "SPAC", "스팩", "리츠", "REIT",
    "부동산투자회사", "인프라", "선박투자", "KODEX", "TIGER",
)


def _krx_exclusion_reason(
    *, row: Mapping[str, Any], ticker: str, security_name_kr: str, exclude_preferred: bool
) -> str | None:
    section_text = (_krx_section_type_name(row) or "").upper()
    name_text = security_name_kr.upper()
    if exclude_preferred and re.search(r"(우B$|우C$|우$|우\(|우선주|전환우)", name_text):
        return "PREFERRED_SHARE"
    if any(t in section_text or t in name_text for t in _KRX_BLOCKED_SECTION_TOKENS):
        return "NON_COMPANY_INSTRUMENT"
    if not ticker.isdigit() or len(ticker) != 6:
        return "NON_COMMON_TICKER"
    return None


def parse_krx_official_market_payload(
    *, payload: Mapping[str, Any], target: KrxOfficialMarketTarget
) -> KrxOfficialParseResult:
    """Parse official KRX OpenAPI daily trading rows without fabricating data."""

    ticker_filter = frozenset(target.ticker_filter)
    parsed: list[dict[str, Any]] = []
    rows_skipped = 0
    rows_failed = 0
    raw_rows = _official_outblock_rows(payload)
    for row in raw_rows:
        try:
            ticker = _krx_short_code(row)
        except ExternalProviderError:
            rows_skipped += 1
            continue
        if ticker_filter and ticker not in ticker_filter:
            continue
        try:
            close_price = _krx_decimal_or_none(row.get("TDD_CLSPRC"), zero_as_none=True)
            if close_price is None:
                rows_skipped += 1
                continue
            security_name_kr = _krx_security_name(row)
            company_key, company_key_source_code = _krx_company_key(security_name_kr, ticker)
            parsed.append(
                {
                    "ticker": ticker,
                    "source_code": "KRX",
                    "price_date": _date(
                        row.get("BAS_DD") or target.bas_dd, field_name="BAS_DD"
                    ),
                    "open_price": _krx_decimal_or_none(row.get("TDD_OPNPRC"), zero_as_none=True),
                    "high_price": _krx_decimal_or_none(row.get("TDD_HGPRC"), zero_as_none=True),
                    "low_price": _krx_decimal_or_none(row.get("TDD_LWPRC"), zero_as_none=True),
                    "close_price": close_price,
                    "volume": _krx_decimal_or_none(row.get("ACC_TRDVOL"), zero_as_none=False),
                    "trading_value_krw": _krx_decimal_or_none(
                        row.get("ACC_TRDVAL"), zero_as_none=False
                    ),
                    "market_cap_krw": _krx_decimal_or_none(
                        row.get("MKTCAP"), zero_as_none=True
                    ),
                    "listed_shares": _krx_decimal_or_none(
                        row.get("LIST_SHRS"), zero_as_none=True
                    ),
                    "change_price": _krx_decimal_or_none(
                        row.get("CMPPREVDD_PRC") or row.get("FLUC_PRC"), zero_as_none=False
                    ),
                    "change_rate_pct": _krx_decimal_or_none(
                        row.get("FLUC_RT"), zero_as_none=False
                    ),
                    "security_name_kr": security_name_kr,
                    "isin": _krx_isin_code(row),
                    "market_code": target.market_code,
                    "section_type_name": _krx_section_type_name(row),
                    "company_key": company_key,
                    "company_key_source_code": company_key_source_code,
                    "raw_payload_hash": _krx_raw_payload_hash(row),
                    "exclusion_reason_code": _krx_exclusion_reason(
                        row=row,
                        ticker=ticker,
                        security_name_kr=security_name_kr,
                        exclude_preferred=target.universe_exclude_preferred,
                    ),
                }
            )
        except ExternalProviderError:
            rows_failed += 1
    return KrxOfficialParseResult(
        rows=parsed,
        rows_skipped=rows_skipped,
        rows_failed=rows_failed,
        raw_row_count=len(raw_rows),
        ticker_filter_count=len(ticker_filter),
    )


def parse_krx_official_basic_info_payload(
    *, payload: Mapping[str, Any], market_code: str, ticker_filter: tuple[str, ...]
) -> list[dict[str, Any]]:
    """Parse official KRX issue basic-info rows for configured domestic tickers."""

    tickers = frozenset(ticker_filter)
    securities: list[dict[str, Any]] = []
    for row in _official_outblock_rows(payload):
        try:
            ticker = _krx_short_code(row)
        except ExternalProviderError:
            continue
        if tickers and ticker not in tickers:
            continue
        isin = str(
            row.get("ISIN_CODE")
            or row.get("ISIN_CD")
            or row.get("ISIN")
            or row.get("ISU_CD")
            or ""
        ).strip()
        name = str(
            row.get("ISU_ABBRV")
            or row.get("ISU_NM")
            or row.get("ISU_KOR_NM")
            or row.get("SECUGRP_NM")
            or ""
        ).strip()
        if not re.match(r"^KR[0-9A-Z]{10}$", isin) or not name:
            continue
        listed_at = None
        listed_text = str(row.get("LIST_DD") or row.get("LIST_DT") or "").strip()
        if listed_text:
            try:
                listed_at = _date(listed_text, field_name="LIST_DD")
            except ExternalProviderError:
                listed_at = None
        securities.append(
            {
                "ticker": ticker,
                "isin": isin,
                "security_name_kr": name,
                "market_code": market_code,
                "listed_at": listed_at,
            }
        )
    return securities


# ---------------------------------------------------------------------------
# Reference / evidence helpers
# ---------------------------------------------------------------------------


def _compact_date_iso(value: str) -> str:
    return _date(value, field_name="date").isoformat()


def krx_target_ref(target: KrxMarketTarget) -> str:
    """Build a deterministic non-secret KRX-family target reference."""
    return f"PYKRX:{target.ticker}:{target.start_date}-{target.end_date}"


def krx_official_ticker_filter_hash(tickers: tuple[str, ...]) -> str:
    source = ",".join(sorted(tickers)) if tickers else "ALL"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]


def select_krx_top_market_cap_universe(
    rows: Iterable[Mapping[str, Any]],
    *,
    target_size: int,
    exclude_preferred: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rank official KRX rows into auditable candidates and selected top members."""

    rankable = sorted(
        (dict(row) for row in rows if row.get("source_code") == "KRX"),
        key=lambda row: (-(row.get("market_cap_krw") or Decimal("-1")), str(row.get("ticker"))),
    )
    candidates: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    seen_company_keys: set[str] = set()
    for rank_before_filter, row in enumerate(rankable, start=1):
        ticker = str(row.get("ticker") or "")
        security_name_kr = str(row.get("security_name_kr") or "")
        company_key = str(row.get("company_key") or ticker)
        reason = row.get("exclusion_reason_code")
        market_cap = row.get("market_cap_krw")
        if market_cap is None:
            reason = reason or "MISSING_MARKET_CAP"
        if not reason and exclude_preferred:
            reason = _krx_exclusion_reason(
                row=row, ticker=ticker, security_name_kr=security_name_kr, exclude_preferred=True,
            )
        if not reason and company_key in seen_company_keys:
            reason = "DUPLICATE_COMPANY_ISSUE"
        if not reason and len(members) >= target_size:
            reason = "OUTSIDE_TARGET_SIZE"
        included = reason is None
        rank_after_filter = len(members) + 1 if included else None
        candidate = {
            "ticker": ticker,
            "isin": row.get("isin"),
            "security_name_kr": security_name_kr or ticker,
            "market_code": row.get("market_code"),
            "rank_before_filter": rank_before_filter,
            "rank_after_filter": rank_after_filter,
            "market_cap_krw": market_cap or Decimal("0"),
            "listed_shares": row.get("listed_shares"),
            "close_price": row.get("close_price"),
            "section_type_name": row.get("section_type_name"),
            "company_key": company_key,
            "company_key_source_code": row.get("company_key_source_code") or "TICKER",
            "raw_payload_hash": row.get("raw_payload_hash") or _krx_raw_payload_hash(row),
            "included": included,
            "exclusion_reason_code": None if included else str(reason),
        }
        candidates.append(candidate)
        if included:
            seen_company_keys.add(company_key)
            members.append(
                {
                    "ticker": ticker,
                    "company_key": company_key,
                    "rank_no": rank_after_filter,
                    "market_code": row.get("market_code"),
                    "market_cap_krw": market_cap or Decimal("0"),
                    "listed_shares": row.get("listed_shares"),
                    "close_price": row.get("close_price"),
                    "included_reason_code": "TOP_MARKET_CAP_COMMON_EQUITY",
                }
            )
    return candidates, members


def krx_official_target_ref(target: KrxOfficialMarketTarget) -> str:
    """Build a deterministic non-secret official KRX target reference."""
    scope = target.universe_code or krx_official_ticker_filter_hash(target.ticker_filter)
    return f"KRX:{target.market_code}:{target.bas_dd}:{scope}"


def krx_target_window_detail(
    *, target: KrxMarketTarget, rows: list[dict[str, Any]], row_count: int
) -> dict[str, Any]:
    """Return non-secret KRX/PYKRX historical-window evidence details."""
    dates = sorted({row["price_date"] for row in rows})
    return {
        "source_code": "PYKRX",
        "source_policy": "AUXILIARY_HISTORICAL_DAILY_PRICE",
        "source_policy_code": "PYKRX_AUXILIARY_APPROVED",
        "requested_window_start": _compact_date_iso(target.start_date),
        "requested_window_end": _compact_date_iso(target.end_date),
        "effective_min_date": dates[0].isoformat() if dates else None,
        "effective_max_date": dates[-1].isoformat() if dates else None,
        "trading_day_count": len(dates),
        "row_count": row_count,
        "ticker": target.ticker,
        "auxiliary_reason": "internal PoC fallback; not official KRX production evidence",
        "rate_limit_sleep_ms": 0,
        "precedence_rank": 2,
    }


def krx_official_target_detail(
    *,
    target: KrxOfficialMarketTarget,
    parse_result: KrxOfficialParseResult,
    row_count: int,
    store_rows_skipped: int,
    store_rows_failed: int,
    basic_info_upserted: int,
    rate_limit_sleep_ms: int,
) -> dict[str, Any]:
    dates = sorted({row["price_date"] for row in parse_result.rows})
    return {
        "source_code": "KRX",
        "source_policy": "OFFICIAL_DAILY_TRADING_PRICE",
        "source_policy_code": "OFFICIAL_KRX_APPROVED",
        "source_official": True,
        "endpoint_paths": [
            KrxOfficialClient.DAILY_TRADING_PATHS.get(target.market_code, ""),
            KrxOfficialClient.BASIC_INFO_PATHS.get(target.market_code, ""),
        ],
        "market": target.market_code,
        "bas_dd": target.bas_dd,
        "requested_window_start": _compact_date_iso(target.requested_window_start),
        "requested_window_end": _compact_date_iso(target.requested_window_end),
        "effective_min_date": dates[0].isoformat() if dates else None,
        "effective_max_date": dates[-1].isoformat() if dates else None,
        "trading_day_count": len(dates),
        "row_count": row_count,
        "api_row_count": parse_result.raw_row_count,
        "parsed_row_count": len(parse_result.rows),
        "ticker_filter_count": parse_result.ticker_filter_count,
        "configured_tickers": list(target.ticker_filter),
        "rows_skipped": parse_result.rows_skipped + store_rows_skipped,
        "rows_failed": parse_result.rows_failed + store_rows_failed,
        "basic_info_upserted": basic_info_upserted,
        "redacted_auth": True,
        "rate_limit_sleep_ms": rate_limit_sleep_ms,
        "precedence_rank": 1,
    }


def _target_requires_multi_day_persistence(target: KrxMarketTarget) -> bool:
    return _date(target.start_date, field_name="start_date") < _date(
        target.end_date, field_name="end_date"
    )
