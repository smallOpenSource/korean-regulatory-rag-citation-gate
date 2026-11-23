"""Backend API lane contract tests without mocks or external services."""

from __future__ import annotations

import ast
import importlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from apps.api.harness.api.router import build_api_router
from apps.api.harness.api.routers.realtime import (
    event_visible_to_actor,
    realtime_channel_for_event,
)
from apps.api.harness.core.rbac import ActorContext
from apps.api.harness.core.security import create_access_token
from apps.api.harness.core.sql import validate_sql_text
from apps.api.harness.services.ai_jobs import ai_unavailable_payload, prompt_hash_from_payload
from apps.api.harness.services.email_delivery import (
    EmailContentRejectedError,
    validate_display_safe_email_content,
)
from apps.api.harness.services.readiness import (
    blocked_market_valuation_source,
    build_portfolio_valuation_payload,
    build_provider_mode_payload,
    build_readiness_payload,
    build_t55_provider_readiness_payload,
    synthetic_customer_notice,
)
from apps.api.harness.services.simulations import (
    RecommendationGateInput,
    evaluate_order_gates,
    evaluate_recommendation_gates,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROUTE_SCREEN_MATRIX_PATH = PROJECT_ROOT / "docs" / "api" / "API-03_route_screen_backlog_matrix.md"
REPOSITORY_MODULES = (
    "apps.api.harness.repositories.ai",
    "apps.api.harness.repositories.audit",
    "apps.api.harness.repositories.auth",
    "apps.api.harness.repositories.batch",
    "apps.api.harness.repositories.consultations",
    "apps.api.harness.repositories.customers",
    "apps.api.harness.repositories.dashboard",
    "apps.api.harness.repositories.documents",
    "apps.api.harness.repositories.email",
    "apps.api.harness.repositories.house_views",
    "apps.api.harness.repositories.nba",
    "apps.api.harness.repositories.products",
    "apps.api.harness.repositories.readiness",
    "apps.api.harness.repositories.simulations",
)


def _fully_ready_market_metrics() -> dict[str, object]:
    return {
        "active_customers": 20,
        "portfolios": 20,
        "active_house_views": 1,
        "embedded_chunks": 4,
        "pending_raw_documents": 0,
        "security_master_rows": 1,
        "accepted_price_bar_rows": 1,
        "price_bar_count": 1,
        "price_bar_rows": 1,
        "quality_check_count": 1,
        "quality_failed_count": 0,
        "market_quality_issues_recent": 0,
        "latest_price_bar_source_as_of": date.today().isoformat(),
        "latest_price_bar_provider_code": "PYKRX",
        "dart_raw_documents": 1,
        "dart_document_sources": 1,
        "dart_document_chunks": 1,
        "embedded_dart_document_chunks": 1,
        "dart_embedded_chunks": 1,
        "required_provider_migrations_applied": 7,
        "batch_provider_evidence_table_present": 1,
        "ecos_parseable_rows": 1,
        "ecos_provider_done": 1,
        "dart_provider_done": 1,
        "pykrx_price_bar_rows": 1,
        "official_krx_price_bar_rows": 0,
        "krx_provider_done": 1,
        "official_krx_provider_done": 0,
        "pykrx_auxiliary_policy_rows": 1,
    }

EXPECTED_ROUTE_PATHS = {
    "/auth/login",
    "/auth/refresh",
    "/auth/logout",
    "/ai-jobs/{job_id}",
    "/ai-outputs/{output_id}",
    "/customers",
    "/customers/{customer_id}",
    "/customers/{customer_id}/portfolio-analysis",
    "/dashboard",
    "/products",
    "/consultations",
    "/consultations/{consultation_id}",
    "/consultations/{consultation_id}/briefing",
    "/consultations/{consultation_id}/compliance-check",
    "/email-drafts",
    "/email-drafts/{draft_id}/send",
    "/house-views",
    "/house-views/{house_view_id}",
    "/house-views/{house_view_id}/generate",
    "/house-views/{house_view_id}/activate",
    "/nba-actions",
    "/nba-actions/{nba_id}/status",
    "/aftercare-events/{event_id}/resolve",
    "/rag/query",
    "/recommendation-simulations",
    "/order-simulations",
    "/order-simulations/{order_simulation_id}/execute-simulated",
    "/batch/status",
    "/data/readiness",
    "/audit-logs",
}


def _route_paths() -> set[str]:
    paths: set[str] = set()
    for path in (PROJECT_ROOT / "apps" / "api" / "harness" / "api" / "routers").glob("*.py"):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                    value = decorator.args[0].value
                    if isinstance(value, str) and value.startswith("/"):
                        paths.add(value)
    return paths


def test_backend_route_surface_matches_contract_paths():
    assert _route_paths() >= EXPECTED_ROUTE_PATHS


def test_realtime_websocket_route_and_inventory_matrix_are_registered():
    websocket_paths = {
        getattr(route, "path", "")
        for route in build_api_router().routes
        if route.__class__.__name__ == "APIWebSocketRoute"
    }
    matrix_text = ROUTE_SCREEN_MATRIX_PATH.read_text(encoding="utf-8")

    assert websocket_paths == {"/ws"}
    for route_path in sorted(EXPECTED_ROUTE_PATHS | {"/health", "/health/config", "/ws"}):
        assert f"`{route_path}`" in matrix_text
    assert "T20 WebSocket server" in matrix_text


@pytest.mark.skip(
    reason="Obsolete: query-token WS endpoint replaced by ticket-flow in Wave 1 #12 "
    "(POST /ws/ticket + harness.v1 subprotocol). New coverage lives in "
    "tests/test_security_ws_ticket.py per ADR-001 short-lived ticket contract."
)
def test_websocket_endpoint_accepts_only_access_tokens_and_answers_ping():
    pass


def test_realtime_event_rbac_filters_match_session_contract():
    pb = ActorContext(
        employee_id="pb-1",
        role_code="PB",
        branch_id="branch-a",
    )
    wm = ActorContext(
        employee_id="wm-1",
        role_code="WM",
        branch_id="branch-a",
    )
    admin = ActorContext(employee_id="admin-1", role_code="ADMIN", branch_id=None)
    audit = ActorContext(employee_id="audit-1", role_code="AUDIT_VIEWER", branch_id=None)

    scoped_nba = {
        "event_type": "nba_created",
        "payload": {"assigned_pb_id": "pb-1", "branch_id": "branch-a"},
    }
    other_branch_nba = {
        "event_type": "nba_updated",
        "payload": {"assigned_pb_id": "pb-2", "branch_id": "branch-b"},
    }
    ai_done = {"event_type": "ai_job_done", "payload": {"requested_by_id": "pb-1"}}
    batch_done = {"event_type": "batch_status_change", "payload": {"job_name": "provider"}}

    assert event_visible_to_actor(pb, scoped_nba) is True
    assert event_visible_to_actor(wm, scoped_nba) is True
    assert event_visible_to_actor(admin, scoped_nba) is True
    assert event_visible_to_actor(audit, scoped_nba) is False
    assert event_visible_to_actor(pb, other_branch_nba) is False
    assert event_visible_to_actor(pb, ai_done) is True
    assert event_visible_to_actor(wm, ai_done) is False
    assert event_visible_to_actor(audit, ai_done) is True
    assert event_visible_to_actor(admin, batch_done) is True
    assert event_visible_to_actor(pb, batch_done) is False
    assert realtime_channel_for_event("batch_status_change") == (
        "harness:events:batch_status_change"
    )


def test_repository_sql_constants_follow_raw_sql_contract():
    for module_name in REPOSITORY_MODULES:
        module = importlib.import_module(module_name)
        sql_constants = {
            name: value
            for name, value in vars(module).items()
            if name.endswith("_SQL") and isinstance(value, str)
        }
        assert sql_constants, f"{module_name} has no SQL constants"
        for name, sql_text in sql_constants.items():
            result = validate_sql_text(sql_text, context=f"{module_name}.{name}")
            assert result.ok, result.errors


def test_recommendation_gate_blocks_when_any_required_gate_fails():
    result = evaluate_recommendation_gates(
        RecommendationGateInput(
            customer_risk_grade="3",
            product_risk_level="4",
            explanation_checked=True,
            simulated_customer_consented=True,
            employee_final_approved=True,
        )
    )

    assert result.status_code == "BLOCKED"
    assert result.detail["failed"] == ["suitability_passed"]


def test_recommendation_gate_approves_only_after_all_four_gates_pass():
    result = evaluate_recommendation_gates(
        RecommendationGateInput(
            customer_risk_grade="4",
            product_risk_level="3",
            explanation_checked=True,
            simulated_customer_consented=True,
            employee_final_approved=True,
        )
    )

    assert result.status_code == "APPROVED"
    assert result.passed is True


def test_order_gate_revalidates_current_recommendation_and_product():
    blocked = evaluate_order_gates(
        recommendation_status_code="CANCELLED",
        requested_product_id="product-a",
        recommendation_product_id="product-a",
        quantity=Decimal("1"),
        amount_krw=None,
    )
    pending = evaluate_order_gates(
        recommendation_status_code="APPROVED",
        requested_product_id="product-a",
        recommendation_product_id="product-a",
        quantity=None,
        amount_krw=Decimal("10000"),
    )

    assert blocked.status_code == "BLOCKED"
    assert "recommendation_approved" in blocked.detail["failed"]
    # P1-b: a passing order gate now yields PENDING_APPROVAL (awaiting second-person
    # 4-eye), not a direct APPROVED self-approval.
    assert pending.status_code == "PENDING_APPROVAL"
    assert pending.passed is True


def test_ai_helpers_hash_redacted_payloads_and_fail_closed():
    first = prompt_hash_from_payload({"question": "safe", "api_key": "secret-one"})
    second = prompt_hash_from_payload({"question": "safe", "api_key": "secret-two"})
    payload = ai_unavailable_payload("rag_qa", "Bearer secret-token failed")

    assert first == second
    assert len(first) == 64
    assert payload["status"] == "BLOCKED_WITH_REDACTED_REASON"
    assert "secret-token" not in payload["reason"]


def test_email_content_safety_rejects_identifiers_and_secrets():
    validate_display_safe_email_content("후속 안내", "상담 내용 요약만 포함합니다.")

    for body in (
        "주민번호 900101-1234567 포함",
        "계좌 123-456-789012 포함",
        "Bearer secret-token 포함",
    ):
        try:
            validate_display_safe_email_content("위험", body)
        except EmailContentRejectedError:
            pass
        else:  # pragma: no cover - explicit failure branch
            raise AssertionError(f"unsafe body was accepted: {body}")


def test_data_readiness_payload_reports_blocked_and_degraded_states():
    blocked = build_readiness_payload(
        {
            "active_customers": 0,
            "portfolios": 0,
            "active_house_views": 0,
            "embedded_chunks": 0,
            "pending_raw_documents": 2,
            "failed_recent_batches": 1,
            "skipped_recent_batches": 1,
        }
    )
    ready = build_readiness_payload(
        {
            "active_customers": 20,
            "portfolios": 20,
            "active_house_views": 1,
            "embedded_chunks": 4,
            "price_bar_count": 1,
        }
    )

    assert blocked["status_code"] == "BLOCKED"
    assert blocked["domestic_market"]["status_code"] == "BLOCKED"
    assert blocked["domestic_market"]["freshness_status_code"] == "MISSING"
    assert blocked["t55_provider_readiness"]["status_code"] == "BLOCKED"
    assert blocked["synthetic_customer_notice"]["status_code"] == "SYNTHETIC_ONLY"
    assert blocked["rag"]["status_code"] == "BLOCKED"
    assert blocked["batch_status_summary"]["failed_recent"] == 1
    assert ready["status_code"] == "BLOCKED"
    assert ready["rag"]["embedded_chunk_count"] == 4


def test_data_readiness_payload_exposes_krx_policy_gate():
    blocked = build_readiness_payload({
        "active_customers": 1,
        "portfolios": 1,
        "active_house_views": 1,
        "embedded_chunks": 1,
        "security_master_rows": 1,
        "accepted_price_bar_rows": 1,
        "price_bar_rows": 1,
        "quality_check_count": 1,
        "dart_document_chunks": 1,
        "embedded_dart_document_chunks": 1,
        "latest_price_bar_source_as_of": date.today().isoformat(),
        "latest_price_bar_provider_code": "PYKRX",
    })
    blocked_krx = next(
        check
        for check in blocked["domestic_market"]["checks"]
        if check["check_code"] == "provider.krx_policy"
    )
    assert blocked_krx["status_code"] == "BLOCKED"
    assert blocked_krx["source_policy_code"] == "KRX_BLOCKED"

    approved = build_readiness_payload({
        "active_customers": 1,
        "portfolios": 1,
        "active_house_views": 1,
        "embedded_chunks": 1,
        "security_master_rows": 1,
        "accepted_price_bar_rows": 1,
        "price_bar_rows": 1,
        "quality_check_count": 1,
        "dart_document_chunks": 1,
        "embedded_dart_document_chunks": 1,
        "latest_price_bar_source_as_of": date.today().isoformat(),
        "latest_price_bar_provider_code": "PYKRX",
        "pykrx_auxiliary_policy_rows": 1,
    })
    approved_krx = next(
        check
        for check in approved["domestic_market"]["checks"]
        if check["check_code"] == "provider.krx_policy"
    )
    assert approved_krx["status_code"] == "READY"
    assert approved_krx["source_code"] == "PYKRX"
    assert approved_krx["source_policy_code"] == "PYKRX_AUXILIARY_APPROVED"

    official = build_readiness_payload({
        "active_customers": 1,
        "portfolios": 1,
        "active_house_views": 1,
        "embedded_chunks": 1,
        "security_master_rows": 1,
        "accepted_price_bar_rows": 1,
        "price_bar_rows": 1,
        "quality_check_count": 1,
        "dart_document_chunks": 1,
        "embedded_dart_document_chunks": 1,
        "latest_price_bar_source_as_of": date.today().isoformat(),
        "latest_price_bar_provider_code": "KRX",
        "official_krx_price_bar_rows": 3,
        "official_krx_policy_rows": 2,
        "official_krx_provider_done": 2,
    })
    official_krx = next(
        check
        for check in official["domestic_market"]["checks"]
        if check["check_code"] == "provider.krx_policy"
    )
    assert official_krx["status_code"] == "READY"
    assert official_krx["source_code"] == "KRX"
    assert official_krx["source_policy_code"] == "OFFICIAL_KRX_APPROVED"


def test_domestic_market_embedding_check_requires_dart_embeddings():
    payload = build_readiness_payload({
        "active_customers": 1,
        "portfolios": 1,
        "active_house_views": 1,
        "embedded_chunks": 5,
        "dart_document_chunks": 1,
        "embedded_dart_document_chunks": 0,
    })
    embedding_check = next(
        check
        for check in payload["domestic_market"]["checks"]
        if check["check_code"] == "market.embeddings"
    )

    assert embedding_check["status_code"] == "BLOCKED"
    assert embedding_check["observed_count"] == 0


def test_readiness_repositories_use_live_market_evidence_tables():
    readiness_repo = (PROJECT_ROOT / "apps/api/harness/repositories/readiness.py").read_text()
    dashboard_repo = (PROJECT_ROOT / "apps/api/harness/repositories/dashboard.py").read_text()

    for source in (readiness_repo, dashboard_repo):
        assert "0::integer AS security_master_rows" not in source
        assert "0::integer AS price_bar_rows" not in source
        assert "0::integer AS accepted_price_bar_rows" not in source
        assert "FROM market_price_bars" in source
        assert "FROM batch_provider_evidence" in source
        assert "pykrx_auxiliary_policy_rows" in source
        assert "official_krx_price_bar_rows" in source
        assert "official_krx_policy_rows" in source


def test_t55_readiness_requires_explicit_pykrx_policy_evidence():
    ready_metrics = {
        "required_provider_migrations_applied": 7,
        "batch_provider_evidence_table_present": 1,
        "ecos_parseable_rows": 1,
        "ecos_provider_done": 1,
        "dart_raw_documents": 1,
        "dart_document_sources": 1,
        "dart_document_chunks": 1,
        "dart_embedded_chunks": 1,
        "dart_provider_done": 1,
        "pykrx_price_bar_rows": 1,
        "krx_provider_done": 1,
        "pykrx_auxiliary_policy_rows": 1,
        "official_krx_policy_rows": 0,
    }
    env_without_policy = {
        "HARNESS_BATCH_KRX_ENABLED": "true",
        "HARNESS_BATCH_KRX_SOURCE": "PYKRX",
    }

    missing_policy = build_t55_provider_readiness_payload(ready_metrics, env_without_policy)
    missing_policy_check = next(
        check
        for check in missing_policy["checks"]
        if check["check_code"] == "provider.krx_policy"
    )
    assert missing_policy["status_code"] == "BLOCKED"
    assert missing_policy_check["status_code"] == "BLOCKED"
    assert missing_policy_check["requested_policy_code"] == "UNSET"
    assert "HARNESS_BATCH_KRX_POLICY=PYKRX_AUXILIARY_APPROVED" in missing_policy_check["message"]

    missing_policy_evidence = build_t55_provider_readiness_payload(
        {**ready_metrics, "pykrx_auxiliary_policy_rows": 0},
        {
            **env_without_policy,
            "HARNESS_BATCH_KRX_POLICY": "PYKRX_AUXILIARY_APPROVED",
        },
    )
    missing_evidence_check = next(
        check
        for check in missing_policy_evidence["checks"]
        if check["check_code"] == "provider.krx_policy"
    )
    assert missing_policy_evidence["status_code"] == "BLOCKED"
    assert missing_evidence_check["status_code"] == "BLOCKED"
    assert missing_evidence_check["policy_evidence_count"] == 0

    approved = build_t55_provider_readiness_payload(
        ready_metrics,
        {
            **env_without_policy,
            "HARNESS_BATCH_KRX_POLICY": "PYKRX_AUXILIARY_APPROVED",
        },
    )
    approved_check = next(
        check for check in approved["checks"] if check["check_code"] == "provider.krx_policy"
    )
    assert approved["status_code"] == "READY"
    assert approved_check["status_code"] == "READY"
    assert approved_check["requested_policy_code"] == "PYKRX_AUXILIARY_APPROVED"
    assert approved_check["policy_evidence_count"] == 1

    official_metrics = {
        **ready_metrics,
        "pykrx_price_bar_rows": 0,
        "pykrx_auxiliary_policy_rows": 0,
        "official_krx_price_bar_rows": 2,
        "official_krx_provider_done": 1,
        "official_krx_policy_rows": 1,
    }
    official = build_t55_provider_readiness_payload(
        official_metrics,
        {
            "HARNESS_BATCH_KRX_ENABLED": "true",
            "HARNESS_BATCH_KRX_SOURCE": "KRX",
            "HARNESS_BATCH_KRX_POLICY": "OFFICIAL_KRX_APPROVED",
        },
    )
    official_check = next(
        check for check in official["checks"] if check["check_code"] == "provider.krx_policy"
    )
    assert official["status_code"] == "READY"
    assert official_check["policy_code"] == "OFFICIAL_KRX_APPROVED"
    assert official_check["observed_count"] == 2
    assert official_check["policy_evidence_count"] == 1


def test_customer_valuation_payloads_fail_closed_without_price_bar_evidence():
    notice = synthetic_customer_notice()
    holding_source = blocked_market_valuation_source("2026-05-16")
    valuation = build_portfolio_valuation_payload(
        [{"id": "portfolio-1"}],
        [{"id": "holding-1", "market_value_krw": Decimal("1000"), "as_of_date": "2026-05-16"}],
    )

    assert notice["status_code"] == "SYNTHETIC_ONLY"
    assert holding_source["status_code"] == "BLOCKED"
    assert holding_source["source_as_of"] is None
    assert holding_source["synthetic_as_of"] == "2026-05-16"
    assert valuation["status_code"] == "BLOCKED"
    assert valuation["quality_status_code"] == "UNVERIFIED"
    assert valuation["source_as_of"] is None


def test_provider_mode_local_is_advisory_not_readiness_failure():
    payload = build_provider_mode_payload({"APP_ENV": "development"})

    assert payload["status_code"] == "READY"
    assert payload["strict_external"] is False
    # Message was translated to Korean banker-facing copy; assert the
    # canonical Korean phrase that mirrors the original English intent.
    assert "현재 화면 준비 상태는 실제 데이터 게이트로 판정합니다" in payload["message"]


def test_data_readiness_ready_when_current_gates_ready_despite_provider_history(monkeypatch):
    monkeypatch.setenv("HARNESS_BATCH_KRX_ENABLED", "true")
    monkeypatch.setenv("HARNESS_BATCH_KRX_SOURCE", "PYKRX")
    monkeypatch.setenv("HARNESS_BATCH_KRX_POLICY", "PYKRX_AUXILIARY_APPROVED")
    payload = build_readiness_payload({
        **_fully_ready_market_metrics(),
        "failed_recent_batches": 24,
        "skipped_recent_batches": 39,
        "provider_detail_problem_recent": 10,
    })
    provider_recent = next(
        check for check in payload["checks"] if check["check_code"] == "provider.recent_batches"
    )

    assert payload["status_code"] == "READY"
    assert payload["domestic_market"]["status_code"] == "READY"
    assert payload["t55_provider_readiness"]["status_code"] == "READY"
    assert payload["provider_mode"]["status_code"] == "READY"
    assert provider_recent["status_code"] == "READY"
    assert provider_recent["observed_count"] == 73
    # Translated Korean equivalent of "retained for audit".
    assert "감사용으로 보존되어 있으나" in provider_recent["message"]
    assert payload["batch_status_summary"]["failed_recent"] == 24
    assert payload["batch_status_summary"]["skipped_recent"] == 39


def test_provider_history_still_degrades_when_current_data_gates_not_ready(monkeypatch):
    monkeypatch.setenv("HARNESS_BATCH_KRX_ENABLED", "true")
    monkeypatch.setenv("HARNESS_BATCH_KRX_SOURCE", "PYKRX")
    monkeypatch.setenv("HARNESS_BATCH_KRX_POLICY", "PYKRX_AUXILIARY_APPROVED")
    payload = build_readiness_payload({
        **_fully_ready_market_metrics(),
        "failed_recent_batches": 1,
        "accepted_price_bar_rows": 0,
        "market_quality_issues_recent": 1,
    })
    provider_recent = next(
        check for check in payload["checks"] if check["check_code"] == "provider.recent_batches"
    )

    assert payload["status_code"] == "DEGRADED"
    assert provider_recent["status_code"] == "DEGRADED"


def test_batch_repository_exposes_top200_universe_raw_sql_contracts():
    # batch.py was split into a package (W3-T2); combine all submodule sources for contract checks
    batch_pkg = PROJECT_ROOT / "apps/api/harness/repositories/batch"
    if batch_pkg.is_dir():
        batch_repo = "\n".join(
            (batch_pkg / f).read_text()
            for f in ("batch_jobs.py", "batch_artifacts.py", "batch_readiness.py")
        )
    else:
        batch_repo = (PROJECT_ROOT / "apps/api/harness/repositories/batch.py").read_text()
    readiness_repo = (PROJECT_ROOT / "apps/api/harness/repositories/readiness.py").read_text()

    for sql_id in (
        "upsert_market_universe_snapshot",
        "upsert_market_universe_candidate",
        "upsert_market_universe_member",
        "upsert_market_trading_calendar",
        "upsert_market_universe_coverage_daily",
        "get_market_universe_coverage_readiness",
    ):
        assert f"/* sql_id: {sql_id} */" in batch_repo

    for function_name in (
        "upsert_market_universe_snapshot",
        "upsert_market_universe_candidate",
        "upsert_market_universe_member",
        "upsert_market_trading_calendar_day",
        "upsert_market_universe_coverage_daily",
        "get_market_universe_coverage_readiness",
    ):
        assert f"async def {function_name}" in batch_repo

    for enriched_field in (
        "trading_value_krw",
        "market_cap_krw",
        "listed_shares",
        "change_price",
        "change_rate_pct",
    ):
        assert enriched_field in batch_repo

    assert "FROM market_universe_snapshots" in readiness_repo
    assert "FROM market_universe_coverage_daily" in readiness_repo
    assert "top200_missing_member_days" in readiness_repo
