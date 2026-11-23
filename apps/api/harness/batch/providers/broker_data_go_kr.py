"""BROKER + data.go.kr batch provider helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from apps.api.harness.batch.collectors import store_market_prices
from apps.api.harness.external.http import ExternalProviderError
from apps.api.harness.external.broker import BrokerReadOnlyClient
from apps.api.harness.external.public_data import DataGoKrClient

# Shared field-parsing utilities (imported from parent package)
from apps.api.harness.batch.providers import (
    _decimal,
    _optional_decimal,
    _date,
    _domestic_equity_identifier,
    _items_from_public_payload,
)


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BrokerQuoteTarget:
    ticker: str
    market_code: str = "J"


@dataclass(frozen=True)
class DataGoKrMarketTarget:
    path: str
    query: dict[str, str | int | None]
    ticker_field: str
    date_field: str
    close_field: str
    open_field: str | None = None
    high_field: str | None = None
    low_field: str | None = None
    volume_field: str | None = None


# ---------------------------------------------------------------------------
# BROKER parser
# ---------------------------------------------------------------------------


def parse_broker_quote_payload(
    *, payload: dict[str, Any], target: BrokerQuoteTarget, fallback_date: date
) -> dict[str, Any]:
    """Convert one BROKER quote response into a market_price_bars row."""

    output = payload.get("output")
    if not isinstance(output, dict):
        raise ExternalProviderError("BROKER quote response missing output")
    if target.market_code != "J":
        raise ExternalProviderError("BROKER quote target must use domestic stock market_code=J")
    return {
        "ticker": _domestic_equity_identifier(target.ticker, field_name="ticker"),
        "source_code": "BROKER",
        "price_date": _date(
            output.get("stck_bsop_date") or fallback_date.isoformat(),
            field_name="stck_bsop_date",
        ),
        "open_price": _optional_decimal(output.get("stck_oprc")),
        "high_price": _optional_decimal(output.get("stck_hgpr")),
        "low_price": _optional_decimal(output.get("stck_lwpr")),
        "close_price": _decimal(output.get("stck_prpr"), field_name="stck_prpr"),
        "volume": _optional_decimal(output.get("acml_vol")),
    }


# ---------------------------------------------------------------------------
# data.go.kr parser
# ---------------------------------------------------------------------------


def parse_data_go_kr_market_payload(
    *, payload: dict[str, Any], target: DataGoKrMarketTarget
) -> list[dict[str, Any]]:
    """Convert DATA_GO_KR item rows into market_price_bars rows."""

    parsed: list[dict[str, Any]] = []
    for item in _items_from_public_payload(payload):
        parsed.append(
            {
                "ticker": _domestic_equity_identifier(
                    item.get(target.ticker_field), field_name=target.ticker_field
                ),
                "source_code": "DATA_GO_KR",
                "price_date": _date(item.get(target.date_field), field_name=target.date_field),
                "open_price": _optional_decimal(item.get(target.open_field))
                if target.open_field
                else None,
                "high_price": _optional_decimal(item.get(target.high_field))
                if target.high_field
                else None,
                "low_price": _optional_decimal(item.get(target.low_field))
                if target.low_field
                else None,
                "close_price": _decimal(
                    item.get(target.close_field), field_name=target.close_field
                ),
                "volume": _optional_decimal(item.get(target.volume_field))
                if target.volume_field
                else None,
            }
        )
    return parsed


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------


async def collect_broker_market_prices(
    *,
    connection: Any,
    client: BrokerReadOnlyClient,
    targets: Iterable[BrokerQuoteTarget],
    fallback_date: date,
) -> dict[str, int]:
    rows = [
        parse_broker_quote_payload(
            payload=client.inquire_price(market_code=target.market_code, ticker=target.ticker),
            target=target,
            fallback_date=fallback_date,
        )
        for target in targets
    ]
    return await store_market_prices(connection, rows)


async def collect_data_go_kr_market_prices(
    *, connection: Any, client: DataGoKrClient, targets: Iterable[DataGoKrMarketTarget]
) -> dict[str, int]:
    rows: list[dict[str, Any]] = []
    for target in targets:
        payload = client.request_endpoint(path=target.path, query=target.query)
        rows.extend(parse_data_go_kr_market_payload(payload=payload, target=target))
    return await store_market_prices(connection, rows)
