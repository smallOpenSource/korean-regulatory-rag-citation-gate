"""ECOS macro-indicator batch provider helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from apps.api.harness.batch.collectors import store_macro_indicators
from apps.api.harness.batch.jobs import BatchCounters, BatchProviderEvidence
from apps.api.harness.external.http import ExternalProviderError
from apps.api.harness.external.public_data import EcosClient

from apps.api.harness.batch.providers import (  # noqa: E402
    _date,
    _decimal,
)


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EcosIndicatorTarget:
    statistic_code: str
    cycle: str
    start: str
    end: str
    indicator_name: str
    unit: str
    item_codes: tuple[str, ...] = ()
    date_lag_days: int = 0
    lookback_days: int = 0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ECOS_NO_DATA_CODE = "INFO-200"


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _ecos_result(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return ECOS RESULT code/message from top-level or StatisticSearch payload."""

    candidates: list[Any] = [payload.get("RESULT")]
    search = payload.get("StatisticSearch")
    if isinstance(search, dict):
        candidates.append(search.get("RESULT"))
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        code = str(candidate.get("CODE") or candidate.get("code") or "").strip()
        message = str(candidate.get("MESSAGE") or candidate.get("message") or "").strip()
        if code or message:
            return code or None, message or None
    return None, None


def is_ecos_no_data_payload(payload: dict[str, Any]) -> bool:
    """Return True for official ECOS success/no-data responses."""

    code, message = _ecos_result(payload)
    if code == ECOS_NO_DATA_CODE:
        return True
    normalized_message = (message or "").lower()
    return "no data" in normalized_message or (
        "데이터" in normalized_message and "없" in normalized_message
    )


def ecos_provider_status_code(payload: dict[str, Any]) -> str:
    """Map an ECOS response status payload into provider-detail taxonomy."""

    code, message = _ecos_result(payload)
    text = f"{code or ''} {message or ''}".lower()
    if is_ecos_no_data_payload(payload):
        return "PROVIDER_NO_DATA"
    if any(token in text for token in ("auth", "key", "인증", "권한", "apikey", "api key")):
        return "PROVIDER_FAILED_AUTH"
    if any(token in text for token in ("rate", "limit", "quota", "초과", "한도")):
        return "PROVIDER_FAILED_RATE_LIMIT"
    return "PROVIDER_FAILED_SCHEMA"


def ecos_target_ref(target: EcosIndicatorTarget) -> str:
    """Build a deterministic non-secret ECOS target reference for provider evidence."""

    item_suffix = ":".join(target.item_codes)
    parts = ["ECOS", target.statistic_code, target.cycle, target.indicator_name]
    if item_suffix:
        parts.append(item_suffix)
    return ":".join(parts)


def ecos_evidence_detail(
    *, payload: dict[str, Any], target: EcosIndicatorTarget
) -> dict[str, Any]:
    """Build non-secret ECOS detail JSON for reports and DB evidence."""

    code, message = _ecos_result(payload)
    return {
        "statistic_code": target.statistic_code,
        "cycle": target.cycle,
        "start": target.start,
        "end": target.end,
        "indicator_name": target.indicator_name,
        "unit": target.unit,
        "item_codes": list(target.item_codes),
        "official_code": code,
        "official_message": message,
    }


def parse_ecos_macro_payload(
    *, payload: dict[str, Any], target: EcosIndicatorTarget
) -> list[dict[str, Any]]:
    """Convert ECOS StatisticSearch rows into macro_indicators rows."""

    search = payload.get("StatisticSearch")
    rows = search.get("row") if isinstance(search, dict) else None
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        if is_ecos_no_data_payload(payload):
            return []
        code, message = _ecos_result(payload)
        if code or message:
            provider_status = ecos_provider_status_code(payload)
            raise ExternalProviderError(
                f"{provider_status}: ECOS status={code or 'missing'} "
                f"{message or 'ECOS returned non-row response'}"
            )
        raise ExternalProviderError("ECOS response missing StatisticSearch rows")
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ExternalProviderError("ECOS response row is not an object")
        parsed.append(
            {
                "indicator_code": target.statistic_code,
                "indicator_name": target.indicator_name,
                "reference_date": _date(row.get("TIME"), field_name="TIME"),
                "value": _decimal(row.get("DATA_VALUE"), field_name="DATA_VALUE"),
                "unit": target.unit,
                "source_code": "ECOS",
            }
        )
    return parsed


# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------


async def collect_ecos_macro_indicators(
    *, connection: Any, client: EcosClient, targets: Iterable[EcosIndicatorTarget]
) -> BatchCounters:
    counters = {"rows_collected": 0, "rows_skipped": 0, "rows_failed": 0}
    evidences: list[BatchProviderEvidence] = []
    for target in targets:
        payload = client.statistic_search(
            statistic_code=target.statistic_code,
            cycle=target.cycle,
            start=target.start,
            end=target.end,
            item_codes=target.item_codes,
        )
        rows = parse_ecos_macro_payload(payload=payload, target=target)
        if not rows:
            counters["rows_skipped"] += 1
            code, message = _ecos_result(payload)
            evidences.append(
                BatchProviderEvidence(
                    provider_code="ECOS",
                    provider_status_code="PROVIDER_NO_DATA",
                    target_ref=ecos_target_ref(target),
                    rows_skipped=1,
                    reason_message=message or "ECOS returned no StatisticSearch rows",
                    provider_detail=ecos_evidence_detail(payload=payload, target=target)
                    | {"official_code": code},
                )
            )
            continue
        target_counters = await store_macro_indicators(connection, rows)
        for key in counters:
            counters[key] += int(target_counters.get(key, 0))
        evidences.append(
            BatchProviderEvidence(
                provider_code="ECOS",
                provider_status_code="PROVIDER_DONE",
                target_ref=ecos_target_ref(target),
                rows_collected=int(target_counters.get("rows_collected", 0)),
                rows_skipped=int(target_counters.get("rows_skipped", 0)),
                rows_failed=int(target_counters.get("rows_failed", 0)),
                provider_detail=ecos_evidence_detail(payload=payload, target=target)
                | {"provider_row_count": len(rows)},
            )
        )
    return BatchCounters(
        rows_collected=counters["rows_collected"],
        rows_skipped=counters["rows_skipped"],
        rows_failed=counters["rows_failed"],
        provider_evidence=tuple(evidences),
    )
