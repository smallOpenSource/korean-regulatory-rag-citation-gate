# AI-04 RAG Specification

## Document Sources
| source_type_code | 내용 | 갱신 주기 | Stage 4 rule |
|---|---|---|---|
| DART | OpenDART filing list plus `document.xml` original report body | 매일/허용된 polling window | receipt_no, corp_code, canonical non-secret URL, content_hash, parser_version required |
| REG_PAGE | 금감원·금투협 규정 페이지 | 주간 | source URL and published_at required before citation |
| RESEARCH | 증권사 리서치 리포트 | 수동 업로드/라이선스 승인 후 | license/display constraints required |
| MANUAL | 내부 운영 매뉴얼 | 수동 업로드 | internal synthetic guidance only; not provider evidence |
| WEB_SEARCH | 뉴스·공시 원문 | 라이선스 승인 후 | no full body storage without approved license |

## OpenDART Ingestion
- The DART collector first reads real filing-list rows, then downloads the matching OpenDART `document.xml` body for each `rcept_no`.
- Persisted canonical URLs must omit `crtfc_key` and any other secret-bearing query parameter.
- `document_sources` records provider, source_document_id/receipt_no, corp_code, canonical_url, published_at, content_hash, parser_version, and sanitized source payload metadata.
- DART XML is parsed with `parser_version=dart-xml-v1`; transformed chunks carry provider_code, corp_code, receipt_no, source_url, published_at, section_path, parser_version, and prompt-quarantine metadata.

## Chunking Rules
- 청크 크기: 512 tokens (overlap: 64 tokens).
- DART XML is normalized by section path before chunking; malformed XML falls back to sanitized raw text only when enough content remains.
- Retrieved provider text is untrusted. Prompt-like instructions such as policy override requests, system-prompt references, or “ignore previous instructions” are quarantined before indexing/answering.
- 임베딩 제공자: 내부 BGE API only. No placeholder vectors are permitted.
- 임베딩 차원: `BGE_EMBEDDING_DIMENSIONS` 값과 DB `vector(N)`이 반드시 일치해야 한다.

## Retrieval
- Current runtime gate uses embedded chunks plus SQL_ID-protected metadata filters: `source_type_code`, `corp_code`, `receipt_no`, `provider_code`, and published date range.
- Internal BGE embedding refresh validates vector count and dimensions before marking chunks embedded.
- Internal BGE rerank calls must go through configured internal API credentials and validate returned item indexes/scores before use.

## Citation and Evidence Rule
- `/rag/query` returns `READY` only when at least one embedded approved chunk can be cited.
- No cited chunk, source mismatch, empty sanitized text, or unsupported filters produce `BLOCKED`; the endpoint still persists a redacted AI output/audit row.
- Every `READY` response writes `ai_outputs.citations_json` and one `rag_answer_evidence` row per cited chunk with quote span, retrieval score, confidence, and source_document_id.
- AI output remains decision support: answers are extractive, caveated, and limited to cited chunks.

## Wave 3 Hardening (W3-T6 / 2026-05-17)

### Dual-LLM Azure Full Path Active (ADR-005)
`rag_qa`, `email_draft`, and `consultation_briefing` now run the full two-lane Azure call pattern:
- **Privileged lane**: structured inputs + tool access → Azure GPT-5-mini call 1.
- **Quarantined lane**: untrusted provider text / customer memo → Azure GPT-5-mini call 2 (no tool access).
- Both calls count against the per-agent token budget (RUN-11 §3.7).
- Spotlighting markers `<RETRIEVED_CONTEXT chunk_id="…" quarantine_flag="…">` wrap all retrieved chunks in the privileged lane prompt.
- Quarantined lane output schema: `{summary: str, extracted_claims: list[str], confidence: float}`.

### Azure Content Safety Toggle (default OFF)
An optional Prompt Shields hook (`AZURE_CONTENT_SAFETY_ENABLED=true`) can be inserted before the
privileged-lane call. Default is OFF for PoC; ON is recommended for production. When enabled:
- User Prompt Attack and Document Attack checks run against the full question + retrieved context.
- A `PROMPT_INJECTION_DETECTED` fail-closed is issued if Prompt Shields returns `attackDetected=true`.
- The toggle is controlled via `AZURE_CONTENT_SAFETY_ENABLED` env var (ADR-003 pre-approved dependency).

### LLM07 System-Prompt Leakage Redactor
A post-generation sanitizer checks the model response for system-prompt echo:
- Jaccard token overlap between response and system prompt ≥ `AI_LEAKAGE_JACCARD_MIN` (default 0.6)
  triggers `LLM07_LEAKAGE_REDACTED` audit + response redaction.
- Spotlight marker echo detection: any `<USER_DATA>`, `<RETRIEVED_CONTEXT>`, or `<SYSTEM>` tag
  appearing in model output triggers `PROMPT_INJECTION_DETECTED` fail-closed.
- Both checks apply to all three dual-LLM agents.

### LLM10 Per-Employee Token Ceiling
- A per-employee, per-session AI call ceiling is enforced at the router layer.
- Env var `AI_EMPLOYEE_CALL_CEILING_PER_HOUR` (default: 60 calls/hour).
- Reaching the ceiling returns HTTP 429 with `Retry-After` header; no Azure call is made.
- The rejection is logged with `action_code=AI_CALL_EMPLOYEE_THROTTLED`.

### §3.7 Token Budget Meter Wiring
- Every Azure call writes `audit_logs.detail_json.token_consumption` with per-call and cumulative
  monthly counters (see RUN-11 §4 Audit Ledger).
- Three escalating thresholds: 70 % warning, 85 % partial throttle (portfolio_analysis + email_draft),
  100 % hard abort (all AI calls blocked).
- Monthly cap: 560,000 input tokens + 112,000 output tokens (RUN-11 §3.7 derivation).
