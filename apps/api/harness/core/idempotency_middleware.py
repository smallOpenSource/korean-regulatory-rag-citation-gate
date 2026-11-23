"""Idempotency-Key middleware — ADR-011 implementation.

The :func:`idempotent` decorator wraps a FastAPI handler so duplicate POST/PATCH
requests carrying the same ``Idempotency-Key`` header get the prior response
verbatim instead of running the handler twice. Designed to defend against:

- browser tab refresh after a slow response
- SPA fetch retry on transient 5xx / network blip
- mobile background restore replaying the in-flight request

The backing store is the ``idempotency_keys`` table (V063). Lifecycle per row:

    in_flight -> completed   (handler returned 2xx/4xx)
    in_flight -> failed      (handler raised)

A 24h TTL sweep happens out-of-band; this module does not delete rows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from functools import wraps
from typing import Any, Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from .error_codes import ErrorCode
from .errors import structured_http_exception

logger = logging.getLogger(__name__)


def _canonicalize_body(body: Any) -> str:
    """Stable JSON for hashing. None → empty so missing-body requests hash."""
    if body is None:
        return ""
    if isinstance(body, (dict, list)):
        return json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    if isinstance(body, str):
        return body
    return json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)


def request_hash(
    method: str,
    route_template: str,
    body_canonical: str,
    actor_id: str | None,
) -> str:
    """SHA-256 of the deduplication tuple per ADR-011 §Server Pipeline."""
    payload = "|".join([method, route_template, body_canonical, actor_id or ""])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _replay_or_claim(
    conn: Any,
    *,
    idempotency_key: str,
    route_template: str,
    req_hash: str,
    actor_id: str | None,
) -> dict[str, Any] | None:
    """Try to claim the (key, route) tuple in an ``in_flight`` row.

    Returns None on a fresh claim (handler should run).
    Returns the existing row dict on UNIQUE conflict so the caller can
    decide between replay / 409 in-flight / 422 payload mismatch.
    """
    insert_sql = """
        INSERT INTO idempotency_keys
            (idempotency_key, route_template, request_hash, status, actor_id, created_at)
        VALUES ($1, $2, $3, 'in_flight', $4, now())
        ON CONFLICT (idempotency_key, route_template) DO NOTHING
        RETURNING idempotency_key
    """
    claimed = await conn.fetchrow(insert_sql, idempotency_key, route_template, req_hash, actor_id)
    if claimed is not None:
        return None

    existing = await conn.fetchrow(
        """
        SELECT idempotency_key, route_template, request_hash, status,
               response_body, response_status_code, actor_id, completed_at
        FROM idempotency_keys
        WHERE idempotency_key = $1 AND route_template = $2
        """,
        idempotency_key,
        route_template,
    )
    return dict(existing) if existing is not None else None


async def _record_completion(
    conn: Any,
    *,
    idempotency_key: str,
    route_template: str,
    status_code: int,
    body: Any,
) -> None:
    await conn.execute(
        """
        UPDATE idempotency_keys
        SET status = 'completed',
            response_body = $3::jsonb,
            response_status_code = $4,
            completed_at = now()
        WHERE idempotency_key = $1 AND route_template = $2
        """,
        idempotency_key,
        route_template,
        json.dumps(body, ensure_ascii=False, default=str),
        int(status_code),
    )


async def _record_failure(
    conn: Any,
    *,
    idempotency_key: str,
    route_template: str,
    error_repr: str,
) -> None:
    await conn.execute(
        """
        UPDATE idempotency_keys
        SET status = 'failed',
            response_body = $3::jsonb,
            completed_at = now()
        WHERE idempotency_key = $1 AND route_template = $2
        """,
        idempotency_key,
        route_template,
        json.dumps({"error": error_repr}, ensure_ascii=False),
    )


def _resolve_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Request | None:
    candidate = kwargs.get("request")
    if isinstance(candidate, Request):
        return candidate
    for arg in args:
        if isinstance(arg, Request):
            return arg
    return None


def _resolve_actor_id(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    actor = kwargs.get("actor")
    if actor is not None:
        emp = getattr(actor, "employee_id", None)
        if emp is not None:
            return str(emp)
    return None


def _resolve_payload(kwargs: dict[str, Any]) -> Any:
    return kwargs.get("payload")


def idempotent(handler: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Wrap a FastAPI handler with ADR-011 Idempotency-Key semantics.

    The handler must accept ``request: Request`` and (typically)
    ``payload: dict`` and ``actor`` kwargs. The wrapper:

    - rejects requests without ``Idempotency-Key`` (409 idempotency_key_required)
    - on UNIQUE conflict:
        * ``completed`` + matching request_hash  → return cached response
        * ``completed`` + different hash         → 422 payload_mismatch
        * ``in_flight``                          → 409 in_flight
    - on fresh claim: runs the handler, captures response + status, updates
      the row to ``completed``; on raise marks ``failed`` then re-raises.
    """

    @wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        request = _resolve_request(args, kwargs)
        if request is None:
            return await handler(*args, **kwargs)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            raise structured_http_exception(
                409,
                ErrorCode.idempotency_key_required,
                "Idempotency-Key header is required for this endpoint",
            )
        # The idempotency_keys.idempotency_key column is UUID (V063). A non-UUID
        # header would reach asyncpg as a str and raise a DataError *before* the
        # try/except below, surfacing as a 500. Validate the format up front and
        # return a clean 400 instead.
        try:
            uuid.UUID(str(idempotency_key))
        except (ValueError, AttributeError, TypeError):
            raise structured_http_exception(
                400,
                ErrorCode.idempotency_key_invalid,
                "Idempotency-Key must be a valid UUID",
            ) from None

        route_obj = request.scope.get("route")
        route_template = getattr(route_obj, "path", None) or request.url.path
        payload = _resolve_payload(kwargs)
        actor_id = _resolve_actor_id(args, kwargs)
        body_canonical = _canonicalize_body(payload)
        req_hash = request_hash(request.method, route_template, body_canonical, actor_id)

        from apps.api.harness.api.dependencies import get_pool

        pool = get_pool(request)
        async with pool.acquire() as conn:
            existing = await _replay_or_claim(
                conn,
                idempotency_key=idempotency_key,
                route_template=route_template,
                req_hash=req_hash,
                actor_id=actor_id,
            )

            if existing is not None:
                if existing["status"] == "in_flight":
                    raise structured_http_exception(
                        409,
                        ErrorCode.idempotency_key_in_flight,
                        "Idempotency-Key is already being processed; retry after the in-flight request completes",
                    )
                if existing["request_hash"] != req_hash:
                    raise structured_http_exception(
                        422,
                        ErrorCode.idempotency_key_payload_mismatch,
                        "Idempotency-Key was reused with a different payload",
                    )
                # Replay completed/failed row verbatim.
                cached_body = existing["response_body"]
                cached_status = existing["response_status_code"] or 200
                if isinstance(cached_body, str):
                    try:
                        cached_body = json.loads(cached_body)
                    except json.JSONDecodeError:
                        pass
                return JSONResponse(status_code=cached_status, content=cached_body)

        # Fresh claim: handler runs OUTSIDE the conn `with` block so the
        # connection is released before the (potentially long) handler call.
        try:
            response = await handler(*args, **kwargs)
        except Exception as exc:
            async with pool.acquire() as conn:
                await _record_failure(
                    conn,
                    idempotency_key=idempotency_key,
                    route_template=route_template,
                    error_repr=f"{type(exc).__name__}: {exc}",
                )
            raise

        # Serialize the response for caching. FastAPI returns dict/Pydantic
        # most of the time; if it's already a Response we record its body.
        if isinstance(response, Response):
            body_bytes = response.body if hasattr(response, "body") else b""
            try:
                cached = json.loads(body_bytes) if body_bytes else None
            except (json.JSONDecodeError, UnicodeDecodeError):
                cached = None
            status_code = response.status_code
        else:
            cached = response
            # Prefer the route's declared status_code (e.g. 201 for POST create)
            # so replays return the same HTTP code as the original handler did.
            declared = getattr(route_obj, "status_code", None)
            status_code = int(declared) if isinstance(declared, int) else 200

        async with pool.acquire() as conn:
            await _record_completion(
                conn,
                idempotency_key=idempotency_key,
                route_template=route_template,
                status_code=status_code,
                body=cached,
            )
        return response

    return wrapper
