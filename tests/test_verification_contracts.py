"""Verification-lane contract checks for docs, static security, and public config."""

from __future__ import annotations

import ast
from pathlib import Path

from apps.api.harness.core.config import load_env_file
from apps.api.harness.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".omx",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "node_modules",
}
APP_CONTRACT_EXCLUSIONS = {
    "/docs",
    "/docs/oauth2-redirect",
    "/health",
    "/health/config",
    "/openapi.json",
    "/redoc",
}
PUBLIC_VITE_KEYS = {"VITE_API_BASE_URL", "VITE_WS_BASE_URL"}
SENSITIVE_NAME_PARTS = ("secret", "password", "token", "api_key", "apikey", "service_key")


def _project_files(suffixes: set[str]) -> list[Path]:
    paths: list[Path] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if set(path.relative_to(PROJECT_ROOT).parts) & IGNORED_PARTS:
            continue
        paths.append(path)
    return paths


def test_api_contract_yaml_text_documents_public_routes():
    api_text = (PROJECT_ROOT / "docs" / "api" / "API-01_contracts.yaml").read_text()
    documented_paths = {
        line.strip()[:-1]
        for line in api_text.splitlines()
        if line.startswith("  /") and line.rstrip().endswith(":")
    }
    app_paths = {route.path for route in app.routes} - APP_CONTRACT_EXCLUSIONS

    assert 'openapi: "3.1.0"' in api_text
    assert app_paths <= documented_paths


def test_ai_agent_spec_is_audited_and_env_driven():
    ai_text = (PROJECT_ROOT / "docs" / "ai" / "AI-02_agent_spec.yaml").read_text()
    required_agent_ids = {
        "house_view_generation",
        "consultation_briefing",
        "nba_script",
        "email_draft",
        "rag_qa",
        "compliance_check",
        "portfolio_analysis",
    }

    for agent_id in required_agent_ids:
        block_start = ai_text.index(f"  - id: {agent_id}")
        block_end = ai_text.find("\n\n", block_start)
        block = ai_text[block_start:] if block_end == -1 else ai_text[block_start:block_end]
        assert "audit: true" in block
        assert "model: ${" in block
        assert "output: [" in block


def test_no_legacy_harness_path_references_outside_omx_state():
    legacy_path = "/".join(["", "app", "poc", "harness"])
    violations = [
        str(path.relative_to(PROJECT_ROOT))
        for path in _project_files({".py", ".ts", ".tsx", ".md", ".yaml", ".yml", ".sql"})
        if legacy_path in path.read_text(errors="ignore")
    ]

    assert not violations


def test_no_public_vite_secret_configuration():
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        env_path = PROJECT_ROOT / ".env.example"
    env_values = load_env_file(env_path)
    vite_keys = {key for key in env_values if key.startswith("VITE_")}

    assert vite_keys == PUBLIC_VITE_KEYS
    for key in vite_keys:
        value = env_values[key].lower()
        name = key.lower()
        assert not any(part in name for part in SENSITIVE_NAME_PARTS)
        assert not any(part in value for part in SENSITIVE_NAME_PARTS)


def test_no_mock_or_local_simulator_imports_in_executable_python():
    forbidden_modules = {"mock", "unittest" + "." + "mock", "pytest" + "_" + "mock"}
    violations: list[str] = []
    for path in _project_files({".py"}):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_modules:
                        violations.append(
                            f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}:{alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom) and (node.module or "") in forbidden_modules:
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}:{node.module}")
    assert not violations


def test_hostile_qa_checks_reject_false_green_outputs():
    import subprocess

    result = subprocess.run(
        [str(PROJECT_ROOT / "scripts" / "qa_hostile_checks.sh")],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "hostile_check=misleading_success result=passed" in result.stdout
    assert "hostile_check=timeout result=passed" in result.stdout
    assert "hostile_check=corrupted_state_parse result=passed" in result.stdout
    assert "hostile_checks=passed failures=0" in result.stdout


def test_web_fetch_calls_include_session_credentials():
    web_paths = (
        PROJECT_ROOT / "apps" / "web" / "src" / "lib" / "api.ts",
        PROJECT_ROOT / "apps" / "web" / "e2e" / "role-matrix.spec.ts",
    )
    fetch_count = 0
    credential_count = 0
    for path in web_paths:
        text = path.read_text()
        fetch_count += text.count("fetch(")
        credential_count += text.count('credentials: "include"')

    assert fetch_count > 0
    assert credential_count >= fetch_count


def test_no_frontend_test_double_helpers_in_checked_in_tests():
    forbidden_patterns = ("vi.mock(", "vi.fn(", "vi.spyOn(", "jest.fn(", "msw")
    frontend_test_roots = (
        PROJECT_ROOT / "apps" / "web" / "src" / "tests",
        PROJECT_ROOT / "apps" / "web" / "e2e",
    )
    violations: list[str] = []
    for root in frontend_test_roots:
        for path in root.rglob("*"):
            if path.suffix not in {".ts", ".tsx"}:
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in forbidden_patterns:
                if pattern in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}:{pattern}")

    assert not violations


def test_provider_normalization_keeps_static_hard_rules():
    v009 = (PROJECT_ROOT / "db" / "migrations" / "V009__batch_tables.sql").read_text()
    v012 = (
        PROJECT_ROOT / "db" / "migrations" / "V012__market_data_foundation.sql"
    ).read_text()
    v016 = (
        PROJECT_ROOT / "db" / "migrations" / "V016__official_krx_provider_readiness.sql"
    ).read_text()
    providers_flat = PROJECT_ROOT / "apps" / "api" / "harness" / "batch" / "providers.py"
    providers_pkg = PROJECT_ROOT / "apps" / "api" / "harness" / "batch" / "providers"
    if providers_flat.exists():
        providers = providers_flat.read_text()
    else:
        providers = "\n".join(p.read_text() for p in sorted(providers_pkg.glob("*.py")))
    runner = (PROJECT_ROOT / "apps" / "api" / "harness" / "batch" / "runner.py").read_text()

    assert "status_code IN ('RUNNING', 'DONE', 'FAILED', 'SKIPPED')" in v009
    assert "CHECK (source_code IN ('BROKER', 'DATA_GO_KR', 'PYKRX'))" in v012
    v016 = (
        PROJECT_ROOT / "db" / "migrations" / "V016__official_krx_provider_readiness.sql"
    ).read_text()
    assert "CHECK (source_code IN ('KRX', 'BROKER', 'DATA_GO_KR', 'PYKRX'))" in v016
    assert '"source_code": "KRX"' in providers
    assert 'persisted_source_code="KRX|PYKRX"' in providers
    assert "HARNESS_BATCH_KRX_SOURCE" in runner
    assert "OFFICIAL_KRX_APPROVED" in runner
    assert "PROVIDER_SKIPPED_DISABLED" in runner
    assert "pykrx 비공식 보조 소스" in runner
    assert "KRX 공식 OpenAPI" in runner
