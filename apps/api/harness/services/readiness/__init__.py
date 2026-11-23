"""Data readiness and API/UI production-surface response helpers.

Backward-compat re-export shim (Stage 3). All public names remain importable
from ``apps.api.harness.services.readiness`` as before the package split.
Real implementations live in the submodules:
  - core.py        — constants, utilities, T55, provider-mode, portfolio helpers
  - serviceable.py — top-200 and domestic-market builders
  - quarantine.py  — REG-04 quarantine readiness surface (Stage 3)
"""

from __future__ import annotations

from typing import Any

from .core import (
    ACCEPTED,
    BLOCKED,
    DEGRADED,
    FRESH,
    KRX_BLOCKED,
    MISSING,
    OFFICIAL_KRX_APPROVED,
    PROVIDER_ENV_KEYS,
    PYKRX_AUXILIARY_APPROVED,
    READY,
    STALE,
    SYNTHETIC_NOTICE,
    T55_REQUIRED_MIGRATIONS,
    UNVERIFIED,
    _bool_from_env,
    _check,
    _count,
    _date_value,
    _decimal_from_any,
    _domestic_check,
    _evidence_check,
    _freshness_status,
    _int_env,
    _iso,
    _json_mapping,
    _ready_when_positive,
    _status_from_checks,
    blocked_market_valuation_source,
    build_portfolio_valuation_payload,
    build_provider_mode_payload,
    build_t55_provider_readiness_payload,
    synthetic_customer_notice,
)
from .serviceable import (
    _krx_policy_status,
    _top200_gate_required,
    build_domestic_market_payload,
    build_top200_coverage_payload,
)
from .quarantine import build_quarantine_readiness_payload


def build_readiness_payload(metrics: dict[str, Any]) -> dict[str, Any]:
    """Build a deterministic readiness payload from aggregate DB metrics."""

    active_customers = _count(metrics, "active_customers")
    portfolios = _count(metrics, "portfolios")
    active_house_views = _count(metrics, "active_house_views")
    embedded_chunks = _count(metrics, "embedded_chunks")
    pending_raw_documents = _count(metrics, "pending_raw_documents")
    failed_recent = _count(metrics, "failed_recent_batches")
    skipped_recent = _count(metrics, "skipped_recent_batches")
    provider_detail_problem_recent = _count(metrics, "provider_detail_problem_recent")
    price_bar_count = _count(metrics, "price_bar_count") or _count(metrics, "price_bar_rows")
    market_quality_issues = _count(metrics, "market_quality_issues_recent") or _count(
        metrics,
        "quality_failed_count",
    )

    checks = [
        _check(
            "seed.active_customers",
            active_customers,
            1,
            "Synthetic customer baseline is available.",
            "Run db/seed.py --profile full-mvp before API/Web verification.",
        ),
        _check(
            "seed.portfolios",
            portfolios,
            1,
            "Portfolio baseline is available.",
            "Seeded portfolios are missing, so Customer 360 cannot be verified end-to-end.",
        ),
        _check(
            "house_view.active",
            active_house_views,
            1,
            "활성 하우스뷰가 등록되어 있습니다.",
            "상담·대시보드 흐름에 사용 가능한 활성 하우스뷰가 아직 없습니다.",
        ),
        _check(
            "rag.embedded_chunks",
            embedded_chunks,
            1,
            "RAG 임베딩 청크가 적재되어 있습니다.",
            "RAG는 실 임베딩이 적재되기 전까지 차단됩니다.",
        ),
    ]

    provider_problem_history = failed_recent + skipped_recent + provider_detail_problem_recent
    market_degraded = int(price_bar_count == 0) + market_quality_issues
    domestic_market = build_domestic_market_payload(metrics)
    t55_provider_readiness = build_t55_provider_readiness_payload(metrics)
    provider_mode = build_provider_mode_payload()
    current_data_ready = (
        market_degraded == 0
        and domestic_market["status_code"] == READY
        and t55_provider_readiness["status_code"] == READY
    )
    provider_history_blocks_readiness = provider_problem_history > 0 and not current_data_ready
    checks.append(
        {
            "check_code": "provider.recent_batches",
            "status_code": DEGRADED if provider_history_blocks_readiness else READY,
            "observed_count": provider_problem_history,
            "required_count": 0,
            "message": (
                "최근 공급자 작업에 건너뜀/실패/무자료 증거가 포함되어 화면이 차단 상태로 표시됩니다."
                if provider_history_blocks_readiness
                else (
                    "공급자 이슈 이력이 감사용으로 보존되어 있으나, 현재 데이터 게이트는 준비 완료 상태입니다."
                )
                if provider_problem_history
                else "최근 공급자 건너뜀/실패/무자료 증거가 없습니다."
            ),
        }
    )
    checks.append(
        {
            "check_code": "market.price_bars",
            "status_code": DEGRADED if market_degraded else READY,
            "observed_count": price_bar_count,
            "required_count": 1,
            "message": (
                "국내 주식 시세 데이터가 누락되었거나 최근 품질 이슈가 있습니다."
                if market_degraded
                else "국내 주식 시세 데이터가 정상 적재되어 있습니다."
            ),
        }
    )

    hard_blocked = any(check["status_code"] == BLOCKED for check in checks)
    status_code = (
        BLOCKED
        if hard_blocked
        or domestic_market["status_code"] == BLOCKED
        or t55_provider_readiness["status_code"] == BLOCKED
        else DEGRADED
        if provider_history_blocks_readiness
        or domestic_market["status_code"] == DEGRADED
        or t55_provider_readiness["status_code"] == DEGRADED
        else READY
    )
    return {
        "status_code": status_code,
        "checks": checks,
        "domestic_market": domestic_market,
        "t55_provider_readiness": t55_provider_readiness,
        "rag": {
            "status_code": READY if embedded_chunks > 0 else BLOCKED,
            "embedded_chunk_count": embedded_chunks,
            "pending_raw_document_count": pending_raw_documents,
            "message": (
                "RAG 검색에 사용 가능한 임베딩 청크가 적재되어 있습니다."
                if embedded_chunks > 0
                else "RAG 검색용 임베딩 청크가 적재되지 않아 검색이 차단 상태입니다."
            ),
        },
        "batch_status_summary": {
            "running": _count(metrics, "running_batches"),
            "done_recent": _count(metrics, "done_recent_batches"),
            "failed_recent": failed_recent,
            "skipped_recent": skipped_recent,
        },
        "provider_mode": provider_mode,
        "synthetic_customer_notice": synthetic_customer_notice(),
    }


__all__ = [
    # constants
    "ACCEPTED",
    "BLOCKED",
    "DEGRADED",
    "FRESH",
    "KRX_BLOCKED",
    "MISSING",
    "OFFICIAL_KRX_APPROVED",
    "PROVIDER_ENV_KEYS",
    "PYKRX_AUXILIARY_APPROVED",
    "READY",
    "STALE",
    "SYNTHETIC_NOTICE",
    "T55_REQUIRED_MIGRATIONS",
    "UNVERIFIED",
    # public functions
    "blocked_market_valuation_source",
    "build_domestic_market_payload",
    "build_portfolio_valuation_payload",
    "build_provider_mode_payload",
    "build_quarantine_readiness_payload",
    "build_readiness_payload",
    "build_t55_provider_readiness_payload",
    "build_top200_coverage_payload",
    "synthetic_customer_notice",
]
