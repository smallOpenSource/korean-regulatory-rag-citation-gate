"""Task 3 external client and batch foundation tests.

These tests avoid test doubles by validating pure request/response parsing,
configuration gates, Redis lock semantics against real Redis in test_redis.py,
and static source constraints for no BROKER mutation/order calls.
"""

from __future__ import annotations

import ast
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

from apps.api.harness.batch.collectors import sanitize_provider_text
from apps.api.harness.batch.discovery import (
    DEFAULT_DART_DISCOVERY_STOCK_CODES,
    build_dart_discovery_windows,
    dart_discovery_seed_targets,
)
from apps.api.harness.batch.embedding import vector_literal
from apps.api.harness.external.bge import extract_dense_embeddings, validate_embeddings
from apps.api.harness.external.broker import (
    BROKER_TOKEN_CACHE_KEY,
    BROKER_TOKEN_TTL_SECONDS,
    BrokerConfig,
    BrokerReadOnlyClient,
)
from apps.api.harness.external.http import ExternalProviderError, build_url
from apps.api.harness.external.public_data import DataGoKrClient, content_hash

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE_ROOTS = (PROJECT_ROOT / "apps", PROJECT_ROOT / "db", PROJECT_ROOT / "tests")
FORBIDDEN_BROKER_MUTATION_FRAGMENTS = (
    "order" + "-" + "cash",
    "order" + "-" + "credit",
    "/".join(["trading", "order"]),
    "/".join(["order", "cancel"]),
)


@contextmanager
def temporary_env(updates: dict[str, str | None]):
    previous = {key: os.environ.get(key) for key in updates}
    try:
        for key, value in updates.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _source_files() -> list[Path]:
    ignored = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules"}
    paths: list[Path] = []
    for root in EXECUTABLE_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if (
                path.is_file()
                and not (set(path.relative_to(PROJECT_ROOT).parts) & ignored)
                and path.suffix in {".py", ".sql", ".ts", ".tsx"}
            ):
                paths.append(path)
    return paths


def test_bge_dense_embeddings_contract_accepts_only_configured_dimension():
    payload = {"dense_embeddings": [[0.1, 0.2, 0.3], [1, 2, 3]]}
    vectors = extract_dense_embeddings(payload)

    validate_embeddings(vectors, expected_count=2, dimensions=3)
    with pytest.raises(Exception, match="dimension"):
        validate_embeddings(vectors, expected_count=2, dimensions=1024)
    with pytest.raises(Exception, match="count"):
        validate_embeddings(vectors, expected_count=1, dimensions=3)


def test_vector_literal_is_pgvector_compatible():
    assert vector_literal([1, 2.5, -3]) == "[1.0,2.5,-3.0]"


def test_broker_config_enforces_core_keys_and_sandbox_balance_gate():
    config = BrokerConfig(
        base_url="https://example.invalid",
        app_key="app-key",
        app_secret="app-secret",
        account_no="12345678",
        account_product_code="01",
        is_virtual=True,
    )
    config.require_core()
    assert BROKER_TOKEN_CACHE_KEY == "broker:access_token"
    assert BROKER_TOKEN_TTL_SECONDS == 23 * 60 * 60

    missing = BrokerConfig("", "", "", None, None, False)
    with pytest.raises(Exception, match="Missing BROKER"):
        missing.require_core()


def test_broker_client_rejects_missing_or_mutation_endpoint_paths():
    base = {
        "base_url": "https://example.invalid",
        "app_key": "app-key",
        "app_secret": "app-secret",
        "account_no": None,
        "account_product_code": None,
        "is_virtual": False,
    }
    with pytest.raises(ExternalProviderError, match="BROKER_TOKEN_PATH"):
        BrokerReadOnlyClient(BrokerConfig(**base)).get_access_token()
    mutation_path = "/".join(["", "trading", "order"])
    with pytest.raises(ExternalProviderError, match="read-only endpoint"):
        BrokerReadOnlyClient(BrokerConfig(**base, token_path=mutation_path)).get_access_token()


def test_content_hash_and_url_builder_are_stable_without_leaking_query_secrets():
    assert content_hash("synthetic raw text") == content_hash("synthetic raw text")
    url = build_url("https://provider.invalid/base/", "/endpoint", {"a": "1", "b": None})
    assert url == "https://provider.invalid/base/endpoint?a=1"


def test_provider_text_sanitizer_removes_postgres_nul_bytes():
    assert sanitize_provider_text("<doc>live\x00dart</doc>") == "<doc>livedart</doc>"


def test_data_go_kr_client_uses_decoded_service_key_before_url_encoding():
    encoded_key = "abc%2Fdef%3D%3D"
    decoded_key = "abc/def=="

    with temporary_env(
        {
            "DATA_GO_KR_API_BASE_URL": "https://provider.invalid",
            "DATA_GO_KR_SERVICE_KEY_ENCODING": encoded_key,
            "DATA_GO_KR_SERVICE_KEY_DECODING": decoded_key,
        }
    ):
        assert DataGoKrClient.from_env().service_key == decoded_key

    with temporary_env(
        {
            "DATA_GO_KR_API_BASE_URL": "https://provider.invalid",
            "DATA_GO_KR_SERVICE_KEY_ENCODING": encoded_key,
            "DATA_GO_KR_SERVICE_KEY_DECODING": None,
        }
    ):
        assert DataGoKrClient.from_env().service_key == decoded_key


def test_dart_discovery_uses_wide_windows_and_non_secret_stock_seeds():
    with temporary_env({"HARNESS_BATCH_DART_DISCOVERY_STOCK_CODES": None}):
        windows = build_dart_discovery_windows(today=date(2026, 5, 16))
        targets = dart_discovery_seed_targets(page_count=100)

    assert [window.lookback_days for window in windows[:2]] == [365, 180]
    assert windows[-1].lookback_days == 1
    assert windows[0].begin_date == "20250516"
    assert targets[0].stock_code == DEFAULT_DART_DISCOVERY_STOCK_CODES[0]
    assert targets[0].corp_code is None


def test_no_broker_mutation_or_order_endpoint_strings_in_executable_code():
    violations: list[str] = []
    for path in _source_files():
        text = path.read_text(errors="ignore").lower()
        for fragment in FORBIDDEN_BROKER_MUTATION_FRAGMENTS:
            if fragment in text and path.name != "test_task3_external_batch.py":
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{fragment}")
    assert not violations


def test_no_mock_imports_in_python_code():
    forbidden_modules = {"mock", "unittest" + "." + "mock"}
    violations: list[str] = []
    for path in _source_files():
        if path.suffix != ".py" or path.name == "test_task3_external_batch.py":
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_modules:
                        violations.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")
            elif isinstance(node, ast.ImportFrom) and (node.module or "") in forbidden_modules:
                violations.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno}")
    assert not violations
