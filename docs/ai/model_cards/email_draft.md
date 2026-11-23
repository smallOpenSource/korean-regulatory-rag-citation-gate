# Model Card — email_draft

| Field | Value |
|---|---|
| **Agent ID** | `email_draft` |
| **Endpoint** | `POST /email-drafts` (sync, 200 OK) |
| **Model** | Azure GPT-5-mini (configurable via `AZURE_OPENAI_DEPLOYMENT_NAME`) |
| **Wave Introduced** | Wave 2 |
| **Last Hardened** | Wave 3 (W3-T6: dual-LLM quarantine active, LLM07 redactor, token ceiling) |

---

## Purpose
Generates a draft email body for PB/WM staff to send to a customer. The draft is **display-only**:
the employee must explicitly approve and trigger SMTP send (ADR-002 PENDING_APPROVAL state machine).
The agent never sends email autonomously.

---

## Training Data / Knowledge Source
- **Synthetic data only** for testing (synthetic customer/portfolio IDs, `@example.invalid` recipients).
- At inference: structured customer context, NBA output, and optional RAG references.
- No fine-tuning. Base Azure GPT-5-mini weights + privileged system prompt.

---

## Dual-LLM Architecture (Wave 3)
- Quarantined lane processes any uploaded memo or inline context from the request.
- Privileged lane receives structured fields (customer_no, product_id, nba_action_id) + quarantined lane summary.
- Faithfulness threshold is **informational** (logged, not gating) because human approval is the gate.

---

## Performance Metrics

| Metric | Threshold | Measurement |
|---|---|---|
| Draft contains `subject` and `body` fields | 100 % | `tests/test_seven_agents_golden.py` |
| PII regex hits in draft | 0 (주민번호/계좌번호 금지) | AI-03 post-processor |
| Human approval required before send | 100 % | ADR-002 state machine |
| SMTP send only on APPROVED state | 100 % | `apps/api/harness/services/email_delivery.py` |

---

## Fail-Closed Reason Codes
`PROMPT_INJECTION_DETECTED`, `EMPTY_SANITIZED_TEXT`

SMTP failure at send-time → 503 `email_draft_send_blocked` (separate from draft generation).

---

## Human-in-the-Loop Gate
**Mandatory, always.** Draft is returned to the UI in `PENDING_APPROVAL` state. The employee
reads, edits if needed, and clicks "Send" — triggering a separate `POST /email-drafts/{id}/send`.
No pathway exists to send without this explicit approval action.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Indirect injection via customer memo (LLM01) | Dual-LLM quarantine (ADR-005); memo in quarantined lane |
| PII leakage to draft (LLM02) | PII regex post-processor (AI-03); customer_no allowed, raw PII forbidden |
| Excessive agency — auto-send (LLM06) | ADR-002 state machine; send is a separate API call with explicit approval |
| System prompt leakage in draft body (LLM07) | Leakage redactor + marker echo detection |
| Unbounded consumption (LLM10) | Token ceiling; 85 % budget triggers throttle of new draft calls (RUN-11) |

---

## Ref
ADR-002, ADR-005, REG-04 §3, AI-05, AI-06, OBS-02
