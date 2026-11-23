"""FastAPI dependency helpers for DB, config, and actor context."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from apps.api.harness.core.config import AppConfig, default_env_path, load_config
from apps.api.harness.core.rbac import ActorContext
from apps.api.harness.core.security import decode_token


def get_request_config(request: Any) -> AppConfig:
    """Return app config loaded at startup, falling back to project .env."""

    config = getattr(request.app.state, "config", None)
    if config is not None:
        return config
    config = load_config(default_env_path())
    request.app.state.config = config
    return config


def get_pool(request: Any) -> Any:
    """Return asyncpg pool from app state."""

    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="database pool is not initialized")
    return pool


def get_async_redis(request: Any) -> Any:
    """Return the async Redis client from app state (injected at startup).

    Raises HTTP 503 if Redis is unavailable, so rate-limit and JWT blocklist
    endpoints fail closed rather than silently bypassing security controls.
    """
    client = getattr(request.app.state, "async_redis_client", None)
    if client is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Redis is not available")
    return client


def actor_from_authorization(config: AppConfig, authorization: str | None) -> ActorContext:
    """Decode the Bearer token into an ActorContext."""

    from fastapi import HTTPException

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token required")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token, secret=config.security.jwt_secret)
        if payload.get("token_type") != "access":
            raise ValueError("Access token required")
        return ActorContext(
            employee_id=str(payload["sub"]),
            role_code=str(payload["role_code"]),
            branch_id=payload.get("branch_id"),
        )
    except Exception as exc:  # noqa: BLE001 - auth boundary normalizes failures
        raise HTTPException(status_code=401, detail="Invalid access token") from exc


def request_audit_context(request: Any) -> dict[str, str | None]:
    """Return request metadata safe for audit detail columns."""

    client = getattr(request, "client", None)
    return {
        "ip_address": getattr(client, "host", None),
        "user_agent": request.headers.get("user-agent"),
    }


def parse_uuid_field(payload: dict[str, Any], field_name: str) -> str:
    """Return a JSON body UUID field as canonical text or raise a 422 boundary error."""

    from fastapi import HTTPException

    value = str(payload.get(field_name, "")).strip()
    try:
        return str(UUID(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} must be a UUID") from exc
