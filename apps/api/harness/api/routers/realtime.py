"""WebSocket realtime event routing — RBAC filters, broadcast, Redis pub/sub fanout.

The WebSocket endpoint itself lives in ``routers/websocket.py`` (ticket-based auth,
T287/T297). This module provides shared state and event-handling helpers:
  - ``manager``  — global RealtimeConnectionManager
  - ``_handle_client_message`` — parses and responds to client control messages
  - ``redis_fanout_loop`` — subscribes to Redis channels and broadcasts events
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, WebSocket

from apps.api.harness.core.db import fetch_one
from apps.api.harness.core.logging import redact_secret_text
from apps.api.harness.core.rbac import ActorContext, can_access_customer

router = APIRouter(tags=["realtime"])
logger = logging.getLogger(__name__)

REALTIME_EVENT_TYPES: tuple[str, ...] = (
    "nba_created",
    "nba_updated",
    "ai_job_done",
    "batch_status_change",
    "price_tick",
)
CLIENT_EVENT_TYPES: tuple[str, ...] = ("connection_ack", "pong", "error")
REDIS_EVENT_CHANNEL_PREFIX = "harness:events:"
REDIS_EVENT_CHANNELS: dict[str, str] = {
    event_type: f"{REDIS_EVENT_CHANNEL_PREFIX}{event_type}" for event_type in REALTIME_EVENT_TYPES
}
LOOKUP_CUSTOMER_EVENT_SCOPE_SQL = """
/* sql_id: lookup_realtime_customer_scope */
SELECT c.id::text AS id, c.assigned_pb_id::text AS assigned_pb_id, c.branch_id::text AS branch_id
FROM customers c
WHERE c.id = $1::uuid
  AND c.is_active IS TRUE;
"""


def realtime_channel_for_event(event_type: str) -> str:
    """Return the canonical Redis pub/sub channel for a realtime event type."""

    if event_type not in REDIS_EVENT_CHANNELS:
        raise ValueError(f"Unsupported realtime event_type: {event_type}")
    return REDIS_EVENT_CHANNELS[event_type]


def event_type_from_channel(channel: str | bytes) -> str | None:
    """Return an event_type from a canonical Redis channel name, if recognized."""

    channel_text = channel.decode("utf-8") if isinstance(channel, bytes) else str(channel)
    if not channel_text.startswith(REDIS_EVENT_CHANNEL_PREFIX):
        return None
    event_type = channel_text.removeprefix(REDIS_EVENT_CHANNEL_PREFIX)
    return event_type if event_type in REALTIME_EVENT_TYPES else None


def normalize_realtime_event(
    raw_event: Mapping[str, Any] | str,
    event_type: str | None = None,
) -> dict[str, Any]:
    """Normalize a Redis/API event into the client WebSocket envelope."""

    data = json.loads(raw_event) if isinstance(raw_event, str) else dict(raw_event)
    resolved_event_type = event_type or data.get("event_type") or data.get("type")
    if not isinstance(resolved_event_type, str):
        raise ValueError("Realtime event_type is required")
    raw_payload = data.get("payload") if "payload" in data else data
    if not isinstance(raw_payload, Mapping):
        raise ValueError("Realtime payload must be an object")
    return {"event_type": resolved_event_type, "payload": dict(raw_payload)}


def _has_scope_fields(payload: Mapping[str, Any]) -> bool:
    return any(payload.get(f) for f in ("assigned_pb_id", "branch_id"))


def _customer_scope_from_payload(payload: Mapping[str, Any]) -> dict[str, str | None] | None:
    if not _has_scope_fields(payload):
        return None
    return {
        "assigned_pb_id": str(payload["assigned_pb_id"]) if payload.get("assigned_pb_id") else None,
        "branch_id": str(payload["branch_id"]) if payload.get("branch_id") else None,
    }


def _target_employee_id(payload: Mapping[str, Any]) -> str | None:
    for employee_field in ("requested_by_id", "employee_id", "actor_id"):
        value = payload.get(employee_field)
        if value:
            return str(value)
    return None


def event_visible_to_actor(
    actor: ActorContext,
    event: Mapping[str, Any],
    *,
    customer_scope: Mapping[str, str | None] | None = None,
) -> bool:
    """Return whether one event may be sent to one authenticated actor."""

    event_type = str(event.get("event_type") or "")
    payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
    payload_map: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}

    if event_type in CLIENT_EVENT_TYPES:
        return True
    if event_type not in REALTIME_EVENT_TYPES:
        return False
    if event_type == "batch_status_change":
        return actor.role_code == "ADMIN"
    if event_type == "price_tick":
        return True
    if event_type == "ai_job_done":
        return actor.role_code in {"ADMIN", "AUDIT_VIEWER"} or _target_employee_id(
            payload_map
        ) == actor.employee_id
    if event_type in {"nba_created", "nba_updated"}:
        if actor.role_code == "ADMIN":
            return True
        if actor.role_code == "AUDIT_VIEWER":
            return False
        scope = customer_scope or _customer_scope_from_payload(payload_map)
        return bool(scope) and can_access_customer(actor, dict(scope))
    return False


async def lookup_customer_event_scope(
    pool: Any,
    customer_id: str | None,
) -> dict[str, str | None] | None:
    """Load the minimal customer row scope needed to filter customer-scoped push events."""

    if not customer_id:
        return None
    try:
        async with pool.acquire() as connection:
            row = await fetch_one(connection, LOOKUP_CUSTOMER_EVENT_SCOPE_SQL, customer_id)
    except Exception as exc:  # noqa: BLE001 - invalid UUID or unavailable DB means fail-closed
        logger.warning("Realtime customer-scope lookup failed: %s", redact_secret_text(str(exc)))
        return None
    if row is None:
        return None
    return {
        "assigned_pb_id": str(row["assigned_pb_id"]) if row["assigned_pb_id"] is not None else None,
        "branch_id": str(row["branch_id"]) if row["branch_id"] is not None else None,
    }


@dataclass
class ConnectionState:
    """One authenticated WebSocket connection and client-side subscription filters."""

    websocket: WebSocket
    actor: ActorContext
    event_types: set[str] | None = None
    tickers: set[str] = field(default_factory=set)


class RealtimeConnectionManager:
    """Track authenticated WebSocket clients and fan out filtered events."""

    def __init__(self) -> None:
        self._connections: dict[int, ConnectionState] = {}

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def register(self, websocket: WebSocket, actor: ActorContext) -> None:
        """Register a pre-accepted WebSocket connection (T287).

        Use when the caller has already called ``websocket.accept()`` (ticket flow).
        For the legacy accept-then-register pattern use ``connect()`` instead.
        """
        self._connections[id(websocket)] = ConnectionState(websocket=websocket, actor=actor)

    async def connect(
        self,
        websocket: WebSocket,
        actor: ActorContext,
        *,
        subprotocol: str | None = None,
    ) -> None:
        """Accept the WebSocket and register it in one step."""
        await websocket.accept(subprotocol=subprotocol)
        self.register(websocket, actor)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.pop(id(websocket), None)

    def update_subscription(
        self,
        websocket: WebSocket,
        *,
        event_types: Sequence[str] | None = None,
        tickers: Sequence[str] | None = None,
    ) -> dict[str, list[str]]:
        state = self._connections[id(websocket)]
        if event_types is not None:
            allowed = {
                event_type for event_type in event_types if event_type in REALTIME_EVENT_TYPES
            }
            state.event_types = allowed or None
        if tickers is not None:
            state.tickers = {ticker.strip().upper() for ticker in tickers if ticker.strip()}
        return {
            "event_types": sorted(state.event_types or REALTIME_EVENT_TYPES),
            "tickers": sorted(state.tickers),
        }

    async def broadcast(self, event: Mapping[str, Any], *, pool: Any | None = None) -> int:
        """Send an event to every currently authorized subscriber.

        Injects a UUID4 ``event_id`` for client-side deduplication (T297).
        """
        normalized = normalize_realtime_event(event)
        normalized["event_id"] = str(uuid.uuid4())
        delivered = 0
        for state in list(self._connections.values()):
            if not await self._event_visible_to_connection(state, normalized, pool=pool):
                continue
            try:
                await state.websocket.send_json(normalized)
                delivered += 1
            except RuntimeError:
                self.disconnect(state.websocket)
        return delivered

    async def _event_visible_to_connection(
        self, state: ConnectionState, event: Mapping[str, Any], *, pool: Any | None
    ) -> bool:
        event_type = str(event.get("event_type") or "")
        if state.event_types is not None and event_type not in state.event_types:
            return False
        payload = event.get("payload") if isinstance(event.get("payload"), Mapping) else {}
        payload_map: Mapping[str, Any] = payload if isinstance(payload, Mapping) else {}
        if event_type == "price_tick" and state.tickers:
            ticker = str(payload_map.get("ticker") or "").upper()
            if ticker not in state.tickers:
                return False
        customer_scope = _customer_scope_from_payload(payload_map)
        needs_customer_lookup = (
            customer_scope is None
            and event_type in {"nba_created", "nba_updated"}
            and pool is not None
        )
        if needs_customer_lookup:
            customer_scope = await lookup_customer_event_scope(
                pool,
                str(payload_map.get("customer_id") or ""),
            )
        return event_visible_to_actor(state.actor, event, customer_scope=customer_scope)


manager = RealtimeConnectionManager()


async def _handle_client_message(websocket: WebSocket, message: Mapping[str, Any]) -> None:
    """Process a parsed client-sent control message and send the appropriate response."""

    message_type = str(message.get("type") or message.get("event_type") or "")
    if message_type == "ping":
        await websocket.send_json({"event_type": "pong", "payload": {"ok": True}})
        return
    if message_type == "pong":
        # Client acknowledging a server-initiated heartbeat ping — no reply needed.
        return
    if message_type == "subscribe":
        event_types_raw = message.get("event_types") or message.get("events")
        tickers_raw = message.get("tickers")
        event_types = (
            [str(value) for value in event_types_raw]
            if isinstance(event_types_raw, list)
            else None
        )
        tickers = [str(value) for value in tickers_raw] if isinstance(tickers_raw, list) else None
        subscription = manager.update_subscription(
            websocket,
            event_types=event_types,
            tickers=tickers,
        )
        await websocket.send_json({"event_type": "connection_ack", "payload": subscription})
        return
    await websocket.send_json(
        {"event_type": "error", "payload": {"message": "unsupported client message type"}}
    )


async def redis_fanout_loop(
    *,
    redis_client: Any,
    pool: Any,
    stop_event: asyncio.Event,
    connection_manager: RealtimeConnectionManager = manager,
) -> None:
    """Subscribe to canonical Redis realtime channels and fan out filtered events."""

    pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
    try:
        await asyncio.to_thread(pubsub.subscribe, *REDIS_EVENT_CHANNELS.values())
        while not stop_event.is_set():
            item = await asyncio.to_thread(pubsub.get_message, timeout=1.0)
            if not item or item.get("type") != "message":
                continue
            event_type = event_type_from_channel(item.get("channel", ""))
            if event_type is None:
                continue
            data = item.get("data")
            try:
                event = normalize_realtime_event(data, event_type=event_type)
            except Exception as exc:  # noqa: BLE001 - malformed pub/sub payload fails closed
                logger.warning(
                    "Ignoring malformed realtime event: %s",
                    redact_secret_text(str(exc)),
                )
                continue
            await connection_manager.broadcast(event, pool=pool)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - realtime must not leak secrets into logs
        logger.warning("Realtime Redis fanout stopped: %s", redact_secret_text(str(exc)))
    finally:
        with contextlib.suppress(Exception):
            await asyncio.to_thread(pubsub.close)
