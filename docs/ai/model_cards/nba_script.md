# Model Card — nba_script

| Field | Value |
|---|---|
| **Agent ID** | `nba_script` |
| **Endpoint** | `POST /nba-actions/{id}/script-job` (async 202) |
| **Model** | Azure GPT-5-mini (configurable via `AZURE_OPENAI_DEPLOYMENT_NAME`) |
| **Wave Introduced** | Wave 2 |
| **Last Hardened** | Wave 3 (W3-T6: tool-call solicitation block PI-004, LLM07 redactor, token ceiling) |

---

## Purpose
Generates a structured talking-point script for PB/WM staff to use during a customer product
discussion, based on a Next-Best-Action (NBA) recommendation. Output is **display-only**: staff
uses it as a conversation guide, not a verbatim script.

---

## Training Data / Knowledge Source
- **Synthetic data only** for PoC demo (synthetic product_id, nba_action_id, customer_no).
- Real inputs at inference: product master data, active house_view, customer risk profile (structured).
- No fine-tuning.

---

## Architecture Note
Structured inputs only (product_id, house_view_id, customer_no). No free-form user prose enters
the prompt. PI-004 pattern (tool-call solicitation: "send email to", "execute") is actively blocked
to prevent LLM06 Excessive Agency.

---

## Performance Metrics

| Metric | Threshold | Measurement |
|---|---|---|
| Required fields | `opening`, `key_message`, `product_discussion_angle`, `closing` | `tests/test_seven_agents_golden.py` |
| Tokens ≤ limit | ≤ configured max_tokens | Enforced at call time |
| Tool-call pattern blocked | 100 % of PI-004 matches | Output sanitizer |
| NBA row written | Only when priority_code = HIGH and AI output present | `repositories/nba.py` |

---

## Fail-Closed Conditions
- `priority_code = HIGH` but AI output missing → BLOCKED, NBA row not created.
- PI-004 (tool-call solicitation) in input or output → BLOCKED.

---

## Human-in-the-Loop Gate
Script displayed to PB/WM staff pre-consultation. Staff decides which points to use. Script is
not shown to the customer. No downstream auto-action from script content.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Excessive agency — tool calls (LLM06) | PI-004 pattern blocks; model outputs JSON only, no tool access |
| Misinformation (LLM09) | product_discussion_angle limited to product master data; no free claims |
| System prompt leakage (LLM07) | Leakage redactor |
| Unbounded consumption (LLM10) | Token ceiling per employee per session (RUN-11) |

---

## Ref
REG-04 §3, ADR-005 (PI-004), AI-06, OBS-02
