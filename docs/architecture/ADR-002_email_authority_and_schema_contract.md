# ADR-002 Email Authority and Schema Contract

## Status
Accepted and implemented for the backend HTTP contract. Email draft/send is current for
row-scoped draft creation; **live SMTP is forbidden in the PoC**. Send transport is restricted to
the Mailpit sandbox with a synthetic recipient allowlist (see "Sandbox Transport" below). If the
sandbox is disabled or unreachable, send fails closed with a sanitized blocked response and no
state change.

Patched 2026-05-17 (RALPLAN-DR Iteration 2 Wave 1 / Stage 0.5) to:
- pin the sandbox-only transport contract (Mailpit) for REG-02 T224 and replace the earlier
  provider-gated SMTP framing (REG-01 T207),
- enforce a server-side synthetic recipient allowlist,
- normalize the draft state machine to DRAFT→PENDING_APPROVAL→APPROVED→SENT|FAILED with
  `approved_at`, `sent_at`, `transport_message_id`, `failure_reason_code`,
- add the marketing classification flag, leading-disclosure block, and `광고심의 사전심의필 [번호]`
  pre-send lint (REG-03 T247),
- require the SEC-02 redaction filter be applied to subject and body **before** persistence and
  audit emission.

## Context
The schema includes `email_drafts`, the AI agent catalog includes `email_draft`, and the audit
vocabulary includes `email_draft_send`. The implemented API now exposes `POST /email-drafts` and
`POST /email-drafts/{draft_id}/send`. The contract must continue to prevent ADMIN/system authority
from being mistaken for PB/WM front-office communication authority, and must keep the PoC honest by
forbidding real SMTP delivery.

## Decision
Email implementation preserves a two-step authority model with a three-state approval pipeline and
a sandbox-only transport:

1. Draft creation stores only staff-provided, display-safe subject/body text and metadata as
   `DRAFT`.
2. The draft author (or peer PB/WM with row-scope) explicitly transitions the draft to
   `PENDING_APPROVAL` once content is ready for review.
3. Send is allowed only after an authorized PB/WM (distinct from the draft author when REG-03
   four-eye is required for marketing classification — see below) approves the draft, persisting
   `APPROVED` with `approved_at` and `approved_by_id`.
4. Send is executed via the Mailpit sandbox transport to a synthetic recipient on the server-side
   allowlist; success transitions to `SENT` with `sent_at` and `transport_message_id`; failure
   transitions to `FAILED` with `failure_reason_code`.

ADMIN may operate sandbox/provider configuration and observe system health, but ADMIN does not gain
customer communication mutation authority unless a separate staff-delegate business decision is
approved and documented.

## Sandbox Transport (PoC) — Mailpit Only
- The PoC **must not** send email to real SMTP relays or real recipient addresses. The only
  permitted transport is the Mailpit container provisioned in `docker-compose.yml` (ADR-003 §3
  "Already-Approved Additions" — Mailpit).
- The send code path resolves transport configuration from the `HARNESS_EMAIL_TRANSPORT` env var.
  Only `mailpit` is accepted in non-production builds; any other value fails closed with
  `failure_reason_code=transport_disallowed` and an `audit_logs.action_code='email_send_blocked'`
  row.
- Production builds dead-code-eliminate the SMTP-relay branch (see ADR-004 §"Dead-code elimination
  in prod build"). Until that elimination exists, deployment to non-PoC environments is gated by
  `scripts/check_no_poc_in_prod.sh`.
- Mailpit credentials, when enabled, live in `.env` (`MAILPIT_SMTP_AUTH_*`) and are never logged or
  persisted in `email_drafts` or `audit_logs`.

## Synthetic Recipient Allowlist
- All recipient addresses **must** match one of the server-side synthetic allowlist patterns. The
  default allowlist is the `@example.invalid` domain (RFC 6761) plus a small set of
  `syn-<role>-NN@example.invalid` synthetic-employee addresses provisioned for demo flows.
- The allowlist is enforced **server-side** at `POST /email-drafts/{draft_id}/send` — never via
  client validation alone. A draft persisted with an out-of-allowlist recipient is rejected at send
  time with `failure_reason_code=recipient_not_synthetic` and the audit code
  `email_send_blocked`.
- Allowlist source-of-truth: `apps/api/harness/services/email.py` constant
  `SYNTHETIC_RECIPIENT_PATTERNS` (regex list); change requires raw-SQL migration of any seeded
  synthetic-employee table plus an ADR-002 amendment.
- Per-recipient daily ceiling (PoC): 50 messages/synthetic-recipient/day, enforced via Redis
  counter `harness:email:rl:<recipient_hash>:<yyyymmdd>` with TTL 24h. Exceeding the ceiling fails
  closed with `failure_reason_code=recipient_rate_limited`.

## State Machine
The draft lifecycle is:

```
DRAFT ──submit──▶ PENDING_APPROVAL ──approve──▶ APPROVED ──send──▶ SENT
   ▲                  │                                  │
   │                  └──reject──▶ DRAFT                 └──send_fail──▶ FAILED
   │                                                                       │
   └─────────────────────────resubmit (new draft row)───────────────────────┘
```

Persisted columns (extending the current `email_drafts` schema; new columns land via V019+ raw-SQL
migration with leading `/* sql_id */` comment, SQL_ID convention per `db/migrator.py`):

| column | type | required | notes |
|---|---|---|---|
| `status_code` | text enum | yes | one of `DRAFT`, `PENDING_APPROVAL`, `APPROVED`, `SENT`, `FAILED` |
| `submitted_at` | timestamptz | when status reaches PENDING_APPROVAL | set by transition |
| `approved_at` | timestamptz | when status reaches APPROVED | set by transition |
| `approved_by_id` | uuid | when status reaches APPROVED | employee_id of approver; row-level CHECK enforces approver row-scope; for marketing-classified drafts, CHECK enforces `approved_by_id != employee_id` (four-eye, REG-03) |
| `sent_at` | timestamptz | when status reaches SENT | set on successful sandbox delivery |
| `transport_message_id` | text | when status reaches SENT | Mailpit Message-ID (or hashed Message-ID for length-safety); never the SMTP transcript |
| `failure_reason_code` | text enum | when status reaches FAILED | closed taxonomy: `transport_disallowed`, `transport_unreachable`, `recipient_not_synthetic`, `recipient_rate_limited`, `redaction_blocked`, `marketing_lint_failed`, `provider_5xx`, `provider_timeout`, `internal_error` |
| `marketing_classified` | boolean | yes (default false) | set at draft create or at AI classification step; once true, additional precondition gates apply |

Transitions are guarded server-side:
- Only the draft author (or row-scoped peer) may invoke `submit` (DRAFT→PENDING_APPROVAL).
- Only a PB/WM **other than** the author may invoke `approve` when `marketing_classified=true`
  (four-eye); for non-marketing drafts, self-approval is permitted but discouraged in the SPA.
- Only an APPROVED draft may invoke `send`.
- Any transition emits an `audit_logs` row with `action_code` in
  `{email_draft_create, email_draft_submit, email_draft_approve, email_draft_reject,
  email_draft_send, email_send_blocked, email_send_failed}` (OBS-02 vocabulary).

## Marketing Classification, Leading-Disclosure Block, and 광고심의 Lint (REG-03 T247)
- `marketing_classified` is set true when the draft is generated under the `email_draft` AI agent
  with intent `marketing` (e.g., product introduction, promotional event), or when a staff user
  manually toggles the marketing flag in the SPA.
- When `marketing_classified=true`, the rendered email body **must** begin with the regulator-
  mandated leading disclosure block (per REG-03 §광고규제 / 금융소비자보호법 광고심의). The
  pre-send lint enforces:
  1. The first non-empty line of `body` matches the leading-disclosure pattern (canonical text
     stored in `apps/api/harness/services/email.py` `LEADING_DISCLOSURE_REQUIRED_BLOCK`).
  2. The body contains the literal token `광고심의 사전심의필 [번호]` where `[번호]` is replaced
     with a non-empty `사전심의필번호` value supplied at submit time.
  3. The body contains a 수신거부 안내 line per REG-03 §광고심의.
- Lint failure aborts send with `failure_reason_code=marketing_lint_failed` and audit
  `email_send_blocked`. The failure response carries a sanitized error_code only — never the raw
  body diff.
- Non-marketing drafts (`marketing_classified=false`) bypass the leading-block / 광고심의 lint but
  are still subject to the redaction filter below.

## Audit Redaction Filter (Subject + Body, REG-05 §3.7 / SEC-02)
- Before any `email_drafts` INSERT/UPDATE that writes `subject` or `body`, **and** before any
  `audit_logs.detail_json` emission that references those fields, the SEC-02 / REG-05 §3.7
  redaction filter is applied:
  - Token patterns: `Authorization`, `Bearer eyJ...`, `*_api_key`, `*_secret`, `smtp_pass`,
    `password`, `harness_refresh_token`, `access_token`, JWT prefix `eyJ`.
  - PII patterns: 주민등록번호(6-7), 카드번호(13-19 with Luhn), 계좌번호(공통 8-14), 휴대전화
    (010-XXXX-XXXX), 외국인등록번호.
  - Prompt-leak patterns: system-prompt sentinel strings registered in
    `prompts/INJECTION_PATTERNS.yaml` (ADR-005 source-of-truth).
- A non-empty redaction hit on the subject/body **blocks persistence** with
  `failure_reason_code=redaction_blocked` and audit `email_send_blocked`. The blocked content is
  not stored anywhere — only the redaction-hit category counts go to `audit_logs.detail_json`.
- For `audit_logs.detail_json`, the filter is applied even when persistence succeeds: any
  subject/body excerpt logged is post-redaction.

## Route Contracts

### `POST /email-drafts`
Required request fields:

| field | rule |
|---|---|
| `customer_id` | UUID; optional when `consultation_id` is supplied; must pass requester row-scope |
| `consultation_id` | UUID; optional only when the draft is not tied to a consultation |
| `subject` | non-empty, display-safe text; redaction filter applied before persistence |
| `body` | non-empty, display-safe text; no account numbers, resident registration numbers, raw prompt text, or provider secrets; redaction filter applied before persistence |
| `marketing_classified` | optional boolean (default false); when true, marketing lint applies at submit/send |
| `사전심의필번호` | required when `marketing_classified=true`; non-empty regulator-issued advert review id |

Required response fields: `draft_id`, `status_code`, `ai_output_id`, `created_at`.
Initial `status_code` is `DRAFT`.

### `POST /email-drafts/{draft_id}/submit`
Preconditions:
- Requester role is PB or WM and within draft row-scope.
- `email_drafts.status_code = 'DRAFT'`.

Postconditions:
- `status_code` → `PENDING_APPROVAL`; `submitted_at` set.
- Audit `email_draft_submit` appended.

### `POST /email-drafts/{draft_id}/approve`
Preconditions:
- Requester role is PB or WM and within draft row-scope.
- `email_drafts.status_code = 'PENDING_APPROVAL'`.
- For `marketing_classified=true` drafts: requester `employee_id != email_drafts.employee_id`
  (four-eye, REG-03).

Postconditions:
- `status_code` → `APPROVED`; `approved_at`, `approved_by_id` set.
- Audit `email_draft_approve` appended.

### `POST /email-drafts/{draft_id}/send`
Preconditions:
- Requester role is PB or WM and within draft row-scope.
- `email_drafts.status_code = 'APPROVED'`.
- `HARNESS_EMAIL_TRANSPORT=mailpit` and the Mailpit sandbox is reachable.
- Recipient matches `SYNTHETIC_RECIPIENT_PATTERNS`.
- For marketing drafts: 광고심의 lint passes.
- Redaction filter on subject + body passes (no token/PII/prompt-leak hits).

Postconditions on success:
- Sandbox transport response is captured as `transport_message_id` (or its hash); no SMTP
  transcript is persisted.
- `email_drafts.status_code` transitions to `SENT` and `sent_at` is set.
- `audit_logs.action_code = 'email_draft_send'` is appended with safe detail JSON (after redaction):
  `{draft_id, customer_id_hash, recipient_hash, transport_message_id_hash, marketing_classified,
  사전심의필번호 (if present)}`.

Postconditions on failure:
- `email_drafts.status_code` transitions to `FAILED` and `failure_reason_code` is set to the
  matching enum value; `sent_at` remains null.
- `audit_logs.action_code = 'email_send_failed'` (or `email_send_blocked` for precondition
  failures) is appended with safe detail JSON containing only `failure_reason_code` and a
  trace_id.

## Schema Notes
- Existing `email_drafts` columns are the minimum durable schema: `customer_id`, `employee_id`,
  `consultation_id`, `subject`, `body`, `ai_generated_at`, `ai_model_name`, `status_code`, `sent_at`.
- The Stage 1+ migration (V019+ as scheduled in §5 Stage 1) adds `submitted_at`, `approved_at`,
  `approved_by_id`, `transport_message_id`, `failure_reason_code`, `marketing_classified`,
  `사전심의필번호`. Migration is raw SQL with leading `/* sql_id: email_drafts_state_machine_v1 */`
  comment, no migration framework (ADR-003).
- Do not store SMTP credentials, provider response bodies, raw prompts, account numbers, or raw
  customer PII in `email_drafts` or `audit_logs.detail_json`.

## Rejected Alternatives
- **ADMIN can send on behalf of PB/WM by default**: rejected because system authority is not
  front-office customer communication authority.
- **Send from DRAFT status**: rejected because it bypasses explicit staff approval; the new
  PENDING_APPROVAL state makes the approval moment auditable.
- **Mock SMTP green path**: rejected; the Mailpit sandbox provides real SMTP semantics against
  synthetic recipients, so blocked/SKIPPED results are honest rather than fabricated.
- **Live SMTP relay behind a feature flag**: rejected for the PoC scope — the risk of accidental
  delivery to real recipients during demos outweighs the realism gain, and the synthetic-recipient
  rule is server-enforced anyway.
- **Self-approval allowed for marketing drafts**: rejected — REG-03 four-eye on advert review
  cannot be waived in PoC simulation runs; the CHECK constraint enforces it.

## Consequences
- API-01 lists `/email-drafts`, `/email-drafts/{id}/submit`, `/email-drafts/{id}/approve`,
  `/email-drafts/{id}/send` once the V019+ migration and route handlers land; integration tests
  cover all five status transitions plus the four blocked paths (transport, recipient, lint,
  redaction).
- Provider-disabled local environments remain honest: send returns blocked rather than simulating
  delivery success.
- The Mailpit container is a required dev/CI dependency (ADR-003 §3); CI pipeline boots Mailpit
  before integration tests and asserts the `/api/v1/info` endpoint returns a version.
- The four-eye CHECK constraint on `approved_by_id != employee_id` for marketing drafts may
  surface as ergonomic friction in single-user demos; the runbook documents seeding two synthetic
  PB/WM employees so demo flows remain green.
- `scripts/verify_email_contract.py` (Stage 0.5 deliverable) enforces the state-machine and
  sandbox-only contract via fixture-based assertions; it fails on current drift and passes after
  implementation.

## Cross-References
- **BIZ-06 Compliance**: row-scope rules for draft access; four-eye policy for advert (광고)
  approval; trace from REG-03 §광고규제 to the marketing classification flag and CHECK constraint
  defined here.
- **SEC-01 Auth Spec**: PB/WM role gating on submit/approve/send; ADMIN exclusion from
  front-office communication authority; row-scope token claim verification.
- **AI-04 RAG Spec**: AI-generated `email_draft` outputs flow through the quarantined LLM lane
  (ADR-005); citation integrity for any factual claims in the body is governed by AI-04 §"Citation
  contract"; the redaction filter shared with SEC-02 strips prompt-leak sentinels before
  persistence.
- **ADR-001 WebSocket**: `consultation.update` `consultation_email_drafted` events on WebSocket
  reflect this state machine but never carry body content (display-safe summary only;
  `quarantined: true` when AI-generated).
- **ADR-003 Dependency Gate**: Mailpit is the only sanctioned email transport dependency (ADR-003
  §3); any change to transport library requires ADR-003 amendment.
- **ADR-004 PoC_AUTO_APPROVAL**: when `PoC_AUTO_APPROVAL` is engaged, the approve/send transitions
  still execute the redaction and marketing lint; the auto-approval governance marker is recorded
  in `audit_logs.governance_marker`, not as a bypass of the state machine.
- **ADR-005 Dual-LLM Quarantine**: AI-generated draft bodies originate from the quarantined LLM
  lane; the redaction filter shares `prompts/INJECTION_PATTERNS.yaml` with ADR-005.
- **ADR-006 Audit Append-Only**: every transition row in `audit_logs` is immutable per V008+V019
  trigger/REVOKE layered design.
- **REG-01 §3.1 / REG-02 §3 / REG-03 §광고규제**: regulator-mandated retention and advert review
  obligations; this ADR implements the proximate technical controls.

## Amendment (2026-05-31) — Sandbox audit vocabulary reconcile

The Decision above was authored before the implementation settled on Mailpit **sandbox-only**
delivery (this ADR §Context forbids real SMTP delivery). As a consequence the real-SMTP-only
success code `email_draft_send` is **registered but never emitted** in the PoC; the implemented
router (`apps/api/harness/api/routers/email.py`) emits the sandbox-honest vocabulary instead.
This amendment reconciles the design-era names with the implemented codes. It changes **no**
emitted code, **no** DB registration, and **no** `audit_logs` history — documentation only.

| 단계 | 설계기 명칭 (원 Decision §108) | 실제 emit code (구현) | emit 위치 |
|---|---|---|---|
| 초안 생성 | email_draft_create | `email_drafted` | routers/email.py |
| 심의 제출 | email_draft_submit | `email_draft_submitted` | routers/email.py |
| 심의 승인 | email_draft_approve | `email_draft_approved` | routers/email.py |
| 심의 반려 | email_draft_reject | `email_draft_rejected` | routers/email.py |
| 발송 성공 | email_draft_send | `email_sent_via_sandbox` | routers/email.py:652 |
| 발송 실패 | email_send_failed | `email_send_failed` | routers/email.py:630 |
| 발송 차단 | email_send_blocked | `email_send_blocked` | routers/email.py:555,585 |

- `email_draft_send` 는 CANONICAL(`core/audit.py`)·DB(`audit_action_codes`, V008)에 **등록을 유지**하며,
  real-SMTP 전송 성공 경로가 활성화될 때 emit하도록 **예약**된다. 등록을 제거하면
  `tests/test_audit_action_code_drift.py` (CANONICAL ≡ DB symmetric-diff 0) 가 깨지므로 제거하지 않는다.
- 본 PoC의 실제 발송 성공 audit 코드는 `email_sent_via_sandbox` (OBS-02 §REG-02) 이며, sandbox 전송임을
  정직하게 표기한다(real-SMTP 미실행).
- 본 amendment 는 문서 정합만 변경하며 emit 코드·등록·append-only audit 이력은 불변이다.
