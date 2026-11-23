"""Real-provider batch collection helpers.

These helpers translate provider responses into persistence rows. They never
invent provider-labelled success rows; malformed or unavailable provider
responses raise sanitized provider errors so the batch job boundary records a
FAILED/SKIPPED log instead of mock data.

Re-export shim: all public names from krx, dart_ecos, and broker_data_go_kr are
re-exported here so existing callers of ``apps.api.harness.batch.providers``
continue to work without changes for one Stage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.api.harness.batch.jobs import (
    BatchCounters,
    persist_batch_log_provider_evidence,
    run_locked_batch_job,
)
from apps.api.harness.external.http import ExternalProviderError

DOMESTIC_EQUITY_IDENTIFIER_RE = re.compile(r"^(?:[0-9]{6}|KR[0-9A-Z]{10})$")


@dataclass(frozen=True)
class ProviderSourceContract:
    """Source-of-truth contract for one live provider collector."""

    provider_code: str
    job_name: str
    job_type_code: str
    persistence_target: str
    persisted_source_code: str
    required_env: tuple[str, ...]
    optional_env: tuple[str, ...] = ()
    gate_env: str | None = None


PROVIDER_SOURCE_CONTRACTS: tuple[ProviderSourceContract, ...] = (
    ProviderSourceContract(
        provider_code="BROKER",
        job_name="broker_market_collector",
        job_type_code="PROVIDER_BROKER",
        persistence_target="market_price_bars",
        persisted_source_code="BROKER",
        required_env=("BROKER_BASE_URL", "BROKER_APP_KEY", "BROKER_APP_SECRET"),
        optional_env=(
            "BROKER_ACCOUNT_NO",
            "BROKER_ACCOUNT_PROD_CD",
            "BROKER_IS_VIRTUAL",
            "BROKER_TIMEOUT_SECONDS",
            "HARNESS_BATCH_BROKER_TICKERS",
            "BROKER_QUOTE_TICKER",
            "BROKER_MARKET_CODE",
        ),
    ),
    ProviderSourceContract(
        provider_code="OPENDART",
        job_name="dart_disclosure_collector",
        job_type_code="PROVIDER_DART",
        persistence_target="raw_documents",
        persisted_source_code="DART",
        required_env=("DART_API_BASE_URL", "DART_API_KEY"),
        optional_env=(
            "DART_TIMEOUT_SECONDS",
            "HARNESS_BATCH_DART_TARGETS_JSON",
            "HARNESS_BATCH_DART_BEGIN_DATE",
            "HARNESS_BATCH_DART_END_DATE",
            "HARNESS_BATCH_DART_CORP_CODES",
            "HARNESS_BATCH_DART_LOOKBACK_DAYS",
            "HARNESS_BATCH_DART_PAGE_COUNT",
            "DART_BEGIN_DATE",
            "DART_END_DATE",
            "DART_CORP_CODE",
        ),
    ),
    ProviderSourceContract(
        provider_code="ECOS",
        job_name="ecos_macro_collector",
        job_type_code="PROVIDER_ECOS",
        persistence_target="macro_indicators",
        persisted_source_code="ECOS",
        required_env=("ECOS_API_BASE_URL", "ECOS_API_KEY"),
        optional_env=(
            "ECOS_TIMEOUT_SECONDS",
            "HARNESS_BATCH_ECOS_START_DATE",
            "HARNESS_BATCH_ECOS_END_DATE",
            "ECOS_START",
            "ECOS_END",
            "ECOS_STATISTIC_CODE",
            "ECOS_CYCLE",
            "ECOS_INDICATOR_NAME",
            "ECOS_UNIT",
            "ECOS_ITEM_CODES",
            "HARNESS_BATCH_ECOS_TARGETS_JSON",
            "HARNESS_BATCH_ECOS_LOOKBACK_DAYS",
            "HARNESS_BATCH_ECOS_DATE_LAG_DAYS",
        ),
    ),
    ProviderSourceContract(
        provider_code="DATA_GO_KR",
        job_name="data_go_kr_market_collector",
        job_type_code="PROVIDER_DATA_GO_KR",
        persistence_target="market_price_bars",
        persisted_source_code="DATA_GO_KR",
        required_env=("DATA_GO_KR_API_BASE_URL", "DATA_GO_KR_SERVICE_KEY_ENCODING"),
        optional_env=(
            "DATA_GO_KR_TIMEOUT_SECONDS",
            "DATA_GO_KR_MARKET_PATH",
            "DATA_GO_KR_TICKER_FIELD",
            "DATA_GO_KR_DATE_FIELD",
            "DATA_GO_KR_CLOSE_FIELD",
            "DATA_GO_KR_OPEN_FIELD",
            "DATA_GO_KR_HIGH_FIELD",
            "DATA_GO_KR_LOW_FIELD",
            "DATA_GO_KR_VOLUME_FIELD",
            "DATA_GO_KR_NUM_ROWS",
            "HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON",
        ),
    ),
    ProviderSourceContract(
        provider_code="KRX",
        job_name="krx_market_collector",
        job_type_code="PROVIDER_KRX",
        persistence_target="market_price_bars",
        persisted_source_code="KRX|PYKRX",
        required_env=(),
        optional_env=(
            "KRX_API_BASE_URL",
            "KRX_API_KEY",
            "KRX_API_TIMEOUT_SECONDS",
            "KRX_API_RATE_LIMIT_SLEEP_MS",
            "HARNESS_BATCH_KRX_SOURCE",
            "HARNESS_BATCH_KRX_POLICY",
            "HARNESS_BATCH_KRX_MARKETS",
            "HARNESS_BATCH_KRX_TICKERS",
            "HARNESS_BATCH_KRX_LOOKBACK_DAYS",
            "HARNESS_BATCH_KRX_START_DATE",
            "HARNESS_BATCH_KRX_END_DATE",
            "HARNESS_BATCH_LOOKBACK_DAYS",
            "KRX_ID",
            "KRX_PW",
        ),
        gate_env="HARNESS_BATCH_KRX_ENABLED",
    ),
)


@dataclass(frozen=True)
class ProviderEvidence:
    """Non-secret provider detail emitted into batch reports and future DB rows."""

    provider_code: str
    provider_status_code: str
    target_ref: str
    rows_collected: int = 0
    rows_skipped: int = 0
    rows_failed: int = 0
    reason_message: str | None = None
    provider_detail_json: dict[str, Any] | None = None

    def as_report_detail(self) -> dict[str, Any]:
        return {
            "provider_code": self.provider_code,
            "provider_status_code": self.provider_status_code,
            "target_ref": self.target_ref,
            "rows_collected": self.rows_collected,
            "rows_skipped": self.rows_skipped,
            "rows_failed": self.rows_failed,
            "reason_message": self.reason_message,
            "provider_detail_json": self.provider_detail_json or {},
        }


# ---------------------------------------------------------------------------
# Shared field-parsing utilities (used by all provider submodules)
# ---------------------------------------------------------------------------


def _decimal(value: Any, *, field_name: str) -> Decimal:
    if value is None or value == "":
        raise ExternalProviderError(f"Provider response missing numeric field: {field_name}")
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ExternalProviderError(
            f"Provider response has invalid numeric field: {field_name}"
        ) from exc


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if str(value).strip() == "-":
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ExternalProviderError("Provider response has invalid optional numeric field") from exc


def _optional_positive_decimal_or_none(value: Any) -> Decimal | None:
    text = str(value or "").strip()
    if not text or text == "-":
        return None
    parsed = _optional_decimal(text)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _date(value: Any, *, field_name: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise ExternalProviderError(f"Provider response missing date field: {field_name}")
    for pattern in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ExternalProviderError(f"Provider response has invalid date field: {field_name}")


def _require_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ExternalProviderError(f"Provider response missing text field: {field_name}")
    return text


def _domestic_equity_identifier(value: Any, *, field_name: str) -> str:
    text = _require_text(value, field_name=field_name)
    if not DOMESTIC_EQUITY_IDENTIFIER_RE.match(text):
        raise ExternalProviderError(
            f"Provider response is outside domestic Korea equity scope: {field_name}"
        )
    return text


def _items_from_public_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    current: Any = payload
    for key in ("response", "body", "items"):
        if isinstance(current, dict) and key in current:
            current = current[key]
    if isinstance(current, dict) and "item" in current:
        current = current["item"]
    if isinstance(current, dict):
        return [current]
    if isinstance(current, list) and all(isinstance(item, dict) for item in current):
        return current
    raise ExternalProviderError("Provider response missing item rows")


# ---------------------------------------------------------------------------
# Provider job runner (registry-level orchestration boundary)
# ---------------------------------------------------------------------------


async def run_provider_job(
    *,
    connection: Any,
    redis_client: Any,
    job_name: str,
    job_type_code: str,
    ttl_seconds: int,
    work: Any,
) -> dict[str, Any]:
    """Run one provider collector through the Redis lock and batch-log boundary."""

    async def wrapped_work() -> BatchCounters:
        rows = await work()
        if isinstance(rows, BatchCounters):
            return rows
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
        ttl_seconds=ttl_seconds,
        work=wrapped_work,
    )
    evidence = await persist_batch_log_provider_evidence(connection, batch_log=log)
    if evidence is not None:
        log["provider_evidence"] = [evidence]
    return log


# ---------------------------------------------------------------------------
# Re-export shim — backward-compat for one Stage (all callers unmodified)
# ---------------------------------------------------------------------------

from apps.api.harness.batch.providers.krx import *  # noqa: E402, F401, F403
from apps.api.harness.batch.providers.krx_collector import *  # noqa: E402, F401, F403
from apps.api.harness.batch.providers.dart import *  # noqa: E402, F401, F403
from apps.api.harness.batch.providers.ecos import *  # noqa: E402, F401, F403
from apps.api.harness.batch.providers.broker_data_go_kr import *  # noqa: E402, F401, F403
