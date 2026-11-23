# AI-06 NIST AI RMF / GAI Profile Mapping

## Metadata
- **Framework**: NIST AI 600-1 Generative AI Profile (July 2024) + NIST AI RMF 1.0 (January 2023)
- **Scope**: 7 Harness AI agents (house_view_generation, consultation_briefing, nba_script, email_draft, rag_qa, compliance_check, portfolio_analysis)
- **Authored**: 2026-05-17 (Wave 3, W3-T8)
- **Source-of-truth**: REG-04 §2 framework matrix, ADR-005, ADR-007

---

## 1. GOVERN Function

| Control ID | Control Summary | Harness Implementation | Evidence Path |
|---|---|---|---|
| GV-1.1 | Policies for trustworthy AI established and documented | REG-04 AI Governance doc + ADR-001~007 architecture contracts; 금융 AI 7대 원칙 self-assessment report | `docs/regulations/REG-04_ai_governance.md` |
| GV-1.2 | Accountability structure for AI risk defined | Each agent has an audit trail: action_code STARTED→SUCCEEDED/FAILED pair; human reviewer field in audit_logs | `apps/api/harness/core/audit.py` |
| GV-1.3 | Organisational risk tolerance for AI documented | PoC scope declared as "내부 직원용·합성 데이터 기반·결정 지원" (REG-04 §2); non-high-risk EU AI Act category | `docs/regulations/REG-04_ai_governance.md §2` |
| GV-2.1 | AI risk management integrated into enterprise risk | ADR-003 Dependency Change Gate gates new AI library adoption; ADR-007 Validator Contracts gate acceptance evidence | `docs/architecture/ADR-003_dependency_change_gate.md` |
| GV-2.2 | AI risk management processes documented | REG-04 §3 per-agent checklist; REG-04 §3-bis cross-cutting controls | `docs/regulations/REG-04_ai_governance.md §3` |
| GV-3.1 | Roles and responsibilities for AI risk defined | Operator roles in SEC-01 Auth Spec; `harness_pb`, `harness_admin`, `harness_batch` role separation | `docs/security/SEC-01_auth_spec.md` |

---

## 2. MAP Function

| Control ID | Control Summary | Harness Implementation | Evidence Path |
|---|---|---|---|
| MP-1.1 | Context for AI deployment established | PoC context: internet-network deployment, Azure GPT-5/mini, synthetic customer/portfolio data, real provider data (DART/KRX) | `docs/regulations/REG-06_simulation_governance.md` |
| MP-1.5 | Organizational risk exposure from AI assessed | REG-04 §3 per-agent risk register: prompt injection, citation failure, excessive agency, overreliance | `docs/regulations/REG-04_ai_governance.md §3` |
| MP-2.1 | Scientific and technical knowledge underlying AI risks understood | OWASP LLM Top 10 2025 applied per agent (LLM01–LLM10); ADR-005 dual-LLM quarantine implements OWASP PIC Cheat Sheet | `docs/architecture/ADR-005_dual_llm_quarantine.md` |
| MP-2.3 | AI system categorized for risk level | 7 agents categorised by output type and human-in-the-loop gate: display-only draft (email_draft), rule-gated (compliance_check), async (portfolio_analysis) | `docs/ai/AI-05_async_endpoint_matrix.md` |
| MP-3.5 | Impacts of AI on individuals and society assessed | "보조수단성" principle: AI output is decision support, not authority; UI badge required on all AI-generated content | `docs/regulations/REG-04_ai_governance.md §3-bis` |
| MP-4.1 | Risks associated with AI system deployment documented | REG-04 §4 (RAG governance), ADR-005 §5 fail_closed_reason_code enum; audit row persisted even for blocked responses | `docs/architecture/ADR-005_dual_llm_quarantine.md §5` |
| MP-5.1 | Likelihood and magnitude of AI risks estimated | fail-closed rates tracked in `ai_outputs.fail_closed_reason_code`; per-principle scores in `generate_seven_principles_report.py` | `scripts/generate_seven_principles_report.py` |

---

## 3. MEASURE Function

| Control ID | Control Summary | Harness Implementation | Evidence Path |
|---|---|---|---|
| MS-1.1 | AI risk measurement approach established | Faithfulness ≥ 0.7 gate (ADR-005 §4) — source: tests/test_rag_golden.py (verified_at=2026-05-19, rag-golden-01..07 all PASS, faithfulness_score ≥ 0.7 enforced via DeepEval FaithfulnessMetric or token-overlap fallback); determinism: golden snapshot JSON-schema regression; fail-closed rate per agent | `tests/test_rag_golden.py`, `tests/test_seven_agents_golden.py` |
| MS-2.1 | AI system tested before deployment | pytest suite 200+ tests; golden snapshot 10 RAG Q&A + 7 agent schema goldens; adversarial 3-scenario suite | `tests/test_rag_adversarial.py`, `tests/test_module_split_compat.py` |
| MS-2.5 | AI system robustness tested adversarially | 3 adversarial RAG scenarios: spotlight-marker injection, system-prompt extraction, quarantined-chunk retrieval | `tests/test_rag_adversarial.py` |
| MS-2.6 | Data quality for AI assessed | Document chunks: content_hash verification, embedding dim validation, quarantine flag scoring at index time | `apps/api/harness/batch/providers/` |
| MS-2.7 | AI system performance metrics established | Per-agent golden snapshot stability ≥ 0.9 — source: tests/test_rag_golden.py (verified_at=2026-05-19, 11/15 rag tests PASS including golden 7-fixture suite); faithfulness ≥ 0.7 — source: tests/test_rag_golden.py (rag-golden-01..07 PASS); token consumption tracked per window | `docs/runbooks/RUN-11_token_budget.md` |
| MS-3.3 | AI risk incidents monitored | `audit_logs` append-only (ADR-006); STARTED→SUCCEEDED/FAILED pair per AI call; OBS-02 canonical action codes | `docs/observability/OBS-02_audit_action_codes.md` |
| MS-4.1 | Risk response actions measured for effectiveness | `generate_seven_principles_report.py` scores 7 principles × 7 agents; ADR-007 acceptance window gates | `scripts/generate_seven_principles_report.py` |

---

## 4. MANAGE Function

| Control ID | Control Summary | Harness Implementation | Evidence Path |
|---|---|---|---|
| MG-1.1 | Risks prioritized and treated | REG-04 §3 priority order: LLM01 (Prompt Injection) → LLM07 (Leakage) → LLM10 (Consumption) → LLM09 (Overreliance) | `docs/regulations/REG-04_ai_governance.md §3-bis` |
| MG-2.2 | AI risks responded to with appropriate controls | fail-closed contract: BLOCKED + redacted `ai_outputs` + `audit_logs` row for every rejected AI call | `apps/api/harness/api/routers/ai.py` |
| MG-2.4 | Human oversight mechanisms implemented | Human-in-the-loop gates: email_draft (PENDING_APPROVAL state, ADR-002); compliance_check (rule-based 1st, AI 2nd) | `docs/architecture/ADR-002_email_authority_and_schema_contract.md` |
| MG-3.1 | AI risk monitoring plans established | External dependency attestation script: 5 deps × acceptance window; token budget cap (RUN-11) | `scripts/external_dependency_attestation.py`, `docs/runbooks/RUN-11_token_budget.md` |
| MG-4.1 | AI risk management residual risks documented | PoC_AUTO_APPROVAL: declared governance_marker; production builds dead-code-eliminate the handler | `docs/architecture/ADR-004_poc_auto_approval_attestation.md` |

---

## 5. 12 GAI Risk Categories × 7 Agents Matrix

| GAI Risk | rag_qa | email_draft | consultation_briefing | house_view_generation | nba_script | compliance_check | portfolio_analysis |
|---|---|---|---|---|---|---|---|
| **Confabulation** | Faithfulness ≥ 0.7 gate; NO_CITATION → BLOCKED | Informational faithfulness score; human approval required | Informational faithfulness; suitability data citation required | Citation per asset_view item; extractive only | product_id citation; no free-form claims | Rule-based 1st; AI risk_notes only | valuation_source citation; DB values verified |
| **Data Privacy** | PII regex post-processor; customer_no only in context | PII regex; AI-03 §Injection; recipient synthetic only | AI-03 PII anonymisation in customer context | No direct PII; portfolio_id reference only | No PII in gate inputs | No PII in compliance payload | portfolio_id reference; no raw PII |
| **Harmful Bias** | Retrieval filter: SQL_ID only; no free user-input filters | Draft only; display-only with human gate | Suitability data is structured; AI adds risk_notes | market data only; no demographic inputs | product master data only | Rule-based; no demographic weighting | Structured portfolio data; no demographic factors |
| **Human-AI Configuration** | UI badge + caveat; 👍/👎 feedback loop | PENDING_APPROVAL state; employee explicit send action | Display-only briefing; employee confirms before consultation | READY/BLOCKED badge; reviewer must verify before use | PoC_AUTO_APPROVAL explicit governance marker | Deterministic rules visible; AI notes advisory only | ASYNC 202; employee reviews before recommendation |
| **Information Integrity** | extractive answers; quote span stored | Draft text only; AI cannot send without employee action | Summary + risk_notes; not authoritative | AI badge + generated_at timestamp | Structured script; not authoritative financial advice | Rule outcome deterministic; AI supplements only | Drift analysis + risk_flags; source_as_of staleness check |
| **Information Security** | PROMPT_INJECTION_DETECTED fail-closed; quarantine flag | Spotlight markers; ADR-002 redaction; SMTP PENDING_APPROVAL | Dual-LLM quarantine; customer memo in quarantined lane | Spotlighting on external research inputs | Tool-call solicitation pattern blocked (PI-004) | Structured inputs only; no free text injection vector | Structured market data; no free-form user input |
| **Intellectual Property** | provider license tracked per source_type | Draft only; no auto-send prevents unauthorized distribution | Internal briefing; not redistributed | Source attribution per asset_view | Product master data; licensed by harness | Internal compliance check; not public | Portfolio data; internal use only |
| **Obscene/Abusive Content** | Output sanitizer (HTML/JS strip); content filter option | Azure Content Safety toggle (default OFF, ADR-006 §3) | Same as email_draft | Same sanitizer applied | Structured output; minimal free text | No free text output | Structured JSON; minimal free text |
| **Operational Resilience** | fail-closed: service unavailable → BLOCKED not READY | PENDING_APPROVAL preserves audit trail even if SMTP down | DB fallback; suitability data gate required | House-view pipeline: async 202 with status polling | NBA row not written on AI failure | Rule gate always runs; AI gate is additive | Async job with STARTED/FAILED pair |
| **Sociotechnical Harms** | "보조수단성": answers support employee, not customer direct | "직원이 최종 책임" policy page required | "AI는 결정 지원" caveat in UI | AI badge + disclaimer | Script is a talking point, not a binding recommendation | Human reviewer required for gate outcome | Analysis supports, not directs, recommendation |
| **Value Chain / Third-Party** | BGE internal API (no public embedding provider) | Azure GPT-5/mini; ADR-003 dependency gate for new libs | Same Azure; ADR-003 gate | Same Azure; DART/REG_PAGE/RESEARCH licensed providers | Same Azure + product master | Rule-based; no third-party AI for gate decision | Azure + BROKER/KRX licensed market data |
| **Unbounded Consumption** | Per-employee AI call ceiling; faithfulness judge count against budget | Token ceiling; PENDING_APPROVAL prevents runaway drafts | Dual-LLM doubles token count; tracked in attestation script | Async 202 with per-job token tracking | Token ceiling per employee per session | No LLM token consumption (rule-based) | Async job; token ceiling enforced in job runner |

---

## 6. Threshold Reference

| Metric | Value | Config Env Var | Source | Measurement Status |
|---|---|---|---|---|
| Faithfulness minimum (rag_qa READY gate) | ≥ 0.7 | `AI_FAITHFULNESS_MIN` | ADR-005 §4, REG-04 §4.1 | source: tests/test_rag_golden.py (verified_at=2026-05-19, test_rag_happy_path_golden parametrized rag-golden-01..07 all PASS — faithfulness_score ≥ 0.7 assertion using DeepEval FaithfulnessMetric or token-overlap fallback per services/ai/faithfulness.py; sample_n=7 golden fixtures) |
| Monthly token ceiling (Azure, all agents) | 560,000 input + 112,000 output | `AZURE_TOKEN_CEILING_MONTHLY` | RUN-11 §3.7 | [PENDING_MEASUREMENT:owner=ai-eng,deadline=2026-06-15,evidence_anchor=scripts/external_dependency_attestation.py] |
| Per-window token ceiling (attestation script) | 100,000 input + 20,000 output | `AZURE_TOKEN_CEILING_PER_WINDOW` | ADR-007 §1 | source: scripts/external_dependency_attestation.py (verified_at=2026-05-19T01:54:15Z, env_profile=poc, sample_window_in=204, sample_window_out=276, ceiling_in=100000, ceiling_out=20000, headroom_in_pct=99.79, evidence=`.omx/reports/verification/attest-azure-20260519T015432Z.json`) |
| Quarantine score threshold (high-severity) | ≥ 0.9 → quarantine_flag=true | `AI_QUARANTINE_SCORE_MIN` | ADR-005 §3 | source: tests/test_rag_adversarial.py (verified_at=2026-05-19, scenario_a + scenario_b + blocked_ai_outputs PASS — prompt injection via USER_DATA blocked, system-prompt extraction blocked, fail-closed ai_outputs row persisted) |
| System-prompt leakage Jaccard threshold | ≥ 0.6 → LLM07_LEAKAGE_REDACTED | `AI_LEAKAGE_JACCARD_MIN` | ADR-005 §6 | source: tests/test_rag_adversarial.py (verified_at=2026-05-19, scenario_b_system_prompt_extraction_attempt_is_blocked PASS — Jaccard threshold enforced via redact_llm_output in services/ai/llm_redactor.py) |
| Golden snapshot stability | ≥ 0.9 key overlap | N/A (test assertion) | REG-04 §3, T261 | source: tests/test_rag_golden.py (verified_at=2026-05-19, rag-golden-01..07 schema regression PASS — answer_keys overlap ≥ 0.9 asserted per fixture) |

---

## 7. Cross-References
- **REG-04 AI/RAG Governance** — primary source for per-agent controls
- **ADR-005 Dual-LLM Quarantine** — mechanizes LLM01/07/08 OWASP controls
- **ADR-006 Audit Append-Only** — mechanizes MS-3.3 (incident monitoring)
- **ADR-007 Validator Contracts** — mechanizes MP-5.1, MS-4.1 measurement
- **OBS-02 Audit Action Codes** — canonical action_code taxonomy
- **RUN-11 Token Budget** — MG-3.1 monitoring plan for LLM10
