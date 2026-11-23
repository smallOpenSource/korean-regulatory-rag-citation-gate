# INT-03 Email Integration

## Current Status
Email draft/send is a current backend HTTP contract for staff-created drafts and provider-gated
send. The implemented routes are `POST /email-drafts` and `POST /email-drafts/{draft_id}/send`.
Draft creation is local-only and never sends mail. Send uses real configured SMTP only after the
row is `APPROVED`; when SMTP is disabled or incomplete it returns a sanitized
`BLOCKED_WITH_REDACTED_REASON` and leaves the draft unchanged. There is no mock SMTP green path.

## Provider
- 기본 제공자: Brevo SMTP 또는 compatible SMTP.
- 표준 앱 설정은 `HARNESS_EMAIL_SEND_ENABLED=true`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
  `SMTP_PASSWORD`, `SMTP_SENDER_EMAIL` 또는 `BREVO_SENDER_EMAIL`, and `TEST_RECIPIENT_EMAIL`.
- Secret values must be redacted from logs, reports, audit detail JSON, and provider evidence.
- Current PoC delivery targets `TEST_RECIPIENT_EMAIL` only; customer recipient persistence remains a
  future schema migration.

## SMTP Setup
- `HARNESS_EMAIL_SEND_ENABLED=true` is required before any provider call.
- TLS/STARTTLS is mandatory.
- SMTP success evidence must use real sandbox/live SMTP credentials. Missing credentials produce an
  honest `503 BLOCKED_WITH_REDACTED_REASON`; do not replace this with a local simulator.
- Future async library candidate: aiosmtplib. Adding it to dependencies requires ADR-003 update.

## Authority Model
| action | allowed role | required state | notes |
|---|---|---|---|
| create draft | PB/WM in row scope | customer/consultation visible to requester | stores DRAFT only; no SMTP side effect |
| approve draft | PB/WM in row scope | PII filter passed | approval state may be written by an external/back-office workflow |
| send draft | PB/WM in row scope | `email_drafts.status_code='APPROVED'` and SMTP enabled | 실제 발송 성공 후에만 audit log append; 본 PoC sandbox 경로는 `email_sent_via_sandbox`, `email_draft_send` 는 real-SMTP 전송 성공 예약(미emit) — ADR-002 §Amendment |
| operate SMTP config | ADMIN | system configuration only | does not grant front-office send authority |
| audit email send | AUDIT_VIEWER | read-only audit access | no mutation authority |

ADMIN system authority is not PB/WM customer communication authority. Any staff-delegate exception
requires a separate business decision, API contract update, and tests.

## Current Draft Schema
`POST /email-drafts` request fields:

| field | rule |
|---|---|
| customer_id | UUID; optional when `consultation_id` is supplied; requester must pass row-scope |
| consultation_id | UUID; optional only when draft is customer-bound rather than consultation-bound |
| subject | non-empty display-safe text |
| body | non-empty display-safe text with no account numbers, resident registration numbers, bearer tokens, raw prompts, or secrets |

Response: `draft_id`, `status_code`, `ai_output_id` (currently null for staff-authored drafts),
`created_at`, customer/consultation ids, and `sent_at`.

## Current Send Flow
1. `POST /email-drafts/{draft_id}/send` loads `email_drafts` using raw SQL with SQL_ID-protected repository queries.
2. Role and row-scope checks prove PB/WM authority for the customer/consultation.
3. `status_code='APPROVED'` is required; `DRAFT`, `SENT`, and `CANCELLED` cannot be sent.
4. PII and secret filters run immediately before SMTP send.
5. SMTP send uses TLS/STARTTLS and records sanitized provider metadata only.
6. Success updates `status_code='SENT'`, sets `sent_at`, and appends `audit_logs.action_code`. 현행 PoC는 mailpit sandbox 전용(ADR-002 real-SMTP 금지)이라 `email_sent_via_sandbox` 를 append하며, `email_draft_send` 는 real-SMTP 전송 성공 시 emit하도록 예약된 코드다.
7. Provider-disabled or provider-failure paths leave draft status unchanged and return/log redacted operational errors.

## PII Rule
- 이메일 본문에 계좌번호, 주민등록번호, raw prompt text, provider secrets, bearer tokens, SMTP credentials 포함 금지.
- audit_logs.detail_json에는 recipient raw PII or SMTP provider body를 저장하지 않는다.
- Recipient persistence, approval metadata (`approved_by_id`, `approved_at`), and provider message-id
  hashes require a future raw-SQL migration before they can become part of the stored contract.
