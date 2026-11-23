# API-03 Route / Screen / Backlog Matrix

This inventory is the contract index for keeping FastAPI routes, the React screen surface, and
BACKLOG status synchronized. It is intentionally concise; detailed request/response schemas remain in
`docs/api/API-01_contracts.yaml`, WebSocket payload rules remain in `docs/api/API-02_websocket.md`,
and screen copy/state details remain in `docs/ui/`.

## Backend route inventory

| Route | Method / transport | Current contract owner | Notes |
|---|---:|---|---|
| `/health` | GET | Backend foundation | Process health; public. |
| `/health/config` | GET | Backend foundation | Sanitized config; public diagnostics. |
| `/auth/login` | POST | Auth/session | Access token JSON + HttpOnly refresh cookie. |
| `/auth/refresh` | POST | Auth/session | Refresh Bearer token or refresh cookie -> access token. |
| `/auth/logout` | POST | Auth/session | Clears refresh cookie. |
| `/ws` | WebSocket | Realtime foundation | JWT access token query param, role/row-scoped event filtering. |
| `/dashboard` | GET | Dashboard | Authenticated role-scoped summary. |
| `/customers` | GET | Customer 360 | PB/WM/manager/admin row scope. |
| `/customers/{customer_id}` | GET | Customer 360 | Customer detail; row scope + audit. |
| `/customers/{customer_id}/portfolio-analysis` | POST | AI job | Durable portfolio analysis job. |
| `/products` | GET | Product catalog | Product list. |
| `/consultations` | POST | Consultation | PB/WM-only mutation. |
| `/consultations/{consultation_id}` | PATCH | Consultation | PB/WM-only update/completion gates. |
| `/consultations/{consultation_id}/briefing` | POST | AI job | Durable consultation briefing job. |
| `/consultations/{consultation_id}/compliance-check` | POST | AI output | Synchronous fail-closed compliance result. |
| `/email-drafts` | POST | Email | PB/WM row-scoped DRAFT creation; no SMTP send on creation. |
| `/email-drafts/{draft_id}/send` | POST | Email | APPROVED-only SMTP send; fail-closed when provider config is disabled/missing. |
| `/house-views` | GET/POST | House view | List/create house views; creation is admin/system scoped. |
| `/house-views/{house_view_id}` | GET | House view | Detail. |
| `/house-views/{house_view_id}/generate` | POST | AI job | Durable house-view generation job. |
| `/house-views/{house_view_id}/activate` | POST | House view | ADMIN activation + audit. |
| `/nba-actions` | GET | NBA/aftercare | Scoped NBA list. |
| `/nba-actions/{nba_id}/status` | PATCH | NBA/aftercare | PB/WM status mutation. |
| `/aftercare-events/{event_id}/resolve` | PATCH | NBA/aftercare | PB/WM aftercare resolution. |
| `/rag/query` | POST | RAG | Fail-closed/citation-gated response. |
| `/ai-jobs/{job_id}` | GET | AI job | Requester/admin/audit job read. |
| `/ai-outputs/{output_id}` | GET | AI output | Authorized generated output read. |
| `/recommendation-simulations` | POST | Simulation | PB/WM four-gate simulation. |
| `/order-simulations` | POST | Simulation | PB/WM order simulation gate. |
| `/order-simulations/{order_simulation_id}/execute-simulated` | POST | Simulation | Simulated execution only; no real trading. |
| `/batch/status` | GET | Batch monitor | ADMIN read-only batch status. |
| `/data/readiness` | GET | Readiness | ADMIN/service readiness evidence. |
| `/audit-logs` | GET | Audit | ADMIN/AUDIT_VIEWER read-only audit surface. |

## Frontend screen inventory

| Screen route | Route key | Allowed roles | Backend dependency |
|---|---|---|---|
| `/login` | public | public | `/auth/login`, `/auth/refresh`, `/auth/logout` |
| `/dashboard` | dashboard | PB, WM, BRANCH_MANAGER, ADMIN, AUDIT_VIEWER | `/dashboard`, `/data/readiness` |
| `/customers` | customers | PB, WM, BRANCH_MANAGER, ADMIN | `/customers` |
| `/customers/:customerId` | customer360 | PB, WM, BRANCH_MANAGER, ADMIN | `/customers/{customer_id}` |
| `/consultations/:consultationId` | consultation | PB, WM | `/consultations`, `/consultations/{consultation_id}` |
| `/nba` | nba | PB, WM | `/nba-actions`, `/nba-actions/{nba_id}/status` |
| `/house-views` | houseViews | PB, WM, BRANCH_MANAGER, ADMIN, AUDIT_VIEWER | `/house-views` |
| `/house-views/:houseViewId` | houseViews | PB, WM, BRANCH_MANAGER, ADMIN, AUDIT_VIEWER | `/house-views/{house_view_id}` |
| `/house-views/:houseViewId/activate` | houseViewActivation | ADMIN | `/house-views/{house_view_id}/activate` |
| `/rag` | rag | PB, WM, BRANCH_MANAGER, ADMIN | `/rag/query` |
| `/batch` | batch | ADMIN | `/batch/status`, `/data/readiness` |
| `/audit` | audit | ADMIN, AUDIT_VIEWER | `/audit-logs` |

## Backlog synchronization

| Backlog item | Current state | Matrix contract |
|---|---|---|
| T14 FastAPI app skeleton/auth/RBAC | Partial | App factory, auth/session, RBAC helpers, and route inclusion exist; WebSocket route now participates in the same access-token boundary. |
| T18 Email Draft API + send workflow | Partial/current API | `/email-drafts` and `/email-drafts/{draft_id}/send` exist with PB/WM row scope, APPROVED-only send, SMTP fail-closed semantics, and `email_sent_via_sandbox` audit on sandbox delivery success (`email_draft_send` reserved for real-SMTP, never emitted in PoC — ADR-002 §Amendment). |
| T20 WebSocket server | Partial | `/ws` server foundation exists with JWT access-token auth, ping/pong, subscribe ack, Redis channel fanout loop, and RBAC event filtering; producer/UI feature completion remains separate backlog. |
| T28 Consultation Workspace + Compliance Checklist | Backlog | Screen route exists; richer workspace controls remain frontend backlog. |
| T29 NBA Inbox + House View screens | Backlog/partial | Screen routes exist; backend NBA/house-view APIs exist; richer realtime UI reactions remain backlog. |
| T30 RAG Q&A + Batch Monitor + Audit Log | Partial | Read-only/fail-closed screens exist; interactive generation/run controls remain bounded-contract backlog. |

## Realtime event access matrix

| Event | Recipients | Required payload scope |
|---|---|---|
| `nba_created` | ADMIN; PB/WM/BRANCH_MANAGER when customer row scope matches | `customer_id` for DB lookup, or `assigned_pb_id`/`branch_id` in payload |
| `nba_updated` | ADMIN; PB/WM/BRANCH_MANAGER when customer row scope matches | `customer_id` for DB lookup, or `assigned_pb_id`/`branch_id` in payload |
| `ai_job_done` | Requesting employee, ADMIN, AUDIT_VIEWER | `requested_by_id` or equivalent employee id |
| `batch_status_change` | ADMIN only | none |
| `price_tick` | Authenticated employees; optional ticker subscription filter | `ticker` when client subscribes by ticker |
