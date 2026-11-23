# Model Card — portfolio_analysis

| Field | Value |
|---|---|
| **Agent ID** | `portfolio_analysis` |
| **Endpoint** | `POST /customers/{id}/portfolio-analysis-job` (async 202) |
| **Model** | Azure GPT-5 (configurable via `AZURE_OPENAI_DEPLOYMENT_NAME_LARGE`) |
| **Wave Introduced** | Wave 2 |
| **Last Hardened** | Wave 3 (W3-T6: staleness check on source_as_of, token ceiling, LLM07 redactor) |

---

## Purpose
Produces structured portfolio drift analysis, risk flags, and action suggestions for PB/WM staff.
Inputs are structured market data (BROKER live quotes, KRX official prices, macro indicators) and the
customer's current portfolio positions. Output supports the staff's portfolio review conversation —
it is **decision support, not an order instruction**.

---

## Training Data / Knowledge Source
- **Synthetic data only** for PoC demo (synthetic portfolio_id, synthetic positions).
- Real inputs at inference: BROKER live quote (005930 etc.), KRX official prices, macro indicators
  (ECOS), portfolio valuations from `get_portfolio_valuation_from_bars`.
- No fine-tuning.

---

## Architecture Note
Structured market/portfolio data only — no free-form user text enters the prompt. Source
staleness is checked before generation: if `source_as_of` is stale or `valuation_source =
PROVIDER_BLOCKED`, the job fails closed with `fail_closed_reason_code=SOURCE_MISMATCH`.

Budget throttle: at 85 % monthly token budget, new portfolio_analysis jobs are rejected
(`consumption_block_reason=BUDGET_85PCT`) to preserve capacity for real-time agents (RUN-11).

---

## Performance Metrics

| Metric | Threshold | Measurement |
|---|---|---|
| Required fields | `summary`, `drift_analysis`, `risk_flags`, `action_suggestions` | `tests/test_seven_agents_golden.py` |
| Numeric values match DB | 100 % (valuation_source verified) | Schema regression |
| source_as_of staleness | Fail-closed if stale | `services/readiness.py` staleness check |
| Budget throttle active at 85 % | New jobs rejected | `apps/api/harness/api/routers/ai.py` |

---

## Fail-Closed Conditions
- `source_as_of` stale → BLOCKED.
- `valuation_source = PROVIDER_BLOCKED` → BLOCKED.
- Monthly token budget ≥ 85 % → new jobs rejected (not BLOCKED — 429 Too Many Requests).

---

## Human-in-the-Loop Gate
Analysis output is displayed in the portfolio review screen. PB/WM staff interprets and decides
which recommendations to act on. The `action_suggestions` field is advisory — no automated
order placement.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Stale market data (misinformation) (LLM09) | source_as_of staleness gate; PROVIDER_BLOCKED check |
| Excessive consumption (LLM10) | 85 % budget throttle; GPT-5 large model cost tracked separately |
| System prompt leakage (LLM07) | Leakage redactor active |
| No injection vector | Structured data only; no free-form user text in prompt |

---

## Ref
REG-04 §3, RUN-11, AI-06, OBS-02, `services/readiness.py`
