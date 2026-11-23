"""Environment-backed configuration validation."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .logging import is_sensitive_key, redact_mapping

# Interpreter pinned by the startup check below. Override per host with
# HARNESS_CANONICAL_PYTHON_PATH; PYTHON_PATH in .env must match it.
CANONICAL_PYTHON_PATH = os.environ.get(
    "HARNESS_CANONICAL_PYTHON_PATH", "/opt/conda/envs/wm_env/bin/python"
)
CANONICAL_PYTHON_VERSION = "3.11.5"
VECTOR_DIMENSIONS = 1024


@dataclass(frozen=True)
class DatabaseConfig:
    database_url: str


@dataclass(frozen=True)
class RedisConfig:
    redis_url: str | None
    sentinel_hosts: str | None
    sentinel_service_name: str | None
    host: str | None
    port: int | None
    password: str | None
    db: int
    socket_timeout: float
    socket_connect_timeout: float
    max_connections: int


@dataclass(frozen=True)
class RuntimeConfig:
    app_env: str
    log_level: str
    python_path: str
    python_version: str


@dataclass(frozen=True)
class AiConfig:
    azure_deployment_name: str
    bge_embedding_url: str
    bge_embedding_model: str
    bge_dimensions: int
    bge_auth_scheme: str
    bge_embedding_timeout_seconds: float
    bge_rerank_url: str
    bge_rerank_model: str


@dataclass(frozen=True)
class SecurityConfig:
    jwt_secret: str
    access_expire_seconds: int
    refresh_expire_seconds: int
    refresh_cookie_name: str
    refresh_cookie_secure: bool
    refresh_cookie_samesite: str
    refresh_cookie_path: str
    refresh_cookie_max_age_seconds: int


@dataclass(frozen=True)
class EmailConfig:
    send_enabled: bool
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    sender_email: str | None
    sender_name: str | None
    test_recipient_email: str | None
    timeout_seconds: float
    # Mailpit sandbox transport (ADR-002 / ADR-003 — only permitted PoC transport)
    transport: str          # must be "mailpit" in PoC; any other value fails closed
    mailpit_host: str
    mailpit_port: int
    mailpit_auth_user: str | None
    mailpit_auth_password: str | None
    # Synthetic-recipient guardrail toggle (follow-up cycle B2 / F1+F2).
    # When True the server-side allowlist (@example.invalid only) is enforced;
    # when False the guardrail is bypassed so production-intended recipients
    # (e.g. a real address in TEST_RECIPIENT_EMAIL) can be delivered through
    # the Mailpit sandbox. Defaults False to keep the PoC happy-path runnable.
    sandbox_guardrail_enabled: bool


@dataclass(frozen=True)
class CorsConfig:
    enabled: bool
    allowed_origins: tuple[str, ...]


@dataclass(frozen=True)
class AppConfig:
    runtime: RuntimeConfig
    database: DatabaseConfig
    redis: RedisConfig
    ai: AiConfig
    security: SecurityConfig
    email: EmailConfig
    cors: CorsConfig
    frontend_public: Mapping[str, str]

    def safe_dict(self) -> dict[str, object]:
        """Return a secret-redacted representation for diagnostics."""

        return redact_mapping(
            {
                "runtime": self.runtime.__dict__,
                "database": self.database.__dict__,
                "redis": self.redis.__dict__,
                "ai": self.ai.__dict__,
                "security": self.security.__dict__,
                "email": self.email.__dict__,
                "cors": self.cors.__dict__,
                "frontend_public": dict(self.frontend_public),
            }
        )


# Critical keys that must survive load_env_file override (defensive list — service-viability F8).
# When any of these appear in .env, the in-process os.environ value MUST equal the .env value
# after load_env_file returns. Failure indicates stale-OS-env-shadowing regression.
CRITICAL_OVERRIDE_KEYS: tuple[str, ...] = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_BASE_URL",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_CONTENT_SAFETY_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "TEST_RECIPIENT_EMAIL",
    "DATABASE_URL",
)


def load_env_file(path: Path) -> dict[str, str]:
    """Parse the project ``.env`` and override ``os.environ`` with its values.

    Equivalent to python-dotenv ``load_dotenv(override=True)``: every key
    parsed from the file is written to ``os.environ`` unconditionally,
    replacing any value the parent shell may have exported.

    The previous ``setdefault`` behavior preserved stale OS-level values when a
    shell had been seeded with an outdated endpoint, which silently routed
    Azure traffic to a non-existent host (2026-05-24 service-viability F8
    finding: backend held ``<stale-azure-resource>`` from a parent shell while
    .env defined ``<active-azure-resource>``, causing AI generation to fail
    closed with ``AI_ERROR``). The project ``.env`` is the single source of
    truth for runtime configuration; OS-level overrides must be applied by
    editing the file rather than by relying on inherited shell state.

    Memory rule: ``[[stale-os-env-shadowing]]``.
    """

    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        clean_key = key.strip()
        clean_value = value.strip().strip('"').strip("'")
        values[clean_key] = clean_value
        os.environ[clean_key] = clean_value
    return values


def assert_critical_env_override(env_values: Mapping[str, str]) -> None:
    """Fail-closed defense against stale-OS-env-shadowing regression.

    For every key in ``CRITICAL_OVERRIDE_KEYS`` present in the parsed .env,
    confirm the live ``os.environ`` value matches. Any divergence indicates
    ``load_env_file`` did not apply override=True semantics (e.g. someone
    swapped the body back to ``setdefault``) and raises immediately so the
    startup fails hard instead of silently routing traffic to a stale
    endpoint. Memory rule ``[[stale-os-env-shadowing]]`` enforced at startup.
    """

    mismatches: list[tuple[str, str, str]] = []
    for key in CRITICAL_OVERRIDE_KEYS:
        if key not in env_values:
            continue
        expected = env_values[key]
        actual = os.getenv(key, "")
        if actual != expected:
            mismatches.append((key, expected, actual))
    if mismatches:
        # Redact secret values; expose only key names + length signature
        rendered = "; ".join(
            f"{key} (env-len={len(exp)} runtime-len={len(act)})"
            for key, exp, act in mismatches
        )
        raise ValueError(
            f"load_env_file override=True failed for critical keys (stale-os-env-shadowing regression): {rendered}"
        )


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def optional_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def optional_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    return float(value) if value else default


def optional_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def optional_csv(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "").strip()
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


def validate_cors_config(enabled: bool, allowed_origins: tuple[str, ...]) -> None:
    if not enabled:
        return
    if not allowed_origins:
        raise ValueError("CORS_ALLOWED_ORIGINS is required when CORS_ENABLED=true")
    if any(origin == "*" for origin in allowed_origins):
        raise ValueError("CORS_ALLOWED_ORIGINS must not contain wildcard origins")


def refresh_cookie_samesite_from_env() -> str:
    value = os.getenv("AUTH_REFRESH_COOKIE_SAMESITE", "lax").strip().lower()
    if value not in {"lax", "strict", "none"}:
        raise ValueError("AUTH_REFRESH_COOKIE_SAMESITE must be one of lax, strict, or none")
    if value == "none" and not optional_bool("AUTH_REFRESH_COOKIE_SECURE", False):
        raise ValueError(
            "AUTH_REFRESH_COOKIE_SAMESITE=none requires AUTH_REFRESH_COOKIE_SECURE=true"
        )
    return value


def database_url_from_env() -> str:
    if os.getenv("DATABASE_URL", "").strip():
        url = require_env("DATABASE_URL")
        if url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must not use SQLAlchemy postgresql+asyncpg scheme")
        return url
    host = require_env("POSTGRES_HOST")
    port = optional_int("POSTGRES_PORT", 5432)
    db = require_env("POSTGRES_DB")
    user = require_env("POSTGRES_USER")
    password = require_env("POSTGRES_PASSWORD")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"



def validate_redis_required() -> None:
    """Ensure Redis is configured as a core startup dependency."""

    has_url = bool(os.getenv("REDIS_URL", "").strip())
    has_direct = bool(os.getenv("REDIS_HOST", "").strip())
    has_sentinel = bool(
        os.getenv("REDIS_SENTINEL_HOSTS", "").strip()
        and os.getenv("REDIS_SENTINEL_SERVICE_NAME", "").strip()
    )
    if not (has_url or has_direct or has_sentinel):
        raise ValueError("Redis configuration is required for startup")

def validate_vite_public_env(env: Mapping[str, str]) -> None:
    for key, value in env.items():
        if key.startswith("VITE_") and (is_sensitive_key(key) or is_sensitive_key(value)):
            raise ValueError(f"VITE_ variable must not contain secrets: {key}")


def default_env_path() -> Path:
    """Resolve the .env file the app loads at startup.

    Defaults to ``<cwd>/.env``. A test harness may set ``HARNESS_ENV_FILE`` to
    point a spawned server process at a per-test env file, so fixture overrides
    survive ``load_env_file``'s override=True semantics — which would otherwise
    clobber subprocess-injected env vars with the repo ``.env`` (service-viability
    F8). Production leaves ``HARNESS_ENV_FILE`` unset, so this is identical to the
    prior hard-coded ``<cwd>/.env``. The chosen file is still applied with
    override=True and still passes ``assert_critical_env_override`` (a test overlay
    is a full copy of .env with only test-scoped keys changed).
    """

    override = os.environ.get("HARNESS_ENV_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.cwd() / ".env"


def load_config(env_path: Path | None = None) -> AppConfig:
    """Load and validate the documented startup configuration."""

    loaded_env = load_env_file(env_path) if env_path is not None else dict(os.environ)
    # Defensive: fail-closed on stale-OS-env-shadowing regression (F8 / 2026-05-24).
    assert_critical_env_override(loaded_env)

    python_path = require_env("PYTHON_PATH")
    python_version = require_env("PYTHON_VERSION")
    canonical_python_path = (
        loaded_env.get("HARNESS_CANONICAL_PYTHON_PATH", "").strip() or CANONICAL_PYTHON_PATH
    )
    if python_path != canonical_python_path:
        raise ValueError("PYTHON_PATH must point to the canonical wm_env interpreter")
    if python_version != CANONICAL_PYTHON_VERSION:
        raise ValueError("PYTHON_VERSION must be 3.11.5")

    bge_dimensions = int(require_env("BGE_EMBEDDING_DIMENSIONS"))
    if bge_dimensions != VECTOR_DIMENSIONS:
        raise ValueError("BGE_EMBEDDING_DIMENSIONS must match vector(1024)")

    env_snapshot = {**loaded_env, **dict(os.environ)}
    validate_redis_required()
    validate_vite_public_env(env_snapshot)
    frontend_public = {key: value for key, value in env_snapshot.items() if key.startswith("VITE_")}
    cors_enabled = optional_bool("CORS_ENABLED", False)
    cors_allowed_origins = optional_csv("CORS_ALLOWED_ORIGINS")
    validate_cors_config(cors_enabled, cors_allowed_origins)

    refresh_expire_seconds = int(require_env("JWT_REFRESH_EXPIRE_SECONDS"))
    refresh_cookie_max_age_seconds = optional_int(
        "AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS",
        refresh_expire_seconds,
    )
    if refresh_cookie_max_age_seconds <= 0:
        raise ValueError("AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS must be positive")

    return AppConfig(
        runtime=RuntimeConfig(
            app_env=require_env("APP_ENV"),
            log_level=require_env("LOG_LEVEL"),
            python_path=python_path,
            python_version=python_version,
        ),
        database=DatabaseConfig(database_url=database_url_from_env()),
        redis=RedisConfig(
            redis_url=os.getenv("REDIS_URL") or None,
            sentinel_hosts=os.getenv("REDIS_SENTINEL_HOSTS") or None,
            sentinel_service_name=os.getenv("REDIS_SENTINEL_SERVICE_NAME") or None,
            host=os.getenv("REDIS_HOST") or None,
            port=optional_int("REDIS_PORT", 6379) if os.getenv("REDIS_HOST") else None,
            password=os.getenv("REDIS_PASSWORD") or None,
            db=optional_int("REDIS_DB", 0),
            socket_timeout=optional_float("REDIS_SOCKET_TIMEOUT", 5.0),
            socket_connect_timeout=optional_float("REDIS_SOCKET_CONNECT_TIMEOUT", 5.0),
            max_connections=optional_int("REDIS_MAX_CONNECTIONS", 20),
        ),
        ai=AiConfig(
            azure_deployment_name=require_env("AZURE_OPENAI_DEPLOYMENT_NAME"),
            bge_embedding_url=require_env("BGE_EMBEDDING_API_URL"),
            bge_embedding_model=require_env("BGE_EMBEDDING_MODEL"),
            bge_dimensions=bge_dimensions,
            bge_auth_scheme=os.getenv("BGE_AUTH_SCHEME", "Bearer").strip() or "Bearer",
            bge_embedding_timeout_seconds=optional_float(
                "BGE_EMBEDDING_TIMEOUT_SECONDS",
                optional_float("BGE_EMBEDDING_TIMEOUT", 30.0),
            ),
            bge_rerank_url=require_env("BGE_RERANK_API_URL"),
            bge_rerank_model=require_env("BGE_RERANK_MODEL"),
        ),
        security=SecurityConfig(
            jwt_secret=require_env("JWT_SECRET"),
            access_expire_seconds=int(require_env("JWT_ACCESS_EXPIRE_SECONDS")),
            refresh_expire_seconds=int(require_env("JWT_REFRESH_EXPIRE_SECONDS")),
            refresh_cookie_name=(
                os.getenv("AUTH_REFRESH_COOKIE_NAME", "harness_refresh_token").strip()
                or "harness_refresh_token"
            ),
            refresh_cookie_secure=optional_bool("AUTH_REFRESH_COOKIE_SECURE", False),
            refresh_cookie_samesite=refresh_cookie_samesite_from_env(),
            refresh_cookie_path=os.getenv("AUTH_REFRESH_COOKIE_PATH", "/").strip() or "/",
            refresh_cookie_max_age_seconds=refresh_cookie_max_age_seconds,
        ),
        email=EmailConfig(
            send_enabled=optional_bool("HARNESS_EMAIL_SEND_ENABLED", False),
            smtp_host=os.getenv("SMTP_HOST") or None,
            smtp_port=optional_int("SMTP_PORT", 587),
            smtp_user=os.getenv("SMTP_USER") or None,
            smtp_password=os.getenv("SMTP_PASSWORD") or None,
            sender_email=os.getenv("SMTP_SENDER_EMAIL")
            or os.getenv("BREVO_SENDER_EMAIL")
            or None,
            sender_name=os.getenv("SMTP_SENDER_NAME")
            or os.getenv("BREVO_SENDER_NAME")
            or None,
            test_recipient_email=os.getenv("TEST_RECIPIENT_EMAIL") or None,
            timeout_seconds=optional_float("SMTP_TIMEOUT_SECONDS", 10.0),
            # Mailpit sandbox transport (ADR-002 / ADR-003)
            transport=os.getenv("HARNESS_EMAIL_TRANSPORT", "mailpit").strip() or "mailpit",
            mailpit_host=os.getenv("MAILPIT_HOST", "localhost").strip() or "localhost",
            mailpit_port=optional_int("MAILPIT_PORT", 1025),
            mailpit_auth_user=os.getenv("MAILPIT_SMTP_AUTH_USER") or None,
            mailpit_auth_password=os.getenv("MAILPIT_SMTP_AUTH_PASSWORD") or None,
            sandbox_guardrail_enabled=optional_bool(
                "EMAIL_SANDBOX_GUARDRAIL_ENABLED", False
            ),
        ),
        cors=CorsConfig(
            enabled=cors_enabled,
            allowed_origins=cors_allowed_origins,
        ),
        frontend_public=frontend_public,
    )
