"""Shared batch pipeline types, constants, SQL strings, and utility functions.

Intentionally pure — no I/O, no side effects.  Everything here is either a
dataclass, a constant, or a plain function that reads env vars or parses data.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from apps.api.harness.batch.providers import (
    PROVIDER_SOURCE_CONTRACTS,
    BrokerQuoteTarget,
    DartFilingTarget,
    DataGoKrMarketTarget,
    EcosIndicatorTarget,
    KrxMarketTarget,
    KrxOfficialMarketTarget,
)

# ---------------------------------------------------------------------------
# Pipeline-stage constants
# ---------------------------------------------------------------------------

DEFAULT_STAGES: tuple[str, ...] = (
    "seed",
    "provider",
    "transform",
    "embed",
    "derived",
    "house-view",
)
SUPPORTED_STAGES = frozenset(DEFAULT_STAGES)
MANDATORY_LOCAL_STAGES = frozenset({"seed", "transform", "derived", "house-view"})
PROVIDER_STAGE = "provider"
EMBED_STAGE = "embed"
DEFAULT_LOCK_TTL_SECONDS = 900
DEFAULT_DART_LOOKBACK_DAYS = 365
DEFAULT_BATCH_LOOKBACK_DAYS = 30
PROVIDER_STRICTNESS_REQUIRED = "required"
PROVIDER_STRICTNESS_ALL = "all"
PROVIDER_STRICTNESS_VALUES = frozenset({PROVIDER_STRICTNESS_REQUIRED, PROVIDER_STRICTNESS_ALL})
REQUIRED_PROVIDER_JOB_TYPE_CODES = frozenset({"PROVIDER_KRX", "PROVIDER_ECOS", "PROVIDER_DART"})
PYKRX_SOURCE_CODE = "PYKRX"
PYKRX_SOURCE_LABEL = "pykrx 비공식 보조 소스"
OFFICIAL_KRX_SOURCE_CODE = "KRX"
OFFICIAL_KRX_SOURCE_LABEL = "KRX 공식 OpenAPI"
OFFICIAL_KRX_POLICY_CODE = "OFFICIAL_KRX_APPROVED"
PYKRX_AUXILIARY_POLICY_CODE = "PYKRX_AUXILIARY_APPROVED"
KRX_BLOCKED_POLICY_CODE = "KRX_BLOCKED"

# ---------------------------------------------------------------------------
# Postcondition SQL (sql_id-protected)
# ---------------------------------------------------------------------------

POSTCONDITION_SQL: dict[str, str] = {
    "batch_job_logs": """
/* sql_id: batch_runner_postcondition_logs */
SELECT status_code, count(*)::integer AS row_count
FROM batch_job_logs
WHERE created_at >= $1::timestamptz
GROUP BY status_code
ORDER BY status_code;
""",
    "readiness": """
/* sql_id: batch_runner_postcondition_readiness */
SELECT
    (SELECT count(*)::integer FROM customers WHERE is_active IS TRUE) AS active_customers,
    (SELECT count(*)::integer FROM portfolios) AS portfolios,
    (SELECT count(*)::integer FROM documents) AS documents,
    (SELECT count(*)::integer FROM document_chunks) AS document_chunks,
    (SELECT count(*)::integer FROM market_price_bars) AS price_bars,
    (SELECT max(source_as_of) FROM market_price_bars) AS latest_market_source_as_of,
    (
        SELECT count(*)::integer
        FROM batch_job_logs
        WHERE status_code IN ('FAILED', 'SKIPPED')
          AND created_at >= $1::timestamptz
    ) AS blocked_batch_logs;
""",
    "provider_window": """
/* sql_id: batch_runner_postcondition_provider_window */
SELECT
    (
        SELECT count(*)::integer
        FROM market_price_bars
        WHERE is_synthetic IS FALSE
          AND source_code IN ('KRX', 'PYKRX')
          AND price_date BETWEEN $1::date AND $2::date
    ) AS historical_price_row_count,
    (
        SELECT count(DISTINCT price_date)::integer
        FROM market_price_bars
        WHERE is_synthetic IS FALSE
          AND source_code IN ('KRX', 'PYKRX')
          AND price_date BETWEEN $1::date AND $2::date
    ) AS historical_price_trading_day_count,
    (
        SELECT min(price_date)
        FROM market_price_bars
        WHERE is_synthetic IS FALSE
          AND source_code IN ('KRX', 'PYKRX')
          AND price_date BETWEEN $1::date AND $2::date
    ) AS historical_price_min_date,
    (
        SELECT max(price_date)
        FROM market_price_bars
        WHERE is_synthetic IS FALSE
          AND source_code IN ('KRX', 'PYKRX')
          AND price_date BETWEEN $1::date AND $2::date
    ) AS historical_price_max_date,
    (
        SELECT count(*)::integer
        FROM market_price_bars
        WHERE is_synthetic IS FALSE
          AND source_code = 'KRX'
          AND price_date BETWEEN $1::date AND $2::date
    ) AS official_krx_price_row_count,
    (
        SELECT count(DISTINCT price_date)::integer
        FROM market_price_bars
        WHERE is_synthetic IS FALSE
          AND source_code = 'KRX'
          AND price_date BETWEEN $1::date AND $2::date
    ) AS official_krx_trading_day_count,
    (
        SELECT count(*)::integer
        FROM market_price_bars
        WHERE is_synthetic IS FALSE
          AND source_code = 'PYKRX'
          AND price_date BETWEEN $1::date AND $2::date
    ) AS pykrx_price_row_count,
    (
        SELECT count(DISTINCT price_date)::integer
        FROM market_price_bars
        WHERE is_synthetic IS FALSE
          AND source_code = 'PYKRX'
          AND price_date BETWEEN $1::date AND $2::date
    ) AS pykrx_trading_day_count,
    (
        SELECT count(*)::integer
        FROM macro_indicators
        WHERE source_code = 'ECOS'
          AND reference_date BETWEEN $1::date AND $2::date
    ) AS ecos_observation_count,
    (
        SELECT min(reference_date)
        FROM macro_indicators
        WHERE source_code = 'ECOS'
          AND reference_date BETWEEN $1::date AND $2::date
    ) AS ecos_min_reference_date,
    (
        SELECT max(reference_date)
        FROM macro_indicators
        WHERE source_code = 'ECOS'
          AND reference_date BETWEEN $1::date AND $2::date
    ) AS ecos_max_reference_date,
    (
        SELECT count(*)::integer
        FROM document_sources
        WHERE provider_code = 'DART'
          AND published_at::date BETWEEN $1::date AND $2::date
    ) AS dart_document_source_count,
    (
        SELECT count(*)::integer
        FROM document_chunks
        WHERE provider_code = 'DART'
          AND receipt_no IS NOT NULL
          AND is_embedded IS TRUE
    ) AS dart_embedded_chunk_count;
""",
}

# ---------------------------------------------------------------------------
# Additional SQL helpers
# ---------------------------------------------------------------------------

COUNT_ACTIVE_HOUSE_VIEWS_SQL = """
/* sql_id: count_active_house_views */
SELECT count(*)::integer AS row_count
FROM house_views
WHERE status_code = 'ACTIVE';
"""

LIST_ACTIVE_DART_SECURITY_TARGETS_SQL = """
/* sql_id: list_active_dart_security_targets */
SELECT ticker
FROM securities
WHERE country_code = 'KR'
  AND security_type_code = 'EQUITY'
  AND currency = 'KRW'
  AND is_active IS TRUE
ORDER BY ticker
LIMIT $1;
"""

GET_LATEST_KRX_TRADING_DAY_SQL = """
/* sql_id: get_latest_krx_trading_day */
SELECT calendar_date
FROM trading_calendar
WHERE calendar_date <= $1::date
  AND is_trading_day IS TRUE
ORDER BY calendar_date DESC
LIMIT 1;
"""

# ---------------------------------------------------------------------------
# Shared dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageResult:
    """Serializable result for one pipeline stage or provider substage."""

    stage: str
    job_name: str
    job_type_code: str
    status_code: str
    rows_collected: int = 0
    rows_skipped: int = 0
    rows_failed: int = 0
    log_id: str | None = None
    error_message: str | None = None
    detail: dict[str, Any] | None = None
    provider_detail_evidence: list[dict[str, Any]] | None = None
    local_mandatory: bool = False
    provider_evidence: bool = False

    @classmethod
    def from_batch_log(
        cls,
        *,
        stage: str,
        batch_log: dict[str, Any],
        detail: dict[str, Any] | None = None,
        local_mandatory: bool | None = None,
        provider_evidence: bool | None = None,
    ) -> StageResult:
        """Build a result from a ``batch_job_logs`` repository row."""

        return cls(
            stage=stage,
            job_name=str(batch_log["job_name"]),
            job_type_code=str(batch_log["job_type_code"]),
            status_code=str(batch_log["status_code"]),
            rows_collected=int(batch_log.get("rows_collected") or 0),
            rows_skipped=int(batch_log.get("rows_skipped") or 0),
            rows_failed=int(batch_log.get("rows_failed") or 0),
            log_id=str(batch_log.get("id")) if batch_log.get("id") else None,
            error_message=batch_log.get("error_message"),
            detail=detail,
            provider_detail_evidence=batch_log.get("provider_evidence"),
            local_mandatory=(
                stage in MANDATORY_LOCAL_STAGES if local_mandatory is None else local_mandatory
            ),
            provider_evidence=(
                (stage == PROVIDER_STAGE or str(batch_log["job_type_code"]).startswith("PROVIDER_"))
                if provider_evidence is None
                else provider_evidence
            ),
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe report object."""

        return {
            "stage": self.stage,
            "job_name": self.job_name,
            "job_type_code": self.job_type_code,
            "status_code": self.status_code,
            "rows_collected": self.rows_collected,
            "rows_skipped": self.rows_skipped,
            "rows_failed": self.rows_failed,
            "log_id": self.log_id,
            "error_message": self.error_message,
            "detail": self.detail or {},
            "provider_detail_evidence": self.provider_detail_evidence or [],
            "local_mandatory": self.local_mandatory,
            "provider_evidence": self.provider_evidence,
        }


@dataclass(frozen=True)
class BatchRunSummary:
    """Operator-facing status summary that keeps provider evidence separate."""

    status_code: str
    local_status_code: str
    provider_status_code: str
    provider_required_status_code: str
    local_ok: bool
    provider_evidence_ok: bool
    provider_required_ok: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "local_status_code": self.local_status_code,
            "provider_status_code": self.provider_status_code,
            "provider_required_status_code": self.provider_required_status_code,
            "local_ok": self.local_ok,
            "provider_evidence_ok": self.provider_evidence_ok,
            "provider_required_ok": self.provider_required_ok,
        }

    def exit_code(
        self,
        *,
        strict_external: bool = False,
        provider_strictness: str = PROVIDER_STRICTNESS_REQUIRED,
    ) -> int:
        if not self.local_ok:
            return 1
        strictness = normalize_provider_strictness(provider_strictness)
        if strict_external or strictness == PROVIDER_STRICTNESS_ALL:
            return 0 if self.provider_evidence_ok else 2
        return 0 if self.provider_required_ok else 2


@dataclass(frozen=True)
class KrxSourcePolicy:
    """Resolved KRX-family source policy for official or auxiliary collection."""

    enabled: bool
    requested_source: str
    requested_policy_code: str
    source_policy_code: str
    source_policy_label: str
    runnable: bool
    provider_status_code: str
    reason: str | None

    def detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {
            "provider": "KRX",
            "requested_source": self.requested_source,
            "requested_policy_code": self.requested_policy_code,
            "source_policy_code": self.source_policy_code,
            "source_policy_label": self.source_policy_label,
            "source_official": self.source_policy_code == OFFICIAL_KRX_POLICY_CODE,
            "provider_status_code": self.provider_status_code,
            "t55_closure_wording": (
                "T55 official KRX READY with OFFICIAL_KRX_APPROVED"
                if self.source_policy_code == OFFICIAL_KRX_POLICY_CODE
                else "T55 internal PoC READY with PYKRX_AUXILIARY"
                if self.source_policy_code == PYKRX_AUXILIARY_POLICY_CODE
                else "T55 READY with official KRX OpenAPI"
                if self.source_policy_code == OFFICIAL_KRX_POLICY_CODE
                else "T55 KRX/PYKRX policy blocked"
            ),
        }
        if self.requested_source == PYKRX_SOURCE_CODE:
            detail["source_code"] = PYKRX_SOURCE_CODE
            detail["source_label"] = PYKRX_SOURCE_LABEL
        elif self.requested_source == OFFICIAL_KRX_SOURCE_CODE:
            detail["source_code"] = OFFICIAL_KRX_SOURCE_CODE
            detail["source_label"] = "KRX 공식 OpenAPI"
        if self.reason:
            detail["policy_reason"] = self.reason
        return detail


# ---------------------------------------------------------------------------
# Timestamp helper
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp for reports and postconditions."""

    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Env-reading utilities
# ---------------------------------------------------------------------------


def parse_stage_list(value: str | None, *, all_stages: bool = False) -> tuple[str, ...]:
    """Parse ``--stages``/``--all-stages`` into a deterministic stage tuple."""

    if all_stages or not value or value.strip().lower() == "all":
        return DEFAULT_STAGES
    requested = {stage.strip() for stage in value.split(",") if stage.strip()}
    unknown = sorted(requested - SUPPORTED_STAGES)
    if unknown:
        raise ValueError(f"Unsupported batch stage(s): {', '.join(unknown)}")
    stages = tuple(stage for stage in DEFAULT_STAGES if stage in requested)
    if not stages:
        raise ValueError("At least one batch stage is required")
    return stages


def missing_env(names: Iterable[str]) -> list[str]:
    """Return required env names that are unset or blank."""

    return [name for name in names if not os.getenv(name, "").strip()]


def env_bool(name: str, *, default: bool = False) -> bool:
    """Read a boolean env value for operator provider gates."""

    text = os.getenv(name, "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def env_int(
    name: str, *, default: int, minimum: int | None = None, maximum: int | None = None
) -> int:
    """Read a bounded integer env value."""

    text = os.getenv(name, "").strip()
    if not text:
        value = default
    else:
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def csv_values(env_name: str, default: Iterable[str] = ()) -> tuple[str, ...]:
    """Return a comma-separated env var as stripped non-empty values."""

    text = os.getenv(env_name, "").strip()
    if not text:
        return tuple(default)
    return tuple(value.strip() for value in text.split(",") if value.strip())


def env_date(env_name: str, default: date) -> date:
    """Read a YYYY-MM-DD or YYYYMMDD date env var."""

    text = os.getenv(env_name, "").strip()
    if not text:
        return default
    for pattern in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"{env_name} must be YYYY-MM-DD or YYYYMMDD")


def compact_date(value: date) -> str:
    """Format a date for provider APIs that expect YYYYMMDD."""

    return value.strftime("%Y%m%d")


def krx_lookback_days(default: int) -> int:
    """Resolve the KRX-specific rolling window with batch lookback fallback."""

    if os.getenv("HARNESS_BATCH_KRX_LOOKBACK_DAYS", "").strip():
        return env_int(
            "HARNESS_BATCH_KRX_LOOKBACK_DAYS",
            default=default,
            minimum=1,
            maximum=3660,
        )
    return env_int(
        "HARNESS_BATCH_LOOKBACK_DAYS",
        default=default,
        minimum=1,
        maximum=3660,
    )


def _optional_int(value: Any, *, field_name: str, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return parsed


def _date_from_text(value: Any, *, field_name: str) -> date:
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"{field_name} must be YYYY-MM-DD or YYYYMMDD")


def _ecos_window_from_target(
    raw: dict[str, Any],
    *,
    base_date: date,
    default_lookback_days: int,
    default_date_lag_days: int,
) -> tuple[str, str, int, int]:
    """Resolve an ECOS target date window without querying only today's date."""

    date_lag_days = _optional_int(
        raw.get("date_lag_days"),
        field_name="date_lag_days",
        default=default_date_lag_days,
    )
    lookback_days = _optional_int(
        raw.get("lookback_days"),
        field_name="lookback_days",
        default=default_lookback_days,
    )
    resolved_end = base_date - timedelta(days=date_lag_days)
    resolved_start = resolved_end - timedelta(days=lookback_days)
    start = compact_date(resolved_start)
    end = compact_date(resolved_end)
    if raw.get("start"):
        start = compact_date(_date_from_text(raw["start"], field_name="start"))
    if raw.get("end"):
        end = compact_date(_date_from_text(raw["end"], field_name="end"))
    return start, end, date_lag_days, lookback_days


def latest_weekday_on_or_before(value: date) -> date:
    """Return a weekday fallback when no trading-calendar row is available."""

    while value.weekday() >= 5:
        value -= timedelta(days=1)
    return value


# ---------------------------------------------------------------------------
# Provider strictness / KRX policy resolution
# ---------------------------------------------------------------------------


def normalize_provider_strictness(value: str) -> str:
    """Validate provider strictness mode for report/exit semantics."""

    strictness = value.strip().lower()
    if strictness not in PROVIDER_STRICTNESS_VALUES:
        raise ValueError("provider strictness must be required or all")
    return strictness


def resolve_krx_source_policy(
    *,
    enabled: bool,
    requested_source: str | None,
    policy_code: str | None,
    pykrx_available: bool,
    official_env_missing: Iterable[str] = (),
) -> KrxSourcePolicy:
    """Resolve the explicit official-KRX/PYKRX source policy without side effects."""

    source = (requested_source or "").strip().upper()
    requested_policy = (policy_code or "").strip().upper()
    official_missing = tuple(official_env_missing)
    if not enabled:
        return KrxSourcePolicy(
            enabled=False,
            requested_source=source or "DISABLED",
            requested_policy_code=requested_policy or "UNSET",
            source_policy_code=KRX_BLOCKED_POLICY_CODE,
            source_policy_label="KRX/PYKRX policy blocked",
            runnable=False,
            provider_status_code="PROVIDER_SKIPPED_DISABLED",
            reason="KRX collector is disabled; set HARNESS_BATCH_KRX_ENABLED=true",
        )
    if source == OFFICIAL_KRX_SOURCE_CODE:
        official_missing = missing_env(("KRX_API_BASE_URL", "KRX_API_KEY"))
        if requested_policy != OFFICIAL_KRX_POLICY_CODE:
            return KrxSourcePolicy(
                enabled=True,
                requested_source=OFFICIAL_KRX_SOURCE_CODE,
                requested_policy_code=requested_policy or "UNSET",
                source_policy_code=KRX_BLOCKED_POLICY_CODE,
                source_policy_label="KRX/PYKRX policy blocked",
                runnable=False,
                provider_status_code="PROVIDER_SKIPPED_DISABLED",
                reason="Official KRX requires HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED",
            )
        if official_missing:
            return KrxSourcePolicy(
                enabled=True,
                requested_source=OFFICIAL_KRX_SOURCE_CODE,
                requested_policy_code=requested_policy,
                source_policy_code=KRX_BLOCKED_POLICY_CODE,
                source_policy_label="KRX/PYKRX policy blocked",
                runnable=False,
                provider_status_code="PROVIDER_SKIPPED_CONFIG",
                reason=f"Official KRX requires configured endpoint and key: {official_missing}",
            )
        return KrxSourcePolicy(
            enabled=True,
            requested_source=OFFICIAL_KRX_SOURCE_CODE,
            requested_policy_code=requested_policy,
            source_policy_code=OFFICIAL_KRX_POLICY_CODE,
            source_policy_label="Official KRX source policy approved",
            runnable=True,
            provider_status_code="PROVIDER_DONE",
            reason=None,
        )
    if source != PYKRX_SOURCE_CODE:
        return KrxSourcePolicy(
            enabled=True,
            requested_source=source or "UNSET",
            requested_policy_code=requested_policy or "UNSET",
            source_policy_code=KRX_BLOCKED_POLICY_CODE,
            source_policy_label="KRX/PYKRX policy blocked",
            runnable=False,
            provider_status_code="PROVIDER_SKIPPED_DISABLED",
            reason=(
                "Set HARNESS_BATCH_KRX_SOURCE=KRX with HARNESS_BATCH_KRX_POLICY="
                "OFFICIAL_KRX_APPROVED for official collection, or source=PYKRX with "
                "PYKRX_AUXILIARY_APPROVED for the internal PoC fallback"
            ),
        )
    if requested_policy != PYKRX_AUXILIARY_POLICY_CODE:
        return KrxSourcePolicy(
            enabled=True,
            requested_source=PYKRX_SOURCE_CODE,
            requested_policy_code=requested_policy or "UNSET",
            source_policy_code=KRX_BLOCKED_POLICY_CODE,
            source_policy_label="KRX/PYKRX policy blocked",
            runnable=False,
            provider_status_code="PROVIDER_SKIPPED_DISABLED",
            reason=(
                "PYKRX fallback requires explicit HARNESS_BATCH_KRX_POLICY=PYKRX_AUXILIARY_APPROVED"
            ),
        )
    if not pykrx_available:
        return KrxSourcePolicy(
            enabled=True,
            requested_source=PYKRX_SOURCE_CODE,
            requested_policy_code=requested_policy,
            source_policy_code=KRX_BLOCKED_POLICY_CODE,
            source_policy_label="KRX/PYKRX policy blocked",
            runnable=False,
            provider_status_code="PROVIDER_SKIPPED_DISABLED",
            reason="PYKRX fallback requires optional pykrx package",
        )
    return KrxSourcePolicy(
        enabled=True,
        requested_source=PYKRX_SOURCE_CODE,
        requested_policy_code=requested_policy,
        source_policy_code=PYKRX_AUXILIARY_POLICY_CODE,
        source_policy_label="PYKRX_AUXILIARY internal PoC policy approved",
        runnable=True,
        provider_status_code="PROVIDER_DONE",
        reason=None,
    )


# ---------------------------------------------------------------------------
# Provider governance / contract helpers
# ---------------------------------------------------------------------------


def provider_contract_matrix() -> list[dict[str, Any]]:
    """Expose provider source contracts in operator reports without secrets."""

    return [
        {
            "provider_code": contract.provider_code,
            "job_name": contract.job_name,
            "job_type_code": contract.job_type_code,
            "persistence_target": contract.persistence_target,
            "persisted_source_code": contract.persisted_source_code,
            "required_env": list(contract.required_env),
            "optional_env": list(contract.optional_env),
            "gate_env": contract.gate_env,
        }
        for contract in PROVIDER_SOURCE_CONTRACTS
    ]


def provider_governance_matrix() -> list[dict[str, Any]]:
    """Expose provider acceptance rules without leaking provider secrets."""

    matrix: list[dict[str, Any]] = []
    for contract in PROVIDER_SOURCE_CONTRACTS:
        required_for_recent_window = contract.job_type_code in REQUIRED_PROVIDER_JOB_TYPE_CODES
        entry: dict[str, Any] = {
            "provider_code": contract.provider_code,
            "job_type_code": contract.job_type_code,
            "persistence_target": contract.persistence_target,
            "persisted_source_code": contract.persisted_source_code,
            "required_for_provider_strictness_required": required_for_recent_window,
            "required_env": list(contract.required_env),
            "optional_env": list(contract.optional_env),
            "gate_env": contract.gate_env,
            "acceptance_notes": [],
        }
        if contract.provider_code == "KRX":
            entry.update(
                {
                    "source_branches": [
                        {
                            "source_code": OFFICIAL_KRX_SOURCE_CODE,
                            "source_policy_code": OFFICIAL_KRX_POLICY_CODE,
                            "source_official": True,
                            "precedence_rank": 1,
                            "required_env": ["KRX_API_BASE_URL", "KRX_API_KEY"],
                            "may_satisfy_official_top200_30d": True,
                            "fallback_behavior": "fail_closed_no_pykrx_auto_fallback",
                        },
                        {
                            "source_code": PYKRX_SOURCE_CODE,
                            "source_policy_code": PYKRX_AUXILIARY_POLICY_CODE,
                            "source_official": False,
                            "precedence_rank": 2,
                            "required_env": ["HARNESS_BATCH_KRX_POLICY"],
                            "may_satisfy_official_top200_30d": False,
                            "fallback_behavior": "explicit_internal_poc_only",
                        },
                    ],
                    "official_top200_30d_gate": {
                        "universe_code": "DOMESTIC_TOP200_MARKET_CAP",
                        "minimum_selected_count": 200,
                        "required_coverage_ratio": 1.0,
                        "required_missing_member_days": 0,
                        "required_source_code": OFFICIAL_KRX_SOURCE_CODE,
                        "required_source_policy_code": OFFICIAL_KRX_POLICY_CODE,
                    },
                }
            )
            entry["acceptance_notes"].append(
                "Official serviceable readiness requires KRX/OFFICIAL_KRX_APPROVED rows; "
                "PYKRX auxiliary rows must remain visibly non-official."
            )
        elif contract.provider_code == "OPENDART":
            entry["acceptance_notes"].append(
                "Required-provider mode needs real OpenDART document lineage in the "
                "requested window."
            )
        elif contract.provider_code == "ECOS":
            entry["acceptance_notes"].append(
                "Required-provider mode needs parseable ECOS observations in the requested window."
            )
        else:
            entry["acceptance_notes"].append(
                "All-provider strictness uses this provider as diagnostic evidence only."
            )
        matrix.append(entry)
    return matrix


# ---------------------------------------------------------------------------
# Provider target parsers
# ---------------------------------------------------------------------------


def parse_broker_targets() -> tuple[BrokerQuoteTarget, ...]:
    """Build BROKER quote targets from env without embedding credentials in reports."""

    tickers = csv_values(
        "HARNESS_BATCH_BROKER_TICKERS",
        default=csv_values("BROKER_QUOTE_TICKER", default=("005930",)),
    )
    market_code = os.getenv("BROKER_MARKET_CODE", "J").strip() or "J"
    if market_code != "J":
        raise ValueError("BROKER_MARKET_CODE must be J for domestic Korea equities")
    for ticker in tickers:
        if not (ticker.isdigit() and len(ticker) == 6):
            raise ValueError("HARNESS_BATCH_BROKER_TICKERS must contain six-digit Korea tickers")
    return tuple(BrokerQuoteTarget(ticker=ticker, market_code=market_code) for ticker in tickers)


def parse_ecos_targets(
    today: date | None = None, *, default_lookback_days: int | None = None
) -> tuple[EcosIndicatorTarget, ...]:
    """Build ECOS macro targets from non-secret env controls."""

    base_date = today or date.today()
    resolved_default_lookback_days = _optional_int(
        os.getenv("HARNESS_BATCH_ECOS_LOOKBACK_DAYS"),
        field_name="HARNESS_BATCH_ECOS_LOOKBACK_DAYS",
        default=default_lookback_days or 10,
    )
    default_date_lag_days = _optional_int(
        os.getenv("HARNESS_BATCH_ECOS_DATE_LAG_DAYS"),
        field_name="HARNESS_BATCH_ECOS_DATE_LAG_DAYS",
        default=0,
    )
    json_value = os.getenv("HARNESS_BATCH_ECOS_TARGETS_JSON", "").strip()
    if json_value:
        raw_targets = json.loads(json_value)
        if not isinstance(raw_targets, list):
            raise ValueError("HARNESS_BATCH_ECOS_TARGETS_JSON must be a JSON list")
        targets: list[EcosIndicatorTarget] = []
        for raw in raw_targets:
            if not isinstance(raw, dict):
                raise ValueError("HARNESS_BATCH_ECOS_TARGETS_JSON entries must be objects")
            item_codes_raw = raw.get("item_codes") or ()
            if isinstance(item_codes_raw, str):
                item_codes = tuple(
                    item_code.strip()
                    for item_code in item_codes_raw.split(",")
                    if item_code.strip()
                )
            elif isinstance(item_codes_raw, list) and all(
                isinstance(item_code, str) for item_code in item_codes_raw
            ):
                item_codes = tuple(
                    item_code.strip() for item_code in item_codes_raw if item_code.strip()
                )
            else:
                raise ValueError("ECOS target item_codes must be a string list or CSV string")
            start, end, date_lag_days, lookback_days = _ecos_window_from_target(
                raw,
                base_date=base_date,
                default_lookback_days=resolved_default_lookback_days,
                default_date_lag_days=default_date_lag_days,
            )
            targets.append(
                EcosIndicatorTarget(
                    statistic_code=str(raw["statistic_code"]),
                    cycle=str(raw.get("cycle") or "D"),
                    start=start,
                    end=end,
                    indicator_name=str(raw.get("indicator_name") or raw["statistic_code"]),
                    unit=str(raw.get("unit") or ""),
                    item_codes=item_codes,
                    date_lag_days=date_lag_days,
                    lookback_days=lookback_days,
                )
            )
        return tuple(targets)

    start = compact_date(
        env_date(
            "HARNESS_BATCH_ECOS_START_DATE",
            env_date("ECOS_START", base_date - timedelta(days=resolved_default_lookback_days)),
        )
    )
    end = compact_date(
        env_date(
            "HARNESS_BATCH_ECOS_END_DATE",
            env_date("ECOS_END", base_date),
        )
    )
    return (
        EcosIndicatorTarget(
            statistic_code=os.getenv("ECOS_STATISTIC_CODE", "722Y001").strip() or "722Y001",
            cycle=os.getenv("ECOS_CYCLE", "D").strip() or "D",
            start=start,
            end=end,
            indicator_name=os.getenv("ECOS_INDICATOR_NAME", "base_rate").strip() or "base_rate",
            unit=os.getenv("ECOS_UNIT", "연%").strip() or "연%",
            item_codes=csv_values("ECOS_ITEM_CODES", default=("0101000",)),
            date_lag_days=default_date_lag_days,
            lookback_days=resolved_default_lookback_days,
        ),
    )


def parse_data_go_kr_targets() -> tuple[DataGoKrMarketTarget, ...]:
    """Build DATA_GO_KR market targets from JSON or explicit field env controls."""

    json_value = os.getenv("HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON", "").strip()
    if json_value:
        raw_targets = json.loads(json_value)
        if not isinstance(raw_targets, list):
            raise ValueError("HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON must be a JSON list")
        targets: list[DataGoKrMarketTarget] = []
        for raw in raw_targets:
            if not isinstance(raw, dict):
                raise ValueError("HARNESS_BATCH_DATA_GO_KR_TARGETS_JSON entries must be objects")
            query = raw.get("query") or {}
            if not isinstance(query, dict):
                raise ValueError("DATA_GO_KR target query must be an object")
            targets.append(
                DataGoKrMarketTarget(
                    path=str(raw["path"]),
                    query={
                        str(key): value
                        for key, value in query.items()
                        if isinstance(value, (str, int)) or value is None
                    },
                    ticker_field=str(raw["ticker_field"]),
                    date_field=str(raw["date_field"]),
                    close_field=str(raw["close_field"]),
                    open_field=str(raw["open_field"]) if raw.get("open_field") else None,
                    high_field=str(raw["high_field"]) if raw.get("high_field") else None,
                    low_field=str(raw["low_field"]) if raw.get("low_field") else None,
                    volume_field=str(raw["volume_field"]) if raw.get("volume_field") else None,
                )
            )
        return tuple(targets)

    if missing_env(
        (
            "DATA_GO_KR_MARKET_PATH",
            "DATA_GO_KR_TICKER_FIELD",
            "DATA_GO_KR_DATE_FIELD",
            "DATA_GO_KR_CLOSE_FIELD",
        )
    ):
        return ()
    return (
        DataGoKrMarketTarget(
            path=os.environ["DATA_GO_KR_MARKET_PATH"],
            query={"numOfRows": int(os.getenv("DATA_GO_KR_NUM_ROWS", "10"))},
            ticker_field=os.environ["DATA_GO_KR_TICKER_FIELD"],
            date_field=os.environ["DATA_GO_KR_DATE_FIELD"],
            close_field=os.environ["DATA_GO_KR_CLOSE_FIELD"],
            open_field=os.getenv("DATA_GO_KR_OPEN_FIELD") or None,
            high_field=os.getenv("DATA_GO_KR_HIGH_FIELD") or None,
            low_field=os.getenv("DATA_GO_KR_LOW_FIELD") or None,
            volume_field=os.getenv("DATA_GO_KR_VOLUME_FIELD") or None,
        ),
    )


def dart_target_dates(
    today: date | None = None, *, default_lookback_days: int | None = None
) -> tuple[str, str]:
    """Return the configured or rolling OpenDART collection window."""

    base_date = today or date.today()
    lookback_days = env_int(
        "HARNESS_BATCH_DART_LOOKBACK_DAYS",
        default=default_lookback_days or DEFAULT_DART_LOOKBACK_DAYS,
        minimum=1,
    )
    begin_default = base_date - timedelta(days=lookback_days)
    begin_date = compact_date(
        env_date(
            "HARNESS_BATCH_DART_BEGIN_DATE",
            env_date("DART_BEGIN_DATE", begin_default),
        )
    )
    end_date = compact_date(
        env_date(
            "HARNESS_BATCH_DART_END_DATE",
            env_date("DART_END_DATE", base_date),
        )
    )
    return begin_date, end_date


def dart_explicit_target_env_set() -> bool:
    """Return true when env explicitly names DART targets."""

    return any(
        os.getenv(name, "").strip()
        for name in (
            "HARNESS_BATCH_DART_TARGETS_JSON",
            "HARNESS_BATCH_DART_CORP_CODES",
            "DART_CORP_CODE",
        )
    )


def env_date_value(text: str, *, field_name: str) -> date:
    """Parse a date value from JSON target config."""

    clean_text = text.strip()
    for pattern in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(clean_text, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"DART target {field_name} must be YYYY-MM-DD or YYYYMMDD")


def _dart_target_from_mapping(
    raw: dict[str, Any], *, default_begin: str, default_end: str, default_page_count: int
) -> DartFilingTarget:
    corp_code = str(raw.get("corp_code") or "").strip() or None
    stock_code = str(raw.get("stock_code") or "").strip() or None
    if corp_code and not (corp_code.isdigit() and len(corp_code) == 8):
        raise ValueError("DART corp_code targets must be eight digits")
    if stock_code and not (stock_code.isdigit() and len(stock_code) == 6):
        raise ValueError("DART stock_code targets must be six digits")
    if not corp_code and not stock_code:
        raise ValueError("DART target must include corp_code or stock_code")
    end_date = default_end
    if raw.get("end_date"):
        end_date = compact_date(env_date_value(str(raw["end_date"]), field_name="end_date"))
    begin_date = default_begin
    if raw.get("begin_date"):
        begin_date = compact_date(env_date_value(str(raw["begin_date"]), field_name="begin_date"))
    elif raw.get("lookback_days"):
        lookback_days = int(raw["lookback_days"])
        if lookback_days < 1:
            raise ValueError("DART lookback_days must be >= 1")
        end_date_value = env_date_value(end_date, field_name="end_date")
        begin_date = compact_date(end_date_value - timedelta(days=lookback_days))
    page_count = int(raw.get("page_count") or default_page_count)
    if page_count < 1 or page_count > 100:
        raise ValueError("DART page_count must be between 1 and 100")
    report_type = str(raw.get("report_type") or "").strip() or None
    return DartFilingTarget(
        corp_code=corp_code,
        stock_code=stock_code,
        begin_date=begin_date,
        end_date=end_date,
        report_type=report_type,
        page_count=page_count,
    )


def parse_dart_targets(
    today: date | None = None,
    *,
    include_default: bool = True,
    default_lookback_days: int | None = None,
) -> tuple[DartFilingTarget, ...]:
    """Build DART filing targets from non-secret env controls."""

    begin_date, end_date = dart_target_dates(today, default_lookback_days=default_lookback_days)
    page_count = env_int("HARNESS_BATCH_DART_PAGE_COUNT", default=100, minimum=1, maximum=100)
    json_value = os.getenv("HARNESS_BATCH_DART_TARGETS_JSON", "").strip()
    if json_value:
        raw_targets = json.loads(json_value)
        if not isinstance(raw_targets, list):
            raise ValueError("HARNESS_BATCH_DART_TARGETS_JSON must be a JSON list")
        targets: list[DartFilingTarget] = []
        for raw in raw_targets:
            if not isinstance(raw, dict):
                raise ValueError("HARNESS_BATCH_DART_TARGETS_JSON entries must be objects")
            targets.append(
                _dart_target_from_mapping(
                    raw,
                    default_begin=begin_date,
                    default_end=end_date,
                    default_page_count=page_count,
                )
            )
        return tuple(targets)

    corp_codes = csv_values(
        "HARNESS_BATCH_DART_CORP_CODES",
        default=csv_values("DART_CORP_CODE", default=()),
    )
    if not corp_codes and not include_default:
        return ()
    if not corp_codes:
        corp_codes = ("00126380",)
    return tuple(
        DartFilingTarget(
            corp_code=corp_code,
            begin_date=begin_date,
            end_date=end_date,
            page_count=page_count,
        )
        for corp_code in corp_codes
    )


def parse_krx_targets(
    today: date | None = None,
    *,
    default_trading_day: date | None = None,
    lookback_days: int | None = None,
) -> tuple[KrxMarketTarget, ...]:
    """Build KRX/pykrx OHLCV targets from non-secret env controls."""

    base_date = default_trading_day or latest_weekday_on_or_before(today or date.today())
    resolved_lookback_days = krx_lookback_days(lookback_days or DEFAULT_BATCH_LOOKBACK_DAYS)
    end_date = env_date("HARNESS_BATCH_KRX_END_DATE", base_date)
    start_default = end_date - timedelta(days=resolved_lookback_days)
    start = compact_date(env_date("HARNESS_BATCH_KRX_START_DATE", start_default))
    end = compact_date(end_date)
    tickers = csv_values("HARNESS_BATCH_KRX_TICKERS", default=("005930",))
    for ticker in tickers:
        if not (ticker.isdigit() and len(ticker) == 6):
            raise ValueError("HARNESS_BATCH_KRX_TICKERS must contain six-digit Korea tickers")
    return tuple(
        KrxMarketTarget(ticker=ticker, start_date=start, end_date=end) for ticker in tickers
    )


def _date_range_compact(start: date, end: date) -> tuple[str, ...]:
    if start > end:
        raise ValueError("KRX start date must be on or before end date")
    days: list[str] = []
    cursor = start
    while cursor <= end:
        days.append(compact_date(cursor))
        cursor += timedelta(days=1)
    return tuple(days)


def _krx_target_date_range(start: date, end: date) -> tuple[date, ...]:
    """Return weekday KRX request dates for a configured official-API window."""

    if start > end:
        raise ValueError("KRX start date must be on or before end date")
    days: list[date] = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return tuple(days)


def parse_krx_official_targets(
    today: date | None = None,
    *,
    default_trading_day: date | None = None,
    lookback_days: int | None = None,
) -> tuple[KrxOfficialMarketTarget, ...]:
    """Build official KRX market/date targets from non-secret env controls."""

    base_date = default_trading_day or latest_weekday_on_or_before(today or date.today())
    resolved_lookback_days = krx_lookback_days(lookback_days or DEFAULT_BATCH_LOOKBACK_DAYS)
    end_date = env_date("HARNESS_BATCH_KRX_END_DATE", base_date)
    start_default = end_date - timedelta(days=resolved_lookback_days)
    start_date = env_date("HARNESS_BATCH_KRX_START_DATE", start_default)
    universe_code = os.getenv("HARNESS_BATCH_KRX_UNIVERSE_CODE", "").strip()
    universe_mode = universe_code == "DOMESTIC_TOP200_MARKET_CAP"
    universe_size = env_int(
        "HARNESS_BATCH_KRX_UNIVERSE_SIZE",
        default=200,
        minimum=1,
        maximum=1000,
    )
    universe_exclude_preferred = env_bool(
        "HARNESS_BATCH_KRX_UNIVERSE_EXCLUDE_PREFERRED",
        default=True,
    )
    if universe_mode:
        tickers: tuple[str, ...] = ()
        markets = csv_values("HARNESS_BATCH_KRX_UNIVERSE_MARKETS", default=("KOSPI", "KOSDAQ"))
    else:
        tickers = csv_values("HARNESS_BATCH_KRX_TICKERS", default=("005930",))
        for ticker in tickers:
            if not (ticker.isdigit() and len(ticker) == 6):
                raise ValueError("HARNESS_BATCH_KRX_TICKERS must contain six-digit Korea tickers")
        markets = csv_values("HARNESS_BATCH_KRX_MARKETS", default=("KOSPI", "KOSDAQ"))
    allowed_markets = {"KOSPI", "KOSDAQ", "KONEX"}
    normalized_markets = tuple(market.upper() for market in markets)
    unknown_markets = [market for market in normalized_markets if market not in allowed_markets]
    if unknown_markets:
        env_name = (
            "HARNESS_BATCH_KRX_UNIVERSE_MARKETS"
            if universe_mode
            else "HARNESS_BATCH_KRX_MARKETS"
        )
        raise ValueError(f"{env_name} contains unsupported markets: {unknown_markets}")
    if universe_mode:
        dates = _date_range_compact(start=start_date, end=end_date)
    else:
        dates = tuple(
            compact_date(target_date)
            for target_date in _krx_target_date_range(start=start_date, end=end_date)
        )
    window_start = compact_date(start_date)
    window_end = compact_date(end_date)
    return tuple(
        KrxOfficialMarketTarget(
            market_code=market,
            bas_dd=bas_dd,
            ticker_filter=tickers,
            requested_window_start=window_start,
            requested_window_end=window_end,
            universe_code=universe_code if universe_mode else None,
            universe_size=universe_size if universe_mode else None,
            universe_exclude_preferred=universe_exclude_preferred,
        )
        for market in normalized_markets
        for bas_dd in dates
    )
