# API-02 WebSocket

## Current Status
WebSocket short-lived ticket auth is **implemented and tested** (Wave 1, REG-05 T287/T297).
The `/ws/ticket` issuance endpoint and `/ws` connection endpoint are live in the backend.
Business-event fanout (nba_created, ai_job_done, etc.) remains `backlog/not-current-contract` —
do not add event push routes to API-01 until RBAC/row-scope fanout and OPS-04 runbook evidence exist.

## Wave 1 — Short-Lived Ticket Auth (REG-05 T287/T297)

### Ticket Issuance
```
POST /ws/ticket
Authorization: Bearer {access_token}
→ 200 { "ticket": "<UUID4>", "ttl_seconds": 30 }
→ 401 if no valid Bearer token
```
- The ticket is a one-shot UUID4 stored in Redis: `harness:ws:ticket:{ticket}` with TTL 30 s.
- Ticket must be consumed within the TTL by opening a WebSocket connection.
- Audit code `ws_ticket_issued` is written on successful issuance (resource_id = ticket UUID).

### WebSocket Handshake
```
GET /ws
Upgrade: websocket
Sec-WebSocket-Protocol: harness.v1
```
- `Sec-WebSocket-Protocol: harness.v1` is **required**. Missing subprotocol → close 4001.
- After upgrade, client sends: `{"ticket": "<UUID4>"}`.
- Server validates the ticket against Redis (single-use: key deleted on consume).
  - Non-existent or expired ticket → close 4002.
  - Valid ticket → connection established; audit code `ws_ticket_consumed` written.
- Origin is validated against `CORS_ALLOWED_ORIGINS`. Disallowed Origin → close 4003.

### Close Code Table
| Code | Meaning | Trigger |
|---|---|---|
| 4001 | No subprotocol | `Sec-WebSocket-Protocol: harness.v1` absent |
| 4002 | Ticket expired / not found | Redis key absent or TTL elapsed before consume |
| 4003 | Origin not allowed | Origin header not in `CORS_ALLOWED_ORIGINS` |
| 4004 | Idle timeout | No pong received within 120 s of last ping |
| 4005 | Server shutdown | Graceful shutdown signal received |

### Heartbeat / Keepalive
- Server sends a WebSocket ping frame every **30 seconds**.
- If no pong is received within **120 seconds** (4× ping interval), the connection is closed with 4004.
- Clients should implement an exponential backoff reconnect sequence:
  `1 s → 2 s → 4 s → 8 s → 16 s → 32 s` (cap), each step ± 20 % jitter.
  Obtain a fresh ticket before each reconnect attempt.

### Event Deduplication
- Client maintains a ring buffer of the last **256** `event_id` values.
- Duplicate `event_id` received on reconnect is silently dropped (client-side replay protection).
- `event_id` is UUID4 assigned by the server at emission time.

### Audit Codes (WebSocket lifecycle)
| action_code | 발생 조건 |
|---|---|
| ws_ticket_issued | `POST /ws/ticket` success |
| ws_ticket_consumed | WebSocket handshake ticket validated |
| ws_connection_opened | Connection fully established |
| ws_connection_closed | Connection terminated (any reason) |
| ws_reconnect | Client reconnect attempt logged |

## Candidate Endpoint
- Browser-facing route: `wss://{host}/api/ws` (same-origin proxy path).
- Backend route behind Nginx/Vite proxy: `/ws`.
- Auth: access-token bootstrap only. Refresh cookies are restricted to `/auth/refresh` and
  `/auth/logout`; they are not WebSocket authorization credentials.

## Required Server → Client Envelope
| field | required | description |
|---|---:|---|
| event_id | yes | UUID or deterministic idempotency key safe for logs |
| event_type | yes | canonical event type below |
| occurred_at | yes | ISO-8601 UTC timestamp |
| trace_id | yes | joins app log, audit row, and client report |
| actor_id | conditional | employee UUID for actor-triggered events |
| tenant_scope | yes | branch/system scope used before fanout |
| row_scope | yes | customer/job/resource scope used before fanout |
| payload | yes | event-specific body with redacted, display-safe fields |

## Candidate Events (server → client)
| event_type | payload schema | 발생 시점 | authority/fanout |
|---|---|---|---|
| nba_created | `{nba_id, customer_id, priority_code, action_type_code}` | NBA 신규 생성 | PB assigned customer, WM/BRANCH_MANAGER branch scope |
| nba_updated | `{nba_id, status_code}` | NBA 상태 변경 | same as NBA owner row scope |
| ai_job_done | `{job_id, resource_type, resource_id, result_summary}` | AI 에이전트 완료 | requester row scope; `/ai-jobs/{job_id}` remains fallback |
| batch_status_change | `{job_name, status_code, finished_at}` | 배치 완료/실패 | ADMIN operations only; `/batch/status` remains current path |
| price_tick | `{ticker, price, change_pct, as_of}` | 실시간 시세 후보 | subscription-gated future event; not readiness evidence |

## Connection Rules
- JWT access-token authentication is mandatory. Expired/invalid access tokens close the connection.
- Client ping interval target: 30 seconds. Reconnect policy target: 5 seconds, maximum five retries.
- No token persistence in `localStorage`, `sessionStorage`, or persisted Zustand stores.
- Every event must pass role and row-level filtering before fanout.
- Event payloads must not contain SMTP credentials, provider keys, bearer tokens, raw prompts, raw
  provider bodies, account numbers, resident registration numbers, or real customer PII.

## Implementation Gate
Before promoting WebSocket to current contract:
1. Add backend route and tests proving access-token auth and role/row-scope filtering.
2. Sync `apps/web/src/lib/websocket.ts`, `VITE_WS_BASE_URL`, Nginx proxy docs, and this endpoint.
3. Add observability evidence in OPS-04 and failure handling in OPS-03.
4. Keep `/ai-jobs/{job_id}`, `/batch/status`, and `/data/readiness` as polling fallbacks.
