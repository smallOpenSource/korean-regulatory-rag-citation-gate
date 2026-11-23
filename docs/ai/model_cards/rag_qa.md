# Model Card — rag_qa

| Field | Value |
|---|---|
| **Agent ID** | `rag_qa` |
| **Endpoint** | `POST /rag/query` (sync, 200 OK) |
| **Model** | Azure GPT-5-mini (configurable via `AZURE_OPENAI_DEPLOYMENT_NAME`) |
| **Embedding** | Internal BGE API (`BGE_EMBEDDING_DIMENSIONS` must match DB `vector(N)`) |
| **Wave Introduced** | Wave 2 |
| **Last Hardened** | Wave 3 (W3-T6: dual-LLM full path, LLM07 leakage redactor, LLM10 token ceiling) |

---

## Purpose
Retrieval-Augmented Generation Q&A for PB/WM staff. Accepts a natural-language question, retrieves
relevant approved document chunks from the corpus, generates a grounded answer, and returns
citations. Output is **decision support only** — not authoritative financial advice.

---

## Training Data / Knowledge Source
- **Synthetic data only** for testing and PoC demo (no real customer PII).
- Real provider corpora at inference time: DART filings, REG_PAGE regulations, RESEARCH reports,
  MANUAL internal documents, WEB_SEARCH approved news.
- No fine-tuning performed. Base Azure GPT-5-mini weights + system prompt + retrieved context.

---

## Dual-LLM Architecture (Wave 3)
Implements ADR-005 dual-LLM quarantine pattern:
- **Privileged lane**: structured inputs only; tool access; emits `READY` or `BLOCKED` JSON.
- **Quarantined lane**: untrusted provider text; no tool access; outputs `{summary, extracted_claims[], confidence}`.
- Spotlighting markers `<RETRIEVED_CONTEXT chunk_id="…" quarantine_flag="…">` wrap all retrieved chunks.

---

## Performance Metrics

| Metric | Threshold | Measurement |
|---|---|---|
| Faithfulness (token-overlap fallback) | ≥ 0.7 | `rag_answer_evidence.faithfulness_score` |
| Citation presence (READY gate) | ≥ 1 cited chunk | `ai_outputs.citations_json` |
| Fail-closed rate (adversarial) | 100 % of injection attempts blocked | `tests/test_rag_adversarial.py` |
| Golden regression stability | 7/7 happy-path goldens READY | `tests/test_rag_golden.py` |
| p95 latency (target) | ≤ 5 s | Monitored via `audit_logs` timestamps |

---

## Fail-Closed Reason Codes

`NO_CITATION`, `SOURCE_MISMATCH`, `EMPTY_SANITIZED_TEXT`, `UNSUPPORTED_FILTER`,
`QUARANTINED_CONTEXT`, `DIMENSION_MISMATCH`, `LOW_FAITHFULNESS`, `PROMPT_INJECTION_DETECTED`

All BLOCKED responses still persist a redacted `ai_outputs` row + `audit_logs` row (ADR-006).

---

## Human-in-the-Loop Gate
Answer is displayed to the PB/WM staff with an AI badge (`AI 생성 · {generated_at} · {model}`).
Staff verifies before acting. No direct customer communication. Staff 👍/👎 feedback stored in
`ai_output_feedback` table.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Prompt injection via retrieved documents (LLM01) | Quarantined lane + spotlighting markers + PI pattern library (ADR-005 §3) |
| System prompt leakage (LLM07) | Jaccard overlap detector; `LLM07_LEAKAGE_REDACTED` audit on violation |
| Hallucination / low faithfulness (LLM09) | Faithfulness ≥ 0.7 gate; BLOCKED on LOW_FAITHFULNESS |
| Embedding dimension mismatch (LLM08) | Pre-flight dim check; BLOCKED on DIMENSION_MISMATCH |
| Unbounded consumption (LLM10) | Per-employee call ceiling; monthly budget cap (RUN-11) |
| Stale corpus (misinformation) | content_hash re-verification on corpus update; source_as_of staleness flag |

---

## Ref
ADR-005, REG-04 §3, AI-04, AI-06 MS-1.1/MS-2.5, OBS-02
