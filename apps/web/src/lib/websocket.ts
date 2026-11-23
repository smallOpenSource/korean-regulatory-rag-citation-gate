/**
 * Ticket-based WebSocket client (REG-05 T287, T297).
 *
 * Auth flow
 * ---------
 * 1. Call POST /ws/ticket with the current access token → server returns a
 *    short-lived (30 s) one-shot ticket UUID.
 * 2. Open a WebSocket to WS_BASE_URL advertising the "harness.v1" subprotocol.
 * 3. Send {"ticket": "<uuid>"} as the very first message (add "reconnect": true
 *    on automatic reconnections so the server can emit ws_reconnect audit events).
 * 4. Await "connection_ack" — the connection is open and ready for events.
 *
 * Reconnect strategy
 * ------------------
 * Exponential backoff: 1 s → 2 s → 4 s → 8 s → 16 s → 32 s (max), plus up to
 * 20 % random jitter on each delay to prevent thundering-herd on server restart.
 * Policy-violation close (4003) suppresses all further reconnection attempts.
 *
 * Event deduplication
 * --------------------
 * The server injects event_id (UUID4) into every broadcast envelope (T297).
 * The client maintains a FIFO ring buffer of the last EVENT_ID_DEDUP_SIZE
 * seen IDs and silently drops duplicate deliveries.
 */

import { API_BASE_URL, WS_BASE_URL } from "./api";
import type { WebSocketEvent } from "./types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const WS_SUBPROTOCOL = "harness.v1";

const TICKET_ENDPOINT = `${API_BASE_URL}/ws/ticket`;
const BASE_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 32_000;
const EVENT_ID_DEDUP_SIZE = 256;

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

async function fetchWsTicket(token: string): Promise<string> {
  const response = await fetch(TICKET_ENDPOINT, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`ticket fetch failed: ${response.status}`);
  }
  const data = (await response.json()) as { ticket: string; ttl_seconds: number };
  return data.ticket;
}

/**
 * Exponential backoff with bounded jitter.
 *
 * attempt 0 → ~1 000 ms, attempt 1 → ~2 000 ms, … attempt 5+ → ~32 000 ms.
 * Each value has up to 20 % random jitter added.
 */
function backoffMs(attempt: number): number {
  const maxExp = Math.floor(Math.log2(MAX_BACKOFF_MS / BASE_BACKOFF_MS));
  const base = BASE_BACKOFF_MS * Math.pow(2, Math.min(attempt, maxExp));
  const capped = Math.min(base, MAX_BACKOFF_MS);
  return capped + Math.floor(Math.random() * capped * 0.2);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface WebSocketOptions {
  /** Return the current access token (may be called on every reconnect). */
  getToken: () => string | null;
  onEvent: (event: WebSocketEvent) => void;
  onStatusChange: (status: "connecting" | "open" | "closed" | "failed") => void;
}

/**
 * Open a ticket-authenticated WebSocket and return a cleanup function.
 *
 * Calling the returned function closes the socket and cancels any pending
 * reconnect timer.
 */
export function connectHarnessWebSocket({
  getToken,
  onEvent,
  onStatusChange,
}: WebSocketOptions): () => void {
  let retryCount = 0;
  let closedByClient = false;
  let socket: WebSocket | null = null;
  let reconnectTimer: number | undefined;

  // Event-id deduplication ring buffer (T297)
  const seenEventIds: string[] = [];

  function isDuplicate(eventId: string | undefined): boolean {
    if (!eventId) return false;
    if (seenEventIds.includes(eventId)) return true;
    seenEventIds.push(eventId);
    if (seenEventIds.length > EVENT_ID_DEDUP_SIZE) seenEventIds.shift();
    return false;
  }

  async function openSocket(): Promise<void> {
    onStatusChange("connecting");

    const token = getToken();
    if (!token) {
      onStatusChange("failed");
      return;
    }

    // Fetch one-shot ticket before opening the WebSocket
    let ticket: string;
    try {
      ticket = await fetchWsTicket(token);
    } catch {
      if (!closedByClient) scheduleReconnect();
      return;
    }

    if (closedByClient) return;

    socket = new WebSocket(WS_BASE_URL, WS_SUBPROTOCOL);

    socket.addEventListener("open", () => {
      if (!socket) return;
      // First message must be the ticket (plus reconnect flag if applicable)
      socket.send(
        JSON.stringify({ ticket, reconnect: retryCount > 0 }),
      );
    });

    socket.addEventListener("message", (evt) => {
      let parsed: WebSocketEvent;
      try {
        parsed = JSON.parse(evt.data as string) as WebSocketEvent;
      } catch {
        return;
      }

      // Deduplicate by server-injected event_id
      if (isDuplicate(parsed.event_id)) return;

      // Transition to "open" on connection_ack (ticket was accepted)
      if (parsed.event_type === "connection_ack") {
        retryCount = 0;
        onStatusChange("open");
      }

      onEvent(parsed);
    });

    socket.addEventListener("close", (evt) => {
      socket = null;
      if (closedByClient) {
        onStatusChange("closed");
        return;
      }
      // 4003 policy violation — do not attempt reconnect
      if (evt.code === 4003) {
        onStatusChange("failed");
        return;
      }
      scheduleReconnect();
    });

    // "error" is always followed by "close"; reconnect is handled there
    socket.addEventListener("error", () => undefined);
  }

  function scheduleReconnect(): void {
    retryCount += 1;
    onStatusChange("closed");
    const delay = backoffMs(retryCount - 1);
    reconnectTimer = window.setTimeout(() => {
      void openSocket();
    }, delay);
  }

  void openSocket();

  return () => {
    closedByClient = true;
    if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer);
    socket?.close();
  };
}
