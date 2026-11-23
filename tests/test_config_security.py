"""Configuration, redaction, auth, audit, and RBAC foundation tests."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from apps.api.harness.api.dependencies import actor_from_authorization
from apps.api.harness.core.audit import CANONICAL_AUDIT_ACTION_CODES, require_audit_action
from apps.api.harness.core.config import (
    CANONICAL_PYTHON_PATH,
    CANONICAL_PYTHON_VERSION,
    load_config,
    load_env_file,
)
from apps.api.harness.core.logging import redact_mapping, redact_secret_text
from apps.api.harness.core.rbac import ActorContext, can_access_customer, can_read_audit_logs
from apps.api.harness.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_CONTRACT_PATH = (
    PROJECT_ROOT / ".env" if (PROJECT_ROOT / ".env").exists() else PROJECT_ROOT / ".env.example"
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


def test_project_env_satisfies_runtime_config_contract():
    clear_keys = {
        key: None
        for key in list(os.environ)
        if key.startswith(("PYTHON_", "BGE_", "VITE_"))
        or key
        in {
            "APP_ENV",
            "LOG_LEVEL",
            "DATABASE_URL",
            "POSTGRES_HOST",
            "POSTGRES_PORT",
            "POSTGRES_DB",
            "POSTGRES_USER",
            "POSTGRES_PASSWORD",
            "REDIS_URL",
            "JWT_SECRET",
            "JWT_ACCESS_EXPIRE_SECONDS",
            "JWT_REFRESH_EXPIRE_SECONDS",
            "AZURE_OPENAI_DEPLOYMENT_NAME",
            "AZURE_GPT5_DEPLOYMENT",
            "AZURE_GPT5_MINI_DEPLOYMENT",
            "CORS_ENABLED",
            "CORS_ALLOWED_ORIGINS",
        }
    }
    with temporary_env(clear_keys):
        config = load_config(ENV_CONTRACT_PATH)

    assert config.runtime.python_path == CANONICAL_PYTHON_PATH
    assert config.runtime.python_version == CANONICAL_PYTHON_VERSION
    assert config.ai.bge_dimensions == 1024
    assert config.ai.bge_auth_scheme == "Bearer"
    assert config.ai.bge_embedding_timeout_seconds > 0
    assert config.database.database_url.startswith("postgresql://")
    assert "postgresql+asyncpg://" not in config.database.database_url
    assert config.cors.enabled is False
    assert config.cors.allowed_origins == ()
    assert config.security.refresh_cookie_name == "harness_refresh_token"
    assert config.security.refresh_cookie_secure is False
    assert config.security.refresh_cookie_samesite == "lax"
    assert config.security.refresh_cookie_path == "/"
    assert config.security.refresh_cookie_max_age_seconds == config.security.refresh_expire_seconds
    assert set(config.frontend_public) >= {"VITE_API_BASE_URL", "VITE_WS_BASE_URL"}


def test_cors_credentials_require_explicit_non_wildcard_origins():
    env_values = load_env_file(ENV_CONTRACT_PATH) | {
        "CORS_ENABLED": "true",
        "CORS_ALLOWED_ORIGINS": "https://app.example.invalid,https://admin.example.invalid",
    }
    with temporary_env(env_values):
        config = load_config()

        assert config.cors.enabled is True
        assert config.cors.allowed_origins == (
            "https://app.example.invalid",
            "https://admin.example.invalid",
        )

        from apps.api.harness.main import create_app

        app = create_app()
        cors_middleware = [
            middleware
            for middleware in app.user_middleware
            if middleware.cls.__name__ == "CORSMiddleware"
        ]
        assert len(cors_middleware) == 1
        assert cors_middleware[0].kwargs["allow_credentials"] is True
        assert cors_middleware[0].kwargs["allow_origins"] == [
            "https://app.example.invalid",
            "https://admin.example.invalid",
        ]

    with (
        temporary_env(env_values | {"CORS_ALLOWED_ORIGINS": "*"}),
        pytest.raises(ValueError, match="wildcard"),
    ):
        load_config()


def test_refresh_cookie_security_envs_are_configurable():
    env_values = load_env_file(ENV_CONTRACT_PATH) | {
        "AUTH_REFRESH_COOKIE_NAME": "wmh_refresh",
        "AUTH_REFRESH_COOKIE_SECURE": "true",
        "AUTH_REFRESH_COOKIE_SAMESITE": "strict",
        "AUTH_REFRESH_COOKIE_PATH": "/api/auth",
        "AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS": "3600",
    }
    with temporary_env(env_values):
        config = load_config()

    assert config.security.refresh_cookie_name == "wmh_refresh"
    assert config.security.refresh_cookie_secure is True
    assert config.security.refresh_cookie_samesite == "strict"
    assert config.security.refresh_cookie_path == "/api/auth"
    assert config.security.refresh_cookie_max_age_seconds == 3600


def test_refresh_cookie_samesite_none_requires_secure():
    env_values = load_env_file(ENV_CONTRACT_PATH) | {
        "AUTH_REFRESH_COOKIE_SECURE": "false",
        "AUTH_REFRESH_COOKIE_SAMESITE": "none",
    }
    with (
        temporary_env(env_values),
        pytest.raises(ValueError, match="AUTH_REFRESH_COOKIE_SAMESITE=none requires"),
    ):
        load_config()


def test_vite_env_contains_no_secrets():
    values = load_env_file(ENV_CONTRACT_PATH)
    vite_values = {key: value for key, value in values.items() if key.startswith("VITE_")}
    assert vite_values
    for key, value in vite_values.items():
        assert not re.search(r"(secret|password|token|api[_-]?key|service[_-]?key)", key, re.I)
        assert not re.search(r"(secret|password|token|api[_-]?key|service[_-]?key)", value, re.I)


def test_redaction_removes_secrets_without_dropping_safe_ids():
    payload = {
        "customer_id": "33333333-3333-3333-3333-333333333301",
        "Authorization": "Bearer abc.def.secret",
        "nested": {"api_key": "should-not-appear", "resource_id": "abc"},
    }

    redacted = redact_mapping(payload)

    assert redacted["customer_id"] == payload["customer_id"]
    assert redacted["Authorization"] == "<redacted>"
    assert redacted["nested"]["api_key"] == "<redacted>"
    assert redact_mapping({"AUTH_KEY": "krx-secret"})["AUTH_KEY"] == "<redacted>"
    assert redact_secret_text("Bearer abc.def.ghi") == "Bearer <redacted>"
    assert (
        redact_secret_text("postgresql://harness_app:secret@localhost:5432/harness")
        == "postgresql://<redacted>@localhost:5432/harness"
    )
    assert redact_secret_text("password=secret, token=abc") == (
        "password=<redacted>, token=<redacted>"
    )
    assert "krx-secret" not in redact_secret_text("?AUTH_KEY=krx-secret&basDd=20260515")


def test_password_hash_and_jwt_roundtrip():
    password_hash = hash_password("synthetic-test-password")
    assert verify_password("synthetic-test-password", password_hash)
    assert not verify_password("wrong-password", password_hash)

    token = create_access_token(
        subject="22222222-2222-2222-2222-222222222201",
        secret="unit-test-secret",
        expires_in_seconds=30,
        extra_claims={"role_code": "PB"},
    )
    payload = decode_token(token, secret="unit-test-secret")
    assert payload["sub"] == "22222222-2222-2222-2222-222222222201"
    assert payload["role_code"] == "PB"

    expired = create_access_token(subject="x", secret="unit-test-secret", expires_in_seconds=-120)
    with pytest.raises(ValueError, match="expired"):
        decode_token(expired, secret="unit-test-secret")


def test_actor_authorization_accepts_only_access_tokens():
    config = SimpleNamespace(security=SimpleNamespace(jwt_secret="unit-test-secret"))
    subject = "22222222-2222-2222-2222-222222222201"
    access_token = create_access_token(
        subject=subject,
        secret="unit-test-secret",
        expires_in_seconds=30,
        extra_claims={"role_code": "PB", "branch_id": "branch-a", "token_type": "access"},
    )

    actor = actor_from_authorization(config, f"Bearer {access_token}")

    assert actor.employee_id == subject
    assert actor.role_code == "PB"
    assert actor.branch_id == "branch-a"

    rejected_claims = (
        {"role_code": "PB", "branch_id": "branch-a", "token_type": "refresh"},
        {"role_code": "PB", "branch_id": "branch-a"},
    )
    for claims in rejected_claims:
        token = create_access_token(
            subject=subject,
            secret="unit-test-secret",
            expires_in_seconds=30,
            extra_claims=claims,
        )
        with pytest.raises(HTTPException) as exc_info:
            actor_from_authorization(config, f"Bearer {token}")
        assert exc_info.value.status_code == 401


def test_rbac_row_level_rules_and_audit_reader_roles():
    customer = {
        "assigned_pb_id": "pb-1",
        "branch_id": "branch-a",
    }

    assert can_access_customer(ActorContext("pb-1", "PB", "branch-a"), customer)
    assert not can_access_customer(ActorContext("pb-2", "PB", "branch-a"), customer)
    assert can_access_customer(ActorContext("wm-1", "WM", "branch-a"), customer)
    assert not can_access_customer(ActorContext("wm-2", "WM", "branch-b"), customer)
    assert can_access_customer(ActorContext("admin-1", "ADMIN"), customer)
    assert not can_access_customer(ActorContext("audit-1", "AUDIT_VIEWER"), customer)

    assert can_read_audit_logs(ActorContext("admin-1", "ADMIN"))
    assert can_read_audit_logs(ActorContext("audit-1", "AUDIT_VIEWER"))
    assert not can_read_audit_logs(ActorContext("pb-1", "PB", "branch-a"))


def test_canonical_audit_codes_match_docs():
    """OBS-02 must enumerate exactly the same canonical action_codes as the
    Python tuple — set-equal + no duplicates, but section ordering in the
    doc may differ from the chronological-add-order of the tuple. Strict
    tuple-equality used to be the assertion; it broke every time a new
    code was registered in a section that lives before its
    chronological slot in CANONICAL_AUDIT_ACTION_CODES. The contract we
    actually want to enforce is membership, not the historical order.
    """
    docs_path = PROJECT_ROOT / "docs" / "observability" / "OBS-02_audit_action_codes.md"
    docs_text = docs_path.read_text()
    # Reference cross-tables (e.g. the ADR-021 SoD human_reviewer_required set)
    # restate codes wrapped in backticks for emphasis; those rows are NOT canonical
    # registration rows (the codes already appear bare in their registry table), so
    # skip backtick-wrapped first columns and count only the bare-code registry tables.
    documented = tuple(
        line.split("|")[1].strip()
        for line in docs_text.splitlines()
        if line.startswith("|")
        and not line.startswith("|---")
        and "action_code" not in line
        and not line.split("|")[1].strip().startswith("`")
    )

    canonical_set = set(CANONICAL_AUDIT_ACTION_CODES)
    doc_set = set(documented)

    extra_in_doc = doc_set - canonical_set
    missing_from_doc = canonical_set - doc_set
    duplicates_in_doc = [c for c in documented if list(documented).count(c) > 1]

    assert not extra_in_doc, f"doc contains codes not in CANONICAL: {sorted(extra_in_doc)}"
    assert not missing_from_doc, f"CANONICAL has codes not in doc: {sorted(missing_from_doc)}"
    assert not duplicates_in_doc, f"doc duplicates: {sorted(set(duplicates_in_doc))}"
    assert len(documented) == len(CANONICAL_AUDIT_ACTION_CODES), (
        f"row counts diverge: doc={len(documented)} canonical={len(CANONICAL_AUDIT_ACTION_CODES)}"
    )

    for action_code in CANONICAL_AUDIT_ACTION_CODES:
        assert require_audit_action(action_code) == action_code
    with pytest.raises(ValueError, match="Unknown audit"):
        require_audit_action("unknown_code")


def test_token_decode_rejects_tampering():
    token = create_access_token(subject="subject", secret="unit-test-secret", expires_in_seconds=30)
    head, payload, signature = token.split(".")
    # base64url packs 2 padding bits into the LAST char of an HMAC-SHA256
    # signature (43 chars encoding 32 bytes ⇒ final char carries only 4
    # meaningful bits + 2 zero pad bits), so a naïve "replace last char
    # with x" tamper has a ≈1/16 chance of producing a same-group neighbor
    # ('w' → 'x', 'A' → 'B'…) that decodes to identical bytes — the
    # signature check then passes and the test silently flakes. The FIRST
    # char of the signature carries a full 6 bits with no padding, so
    # toggling it always yields a different decoded byte and a guaranteed
    # signature mismatch.
    tampered_first = "A" if signature[0] != "A" else "B"
    tampered = f"{head}.{payload}.{tampered_first}{signature[1:]}"
    with pytest.raises(ValueError, match="signature"):
        decode_token(tampered, secret="unit-test-secret")


def test_redis_configuration_is_required():
    env_values = load_env_file(ENV_CONTRACT_PATH) | {
        "REDIS_URL": None,
        "REDIS_HOST": None,
        "REDIS_SENTINEL_HOSTS": None,
        "REDIS_SENTINEL_SERVICE_NAME": None,
    }
    with (
        temporary_env(env_values),
        pytest.raises(ValueError, match="Redis configuration is required"),
    ):
        load_config()
