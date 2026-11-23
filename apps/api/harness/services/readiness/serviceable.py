"""Serviceable readiness: canonical top-200 logic and domestic-market builders."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from .core import (
    ACCEPTED,
    BLOCKED,
    DEGRADED,
    FRESH,
    MISSING,
    OFFICIAL_KRX_APPROVED,
    PYKRX_AUXILIARY_APPROVED,
    KRX_BLOCKED,
    READY,
    STALE,
    UNVERIFIED,
    _bool_from_env,
    _count,
    _decimal_from_any,
    _domestic_check,
    _freshness_status,
    _int_env,
    _iso,
    _json_mapping,
    _status_from_checks,
    build_provider_mode_payload,
)


def _krx_policy_status(metrics: dict[str, Any]) -> dict[str, str | int]:
    """Return the KRX/PYKRX source-policy gate without treating pykrx as official KRX."""

    pykrx_auxiliary_rows = _count(metrics, "pykrx_auxiliary_policy_rows")
    official_krx_policy_rows = _count(metrics, "official_krx_policy_rows")
    official_krx_price_rows = _count(metrics, "official_krx_price_bar_rows")
    official_krx_provider_done = _count(metrics, "official_krx_provider_done")
    official_ready = (
        official_krx_price_rows > 0
        and official_krx_policy_rows > 0
        and official_krx_provider_done > 0
    )
    if official_ready:
        return {
            "status_code": READY,
            "observed_count": official_krx_price_rows,
            "source_code": "KRX",
            "source_policy_code": OFFICIAL_KRX_APPROVED,
            "source_policy_label": "KRX official OpenAPI policy approved",
        }
    if pykrx_auxiliary_rows > 0:
        return {
            "status_code": READY,
            "observed_count": pykrx_auxiliary_rows,
            "source_code": "PYKRX",
            "source_policy_code": PYKRX_AUXILIARY_APPROVED,
            "source_policy_label": "PYKRX_AUXILIARY internal PoC policy approved",
        }
    return {
        "status_code": BLOCKED,
        "observed_count": 0,
        "source_code": "",
        "source_policy_code": KRX_BLOCKED,
        "source_policy_label": "KRX/PYKRX policy blocked",
    }


def _top200_gate_required(metrics: dict[str, Any], env_values: Mapping[str, str]) -> bool:
    configured_universe = (env_values.get("HARNESS_BATCH_KRX_UNIVERSE_CODE") or "").strip()
    official_krx_requested = (
        (env_values.get("HARNESS_BATCH_KRX_SOURCE") or "").strip().upper() == "KRX"
        and (env_values.get("HARNESS_BATCH_KRX_POLICY") or "").strip().upper()
        == OFFICIAL_KRX_APPROVED
    )
    serviceable_profile = (env_values.get("HARNESS_PROFILE") or "").strip().lower() == "serviceable"
    explicit_required = _bool_from_env(
        env_values.get("HARNESS_SERVICEABLE_READINESS_REQUIRED"),
        False,
    )
    return (
        explicit_required
        or serviceable_profile
        or (official_krx_requested and configured_universe == "DOMESTIC_TOP200_MARKET_CAP")
        or _count(metrics, "top200_universe_snapshot_count") > 0
        or _count(metrics, "top200_expected_member_days") > 0
    )


def build_top200_coverage_payload(
    metrics: dict[str, Any],
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return serviceable top-200/30-day coverage without fabricating readiness.

    The payload is intentionally metrics-driven so API callers and the standalone
    validator can share the same contract. It remains advisory unless the
    serviceable profile/official KRX universe is configured or persisted top-200 evidence exists.
    """

    import os
    env_values = env or os.environ
    universe_code = (
        env_values.get("HARNESS_BATCH_KRX_UNIVERSE_CODE")
        or str(metrics.get("top200_universe_code") or "DOMESTIC_TOP200_MARKET_CAP")
    )
    required_count = _count(metrics, "top200_target_size") or _int_env(
        env_values,
        "HARNESS_BATCH_KRX_UNIVERSE_SIZE",
        200,
    )
    lookback_days = _count(metrics, "top200_lookback_days") or _int_env(
        env_values,
        "HARNESS_BATCH_KRX_LOOKBACK_DAYS",
        30,
    )
    required_ratio = _decimal_from_any(
        metrics.get("top200_required_coverage_ratio")
        or env_values.get("HARNESS_BATCH_KRX_MIN_TRADING_DAY_COVERAGE_RATIO"),
        Decimal("1.0"),
    )
    snapshot_count = _count(metrics, "top200_universe_snapshot_count")
    selected_count = _count(metrics, "top200_selected_count")
    expected_member_days = _count(metrics, "top200_expected_member_days")
    observed_member_days = _count(metrics, "top200_valid_member_days") or _count(
        metrics,
        "top200_observed_member_days",
    )
    missing_member_days = _count(metrics, "top200_missing_member_days")
    if expected_member_days and not metrics.get("top200_missing_member_days"):
        missing_member_days = max(expected_member_days - observed_member_days, 0)
    coverage_ratio = (
        Decimal(observed_member_days) / Decimal(expected_member_days)
        if expected_member_days > 0
        else Decimal("0")
    )
    coverage_ready = (
        snapshot_count > 0
        and selected_count >= required_count
        and expected_member_days > 0
        and missing_member_days == 0
        and coverage_ratio >= required_ratio
    )
    universe_ready = snapshot_count > 0 and selected_count >= required_count
    gate_required = _top200_gate_required(metrics, env_values)

    blocking_reasons: list[str] = []
    if snapshot_count <= 0:
        blocking_reasons.append("공식 KRX 상위 200 종목 기준 데이터가 아직 준비되지 않았습니다.")
    if selected_count < required_count:
        blocking_reasons.append(
            f"선택된 종목 {selected_count}개가 요구 기준 {required_count}개에 못 미칩니다."
        )
    if expected_member_days <= 0:
        blocking_reasons.append("공식 KRX 기준 종목·거래일 산정 기준이 아직 준비되지 않았습니다.")
    if missing_member_days > 0:
        blocking_reasons.append(
            f"기준 종목·거래일 {missing_member_days}건의 KRX 시세 자료가 누락되었습니다."
        )
    if expected_member_days > 0 and coverage_ratio < required_ratio:
        blocking_reasons.append(
            f"커버리지 {coverage_ratio} 가 요구 기준 {required_ratio} 미만입니다."
        )

    if not gate_required:
        # Gate intentionally skipped for this profile — don't surface
        # "blocking" copy on the PB dashboard when the missing data is
        # by design rather than a real incident.
        blocking_reasons = []
        status_code = READY
    elif coverage_ready:
        status_code = READY
    elif not universe_ready or expected_member_days <= 0:
        status_code = BLOCKED
    else:
        status_code = DEGRADED

    return {
        "universe_code": universe_code,
        "as_of_date": _iso(metrics.get("top200_as_of_date")),
        "resolved_trading_date": _iso(metrics.get("top200_resolved_trading_date")),
        "selected_count": selected_count,
        "required_count": required_count,
        "lookback_days": lookback_days,
        "required_coverage_ratio": float(required_ratio),
        "expected_trading_days_by_market": _json_mapping(
            metrics.get("top200_expected_trading_days_by_market")
        ),
        "expected_member_days": expected_member_days,
        "observed_member_days": observed_member_days,
        "covered_tickers": _count(metrics, "top200_covered_tickers"),
        "coverage_ratio": float(coverage_ratio),
        "missing_member_days": missing_member_days,
        "latest_source_as_of": _iso(
            metrics.get("top200_latest_source_as_of")
            or metrics.get("latest_price_bar_source_as_of")
        ),
        "status_code": status_code,
        "required": gate_required,
        "snapshot_count": snapshot_count,
        "blocking_reasons": blocking_reasons,
        "message": (
            "공식 KRX 상위 200 종목 30일 커버리지가 충족되었습니다."
            if status_code == READY and coverage_ready
            else (
                "이 프로필에서는 상위 200 종목 30일 커버리지 게이트를 적용하지 않습니다."
            )
            if not gate_required and snapshot_count <= 0
            else "공식 KRX 상위 200 종목 30일 커버리지가 아직 충족되지 않았습니다."
        ),
    }


def build_domestic_market_payload(metrics: dict[str, Any]) -> dict[str, Any]:
    """Build domestic-market readiness used by API and web screens.

    The payload intentionally distinguishes legacy or missing market data from accepted
    production price-bar data so local/demo environments cannot look production-ready.
    """

    security_master_rows = _count(metrics, "security_master_rows")
    price_bar_rows = _count(metrics, "price_bar_rows")
    accepted_price_bar_rows = _count(metrics, "accepted_price_bar_rows")
    legacy_market_price_rows = _count(metrics, "legacy_market_price_rows")
    quality_check_count = _count(metrics, "quality_check_count")
    quality_failed_count = _count(metrics, "quality_failed_count")
    dart_chunk_count = _count(metrics, "dart_document_chunks")
    embedded_dart_chunks = _count(metrics, "embedded_dart_document_chunks")
    krx_policy = _krx_policy_status(metrics)
    top200_coverage = build_top200_coverage_payload(metrics)
    source_as_of = (
        metrics.get("latest_price_bar_source_as_of")
        or metrics.get("latest_legacy_market_price_date")
    )
    source_code = metrics.get("latest_price_bar_provider_code") or metrics.get(
        "latest_legacy_source_code"
    )
    freshness_status_code = _freshness_status(source_as_of)

    provider_mode = build_provider_mode_payload()
    freshness_check_status = (
        READY
        if freshness_status_code == FRESH
        else BLOCKED
        if freshness_status_code == MISSING
        else DEGRADED
    )
    quality_accepted = accepted_price_bar_rows > 0 and quality_failed_count == 0

    checks: list[dict[str, Any]] = [
        _domestic_check(
            "market.security_master",
            READY if security_master_rows > 0 else BLOCKED,
            security_master_rows,
            1,
            (
                "국내 종목 기준 정보가 적재되어 있습니다."
                if security_master_rows > 0
                else (
                    "국내 종목 기준 정보가 누락되어 시장 연동 상품을 정상적으로 평가할 수 없습니다."
                )
            ),
        ),
        _domestic_check(
            "market.price_coverage",
            (
                READY
                if accepted_price_bar_rows > 0
                else DEGRADED
                if legacy_market_price_rows > 0 or price_bar_rows > 0
                else BLOCKED
            ),
            accepted_price_bar_rows or price_bar_rows or legacy_market_price_rows,
            1,
            (
                "검증을 통과한 국내 시세 데이터가 적재되어 있습니다."
                if accepted_price_bar_rows > 0
                else (
                    "검증 미통과 시세만 존재합니다. 화면 평가는 출처 미검증으로 표시되어야 합니다."
                )
                if legacy_market_price_rows > 0 or price_bar_rows > 0
                else (
                    "검증된 국내 시세 데이터가 없어 일부 평가 화면이 차단/제한 표시됩니다."
                )
            ),
            source_as_of=source_as_of,
            source_code=str(source_code) if source_code else None,
        ),
        _domestic_check(
            "market.freshness",
            freshness_check_status,
            0 if freshness_status_code == MISSING else 1,
            1,
            (
                "최신 국내 시장 데이터 출처가 화면 표시 기준의 신선도를 충족합니다."
                if freshness_status_code == FRESH
                else "최신 국내 시장 데이터 출처가 오래되어 제한 상태로 표시됩니다."
                if freshness_status_code == STALE
                else "국내 시장 데이터의 기준시각이 확인되지 않습니다."
            ),
            source_as_of=source_as_of,
            source_code=str(source_code) if source_code else None,
            freshness_status_code=freshness_status_code,
        ),
        _domestic_check(
            "market.quality",
            (
                READY
                if accepted_price_bar_rows > 0 and quality_failed_count == 0
                else DEGRADED
                if quality_check_count > 0 or legacy_market_price_rows > 0
                else BLOCKED
            ),
            accepted_price_bar_rows if quality_accepted else quality_check_count,
            1,
            (
                "국내 시세 품질 검증이 모두 통과되었습니다."
                if accepted_price_bar_rows > 0 and quality_failed_count == 0
                else (
                    "품질 검증이 일부 통과되지 않았거나 미검증 데이터만 있습니다. 검증 전/제한 상태로 표시됩니다."
                )
                if quality_check_count > 0 or legacy_market_price_rows > 0
                else "국내 시세 품질 보고서가 아직 적재되지 않았습니다."
            ),
            quality_status_code=ACCEPTED if quality_accepted else UNVERIFIED,
        ),
        _domestic_check(
            "market.dart_chunks",
            READY if dart_chunk_count > 0 else BLOCKED,
            dart_chunk_count,
            1,
            (
                "OpenDART 파서 버전 청크가 적재되어 있습니다."
                if dart_chunk_count > 0
                else "OpenDART 청크가 없어 RAG 시장 근거 답변이 차단 상태로 유지됩니다."
            ),
        ),
        _domestic_check(
            "market.embeddings",
            READY if embedded_dart_chunks > 0 else BLOCKED,
            embedded_dart_chunks,
            1,
            (
                "OpenDART 임베딩 청크가 적재되어 RAG 인용 답변에 사용 가능합니다."
                if embedded_dart_chunks > 0
                else (
                    "OpenDART 임베딩이 없어 시장 RAG 인용 답변이 차단됩니다."
                )
            ),
        ),
        _domestic_check(
            "market.top200_universe",
            top200_coverage["status_code"]
            if top200_coverage["required"] or top200_coverage["snapshot_count"] > 0
            else READY,
            int(top200_coverage["selected_count"]),
            int(top200_coverage["required_count"]),
            (
                "공식 KRX 상위 200 종목 기준 데이터가 적재되어 있습니다."
                if top200_coverage["selected_count"] >= top200_coverage["required_count"]
                else "공식 KRX 상위 200 종목 기준 데이터가 누락되었거나 부족합니다."
            ),
            source_code="KRX",
            source_policy_code=OFFICIAL_KRX_APPROVED,
        ),
        _domestic_check(
            "market.top200_30d_coverage",
            top200_coverage["status_code"]
            if top200_coverage["required"] or top200_coverage["snapshot_count"] > 0
            else READY,
            int(top200_coverage["observed_member_days"]),
            int(top200_coverage["expected_member_days"] or 1),
            str(top200_coverage["message"]),
            source_as_of=top200_coverage["latest_source_as_of"],
            source_code="KRX",
            source_policy_code=OFFICIAL_KRX_APPROVED,
        ),
        _domestic_check(
            "provider.krx_policy",
            str(krx_policy["status_code"]),
            int(krx_policy["observed_count"]),
            1,
            (
                "KRX 계열 자료의 출처 정책이 명확히 지정되어 있습니다."
                if krx_policy["status_code"] == READY
                else (
                    "KRX 계열 자료는 공식 KRX 승인 또는 보조 정책이 명시되기 전까지 차단됩니다."
                )
            ),
            source_code=str(krx_policy["source_code"]) or None,
            source_policy_code=str(krx_policy["source_policy_code"]),
            source_policy_label=str(krx_policy["source_policy_label"]),
        ),
        _domestic_check(
            "provider.strictness",
            provider_mode["status_code"],
            len(provider_mode["required_provider_codes"]),
            0,
            provider_mode["message"],
        ),
    ]
    status_code = _status_from_checks(checks)
    return {
        "status_code": status_code,
        "source_code": str(source_code) if source_code else None,
        "source_policy_code": str(krx_policy["source_policy_code"]),
        "source_policy_label": str(krx_policy["source_policy_label"]),
        "source_as_of": _iso(source_as_of),
        "freshness_status_code": freshness_status_code,
        "quality_status_code": ACCEPTED if quality_accepted else UNVERIFIED,
        "checks": checks,
        "top200_coverage": top200_coverage,
        "message": (
            "국내 시장 기준 데이터가 화면 표시 준비를 마쳤습니다."
            if status_code == READY
            else (
                "국내 시장 기준 데이터가 아직 완전하지 않아 일부 화면이 차단 또는 "
                "제한 표시됩니다."
            )
        ),
    }
