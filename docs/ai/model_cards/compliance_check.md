# Model Card — compliance_check

| Field | Value |
|---|---|
| **Agent ID** | `compliance_check` |
| **Endpoint** | `POST /recommendation-simulations` → `gate_detail` (sync, within 4-gate flow) |
| **Model** | **None** — compliance_check is **rule-based only** (no LLM call) |
| **Wave Introduced** | Wave 2 |
| **Last Hardened** | Wave 3 (PoC_AUTO_APPROVAL governance marker; no LLM changes needed) |

---

## Purpose
Evaluates a product recommendation simulation against the 4-gate compliance framework:
suitability, explanation duty, conflict of interest, and KYC/EDD. Returns structured `passed`,
`issues`, and `recommendation` fields. The result gates whether the simulation proceeds.

**This agent performs zero LLM token consumption.** It is deterministic and rule-based.

---

## Training Data / Knowledge Source
Not applicable — no model, no training data. Logic is SQL + Python rules sourced from:
- REG-02 Supervisor Rules
- REG-03 Bank Practice
- Four-gate compliance framework (`apps/api/harness/services/four_gate.py`)

---

## Architecture Note
Structured inputs only (portfolio_id, product_id, customer_no, gate codes). No free-form text
injection vector exists. AI-generated `risk_notes` from other agents may appear as **advisory**
context but do not change the deterministic gate outcome.

PoC_AUTO_APPROVAL: when `governance_marker = 'PoC_AUTO_APPROVAL'` is set, the human reviewer
field is explicitly waived for simulation purposes. Production builds enforce human review
(ADR-004).

---

## Performance Metrics

| Metric | Threshold | Measurement |
|---|---|---|
| Deterministic output | 100 % rule coverage, 0 non-determinism | `tests/test_four_gate_compliance.py` |
| Token consumption | 0 | No Azure calls |
| PoC_AUTO_APPROVAL rows | Counted in SoD evidence pack (Bucket A) | `scripts/generate_sod_evidence_pack.py` |

---

## Human-in-the-Loop Gate
Rule-based gate is the primary decision. Human compliance reviewer required for production
`action_code`s that are not under `PoC_AUTO_APPROVAL` governance marker (ADR-004, ADR-007 Script 3).

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Rule gap / missing scenario | Quarterly rule review against REG-02/REG-03 |
| PoC_AUTO_APPROVAL misuse | governance_marker explicitly audited; `generate_sod_evidence_pack.py` counts Bucket A |
| No LLM-specific risks | Not applicable |

---

## Ref
ADR-004, REG-02, REG-03, AI-06, OBS-02, `scripts/generate_sod_evidence_pack.py`
