"""Real external client smoke tests with redacted blocked semantics.

These tests never use mocks or local simulators. They perform safe read-only/token
operations only when the required provider endpoint and credentials are present.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from apps.api.harness.batch import runner
from apps.api.harness.batch.providers import parse_ecos_macro_payload
from apps.api.harness.external.broker import BrokerConfig, BrokerReadOnlyClient
from apps.api.harness.external.http import ExternalProviderError
from apps.api.harness.external.public_data import (
    DartClient,
    DataGoKrClient,
    EcosClient,
    KrxOfficialClient,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _skip_if_missing(*names: str) -> None:
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        pytest.skip(f"SKIPPED/BLOCKED_WITH_REDACTED_REASON missing: {', '.join(missing)}")


def test_broker_oauth_token_smoke_read_only():
    _load_env()
    _skip_if_missing("BROKER_BASE_URL", "BROKER_APP_KEY", "BROKER_APP_SECRET", "BROKER_TOKEN_PATH")
    client = BrokerReadOnlyClient(BrokerConfig.from_env())
    try:
        token = client.get_access_token()
    except ExternalProviderError as exc:
        reason = str(exc)
        if any(word in reason.lower() for word in ("throttl", "rate limit", "too many", "1분당")):
            pytest.skip(f"SKIPPED/BLOCKED_WITH_REDACTED_REASON transient BROKER throttle: {reason}")
        pytest.fail(f"BLOCKED_WITH_REDACTED_REASON BROKER token smoke failed: {reason}")
    assert isinstance(token, str)
    assert token


def test_optional_dart_client_requires_config_or_real_call():
    _load_env()
    if not os.getenv("DART_API_BASE_URL", "").strip():
        pytest.skip("SKIPPED/BLOCKED_WITH_REDACTED_REASON missing: DART_API_BASE_URL")
    _skip_if_missing("DART_API_KEY")
    payload = DartClient.from_env().list_filings(
        corp_code="00126380", begin_date="20260101", end_date="20260131"
    )
    assert isinstance(payload, dict)


def test_optional_ecos_client_requires_config_or_real_call():
    _load_env()
    if not os.getenv("ECOS_API_BASE_URL", "").strip():
        pytest.skip("SKIPPED/BLOCKED_WITH_REDACTED_REASON missing: ECOS_API_BASE_URL")
    _skip_if_missing("ECOS_API_KEY")
    payload = EcosClient.from_env().statistic_search(
        statistic_code="731Y001", cycle="D", start="20260101", end="20260131"
    )
    assert isinstance(payload, dict)


def test_optional_ecos_configured_target_returns_parseable_row():
    _load_env()
    if not os.getenv("ECOS_API_BASE_URL", "").strip():
        pytest.skip("SKIPPED/BLOCKED_WITH_REDACTED_REASON missing: ECOS_API_BASE_URL")
    _skip_if_missing("ECOS_API_KEY")
    client = EcosClient.from_env()
    parseable_rows = []
    for target in runner.parse_ecos_targets():
        payload = client.statistic_search(
            statistic_code=target.statistic_code,
            cycle=target.cycle,
            start=target.start,
            end=target.end,
            item_codes=target.item_codes,
        )
        parseable_rows.extend(parse_ecos_macro_payload(payload=payload, target=target))
        if parseable_rows:
            break

    assert parseable_rows, "ECOS configured targets did not return parser-ready rows"
    assert {row["source_code"] for row in parseable_rows} == {"ECOS"}


def test_optional_data_go_kr_client_requires_config_or_real_call():
    _load_env()
    if not os.getenv("DATA_GO_KR_API_BASE_URL", "").strip():
        pytest.skip("SKIPPED/BLOCKED_WITH_REDACTED_REASON missing: DATA_GO_KR_API_BASE_URL")
    _skip_if_missing("DATA_GO_KR_SERVICE_KEY_ENCODING")
    payload = DataGoKrClient.from_env().request_endpoint(
        path=os.getenv("DATA_GO_KR_MARKET_PATH", "/getStockPriceInfo"),
        query={"numOfRows": 1, "likeSrtnCd": "005930"},
    )
    assert isinstance(payload, dict)


def test_optional_krx_client_requires_gate_or_real_call():
    _load_env()
    if os.getenv("HARNESS_BATCH_KRX_ENABLED", "false").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        pytest.skip("SKIPPED/BLOCKED_WITH_REDACTED_REASON missing: HARNESS_BATCH_KRX_ENABLED")

    source = os.getenv("HARNESS_BATCH_KRX_SOURCE", "PYKRX").strip().upper()
    if source == "KRX":
        _skip_if_missing("KRX_API_BASE_URL", "KRX_API_KEY")
        market = os.getenv("HARNESS_BATCH_KRX_MARKETS", "KOSPI").split(",")[0].strip() or "KOSPI"
        bas_dd = os.getenv("HARNESS_BATCH_KRX_END_DATE", "20260515").replace("-", "")
        payload = KrxOfficialClient.from_env().daily_trading(market_code=market, bas_dd=bas_dd)
        assert isinstance(payload, dict)
        assert "OutBlock_1" in payload or "outBlock_1" in payload
        return

    pytest.importorskip("pykrx", reason="SKIPPED/BLOCKED_WITH_REDACTED_REASON missing: pykrx")

    from pykrx import stock  # type: ignore[import-untyped]

    ticker = os.getenv("HARNESS_BATCH_KRX_TICKERS", "005930").split(",")[0].strip()
    end = os.getenv("HARNESS_BATCH_KRX_END_DATE", "20260515").replace("-", "")
    start = os.getenv("HARNESS_BATCH_KRX_START_DATE", end).replace("-", "")
    payload = stock.get_market_ohlcv_by_date(start, end, ticker)
    assert payload is not None


def test_optional_official_krx_client_returns_real_outblock_rows():
    _load_env()
    if os.getenv("HARNESS_BATCH_KRX_SOURCE", "").strip().upper() != "KRX":
        pytest.skip("SKIPPED/BLOCKED_WITH_REDACTED_REASON missing: HARNESS_BATCH_KRX_SOURCE=KRX")
    _skip_if_missing("KRX_API_BASE_URL", "KRX_API_KEY")
    bas_dd = os.getenv("HARNESS_BATCH_KRX_END_DATE", "20260515").replace("-", "")
    payload = KrxOfficialClient.from_env().daily_trading(market_code="KOSPI", bas_dd=bas_dd)
    rows = payload.get("OutBlock_1")
    assert isinstance(rows, list)
    # Live KRX OpenAPI returns an empty OutBlock_1 for non-trading days or
    # dates where the daily settlement hasn't been published yet. The
    # invariants under test (real list shape + secret redaction) still hold;
    # only the "rows present" assertion is environmental, so skip with a
    # clear reason rather than fail when KRX itself has nothing to return.
    assert "KRX_API_KEY" not in str(payload)
    assert "AUTH_KEY" not in str(payload)
    if not rows:
        pytest.skip(
            f"SKIPPED/KRX_NO_ROWS bas_dd={bas_dd}: KRX OpenAPI returned an "
            "empty OutBlock_1 — likely a non-trading day, holiday, or daily "
            "settlement not yet published. Set HARNESS_BATCH_KRX_END_DATE to "
            "a known trading day to exercise the rows-present branch."
        )
