# Model Card — consultation_briefing

| Field | Value |
|---|---|
| **Agent ID** | `consultation_briefing` |
| **Endpoint** | `POST /consultations/{id}/briefing-job` (async 202) |
| **Model** | Azure GPT-5-mini (configurable via `AZURE_OPENAI_DEPLOYMENT_NAME`) |
| **Wave Introduced** | Wave 2 |
| **Last Hardened** | Wave 3 (W3-T6: dual-LLM quarantine, LLM07 redactor, token ceiling) |

---

## Purpose
Generates a pre-consultation briefing document for PB/WM staff preparing for a customer meeting.
Summarises the customer's portfolio status, NBA recommendations, and any relevant aftercare items.
Output is **display-only** for the employee — not stored in the customer record without review.

---

## Training Data / Knowledge Source
- **Synthetic data only** (synthetic customer_no, portfolio_id, consultation_id).
- Structured inputs: suitability data, NBA rows, aftercare records from the Harness DB.
- No fine-tuning. Base Azure GPT-5-mini weights.

---

## Dual-LLM Architecture (Wave 3)
- Quarantined lane: any customer-uploaded memo or freeform notes attached to the consultation.
- Privileged lane: structured suitability / NBA / aftercare data from Harness DB views.
- Faithfulness is informational (human review is the gate); auto-approval under PoC_AUTO_APPROVAL
  carries faithfulness score in `four_gates.explanation_duty.score`.

---

## Performance Metrics

| Metric | Threshold | Measurement |
|---|---|---|
| Required fields present | `customer_context_summary`, `risk_notes` (non-empty) | `tests/test_seven_agents_golden.py` |
| PII in output | 0 raw PII items | AI-03 redaction |
| Suitability data present | Required for READY | Suitability gate in consultation pipeline |

---

## Human-in-the-Loop Gate
Briefing is displayed to the PB/WM staff before the consultation. The employee reviews it and may
choose not to use any portion. Not surfaced to the customer directly.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Memo injection (LLM01) | Dual-LLM: memo in quarantined lane only |
| PII leakage (LLM02) | PII regex (AI-03); customer_no allowed, raw identifiers forbidden |
| Suitability data missing (LLM09) | Suitability gate: BLOCKED if data absent |
| System prompt in output (LLM07) | Leakage redactor |
| Unbounded consumption (LLM10) | Token ceiling (RUN-11) |

---

## Ref
ADR-005, REG-04 §3, AI-03, AI-06, OBS-02
