"""WebSocket short-lived ticket flow (REG-05 T287, T297).

Endpoints
---------
POST /ws/ticket
    Issue a 30-second one-shot authentication ticket.
    Requires:  Authorization: Bearer <access_token>
    Returns:   {ticket: str, ttl_seconds: int}

WS /ws
    Ticket-authenticated realtime stream.
    Requires:  Sec-WebSocket-Protocol: harness.v1
    First message from client must be: {"ticket": "<uuid>"}
                                    or {"ticket": "<uuid>", "reconnect": true}

Auth flow
---------
1. Client POSTs to POST /ws/ticket with Bearer access token.
2. Client opens WS /ws advertising Sec-WebSocket-Protocol: harness.v1.
3. Client sends first message {"ticket": "<uuid>"} within 10 s of connect.
4. Server atomically GETDELs the ticket from Redis (one-shot; expires in 30 s).
5. Server registers the connection and sends connection_ack.
6. Server sends server-initiated pings every 30 s; idle timeout is 120 s (→ 4005).

Close codes
-----------
4001  unauthorized — missing/invalid subprotocol or ticket parse failure
4002  ticket expired or already consumed (Redis GETDEL returned nil)
4003  policy violation (reserved; not currently issued)
4004  unexpected server error
4005  idle timeout — no client message for IDLE_TIMEOUT seconds
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from apps.api.harness.api.dependencies import (
    actor_from_authorization,
    get_async_redis,
    get_pool,
    get_request_config,
)
from apps.api.harness.core.rbac import ActorContext
from apps.api.harness.repositories import audit as audit_repo

from .realtime import (
    REALTIME_EVENT_TYPES,
    _handle_client_message,
    manager,
)

router = APIRouter(tags=["realtime"])
logger = logging.getLogger(__name__)

# Redis key namespace — REG-05 T287
_WS_TICKET_PREFIX = "harness:ws:ticket:"
TICKET_TTL_SECONDS = 30

# Protocol constant (also exported for the frontend test contract)
WS_SUBPROTOCOL = "harness.v1"

# Timing
HEARTBEAT_INTERVAL = 30   # seconds — server → client ping cadence
IDLE_TIMEOUT = 120         # seconds — max silence before 4005 close

# Application-level WebSocket close codes
WS_CLOSE_UNAUTHORIZED = 4001
WS_CLOSE_EXPIRED = 4002
WS_CLOSE_POLICY = 4003
WS_CLOSE_SERVER_ERROR = 4004
WS_CLOSE_IDLE_TIMEOUT = 4005


def _extract_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for", "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None)


# ---------------------------------------------------------------------------
# Ticket issuance
# ---------------------------------------------------------------------------


@router.post("/ws/ticket")
async def issue_ws_ticket(request: Request) -> dict[str, Any]:
    """Issue a 30-second one-shot WebSocket authentication ticket (T287).

    The ticket is stored in Redis under ``harness:ws:ticket:<uuid>`` with a 30 s TTL.
    Consuming the ticket (via WS /ws) atomically deletes it; it cannot be reused.
    """
    config = get_request_config(request)
    actor = actor_from_authorization(config, request.headers.get("Authorization"))
    redis = get_async_redis(request)
    pool = get_pool(request)

    ticket = str(uuid.uuid4())
    key = f"{_WS_TICKET_PREFIX}{ticket}"
    ticket_payload = json.dumps(
        {
            "employee_id": actor.employee_id,
            "role_code": actor.role_code,
            "branch_id": actor.branch_id,
        }
    )
    await redis.set(key, ticket_payload, ex=TICKET_TTL_SECONDS)

    async with pool.acquire() as conn:
        await audit_repo.insert_audit_log(
            conn,
            actor_id=actor.employee_id,
            action_code="ws_ticket_issued",
            resource_type="ws_ticket",
            resource_id=ticket,
            detail={"ttl_seconds": TICKET_TTL_SECONDS},
            ip_address=_extract_ip(request),
            user_agent=request.headers.get("user-agent"),
        )

    return {"ticket": ticket, "ttl_seconds": TICKET_TTL_SECONDS}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


async def _run_heartbeat(websocket: WebSocket, interval: int) -> None:
    """Periodically send server-initiated pings (cancelled on disconnect)."""
    try:
        while True:
            await asyncio.sleep(interval)
            await websocket.send_json({"event_type": "ping", "payload": {}})
    except Exception:  # noqa: BLE001 — connection closed or task cancelled
        pass


@router.websocket("/ws")  # type: ignore[misc]
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Ticket-authenticated realtime WebSocket (harness.v1 subprotocol, T287/T297)."""

    # ── 1. Verify Sec-WebSocket-Protocol: harness.v1 ──────────────────────
    requested_protocols = [
        p.strip()
        for p in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if p.strip()
    ]
    if WS_SUBPROTOCOL not in requested_protocols:
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return

    redis = getattr(websocket.app.state, "async_redis_client", None)
    pool = getattr(websocket.app.state, "pool", None)
    if redis is None or pool is None:
        await websocket.close(code=WS_CLOSE_SERVER_ERROR)
        return

    # ── 2. Accept with agreed subprotocol (must come before receive) ──────
    await websocket.accept(subprotocol=WS_SUBPROTOCOL)

    # ── 3. Receive first message — must be ticket JSON within 10 s ────────
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        first_msg: Any = json.loads(raw)
        if not isinstance(first_msg, Mapping):
            raise ValueError("first message must be an object")
        ticket = str(first_msg.get("ticket", "")).strip()
        is_reconnect = bool(first_msg.get("reconnect", False))
        if not ticket:
            raise ValueError("ticket missing")
    except Exception:  # noqa: BLE001 — parse/timeout treated as unauthorized
        await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
        return

    # ── 4. Atomically consume ticket from Redis (GETDEL — one-shot) ───────
    ticket_key = f"{_WS_TICKET_PREFIX}{ticket}"
    ticket_raw: str | bytes | None = await redis.getdel(ticket_key)
    if ticket_raw is None:
        await websocket.close(code=WS_CLOSE_EXPIRED)
        return

    # ── 5. Parse actor from stored ticket payload ──────────────────────────
    try:
        ticket_data: dict[str, Any] = json.loads(ticket_raw)
        actor = ActorContext(
            employee_id=str(ticket_data["employee_id"]),
            role_code=str(ticket_data["role_code"]),
            branch_id=ticket_data.get("branch_id"),
        )
    except Exception:  # noqa: BLE001 — corrupted ticket data
        await websocket.close(code=WS_CLOSE_SERVER_ERROR)
        return

    # ── 6. Register connection (websocket already accepted) ────────────────
    manager.register(websocket, actor)
    conn_id = str(uuid.uuid4())

    # ── 7. Audit ticket_consumed + connection_opened (+ reconnect) ─────────
    try:
        async with pool.acquire() as conn:
            await audit_repo.insert_audit_log(
                conn,
                actor_id=actor.employee_id,
                action_code="ws_ticket_consumed",
                resource_type="ws_ticket",
                resource_id=ticket,
                detail={"conn_id": conn_id},
                ip_address=None,
                user_agent=None,
            )
            await audit_repo.insert_audit_log(
                conn,
                actor_id=actor.employee_id,
                action_code="ws_connection_opened",
                resource_type="ws_connection",
                resource_id=conn_id,
                detail={"role_code": actor.role_code, "reconnect": is_reconnect},
                ip_address=None,
                user_agent=None,
            )
            if is_reconnect:
                await audit_repo.insert_audit_log(
                    conn,
                    actor_id=actor.employee_id,
                    action_code="ws_reconnect",
                    resource_type="ws_connection",
                    resource_id=conn_id,
                    detail={},
                    ip_address=None,
                    user_agent=None,
                )
    except Exception:  # noqa: BLE001 — audit failure must not break the WS session
        logger.debug("ws open audit write failed (best-effort)")

    # ── 8. Send connection_ack ─────────────────────────────────────────────
    try:
        await websocket.send_json(
            {
                "event_type": "connection_ack",
                "payload": {
                    "conn_id": conn_id,
                    "role_code": actor.role_code,
                    "event_types": list(REALTIME_EVENT_TYPES),
                },
            }
        )
    except Exception:  # noqa: BLE001 — could not send ack; abort cleanly
        manager.disconnect(websocket)
        return

    # ── 9. Message loop with server-side heartbeat ─────────────────────────
    hb_task = asyncio.create_task(_run_heartbeat(websocket, HEARTBEAT_INTERVAL))
    try:
        while True:
            try:
                raw_msg = await asyncio.wait_for(
                    websocket.receive_text(), timeout=float(IDLE_TIMEOUT)
                )
            except asyncio.TimeoutError:
                await websocket.close(code=WS_CLOSE_IDLE_TIMEOUT)
                break

            try:
                message: Any = json.loads(raw_msg)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"event_type": "error", "payload": {"message": "invalid JSON"}}
                )
                continue

            if isinstance(message, Mapping):
                await _handle_client_message(websocket, message)
            else:
                await websocket.send_json(
                    {"event_type": "error", "payload": {"message": "message must be JSON object"}}
                )
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — log but don't surface internals
        logger.debug("ws_connection error in message loop")
    finally:
        hb_task.cancel()
        manager.disconnect(websocket)

        # Audit ws_connection_closed (best-effort — must not raise)
        try:
            async with pool.acquire() as conn:
                await audit_repo.insert_audit_log(
                    conn,
                    actor_id=actor.employee_id,
                    action_code="ws_connection_closed",
                    resource_type="ws_connection",
                    resource_id=conn_id,
                    detail={},
                    ip_address=None,
                    user_agent=None,
                )
        except Exception:  # noqa: BLE001 — best-effort close audit
            logger.debug("ws_connection_closed audit write failed")
