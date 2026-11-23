# ADR-011 Idempotency-Key Middleware

## Status
ACCEPTED — fully implemented 2026-05-22 across three landing PRs:
- phase 1 (800318f): V063 migration + `idempotency_middleware.py` +
  POST /consultations + 5 functional scenarios + 50-iteration
  determinism pytest (400 parallel POSTs converge to 1 id).
- phase 2 (010f19b): PATCH /consultations + POST /email-drafts +
  POST /email-drafts/{id}/send.
- phase 3 (21aa309): POST /house-views + POST /kyc-edd/evaluate +
  PATCH /nba-actions/{id}/status + V064 unblocks the canonical
  `house_view_drafted` action_code (test_nba_aftercare_and_house_view
  regression flips from 500 → PASS).

7 of 7 applicable harness endpoints are now under the contract — the
8th proposed route (PATCH /house-views/{id}) does not exist; see the
reconciled enumeration below.

Still on the runway (not in this ADR's PR set):
- 24-hour TTL cleanup is **scheduled via systemd timer**
  (`scripts/cron/idempotency_keys_ttl_sweep.py`); the operator runbook
  is `docs/runbooks/RUN-13_idempotency_keys_ttl_sweep.md` (added
  2026-05-23 observability cycle Item 6). The runbook covers
  systemd unit/timer file contents, install + enable commands,
  monitoring thresholds (90-min staleness alert, >50k-row growth
  warning, >10s sweep-duration index-missing warning), and the
  failure-mode + recovery matrix. Status flips to DEPLOYED when ops
  promotes the timer to production.
- Cross-region replication is left to a future Wave 7+ ADR.

## Context
Several mutation endpoints in the harness API have side effects that are
expensive or externally observable:

- email send (SMTP relay to outbox; double-send is a regulator-visible defect)
- consultation create / state transition (4-gate gating, downstream NBA effects)
- house_view create / update (AI re-grounding cycle on save)
- nba trigger (queues a real-time WS broadcast)
- kyc_edd trigger create (governance evidence)

Real-world client conditions that cause duplicate POST/PATCH today:
- browser tab refresh after a slow response
- SPA fetch retry on transient 5xx / network blip
- mobile background restore replaying the in-flight request

The current API has no server-side replay defense. The only protection
is client-side button disable, which fails under all three conditions
above. Each duplicate request runs the full handler, emits a fresh
audit row, and may send a second email or create a second consultation
draft.

## Drivers
- ADR-002 Email Authority & Schema Contract §3: duplicate `email_sent`
  audit rows break the 1:1 client → record invariant.
- ADR-001 WebSocket Delivery Contract: duplicate NBA triggers cause
  duplicate broadcasts, surfacing as ghost notifications.
- OBS-02 §audit canonical: duplicate audit rows pollute action_code
  counts that downstream dashboards rely on.
- REG-04 §3-bis Audit Backbone: append-only means duplicates are
  permanent; a CREATE replay cannot be undone by a DELETE.
- SEC-02 §replay defense: lack of idempotency is the unhandled
  failure mode listed under "deferred to Wave Z5".

## Decision — Idempotency-Key Middleware + DB-Backed Dedupe

### Header Contract (RFC draft)
- Client sends `Idempotency-Key: <uuid-v4>` on annotated endpoints.
- Server treats the (route_template, idempotency_key) pair as the
  dedupe key (route_template included so the same key on two routes
  remains independent).
- TTL = 24 hours; expired keys are reusable.
- Missing header on an annotated endpoint returns **409
  `idempotency_key_required`** (not 400; the request is otherwise
  valid, only the dedupe contract is broken).

### Server Pipeline
1. Middleware reads the header at request entry, before the route handler.
2. Compute `request_hash = sha256(method || route_template || body_canonical_json || actor_id)`.
3. Insert `(idempotency_key, route_template, request_hash, status='in_flight')`
   into `idempotency_keys`. UNIQUE (idempotency_key, route_template) constraint
   serializes parallel duplicates.
4. On UNIQUE conflict:
   - If existing row `status='completed'` and `request_hash` matches:
     read back stored `response_body` + `status_code` and return it directly
     (no handler invocation).
   - If existing row `status='completed'` and `request_hash` differs:
     return **422 `idempotency_key_payload_mismatch`** (client reused the
     key with different content).
   - If existing row `status='in_flight'`: return **409
     `idempotency_key_in_flight`** (concurrent retry; client backs off).
5. On `in_flight` insert success: invoke the handler, capture the
   response, update the row to `status='completed'` with response_body
   + status_code, return the response.
6. Handler exceptions: update the row to `status='failed'` with the
   error envelope, then re-raise; the client may retry with the same
   key once the row TTLs.

### File Layout — Flat Module per OQ-5(a)
- `apps/api/harness/core/idempotency_middleware.py` — ASGI middleware +
  `@idempotent` decorator + DB session usage. **Flat** module
  (not a package); rationale: avoids the same `core/middleware/`
  package vs `core/middleware.py` collision documented in v4 plan §1.5.
- `apps/api/harness/core/error_codes.py` — append the three new codes
  above to the canonical enum.
- `db/migrations/V068__idempotency_keys.sql` — table create
  (the version number is provisional; the migration is allocated
  during the actual implementation cycle).

### Table Schema (`idempotency_keys`)
```sql
/* sql_id: create_idempotency_keys */
CREATE TABLE idempotency_keys (
  idempotency_key UUID NOT NULL,
  route_template  TEXT NOT NULL,
  request_hash    TEXT NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('in_flight','completed','failed')),
  response_body   JSONB,
  response_status_code SMALLINT,
  actor_id        UUID,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at    TIMESTAMPTZ,
  PRIMARY KEY (idempotency_key, route_template)
);

/* sql_id: idempotency_keys_created_at_idx */
CREATE INDEX idempotency_keys_created_at_idx
  ON idempotency_keys (created_at);
```

A periodic `DELETE FROM idempotency_keys WHERE created_at < now() - interval '24 hours'`
runs out-of-band (RUN-* cron, not in-handler). Append-only does **not**
apply here; this table is operational state, not audit evidence.

### Endpoint Enumeration (canonical, 2026-05-22 reconciliation)

The original 8-endpoint list was provisional; the actual harness routes
diverge in three places. The reconciled enumeration:

| # | route | method | status | reason |
|---|---|---|---|---|
| 1 | `/email-drafts` | POST | ✅ decorated | mutation creates `email_drafts` row |
| 2 | `/email-drafts/{draft_id}/send` | POST | ✅ decorated | external SMTP side effect |
| 3 | `/consultations` | POST | ✅ decorated | creates draft + emits `consultation_created` |
| 4 | `/consultations/{id}` | PATCH | ✅ decorated | 4-gate transition; emits state-change audit |
| 5 | `/house-views` | POST | ✅ decorated | inserts DRAFT house view + emits `house_view_drafted` |
| 6 | `/kyc-edd/evaluate` | POST | ✅ decorated | evaluates customer + creates KYC/EDD trigger row |
| 7 | `/nba-actions/{nba_id}/status` | PATCH | ✅ decorated | NBA card status transition; queues WS broadcast |
| 8 | `/house-views/{id}` PATCH | N/A | not applicable | route does not exist; house-view governance is split across `/activate`, `/generate`, `/review`, `/activate-lifecycle` — each is an opt-in governance step rather than a payload-driven mutation, so they sit outside this contract |

Naming corrections from the proposal:
- `/email/draft` → `/email-drafts` (actual route)
- `/email/send` → `/email-drafts/{draft_id}/send`
- `/nba/trigger` → `/nba-actions/{nba_id}/status` (the harness exposes
  per-action status mutation, not a single trigger endpoint)
- `/kyc-edd/triggers` → `/kyc-edd/evaluate` (the route that creates the
  trigger row; `/kyc-edd/triggers/{id}/...` are subsequent governance
  steps and are not under the Idempotency-Key contract)

(GET endpoints are intentionally **not** annotated; idempotent by HTTP semantics.)

### Async-202 Job Idempotency (2026-05-23 observability cycle Item 5 amend)

The original endpoint enumeration is a flat DECORATE/NO_DECORATE table.
Reviewing the sub-route surface for the observability cycle surfaced two
classes of mutation that need different idempotency semantics:

1. **Synchronous state transitions** — 200 OK responses. The Idempotency-Key
   middleware works as designed: replay returns the cached response,
   double-POST does not re-emit the audit row.

2. **Async 202 ACCEPTED jobs** — the response is "queued"; the actual side
   effect lands in a background task that may take seconds-to-minutes.
   Re-submitting the same Idempotency-Key has multiple plausible
   interpretations:
   - **Cancel-and-re-queue**: kill the in-flight job, start a new one.
   - **No-op-if-pending**: if the prior job is still RUNNING, return its
     job_id; if FAILED, allow retry; if SUCCEEDED, return cached
     response.
   - **Resource-key dedupe**: dedupe on the resource being acted on (e.g.
     `house_view_id`) rather than the request Idempotency-Key, so two
     UI clicks on the same DRAFT house-view's "generate" button can never
     spawn two concurrent generations regardless of header.

**Decision (this ADR)**: adopt **no-op-if-pending + resource-key dedupe**
for async-202 routes. The Idempotency-Key middleware is NOT the
authoritative dedupe layer for these routes; instead each handler
must:
- Read the resource's current state at request entry.
- If a prior job for this resource is `RUNNING` or `QUEUED`, return the
  existing job_id with status_code=202 (no new job).
- If a prior job is `SUCCEEDED`, return the cached result with
  status_code=200 (or 202 with `existing=true` flag).
- If a prior job is `FAILED` or absent, enqueue a new job.

This is the same contract the OpenAPI spec already exposes via the
`existing_job_id` field in the 202 response.

### Per-Endpoint Verdict Matrix

7 sub-routes audited; verdict per row:

| # | Route | Method | Class | Verdict | Rationale |
|---|---|---|---|---|---|
| 1 | `/email-drafts/{id}/submit` | POST | Sync state transition | **DECORATE** | DRAFT → PENDING_APPROVAL transition + audit emit. Replay must not duplicate audit. |
| 2 | `/email-drafts/{id}/approve` | POST | Sync state transition | **DECORATE** | PENDING_APPROVAL → APPROVED + audit emit. Replay must not duplicate audit. |
| 3 | `/email-drafts/{id}/reject` | POST | Sync state transition | **DECORATE** | PENDING_APPROVAL → REJECTED + audit emit. Replay must not duplicate audit. |
| 4 | `/house-views/{id}/activate` | POST | Sync state transition | **DECORATE** | DRAFT → ACTIVE governance step + audit emit. Sync 200. |
| 5 | `/house-views/{id}/review` | POST | Sync state transition | **DECORATE** | GENERATED → REVIEWED governance step + audit emit. Sync 200. |
| 6 | `/house-views/{id}/activate-lifecycle` | POST | Sync state transition | **DECORATE** | Lifecycle activation + audit emit. Sync 200. |
| 7 | `/house-views/{id}/generate` | POST | Async-202 job | **ASYNC_JOB** (no `@idempotent`) | 202 ACCEPTED; resource-key dedupe via house_view_id + current job status. Decorating with `@idempotent` would cache the wrong response (it would treat the 202 job_id as the canonical answer; a real client retry should get the same job_id, which the resource-key dedupe already provides). |
| 8 | `/house-views/{id}/generate-content` | POST | Async-202 job | **ASYNC_JOB** (no `@idempotent`) | Same as #7. |

**6 DECORATE + 2 ASYNC_JOB**. The DECORATE verdicts ship as their own PR
(observability cycle Item 5 implementation) with paired test-suite
updates per Z5 B.2 phase-2/3 pattern; this ADR amendment is the contract
anchor, not the implementation. ASYNC_JOB verdicts require no decoration
but record their resource-key dedupe expectation in the OpenAPI spec
`existing_job_id` field documentation (already present).

## Drivers Rejected
- **Pure client-side dedupe (UI button disable + storage flag)**.
  Rejected: fails under tab refresh, SPA hot-reload, network retry —
  the exact conditions where the server needs the defense.
- **ETag / If-Match on the resource**. Rejected: ETag applies to PUT
  on an existing resource (read state → conditional write). It cannot
  defend the CREATE case where there is no prior resource to ETag.
- **Per-row UNIQUE on a business key (e.g., consultation_subject + author_id)**.
  Rejected: forces a business invariant that the domain does not
  actually have. Two legitimate consultations on the same subject by
  the same author must remain possible.

## Consequences
- Clients MUST mint a uuid-v4 per logical action and resend it on retry.
  The OpenAPI spec (`docs/api/API-01_contracts.yaml`) is updated to
  surface the header requirement on the 8 routes.
- Duplicate POST/PATCH within 24h returns the **stored** response
  byte-for-byte. The server skips audit emission on the duplicate.
- Failed handlers (5xx) DO record their failure in `idempotency_keys`
  so the client cannot retry-storm; the operator must wait for TTL
  expiry or insert a manual cleanup row.
- Audit rows are emitted only on first success. Replay returns the
  cached response without re-emitting — this preserves the 1:1
  invariant required by OBS-02 / ADR-002.

## Test Plan (per [[test-determinism-against-random-input]] + replay-attack pytest)
1. **Happy path**: POST with Idempotency-Key → 200 + audit row.
2. **Identical replay**: POST same key + same body → 200 with cached
   response, audit row count unchanged.
3. **Same key + different body**: 422 `idempotency_key_payload_mismatch`.
4. **Missing header**: 409 `idempotency_key_required`.
5. **Concurrent identical replays**: 50× parallel POST same key →
   exactly one audit row, one stored response, all clients receive
   either the success response or a 409 in_flight.
6. **TTL expiry**: insert with `created_at` 25h ago, replay same key →
   new handler invocation, new audit row.
7. **Determinism**: 50× repeat of the parallel replay test must
   converge to exactly 1 row (not "~1") — flakiness here is a hard fail.

## Migration & Rollout
1. `V068__idempotency_keys.sql` lands first; table exists but no
   handler uses it.
2. Middleware ships next; `@idempotent` is opt-in — annotating an
   endpoint is what enables enforcement.
3. The 8 endpoints are decorated in 1-2 PR batches, each with the
   replay-attack test plan run live against the staged endpoint.
4. ADR-002 + ADR-001 + OBS-02 cross-references updated when all 8 are
   live.

## Open Questions Closed in This ADR
- **OQ-5**: flat `core/idempotency_middleware.py` (option a) — accepted
  here.
- **OQ on cleanup ownership**: out-of-band job, not in-handler — accepted.
- **OQ on per-actor vs global scoping**: keyed by (key, route_template)
  only; actor_id is recorded but not part of the dedupe key, so a
  malicious actor cannot DoS another actor's keys.

## Follow-ups (not in scope for this ADR)
- Production observability: idempotency hit/miss metrics surface to the
  same Prometheus stream that backs OBS-02 dashboards.
- Multi-region: cross-region UUID collisions are mathematically negligible
  but the table replication strategy needs an explicit decision once the
  PoC graduates to multi-region — deferred to a Wave-7+ ADR.
