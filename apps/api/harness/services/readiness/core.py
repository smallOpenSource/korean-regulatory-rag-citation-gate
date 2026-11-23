"""Core readiness utilities: constants, payload helpers, T55 and provider-mode builders."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

READY = "READY"
DEGRADED = "DEGRADED"
BLOCKED = "BLOCKED"
FRESH = "FRESH"
STALE = "STALE"
MISSING = "MISSING"
ACCEPTED = "ACCEPTED"
UNVERIFIED = "UNVERIFIED"
OFFICIAL_KRX_APPROVED = "OFFICIAL_KRX_APPROVED"
PYKRX_AUXILIARY_APPROVED = "PYKRX_AUXILIARY_APPROVED"
KRX_BLOCKED = "KRX_BLOCKED"

PROVIDER_ENV_KEYS = {
    "BROKER": "BROKER_REQUIRED",
    "DATA_GO_KR": "DATA_GO_KR_REQUIRED",
    "DART": "DART_REQUIRED",
    "ECOS": "ECOS_REQUIRED",
    "KRX": "KRX_REQUIRED",
}

SYNTHETIC_NOTICE = {
    "status_code": "SYNTHETIC_ONLY",
    "message": (
        "고객·직원·포트폴리오·상담 데이터는 합성 데이터입니다. "
        "실제 고객 PII 또는 실제 계좌 식별자로 해석하면 안 됩니다."
    ),
}

T55_REQUIRED_MIGRATIONS = 7


def _count(metrics: dict[str, Any], key: str) -> int:
    value = metrics.get(key, 0)
    return int(value or 0)


def _check(
    check_code: str,
    observed: int,
    required: int,
    ready_message: str,
    blocked_message: str,
) -> dict[str, Any]:
    status_code = READY if observed >= required else BLOCKED
    return {
        "check_code": check_code,
        "status_code": status_code,
        "observed_count": observed,
        "required_count": required,
        "message": ready_message if status_code == READY else blocked_message,
    }


def _bool_from_env(value: str | None, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _date_value(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _freshness_status(source_as_of: Any, *, max_age_days: int = 3) -> str:
    value = _date_value(source_as_of)
    if value is None:
        return MISSING
    age_days = (datetime.now(UTC).date() - value).days
    return FRESH if age_days <= max_age_days else STALE


def _status_from_checks(checks: Sequence[dict[str, Any]]) -> str:
    if any(check["status_code"] == BLOCKED for check in checks):
        return BLOCKED
    if any(check["status_code"] == DEGRADED for check in checks):
        return DEGRADED
    return READY


def synthetic_customer_notice() -> dict[str, str]:
    """Return the canonical synthetic-data boundary notice for API/UI payloads."""

    return dict(SYNTHETIC_NOTICE)


def build_provider_mode_payload(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Describe strict-external/provider requirements without exposing secrets."""

    env_values = env or os.environ
    profile = (env_values.get("HARNESS_PROFILE") or env_values.get("APP_ENV") or "local").strip()
    profile_code = profile or "local"
    production_profile = profile_code.lower() == "production"
    strict_external = _bool_from_env(
        env_values.get("HARNESS_BATCH_STRICT_EXTERNAL"),
        production_profile,
    )
    required_provider_codes = [
        provider_code
        for provider_code, env_key in PROVIDER_ENV_KEYS.items()
        if _bool_from_env(
            env_values.get(env_key),
            production_profile and provider_code != "KRX",
        )
    ]
    return {
        "profile": profile_code,
        "strict_external": strict_external,
        "required_provider_codes": required_provider_codes,
        "status_code": READY,
        "message": (
            "운영/엄격 모드에서는 공급자 데이터 적재 증거가 있어야 하며, 부족 시 차단됩니다."
            if strict_external
            else (
                "내부 PoC/로컬 공급자 모드가 활성화되어 있습니다. 과거 공급자 이슈는 표시되지만 "
                "현재 화면 준비 상태는 실제 데이터 게이트로 판정합니다."
            )
        ),
    }


def _domestic_check(
    check_code: str,
    status_code: str,
    observed: int,
    required: int,
    message: str,
    *,
    source_as_of: Any = None,
    source_code: str | None = None,
    source_policy_code: str | None = None,
    source_policy_label: str | None = None,
    freshness_status_code: str | None = None,
    quality_status_code: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "check_code": check_code,
        "status_code": status_code,
        "observed_count": observed,
        "required_count": required,
        "message": message,
    }
    if source_as_of is not None:
        payload["source_as_of"] = _iso(source_as_of)
    if source_code:
        payload["source_code"] = source_code
    if source_policy_code:
        payload["source_policy_code"] = source_policy_code
    if source_policy_label:
        payload["source_policy_label"] = source_policy_label
    if freshness_status_code:
        payload["freshness_status_code"] = freshness_status_code
    if quality_status_code:
        payload["quality_status_code"] = quality_status_code
    return payload


def _decimal_from_any(value: Any, default: Decimal) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _int_env(env: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int((env.get(key) or "").strip() or default)
    except ValueError:
        return default


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _evidence_check(
    check_code: str,
    status_code: str,
    observed: int,
    required: int,
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "check_code": check_code,
        "status_code": status_code,
        "observed_count": observed,
        "required_count": required,
        "message": message,
    }
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


def _ready_when_positive(value: int) -> str:
    return READY if value > 0 else BLOCKED


def build_t55_provider_readiness_payload(
    metrics: dict[str, Any],
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build source-specific T55 readiness from persisted DB evidence only."""

    env_values = env or os.environ
    required_migrations_applied = _count(metrics, "required_provider_migrations_applied")
    batch_provider_evidence_table_present = _count(
        metrics,
        "batch_provider_evidence_table_present",
    )
    ecos_rows = _count(metrics, "ecos_parseable_rows")
    ecos_provider_done = _count(metrics, "ecos_provider_done")
    dart_raw_documents = _count(metrics, "dart_raw_documents")
    dart_document_sources = _count(metrics, "dart_document_sources")
    dart_document_chunks = _count(metrics, "dart_document_chunks")
    dart_embedded_chunks = _count(metrics, "dart_embedded_chunks")
    dart_provider_done = _count(metrics, "dart_provider_done")
    official_krx_price_bar_rows = _count(metrics, "official_krx_price_bar_rows")
    official_krx_policy_rows = _count(metrics, "official_krx_policy_rows")
    pykrx_price_bar_rows = _count(metrics, "pykrx_price_bar_rows")
    krx_provider_done = _count(metrics, "krx_provider_done")
    official_krx_provider_done = _count(metrics, "official_krx_provider_done")
    pykrx_auxiliary_policy_rows = _count(metrics, "pykrx_auxiliary_policy_rows")

    krx_enabled = _bool_from_env(env_values.get("HARNESS_BATCH_KRX_ENABLED"), False)
    requested_krx_source = (env_values.get("HARNESS_BATCH_KRX_SOURCE") or "").strip().upper()
    requested_krx_policy = (env_values.get("HARNESS_BATCH_KRX_POLICY") or "").strip().upper()
    krx_policy_code = "KRX_BLOCKED"
    krx_policy_status = BLOCKED
    krx_policy_message = (
        "KRX source policy is disabled; readiness must stay blocked until official KRX "
        "is approved or PYKRX_AUXILIARY is explicitly enabled."
    )
    if krx_enabled and requested_krx_source == "KRX":
        krx_policy_code = OFFICIAL_KRX_APPROVED
        official_policy_approved = requested_krx_policy == OFFICIAL_KRX_APPROVED
        official_evidence_ready = (
            official_policy_approved
            and official_krx_price_bar_rows > 0
            and official_krx_provider_done > 0
            and official_krx_policy_rows > 0
        )
        krx_policy_status = READY if official_evidence_ready else BLOCKED
        krx_policy_message = (
            "KRX 공식 OpenAPI 자료가 적재되어 있습니다."
            if krx_policy_status == READY
            else "공식 KRX 정책 승인이 필요합니다. (관리자 환경 변수 확인)"
            if not official_policy_approved
            else (
                "공식 KRX 정책이 설정되어 있으나, KRX 자료·공급자 완료 증거·정책 승인 증거 중 일부가 누락되었습니다."
            )
        )
    elif krx_enabled and requested_krx_source == "PYKRX":
        krx_policy_code = "PYKRX_AUXILIARY"
        pykrx_policy_approved = requested_krx_policy == PYKRX_AUXILIARY_APPROVED
        pykrx_evidence_ready = (
            pykrx_policy_approved
            and pykrx_price_bar_rows > 0
            and krx_provider_done > 0
            and pykrx_auxiliary_policy_rows > 0
        )
        krx_policy_status = READY if pykrx_evidence_ready else BLOCKED
        krx_policy_message = (
            "pykrx 비공식 보조 출처 자료가 적재되어 있습니다."
            if krx_policy_status == READY
            else (
                "보조 출처(pykrx) 정책 승인이 필요합니다. 관리자 환경 변수 HARNESS_BATCH_KRX_POLICY=PYKRX_AUXILIARY_APPROVED 를 설정하세요."
            )
            if not pykrx_policy_approved
            else (
                "보조 출처(pykrx) 정책이 설정되어 있으나, pykrx 자료·공급자 완료 증거·정책 승인 증거 중 일부가 누락되었습니다."
            )
        )
    elif krx_enabled:
        krx_policy_message = (
            "KRX 출처 정책이 지원되지 않는 값으로 설정되어 있습니다. 공식 KRX 또는 보조 출처(pykrx)를 명시해야 합니다."
        )

    schema_ready = (
        required_migrations_applied >= T55_REQUIRED_MIGRATIONS
        and batch_provider_evidence_table_present > 0
    )
    ecos_ready = ecos_rows > 0 and ecos_provider_done > 0
    dart_documents_ready = (
        dart_raw_documents > 0 and dart_document_sources > 0 and dart_provider_done > 0
    )
    dart_chunks_ready = dart_document_chunks > 0 and dart_embedded_chunks > 0

    checks = [
        _evidence_check(
            "schema.provider_evidence",
            READY if schema_ready else BLOCKED,
            required_migrations_applied,
            T55_REQUIRED_MIGRATIONS,
            (
                "공급자 증거 테이블과 필수 스키마 마이그레이션이 모두 적용되어 있습니다."
                if schema_ready
                else (
                    "공급자 준비 상태를 신뢰하기 전에 필수 스키마 마이그레이션과 공급자 증거 테이블이 적재되어야 합니다."
                )
            ),
            batch_provider_evidence_table_present=batch_provider_evidence_table_present,
        ),
        _evidence_check(
            "provider.ecos_parseable_rows",
            READY if ecos_ready else BLOCKED,
            ecos_rows,
            1,
            (
                "ECOS 파싱 데이터가 거시지표 테이블에 공급자 증거와 함께 적재되어 있습니다."
                if ecos_ready
                else (
                    "ECOS 파싱 데이터가 적재되지 않았거나 공급자 완료 증거가 없습니다. 부족한 증거로는 준비 상태를 종료할 수 없습니다."
                )
            ),
            provider_done_count=ecos_provider_done,
            latest_reference_date=_iso(metrics.get("latest_ecos_reference_date")),
        ),
        _evidence_check(
            "provider.dart_parseable_documents",
            READY if dart_documents_ready else BLOCKED,
            dart_raw_documents,
            1,
            (
                "OpenDART 공시 본문과 출처 메타데이터가 공급자 증거와 함께 적재되어 있습니다."
                if dart_documents_ready
                else (
                    "OpenDART은 실제 공시 본문 1건 이상과 출처 메타데이터, 공급자 완료 증거가 모두 적재되어야 합니다."
                )
            ),
            provider_done_count=dart_provider_done,
            document_source_count=dart_document_sources,
        ),
        _evidence_check(
            "rag.dart_chunks",
            READY if dart_chunks_ready else BLOCKED,
            dart_embedded_chunks,
            1,
            (
                "OpenDART 청크가 파서 버전을 거쳐 임베딩까지 적재되어 인용 기반 RAG에 사용 가능합니다."
                if dart_chunks_ready
                else "OpenDART 청크 또는 임베딩이 누락되어 RAG 준비 상태가 차단됩니다."
            ),
            chunk_count=dart_document_chunks,
        ),
        _evidence_check(
            "provider.krx_policy",
            krx_policy_status,
            official_krx_price_bar_rows if requested_krx_source == "KRX" else pykrx_price_bar_rows,
            1,
            krx_policy_message,
            policy_code=krx_policy_code,
            requested_source=requested_krx_source or "DISABLED",
            requested_policy_code=requested_krx_policy or "UNSET",
            provider_done_count=(
                official_krx_provider_done if requested_krx_source == "KRX" else krx_provider_done
            ),
            policy_evidence_count=(
                official_krx_policy_rows
                if requested_krx_source == "KRX"
                else pykrx_auxiliary_policy_rows
            ),
        ),
    ]
    status_code = _status_from_checks(checks)
    return {
        "status_code": status_code,
        "policy_code": krx_policy_code,
        "checks": checks,
        "message": (
            "공급자 준비 상태가 스키마·ECOS·OpenDART·RAG·KRX 정책 증거로 모두 뒷받침되고 있습니다."
            if status_code == READY
            else (
                "공급자 준비 상태가 모든 게이트 증거를 충족하기 전까지 차단됩니다."
            )
        ),
    }


def blocked_market_valuation_source(synthetic_as_of: Any = None) -> dict[str, Any]:
    """Return per-holding provenance when only synthetic holding valuation exists."""

    return {
        "status_code": BLOCKED,
        "source_code": None,
        "source_as_of": None,
        "synthetic_as_of": _iso(synthetic_as_of),
        "freshness_status_code": MISSING,
        "quality_status_code": UNVERIFIED,
        "message": (
            "실제 국내 시세 기준시각·품질검사 자료가 없어 합성 보유 평가액만 표시합니다."
        ),
    }


def build_portfolio_valuation_payload(
    portfolios: Sequence[dict[str, Any]],
    holdings: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize the current Customer 360 valuation boundary for UI display."""

    total_market_value = sum(
        Decimal(str(holding.get("market_value_krw") or 0)) for holding in holdings
    )
    latest_synthetic_as_of = max(
        (_date_value(holding.get("as_of_date")) for holding in holdings),
        default=None,
    )
    status_code = BLOCKED if holdings else DEGRADED
    return {
        "status_code": status_code,
        "portfolio_count": len(portfolios),
        "holding_count": len(holdings),
        "display_basis_code": "SYNTHETIC_HOLDING_VALUE",
        "total_market_value_krw": total_market_value,
        "source_code": None,
        "source_as_of": None,
        "synthetic_as_of": _iso(latest_synthetic_as_of),
        "freshness_status_code": MISSING,
        "quality_status_code": UNVERIFIED,
        "message": (
            "포트폴리오 금액은 합성 시드 기반입니다. 실제 국내 시세 바가 승인되기 전까지 "
            "실제 시장 평가액으로 사용하지 않습니다."
        ),
    }


def synthetic_portfolio_provenance(
    portfolios: Sequence[dict[str, Any]] = (),
    holdings: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Disclosure-only projection of the valuation basis for AI dispatchers that
    reference synthetic customer/portfolio data but do not surface a holding total.

    consultation_briefing and nba_script use customer attributes (risk grade,
    segment, total_assets_krw) and portfolio names — not per-holding market values
    — so stamping the full ``build_portfolio_valuation_payload`` (with a 0 holding
    total) would mislead. This carries only the data-quality basis
    (display_basis_code / freshness_status_code / quality_status_code + message) so
    their ``output_json`` discloses the synthetic/unverified provenance consistently
    with portfolio_analysis. It delegates to ``build_portfolio_valuation_payload`` so
    a future real-data basis flip propagates here automatically.
    """
    valuation = build_portfolio_valuation_payload(portfolios, holdings)
    return {
        "display_basis_code": valuation["display_basis_code"],
        "freshness_status_code": valuation["freshness_status_code"],
        "quality_status_code": valuation["quality_status_code"],
        "message": valuation["message"],
    }
