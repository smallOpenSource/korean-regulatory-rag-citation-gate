# Model Card — house_view_generation

| Field | Value |
|---|---|
| **Agent ID** | `house_view_generation` |
| **Endpoint** | `POST /house-views/{id}/generate` (async 202) |
| **Model** | Azure GPT-5 (configurable via `AZURE_OPENAI_DEPLOYMENT_NAME_LARGE`) |
| **Wave Introduced** | Wave 2 |
| **Last Hardened** | Wave 3 (W3-T6: spotlighting on external research, LLM07 redactor, token ceiling) |

---

## Purpose
Generates structured house-view documents (asset class views, model portfolios) from real provider
data (DART filings, REG_PAGE, RESEARCH reports). Output populates the `house_views` and
`asset_views` tables, consumed downstream by NBA and consultation briefing agents.

---

## Training Data / Knowledge Source
- **Synthetic data only** for PoC demo fixtures (`tests/goldens/agents/house_view_generation.json`).
- Real inputs at inference: DART receipt_no, REG_PAGE URLs, approved RESEARCH chunk IDs from the
  RAG corpus. No raw customer PII.
- No fine-tuning.

---

## Architecture Note
Does **not** use the dual-LLM quarantine (ADR-005) at Stage 0.5 scope — external research inputs
use spotlighting markers only. Dual-LLM is scheduled for Stage 5 (T265).
Output sanitizer and leakage redactor are active.

---

## Performance Metrics

| Metric | Threshold | Measurement |
|---|---|---|
| JSON schema: required keys present | `asset_views`, `model_portfolios`, `generated_at`, `model` | `tests/test_seven_agents_golden.py` |
| Citation per asset_view item | ≥ 1 DART receipt_no or REG_PAGE URL | Schema regression |
| Key stability (golden snapshot) | ≥ 0.9 overlap on asset_view keys | REG-04 §3 T261 |
| Injection patterns detected | 0 in output (PI-001~PI-006) | Output sanitizer |

---

## Fail-Closed Conditions
- Cited chunk count = 0 → BLOCKED + audit.
- JSON schema violation → BLOCKED.
- Multiple high-severity injection patterns in research input → BLOCKED.

---

## Human-in-the-Loop Gate
House views are reviewed by the research/strategy team before activation in the UI. The
`house_views.status` column transitions: `DRAFT` → `UNDER_REVIEW` → `ACTIVE`. NBA and
consultation agents consume only `ACTIVE` views.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Injection via research document (LLM01) | Spotlighting markers on all external research; PI pattern scan |
| Misinformation (LLM09) | Extractive only; each asset_view item requires citation or "내부 합성 가정" marker |
| System prompt leakage (LLM07) | Leakage redactor active |
| Unbounded consumption (LLM10) | Token ceiling; GPT-5 large model has higher per-call cost, tracked separately |

---

## Ref
REG-04 §3, ADR-005 (spotlighting portions), AI-04, AI-06, OBS-02
