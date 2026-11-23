"""Exact FastAPI route/OpenAPI document synchronization gates."""

from __future__ import annotations

from pathlib import Path

from apps.api.harness.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_CONTRACT_PATH = PROJECT_ROOT / "docs" / "api" / "API-01_contracts.yaml"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
APP_CONTRACT_EXCLUSIONS = {
    "/docs",
    "/docs/oauth2-redirect",
    "/openapi.json",
    "/redoc",
}
REQUIRED_SCHEMAS = {
    "DashboardSummary",
    "ListEnvelope",
    "CustomerListItem",
    "Customer360Response",
    "ProductListEnvelope",
    "EmailDraft",
    "EmailSendResponse",
    "HouseView",
    "HouseViewListEnvelope",
    "NbaActionListEnvelope",
    "RagQueryResponse",
    "BatchStatusEnvelope",
    "DataReadiness",
    "Top200Coverage",
    "AuditLogEnvelope",
    "RecommendationSimulation",
    "OrderSimulation",
}
REQUIRED_RESPONSE_REFS = {
    "/dashboard": "DashboardSummary",
    "/customers": "ListEnvelope",
    "/customers/{customer_id}": "Customer360Response",
    "/products": "ProductListEnvelope",
    "/email-drafts": "EmailDraft",
    "/email-drafts/{draft_id}/send": "EmailSendResponse",
    "/house-views": "HouseViewListEnvelope",
    "/house-views/{house_view_id}": "HouseView",
    "/nba-actions": "NbaActionListEnvelope",
    "/rag/query": "RagQueryResponse",
    "/batch/status": "BatchStatusEnvelope",
    "/data/readiness": "DataReadiness",
    "/audit-logs": "AuditLogEnvelope",
    "/recommendation-simulations": "RecommendationSimulation",
    "/order-simulations": "OrderSimulation",
}


def _app_route_methods() -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods or path in APP_CONTRACT_EXCLUSIONS:
            continue
        routes.setdefault(path, set()).update(
            method.lower() for method in methods if method.lower() in HTTP_METHODS
        )
    return {path: methods for path, methods in routes.items() if methods}


def _documented_route_methods() -> dict[str, set[str]]:
    routes: dict[str, set[str]] = {}
    current_path: str | None = None
    in_paths = False
    for line in API_CONTRACT_PATH.read_text(encoding="utf-8").splitlines():
        if line == "paths:":
            in_paths = True
            continue
        if line.startswith("components:"):
            break
        if not in_paths:
            continue
        stripped = line.strip()
        if line.startswith("  /") and stripped.endswith(":"):
            current_path = stripped[:-1]
            routes.setdefault(current_path, set())
            continue
        if current_path and line.startswith("    ") and not line.startswith("      "):
            key = stripped[:-1] if stripped.endswith(":") else stripped
            if key in HTTP_METHODS:
                routes[current_path].add(key)
    return {path: methods for path, methods in routes.items() if methods}


def test_fastapi_routes_match_documented_paths_and_methods_exactly():
    app_routes = _app_route_methods()
    documented_routes = _documented_route_methods()

    implemented_only = sorted(set(app_routes) - set(documented_routes))
    documented_only = sorted(set(documented_routes) - set(app_routes))
    method_mismatch = {
        path: {"app": sorted(app_routes[path]), "docs": sorted(documented_routes[path])}
        for path in sorted(set(app_routes) & set(documented_routes))
        if app_routes[path] != documented_routes[path]
    }

    assert implemented_only == []
    assert documented_only == []
    assert method_mismatch == {}


def test_openapi_contract_defines_drift_prone_response_schemas():
    api_text = API_CONTRACT_PATH.read_text(encoding="utf-8")

    for schema_name in sorted(REQUIRED_SCHEMAS):
        assert f"    {schema_name}:" in api_text

    for route_path, schema_name in REQUIRED_RESPONSE_REFS.items():
        path_index = api_text.index(f"  {route_path}:")
        next_path_index = api_text.find("\n  /", path_index + 1)
        block = (
            api_text[path_index:] if next_path_index == -1 else api_text[path_index:next_path_index]
        )
        assert f"#/components/schemas/{schema_name}" in block



def test_data_readiness_contract_documents_top200_coverage_fields():
    api_text = API_CONTRACT_PATH.read_text(encoding="utf-8")
    domestic_index = api_text.index("    DomesticMarketStatus:")
    next_schema_index = api_text.find("\n    MarketReadinessCheck:", domestic_index)
    domestic_block = api_text[domestic_index:next_schema_index]
    top200_index = api_text.index("    Top200Coverage:")
    next_top200_index = api_text.find("\n    MarketReadinessCheck:", top200_index)
    top200_block = api_text[top200_index:next_top200_index]

    assert "top200_coverage:" in domestic_block
    assert "universe_code" in top200_block
    assert "DOMESTIC_TOP200_MARKET_CAP" in top200_block
    assert "coverage_ratio" in top200_block
    assert "missing_member_days" in top200_block
    assert "source_policy_code" in top200_block
