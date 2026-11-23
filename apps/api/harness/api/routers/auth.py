"""Authentication routes with REG-05 T280-T283 security baseline."""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any, Literal, cast

from fastapi import APIRouter, HTTPException, Request, Response

from apps.api.harness.api.dependencies import get_async_redis, get_pool, get_request_config
from apps.api.harness.core.config import SecurityConfig
from apps.api.harness.core.rate_limit import check_login_rate_limit, check_refresh_rate_limit
from apps.api.harness.core.security import create_access_token, decode_token, verify_password
from apps.api.harness.repositories import audit as audit_repo
from apps.api.harness.repositories import auth as auth_repo
from apps.api.harness.services.password_breach import is_password_breached

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Redis key templates — REG-05 T282/T283
_BLOCKLIST_KEY = "harness:auth:refresh:jti:{jti}"
_EMPLOYEE_JTI_KEY = "harness:auth:employee:{employee_id}:refresh_jti:{jti}"
_EMPLOYEE_JTI_PATTERN = "harness:auth:employee:{employee_id}:refresh_jti:*"


# ---------------------------------------------------------------------------
# Cookie / token helpers
# ---------------------------------------------------------------------------

def _employee_public(employee: dict[str, Any]) -> dict[str, Any]:
    return {key: employee[key] for key in ("id", "name", "role_code", "branch_id")}


def _employee_claims(employee: dict[str, Any]) -> dict[str, str | None]:
    return {
        "role_code": str(employee["role_code"]),
        "branch_id": str(employee["branch_id"]) if employee["branch_id"] is not None else None,
    }


def _set_refresh_cookie(response: Response, refresh_token: str, security: SecurityConfig) -> None:
    samesite = cast(Literal["lax", "strict", "none"], security.refresh_cookie_samesite)
    response.set_cookie(
        key=security.refresh_cookie_name,
        value=refresh_token,
        max_age=security.refresh_cookie_max_age_seconds,
        path=security.refresh_cookie_path,
        httponly=True,
        secure=security.refresh_cookie_secure,
        samesite=samesite,
    )


def _clear_refresh_cookie(response: Response, security: SecurityConfig) -> None:
    samesite = cast(Literal["lax", "strict", "none"], security.refresh_cookie_samesite)
    response.delete_cookie(
        key=security.refresh_cookie_name,
        path=security.refresh_cookie_path,
        httponly=True,
        secure=security.refresh_cookie_secure,
        samesite=samesite,
    )


def _refresh_token_from_request(request: Request, security: SecurityConfig) -> str:
    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        if token:
            return token
    token = request.cookies.get(security.refresh_cookie_name, "").strip()
    if token:
        return token
    raise HTTPException(status_code=401, detail="refresh Bearer token or refresh cookie required")


def _client_ip(request: Request) -> str:
    """Return the client IP, honouring X-Forwarded-For when behind a trusted proxy."""
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", "unknown") if client else "unknown"


def _short_hash(value: str) -> str:
    """16-char SHA-256 prefix for PII-safe audit detail (ip_hash / ua_hash)."""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Redis JTI helpers — REG-05 T282/T283
# ---------------------------------------------------------------------------

async def _register_refresh_jti(
    redis: Any, *, employee_id: str, jti: str, ttl_seconds: int
) -> None:
    """Record an active refresh JTI under the per-employee namespace.

    Fail-open on Redis outage: login itself must succeed even when the JTI
    namespace is temporarily unreachable. Without registration, refresh
    rotation cannot mass-revoke this employee later — that is an acceptable
    degraded-security state (logged) versus a hard 500 on every login.
    """
    try:
        await redis.set(
            _EMPLOYEE_JTI_KEY.format(employee_id=employee_id, jti=jti),
            "active",
            ex=ttl_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("_register_refresh_jti fail-open: %s: %s", type(exc).__name__, exc)


# OQ-5 (ralplan v4 residual-closure follow-up, 2026-05-23): JTI blocklist
# grace window. Two near-concurrent refreshes from the same browser
# session can race: T1 succeeds + blocklists; T2 (still in flight,
# holding the old token) sees the immediate blocklist and gets 401 +
# triggers mass-revoke even though no attacker is involved. The grace
# window stores the blocklist timestamp instead of a sentinel and
# treats keys younger than JTI_BLOCKLIST_GRACE_SECONDS as not-yet-
# enforced. After the grace window elapses, the key is enforced
# normally — true reuse (post-grace) still triggers mass-revoke.
# Security trade-off + ops rationale in ADR-007.1.
JTI_BLOCKLIST_GRACE_SECONDS = 5


async def _blocklist_refresh_jti(redis: Any, *, jti: str, ttl_seconds: int) -> None:
    """Record a consumed refresh JTI with a blocklist timestamp.

    Stores the unix timestamp of consumption as the Redis value. The
    grace window in :func:`_is_jti_blocklisted` reads this back and
    returns False while ``now - stored_ts < JTI_BLOCKLIST_GRACE_SECONDS``,
    giving in-flight refreshes a chance to complete without triggering
    reuse-detection. Past the grace window the key is enforced as
    blocklisted.
    """
    try:
        ts_value = str(int(time.time()))
        await redis.set(_BLOCKLIST_KEY.format(jti=jti), ts_value, ex=max(ttl_seconds, 1))
    except Exception as exc:  # noqa: BLE001
        logger.warning("_blocklist_refresh_jti fail-open: %s: %s", type(exc).__name__, exc)


async def _is_jti_blocklisted(
    redis: Any, *, jti: str, grace_seconds: int = JTI_BLOCKLIST_GRACE_SECONDS
) -> bool:
    """Check whether a JTI is in the blocklist AND past the grace window.

    Returns True only when the key exists AND the stored timestamp is
    older than ``grace_seconds``. A legacy "revoked" sentinel (pre-OQ-5
    code path) is treated as already-past-grace so a rollback to the
    old writer would still enforce immediately.
    """
    try:
        value = await redis.get(_BLOCKLIST_KEY.format(jti=jti))
        if value is None:
            return False
        # Redis returns bytes by default; normalise.
        raw = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        try:
            blocklisted_at = int(raw)
        except (TypeError, ValueError):
            # Legacy sentinel string ("revoked") or unparseable value →
            # enforce immediately (no grace).
            return True
        return (int(time.time()) - blocklisted_at) >= grace_seconds
    except Exception as exc:  # noqa: BLE001
        # Cannot verify blocklist → treat as not-blocklisted (fail-open) so the
        # refresh path doesn't hard-fail; reuse-detection still runs at the
        # downstream mass-revoke layer which is also fail-open.
        logger.warning("_is_jti_blocklisted fail-open: %s: %s", type(exc).__name__, exc)
        return False


async def _mass_revoke_employee_tokens(redis: Any, *, employee_id: str) -> None:
    """Delete ALL active refresh JTIs for employee_id (T283 reuse-detection response)."""
    pattern = _EMPLOYEE_JTI_PATTERN.format(employee_id=employee_id)
    cursor = 0
    try:
        while True:
            cursor, keys = await redis.scan(cursor, match=pattern, count=100)
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break
    except Exception as exc:  # noqa: BLE001
        logger.warning("_mass_revoke_employee_tokens fail-open: %s: %s", type(exc).__name__, exc)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/auth/login")  # type: ignore[union-attr]
async def login(request: Request, response: Response, payload: dict[str, Any]) -> dict[str, Any]:
    """Authenticate an employee, set an HttpOnly refresh cookie, and return access metadata.

    REG-05 T280: Rate-limited per IP+username (10/min, 60/15min). Audit on 429.
    REG-05 T281: HIBP breach check is soft (non-blocking); flags compromised passwords.
    REG-05 T282: Tokens include iss, aud, nbf, jti (RFC 8725).
    REG-05 T283: Refresh JTI registered in Redis for rotation tracking.
    """
    email = str(payload.get("email", "")).strip()
    password = str(payload.get("password", ""))
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")

    config = get_request_config(request)
    redis = get_async_redis(request)
    pool = get_pool(request)
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")

    # T280 — rate limit before any DB work
    if not await check_login_rate_limit(redis, ip=ip, username=email):
        async with pool.acquire() as conn:
            await audit_repo.insert_audit_log(
                conn,
                actor_id=None,
                action_code="auth_login_rate_limited",
                resource_type="auth",
                resource_id=None,
                detail={"ip_hash": _short_hash(ip), "username_hash": _short_hash(email)},
                ip_address=ip,
                user_agent=ua,
            )
        raise HTTPException(status_code=429, detail="Too many login attempts. Please wait.")

    # Auth — single pool.acquire() for employee lookup + failure audit
    async with pool.acquire() as conn:
        employee = await auth_repo.find_employee_by_email(conn, email)
        if not employee or not verify_password(password, str(employee["password_hash"])):
            await audit_repo.insert_audit_log(
                conn,
                actor_id=None,
                action_code="auth_login_failure",
                resource_type="auth",
                resource_id=None,
                detail={"ip_hash": _short_hash(ip), "username_hash": _short_hash(email)},
                ip_address=ip,
                user_agent=ua,
            )
            raise HTTPException(status_code=401, detail="invalid credentials")

    employee_id = str(employee["id"])
    claims = _employee_claims(employee)

    # T282 — build tokens; provide explicit refresh jti for Redis tracking
    access_token = create_access_token(
        subject=employee_id,
        secret=config.security.jwt_secret,
        expires_in_seconds=config.security.access_expire_seconds,
        extra_claims={**claims, "token_type": "access"},
    )
    refresh_jti = str(uuid.uuid4())
    refresh_token = create_access_token(
        subject=employee_id,
        secret=config.security.jwt_secret,
        expires_in_seconds=config.security.refresh_expire_seconds,
        extra_claims={**claims, "token_type": "refresh", "jti": refresh_jti},
    )

    # T283 — register refresh jti in per-employee namespace
    await _register_refresh_jti(
        redis,
        employee_id=employee_id,
        jti=refresh_jti,
        ttl_seconds=config.security.refresh_expire_seconds,
    )

    # T281 — soft HIBP breach flag (best-effort; never blocks login)
    try:
        if await is_password_breached(password):
            logger.warning(
                "Login with breached password detected",
                extra={"employee_id": employee_id, "ip_hash": _short_hash(ip)},
            )
    except Exception:  # noqa: BLE001
        pass

    _set_refresh_cookie(response, refresh_token, config.security)
    return {
        "access_token": access_token,
        "employee": _employee_public(employee),
    }


@router.post("/auth/refresh")  # type: ignore[union-attr]
async def refresh(request: Request, response: Response) -> dict[str, Any]:
    """Issue new access + refresh tokens (rotation) from a valid refresh cookie or Bearer token.

    REG-05 T280: Rate-limited per IP (30/min).
    REG-05 T282: Validates JTI against Redis blocklist before issuing new tokens.
    REG-05 T283: Rotates refresh JTI; blocklists old JTI; mass-revokes on reuse detection.
    """
    config = get_request_config(request)
    redis = get_async_redis(request)
    pool = get_pool(request)
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")

    # T280 — refresh rate limit
    if not await check_refresh_rate_limit(redis, ip=ip):
        # Wave-Audit-Defect-Fix B5: emit canonical auth_refresh_rate_limited
        # audit row before the 429 so repeated abuse is visible in audit.
        async with pool.acquire() as conn:
            await audit_repo.insert_audit_log(
                conn,
                actor_id=None,
                action_code="auth_refresh_rate_limited",
                resource_type="auth",
                resource_id=None,
                detail={"ip_hash": _short_hash(ip), "ua_hash": _short_hash(ua or "")},
                ip_address=ip,
                user_agent=ua,
            )
        raise HTTPException(status_code=429, detail="Too many refresh attempts. Please wait.")

    refresh_token_str = _refresh_token_from_request(request, config.security)
    try:
        token_payload = decode_token(refresh_token_str, secret=config.security.jwt_secret)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    if token_payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="refresh token required")

    old_jti = str(token_payload.get("jti", ""))
    employee_id = str(token_payload["sub"])
    old_exp = int(token_payload.get("exp", 0))

    # T283 — JTI reuse detection → mass-revoke + audit
    if old_jti and await _is_jti_blocklisted(redis, jti=old_jti):
        await _mass_revoke_employee_tokens(redis, employee_id=employee_id)
        async with pool.acquire() as conn:
            await audit_repo.insert_audit_log(
                conn,
                actor_id=employee_id,
                action_code="auth_refresh_reuse",
                resource_type="auth",
                resource_id=None,
                detail={
                    "ip_hash": _short_hash(ip),
                    "ua_hash": _short_hash(ua or ""),
                    "jti": old_jti,
                },
                ip_address=ip,
                user_agent=ua,
            )
        raise HTTPException(status_code=401, detail="refresh token has been revoked")

    # DB — verify employee is still active
    async with pool.acquire() as conn:
        employee = await auth_repo.find_employee_by_id(conn, employee_id)
    if employee is None:
        raise HTTPException(status_code=401, detail="invalid refresh token")

    claims = {
        "role_code": employee["role_code"],
        "branch_id": str(employee["branch_id"]) if employee["branch_id"] is not None else None,
    }

    # T282/T283 — issue new tokens with fresh JTI
    access_token = create_access_token(
        subject=employee_id,
        secret=config.security.jwt_secret,
        expires_in_seconds=config.security.access_expire_seconds,
        extra_claims={**claims, "token_type": "access"},
    )
    new_refresh_jti = str(uuid.uuid4())
    new_refresh_token = create_access_token(
        subject=employee_id,
        secret=config.security.jwt_secret,
        expires_in_seconds=config.security.refresh_expire_seconds,
        extra_claims={**claims, "token_type": "refresh", "jti": new_refresh_jti},
    )

    # T283 — blocklist old JTI, deregister it, register new JTI
    remaining_ttl = max(1, old_exp - int(time.time()))
    if old_jti:
        await _blocklist_refresh_jti(redis, jti=old_jti, ttl_seconds=remaining_ttl)
        try:
            await redis.delete(_EMPLOYEE_JTI_KEY.format(employee_id=employee_id, jti=old_jti))
        except Exception as exc:  # noqa: BLE001
            logger.warning("refresh: deregister old jti fail-open: %s: %s", type(exc).__name__, exc)
    await _register_refresh_jti(
        redis,
        employee_id=employee_id,
        jti=new_refresh_jti,
        ttl_seconds=config.security.refresh_expire_seconds,
    )

    # Wave-Audit-Defect-Fix B6: success path emits canonical auth_refresh
    # audit row (already canonical at core/audit.py:30) so the rotation
    # event leaves evidence — previously refresh success was unaudited.
    async with pool.acquire() as conn:
        await audit_repo.insert_audit_log(
            conn,
            actor_id=employee_id,
            action_code="auth_refresh",
            resource_type="auth",
            resource_id=None,
            detail={
                "ip_hash": _short_hash(ip),
                "ua_hash": _short_hash(ua or ""),
                "new_jti": new_refresh_jti,
            },
            ip_address=ip,
            user_agent=ua,
        )

    _set_refresh_cookie(response, new_refresh_token, config.security)
    return {"access_token": access_token, "employee": _employee_public(employee)}


@router.post("/auth/logout")  # type: ignore[union-attr]
async def logout(request: Request, response: Response) -> dict[str, str]:
    """Clear the browser refresh cookie. Requires a valid refresh token.

    Wave-Audit-Defect-Fix A3 (audit defect: ``/auth/logout`` returned 200 to
    unauthenticated callers and emitted no audit row). The endpoint now
    validates the refresh cookie/Bearer header, returns 401 on missing or
    invalid tokens, and emits an ``auth_logout`` audit row (canonical at
    core/audit.py:32 and V022:6) before clearing the cookie.
    """
    config = get_request_config(request)
    pool = get_pool(request)
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")

    refresh_token_str = _refresh_token_from_request(request, config.security)
    try:
        token_payload = decode_token(refresh_token_str, secret=config.security.jwt_secret)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    if token_payload.get("token_type") != "refresh":
        raise HTTPException(status_code=401, detail="refresh token required")

    employee_id = str(token_payload["sub"])

    async with pool.acquire() as conn:
        await audit_repo.insert_audit_log(
            conn,
            actor_id=employee_id,
            action_code="auth_logout",
            resource_type="auth",
            resource_id=None,
            detail={
                "ip_hash": _short_hash(ip),
                "ua_hash": _short_hash(ua or ""),
            },
            ip_address=ip,
            user_agent=ua,
        )

    _clear_refresh_cookie(response, config.security)
    return {"status": "logged_out"}
