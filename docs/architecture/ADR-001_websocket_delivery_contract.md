# ADR-001 WebSocket Delivery Contract

## Status
Accepted as a Stage 0.5 architecture contract. Runtime delivery is `backlog/not-current-contract`
until a FastAPI WebSocket route, RBAC/row-scope fanout, tests, and runbook evidence are committed.

Patched 2026-05-17 (RALPLAN-DR Iteration 2 Wave 1 / Stage 0.5) to:
- replace the query-token connection bootstrap with a short-lived single-use ticket flow (REG-05 T287),
- pin `Sec-WebSocket-Protocol=harness.v1` and Origin allowlist verification,
- specify reconnect/heartbeat/backoff and `event_id` idempotent replay (REG-05 T297),
- enumerate the subscribed event taxonomy with a one-message-per-event guarantee,
- cross-link ADR-005 dual-LLM quarantine so the WS fanout layer surfaces quarantined LLM output.

## Context
The product needs real-time notifications for NBA updates, async AI job completion, batch status,
and optional price ticks. The current implemented API contract intentionally excludes WebSocket
push. A frontend helper exists, but there is no implemented backend route in API-01 and no current
operations alert path that depends on push delivery.

## Decision
Keep WebSocket out of the implemented API contract until it can be delivered with a single canonical
envelope, explicit auth, row-scope filtering, replay-safe IDs, and operations runbooks. Future
implementation must use the candidate envelope in `docs/api/API-02_websocket.md` and must not expose
raw provider payloads, secrets, customer PII, or refresh cookies over the socket.

## Candidate Endpoint
- Browser-facing route: `/api/ws` through Vite/Nginx same-origin proxy.
- Backend route behind the proxy: `/ws`.
- Authentication: access token only, exchanged for a short-lived ticket (see "Connection Bootstrap"
  below). Refresh cookies are not authorization credentials and must not be used as socket auth
  fallback.
- Connection state: memory-only in the SPA; no token persistence in `localStorage` or
  `sessionStorage`.

## Connection Bootstrap — Short-Lived Ticket Flow (REG-05 T287)
The earlier draft used the access token in the WebSocket URL (`wss://.../ws?token=...`). That path is
rejected because the token appears in proxy access logs, browser history, and `Referer` headers, and
because it cannot be invalidated mid-handshake. The new contract is:

1. The SPA, already holding a valid access token in memory, calls `POST /ws/ticket` with the access
   token in the `Authorization: Bearer` header. The request body is empty.
2. The backend validates the access token (full JWT BCP per SEC-01 §4 / REG-05 §4), then issues a
   ticket JWT (or opaque random ≥128-bit) with the following claims:
   - `jti` — UUIDv4, used as the Redis key.
   - `sub` — `employee_id` of the requester.
   - `role_code`, `branch_id` — copied from access token claims (re-verified server-side; client
     claims are not trusted).
   - `iat`, `exp` — `exp - iat ≤ 30s`.
   - `iss=harness-poc`, `aud=harness-ws`.
3. The backend stores `harness:ws:ticket:{jti}` in Redis with `TTL=30s` and `status=issued`. The
   ticket is **one-shot**: on the first WebSocket handshake that presents it, the backend atomically
   transitions the key to `status=consumed` via Redis `SET ... XX NX` semantics (or `LUA CAS`); a
   second handshake with the same `jti` is rejected with HTTP 401 and the audit event
   `auth_ws_ticket_replay` (action_code per OBS-02).
4. The SPA opens `wss://<host>/api/ws` and provides the ticket via the first WebSocket text message
   `{"type":"hello","ticket":"<jwt>"}`. Tickets are **not** placed in the URL query string. (Sanitized
   subprotocol carrying the ticket is permitted only if HTTP `POST /ws/ticket` cannot be added —
   currently `POST /ws/ticket` is mandatory.)
5. On ticket consumption the backend re-resolves `employee_id → role_code/branch_id/row_scope` from
   PostgreSQL (not from claims) before fanout is unlocked, to defend against stale claims.
6. Connection failure modes:
   - ticket expired (> 30s) → 4401 close with reason `ticket_expired`,
   - ticket already consumed → 4403 close with reason `ticket_replay` + audit `auth_ws_ticket_replay`,
   - ticket signature/issuer/audience mismatch → 4401 close with reason `ticket_invalid`,
   - employee deactivated between ticket issue and handshake → 4403 close with reason
     `employee_inactive` + audit `auth_ws_session_revoked`.

## Subprotocol and Origin (REG-05 §6)
- The server **must** require `Sec-WebSocket-Protocol: harness.v1` on the handshake and must echo
  exactly `harness.v1` in the response. Handshakes without this subprotocol or with any other value
  are rejected with HTTP 400 (`subprotocol_required`).
- The handshake `Origin` header **must** be present and **must** match the configured allowlist
  (`CORS_ALLOWED_ORIGINS` when `CORS_ENABLED=true`, otherwise the same-origin host). Mismatched or
  missing `Origin` headers are rejected with HTTP 403 (`origin_rejected`).
- `harness.v1` is reserved as the only subprotocol for this contract. A future breaking event-shape
  change requires `harness.v2` and an ADR amendment.

## Reconnect, Heartbeat, and Replay Safety (REG-05 T297)
- **Ping**: the server sends a WebSocket ping frame every 30s. The client must reply with pong within
  10s; failure to pong twice consecutively closes the socket with reason `heartbeat_missing`.
- **Idle**: any connection with no client→server frame for 120s is closed by the server with reason
  `idle_timeout`. Server→client events do not reset the idle timer (server activity is unilateral).
- **Reconnect backoff**: the client must use exponential backoff with jitter on reconnect attempts:
  base 1s, factor 2, jitter ±25%, cap 30s. After 8 consecutive failed reconnects the client surfaces
  a sanitized banner and falls back to polling (`/ai-jobs/{job_id}`, `/batch/status`,
  `/data/readiness`).
- **Replay safety on reconnect**: each client maintains the highest-seen `event_id` per channel. On
  reconnect the client may resubscribe with `{"type":"subscribe","channel":"<ch>","since_event_id":
  "<id>"}`; the server replays events with `event_id > since_event_id` from a bounded ring (capacity
  policy: per-channel last-N or last-T-seconds, defined in API-02). Events outside the ring are
  dropped silently — the client is expected to reconcile via the HTTP polling endpoint for that
  channel. `event_id` is the idempotency key: duplicates **must** be discarded by the client without
  side effects.

## Required Event Envelope
Every server-to-client event must use this shape:

| field | required | rule |
|---|---:|---|
| `event_id` | yes | server-generated UUID or deterministic idempotency key; safe for logs |
| `event_type` | yes | one of the canonical event types in API-02 |
| `channel` | yes | logical fanout channel name (see "Subscribed Channels" below) |
| `occurred_at` | yes | ISO-8601 UTC timestamp |
| `trace_id` | yes | correlates application log, audit row, and client report |
| `actor_id` | conditional | employee UUID when the event was actor-triggered; omit for system-only events |
| `tenant_scope` | yes | branch/system scope descriptor used before fanout |
| `row_scope` | yes | customer/job/resource scope descriptor used before fanout |
| `quarantined` | conditional | boolean, present **only** for events whose payload originated from a quarantined LLM (see ADR-005); absent means privileged LLM or non-LLM source |
| `payload` | yes | schema-specific body with redacted, display-safe fields only |

## Subscribed Channels (Event Taxonomy)
The candidate WebSocket contract defines the following channels. Channel naming is dot-segmented and
stable; channel additions require an ADR amendment.

| channel | event_type set | description | row_scope key |
|---|---|---|---|
| `consultation.update` | `consultation_started`, `consultation_briefed`, `consultation_completed`, `consultation_email_drafted` | mutations and status transitions for a consultation row the subscriber is row-scoped to | `consultation_id` (PB/WM-only) |
| `nba.card` | `nba_card_published`, `nba_card_dismissed`, `nba_card_acted` | NBA recommendation lifecycle for the subscriber's assigned customers | `customer_id` (PB/WM/branch) |
| `market.tick` | `market_quote_tick`, `market_index_tick` | optional price/index ticks for symbols in the subscriber's watchlist; degraded silently outside BROKER office hours per ADR-007 | `symbol` (universal but rate-limited) |
| `audit.tail` | `audit_event_appended` | audit tail for AUDIT_VIEWER and ADMIN observability; payload is the safe-detail projection of `audit_logs` (no raw PII, no prompt text) | `none` (audience-gated by role) |

**One-message-per-event guarantee:** the server must emit exactly one WebSocket message per logical
event per subscriber. Coalescing or batching multiple logical events into a single frame is
prohibited. Duplicate emissions are tolerated by client-side `event_id` idempotency (see Replay
Safety), but must not be the server's primary delivery mode.

## Fanout and Authority Rules
- PB subscribers receive only their assigned customer events.
- WM and BRANCH_MANAGER subscribers receive branch-scoped customer events.
- ADMIN subscribers receive system/batch operations events, but not PB/WM front-office mutation
  authority by implication.
- AUDIT_VIEWER does not receive mutation prompts; audit visibility remains pull-based through
  `/audit-logs` plus the read-only `audit.tail` channel.
- `batch_status_change` remains operations-only until an ADMIN WebSocket path is implemented; current
  operations evidence is `/batch/status`, `/data/readiness`, logs, and batch reports.

## Quarantined-LLM Flagging (ADR-005 Cross-Link)
Per ADR-005 (Dual-LLM Quarantine), outputs from the quarantined LLM lane (rag_qa, email_draft,
consultation_briefing) carry a quarantine marker. When such an output is surfaced over WebSocket
(typically on `consultation.update` `consultation_briefed`/`consultation_email_drafted` or on
`nba.card` `nba_card_published` for AI-generated rationale), the envelope **must** include
`quarantined: true`. The SPA renders quarantined payloads with the unspoofable UI affordance defined
in AI-04 §"Quarantined output rendering" (currently: yellow chrome, "AI 인용 검증 필요" tag,
no auto-send actions). The privileged LLM lane does not set this flag.

## Rejected Alternatives
- **Cookie-authorized WebSocket**: rejected because refresh cookies are session-restoration tokens,
  not protected-route authorization credentials.
- **Per-feature ad hoc payloads**: rejected because they create drift between UI labels, audit logs,
  and operations evidence.
- **Green push alerts before polling works**: rejected because `/ai-jobs/{job_id}`, `/batch/status`,
  and `/data/readiness` must remain sufficient fallback paths.
- **Access token in query string (`wss://.../ws?token=...`)**: rejected per REG-05 §6 — token appears
  in proxy access logs, browser history, and `Referer`; not invalidatable mid-handshake.
- **Long-lived WebSocket session token**: rejected — a session-long token gives an attacker a single
  high-value credential; the ticket flow scopes credential exposure to ≤30s and one handshake.
- **Subprotocol-encoded ticket as primary path**: rejected as default — sanitized subprotocol is
  acceptable only as a fallback if `POST /ws/ticket` cannot land; the primary path is the hello-frame
  flow above to keep the handshake URL credential-free.

## Consequences
- Worker lanes may implement polling/UI states without waiting for WebSocket delivery.
- A future WebSocket backend lane must update API-01 only after route, tests, fanout filtering,
  ticket flow, subprotocol gate, heartbeat behavior, and OPS-04 runbook evidence exist.
- Validator scaffolding (`scripts/verify_websocket_contract.py`) can enforce the documented
  candidate contract — including ticket flow, `harness.v1` subprotocol, envelope fields, and event
  taxonomy — without claiming runtime delivery.
- The `harness:ws:ticket:{jti}` Redis namespace is reserved (REG-05 §7 Redis baseline); operations
  must size Redis memory to accommodate ticket TTL × peak issuance rate.
- ADR-005's quarantine marker becomes a required envelope field for any LLM-sourced payload; new
  AI surfaces adding WebSocket delivery must wire this flag at fanout time.

## Cross-References
- **BIZ-06 Compliance**: WebSocket fanout must not bypass row-scope authority that BIZ-06 §RBAC
  authorizes; PB/WM/BRANCH_MANAGER/ADMIN/AUDIT_VIEWER role matrix is the source of truth for
  channel access.
- **SEC-01 Auth Spec**: ticket issuance reuses the access-token validation pipeline (JWT BCP, alg
  allowlist, `iss`/`aud`/`nbf` checks). Refresh cookies are out of scope for WebSocket auth.
- **AI-04 RAG Spec**: payloads on `consultation.update` / `nba.card` originating from RAG inference
  must include citation integrity per AI-04 §"Citation contract" and the `quarantined` flag per
  ADR-005.
- **ADR-002 Email**: `consultation.update` `consultation_email_drafted` events surface email draft
  state transitions; the WS envelope reflects the ADR-002 state machine but never carries draft
  body content (display-safe summary only).
- **ADR-003 Dependency Gate**: no new WebSocket library beyond FastAPI's built-in support is
  permitted without ADR-003 amendment.
- **ADR-005 Dual-LLM Quarantine**: source of the `quarantined` envelope flag and of the UI
  rendering contract for quarantined output surfaced over WebSocket.
- **REG-05 §3 / §4 / §6**: source-of-truth for ticket flow, JWT BCP, and WS Origin/subprotocol
  controls; T287 and T297 trace to this ADR.
- **API-02 WebSocket**: canonical envelope schema and channel registry; this ADR governs the contract
  and API-02 carries the per-event payload schemas.
