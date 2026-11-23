# REG-04 AI/RAG Governance — 금융권 외부 리서치 보강 (L4)

## 1. Metadata
- 리서치 lane: L4 (AI/RAG 거버넌스 best practice)
- 산출일: 2026-05-17 (Asia/Seoul)
- 산출자: external-research worker (deep-interview-wmah Phase 2)
- 입력 컨텍스트: AI-01~05, PROMPT-01~07, `.omc/specs/deep-interview-wmah.md` Round 3·8·10
- 대상 Harness 구성: B. AI Authoring Suite 7 에이전트 (house_view_generation, consultation_briefing, nba_script, email_draft, rag_qa, compliance_check, portfolio_analysis) + RAG corpus + 2 derived
- 적용 PoC 범위: 인터넷망 PoC, Azure GPT5/mini 실 호출, BGE 임베딩/리랭크 내부 API, 합성 고객/포트폴리오, 실 provider 데이터(DART/REG_PAGE/RESEARCH/MANUAL/WEB_SEARCH)
- 본 문서 갱신 트리거: OWASP LLM Top 10 차기 개정, NIST AI 600-1 후속 가이드, 금융위 통합 AI 가이드라인 정식 시행(2026 1Q 예정), EU AI Act 고위험 의무 발효(2026-08-02), Azure Content Safety 신규 기능

## 2. 거버넌스 프레임워크 매트릭스
| 프레임워크 | 발행기관 | 발행/시행 | 핵심 통제 (PoC 관련) | Harness 영향 |
|---|---|---|---|---|
| OWASP Top 10 for LLM Applications 2025 (v2025) | OWASP Gen AI Security Project | 2024-11 발표, 2025 활성 | LLM01 Prompt Injection, LLM02 Sensitive Info Disclosure, LLM05 Improper Output Handling, LLM06 Excessive Agency, LLM07 System Prompt Leakage, LLM08 Vector & Embedding Weaknesses, LLM09 Misinformation, LLM10 Unbounded Consumption | 모든 7 에이전트 prompt-injection 검역·출력 sanitize·system prompt 유출 차단·RAG 임베딩 오염 차단·max_tokens 상한 enforcement |
| OWASP LLM Prompt Injection Prevention Cheat Sheet | OWASP | 2024 | privileged/quarantined dual-LLM, instruction hierarchy, output filtering, spotlighting | rag_qa·email_draft·compliance_check에 dual-LLM 패턴; 사용자 입력은 system prompt와 분리 marker로 격리 |
| NIST AI RMF 1.0 + Generative AI Profile (NIST AI 600-1) | NIST | 2023-01 (RMF), 2024-07-26 (GAI Profile) | Govern/Map/Measure/Manage 4 functions + 12 GAI 위험 카테고리(confabulation, data privacy, harmful bias, info security, IP, obscene/abusive, value chain, human-AI configuration 등) + 200+ actions | GOVERN: AI 사용 정책·책임자 지정 audit_logs / MAP: 7 에이전트별 risk register / MEASURE: 결정성 테스트·golden snapshot / MANAGE: fail-closed·사용자 평가 루프 |
| EU AI Act (Regulation 2024/1689) | EU Council/Parliament | 2024-08-01 발효, 고위험 의무 2026-08-02 적용 | Annex III 고위험 분류, 기술문서·데이터 거버넌스·human oversight·로깅·robustness·post-market monitoring, GPAI 의무 | PoC scope는 신용평가/employment 직접 사용 없음 → 현재 고위험 미해당. 단 "AI 시스템 생애주기 기술문서" 패턴(provenance, data lineage)·"automatic event recording"은 audit_logs/ai_outputs 설계에 모범 사례로 반영 |
| 금융분야 AI 가이드라인 (통합·개정안) | 금융위·금감원 | 2024-12-12 발표, 2026 1Q 시행 예정 | 금융 AI 7대 원칙: ①거버넌스 ②합법성 ③보조수단성 ④신뢰성 ⑤금융안정성 ⑥신의성실 ⑦보안성 | "보조수단성" → AI 답변은 결정 지원만(extractive·caveated, AI-04와 일치). "거버넌스" → AI 윤리/위원회 audit. "보안성" → prompt injection·데이터 유출 통제 |
| 금융권 생성형 AI 활용 지원방안 | 금융위 | 2024-12-12 | 인터넷망 상용 AI 특례, 내부망 오픈소스 AI, 금융 특화 학습 데이터, 위험 최소화 가이드라인 | 인터넷망 PoC(Round 7)와 정합: "특례" 패턴 = id/password 1-factor 운영 정합 (단 운영 시 추가 게이트 필요는 별도) |
| 금융분야 AI 운영/개발/보안 가이드라인 (기존) | 금융위 | '21.7 / '22.8 / '23.4 | 데이터 품질, 설명가능성, 차별 방지, 보안 위험 평가 | 통합 가이드라인 시행 전까지 baseline. PoC 보고서·설명 의무 디자인에 활용 |
| 인공지능기본법 (제정) | 국회·과기부 | 2025 제정 (시행 후속) | 고영향 AI 사업자 의무, 사후 모니터링 | 통합 AI 가이드라인 입법 근거. PoC 단계서 high-impact 범위에 들지 않도록 "내부 직원용·합성 데이터 기반·결정 지원" 명시 |
| Azure AI Content Safety (Prompt Shields + Groundedness + Protected Material) | Microsoft | GA 2024~2025 | User Prompt Attack & Document Attack 감지, Groundedness Detection, Protected Material Detection, harmful content filters | Azure GPT5/mini 호출 전후에 Prompt Shields 적용 검토; rag_qa 응답에 Groundedness Detection 옵션 검토 |
| Microsoft Responsible AI Standard v2 | Microsoft | 2022 → 2024 보강 | Accountability, Transparency, Fairness, Reliability & Safety, Privacy & Security, Inclusiveness | "AI 생성 · {generated_at} · {model}" 배지(transparency)와 "보조수단성"(accountability) 정합 |
| Microsoft Defender for Cloud — AI Workload Threat Protection | Microsoft | 2025 GA | AI alerts (jailbreak, prompt injection, data exfiltration), AI Security Posture Management, Defender XDR 통합 | 운영 보강 후보. PoC에서는 alert hook 위치(엔드포인트별 audit_logs)만 식별 |

## 3. 7 에이전트별 거버넌스 체크리스트
| 에이전트 | prompt-injection 게이트 | citation 정합성 | 결정성 평가 | fail-closed 사유 | audit |
|---|---|---|---|---|---|
| house_view_generation | 외부 리서치/뉴스 입력에 spotlighting 마커; "ignore previous"·system-prompt 참조·정책 우회 패턴 검역 (LLM01) | 출처: DART receipt_no + REG_PAGE URL; asset_views/model_portfolios 각 항목은 citation 또는 "내부 합성 가정" 명시 (LLM09) | golden snapshot: 동일 입력 → JSON schema 100% 일치 + asset_view 핵심 키 stability ≥ 0.9 | 인용 chunk 0개, JSON schema 위반, prompt-injection 패턴 다중 검출 → BLOCKED + audit | action_code=AI_CALL_STARTED/SUCCEEDED/FAILED + house_view_id, model_name, generated_at |
| consultation_briefing | customer PII 익명화(AI-03 §Injection); 외부 메모 첨부 시 quarantined LLM로 1차 처리 | portfolio·NBA·aftercare 데이터 referent_id citation 필수; AI 자유서술은 caveat 필수 | golden snapshot: customer_context_summary 핵심 5 필드 존재 + risk_notes 비어있지 않음 | suitability 데이터 결손 또는 prompt-injection 검역 → BLOCKED, derived NBA에 AI 텍스트 미저장 | action_code 동일 + consultation_id |
| nba_script | 상품·고객 코드 외 자유 텍스트 제한; "send email to" 등 도구 호출 유도 패턴 차단 (LLM06 Excessive Agency) | product_id·house_view_id citation; product_discussion_angle은 product 마스터 데이터에 한정 | golden snapshot: opening/key_message/product_discussion_angle/closing 4 필드 존재; tokens ≤ 한도 | priority_code = HIGH인데 AI 출력 누락 → BLOCKED, nba 행 미생성 | action_code 동일 + nba_action_id |
| email_draft | 수신 메일·웹 URL inline 컨텍스트 금지; AI는 본문 제안만, 발송은 직원 명시 승인 후 SMTP green-path | 인용 필요 시 RAG_QA 결과 참조 ID; 첨부 자료 제목 + canonical URL 표기 | subject·body 두 필드 존재; PII regex 0건 | SMTP 미가용 또는 BLOCKED 정책 위반 단어 → 503 BLOCKED + audit `email_draft_send_blocked` | sync draft 작성은 미감사(AI-05), 발송 성공 시 `email_sent_via_sandbox` (본 PoC sandbox 전용 — ADR-002 §Amendment; `email_draft_send` 는 real-SMTP 예약/미emit) |
| rag_qa | retrieve된 untrusted provider 텍스트는 chunk 단위 quarantine 메타데이터; "system prompt"·"override" 패턴 (Round 3 결정) | AI-04 강제: cited chunk 없으면 BLOCKED; `rag_answer_evidence` row 1:1; quote span·retrieval score·confidence 저장 | LLM-as-a-judge faithfulness + groundedness; DeepEval pytest hook(향후); golden Q→A 10건 회귀 | 인용 0 / 임베딩 dim mismatch / BGE 호출 실패 / quarantine flag 다수 → BLOCKED + redacted ai_outputs 행 | action_code 동일 + rag_query_id; citations_json 필수 |
| compliance_check | 4-gate 입력은 구조화 데이터만; 외부 텍스트 유입 차단 | 적합성·설명의무 결과는 결정성 룰(SQL)이 1차, AI는 risk_notes 보조; 인용은 정책 문서 ID | passed/issues/recommendation 결정성 100% (룰 기반) | 룰 실패 → fail-closed 즉시; PoC_AUTO_APPROVAL과 명시 구분 | sync 200, action_code 동일, PoC_AUTO_APPROVAL 별 코드 |
| portfolio_analysis | 시장·평가 데이터 외 자유 텍스트 차단; LLM 호출 입력은 portfolio_id·position 구조화 | drift_analysis·risk_flags 항목별 source_as_of·valuation_source 인용 | summary/drift_analysis/risk_flags/action_suggestions 4 필드; 수치는 DB 값과 일치 검증 | source_as_of stale·valuation_source PROVIDER_BLOCKED → BLOCKED + audit | async 202, action_code 동일 + portfolio_id |

### 3-bis. cross-cutting 통제 (모든 에이전트 공통)
- **System Prompt Leakage (LLM07):** prompts/PROMPT-XX 내 비밀·정책 텍스트는 응답에 echo 금지. 응답 후처리에서 system prompt 토큰 일치율 임계값 초과 시 redact.
- **Unbounded Consumption (LLM10):** max_tokens 상한·in-flight 중복 차단(AI-01) + 사용자별 분당 호출 ceiling.
- **Sensitive Information Disclosure (LLM02):** customer_no는 허용, 주민번호/계좌번호/이름 원문 금지(AI-03). 응답 후처리 PII regex.
- **Excessive Agency (LLM06):** 도구 호출은 코드 측에서만; 모델은 JSON 데이터만 반환. email 발송·주문 시뮬레이션은 별도 승인 게이트.
- **Misinformation/Overreliance (LLM09):** UI 배지 "AI 생성 · {generated_at} · {model}" + caveat 문구. 사용자 평가(👍/👎) 루프 저장.
- **Audit Backbone:** OBS-02 canonical action_code; 모든 AI 호출은 STARTED→(SUCCEEDED|FAILED) pair.

## 4. RAG 거버넌스 (AI-04 보강)
### 4.1 Retrieval Evaluation
- 메트릭: **context relevance**(top-k 중 관련 chunk 비율), **faithfulness/groundedness**(생성된 claim이 cited chunk에 의해 지지되는지), **answer relevance**, **latency p95**.
- 도구 후보: DeepEval (pytest 회귀, 결정성 메트릭 DAG), RAGAS (faithfulness/context_precision/context_recall), TruLens (tracing+eval). PoC는 DeepEval pytest hook 우선.
- 골든 셋: PoC용 Q-A-evidence 트리플 10건(MANUAL·REG_PAGE·DART 균형) → `tests/ai/golden_rag/*.yaml` (T260 시리즈로 추적).

### 4.2 Citation Gating (AI-04 §Citation and Evidence Rule 정밀화)
- **READY 조건:** ≥1 embedded approved chunk + faithfulness 임계값(예: ≥0.7) + chunk quarantine flag 없음 + content_hash 검증 성공.
- **BLOCKED 사유 코드(권장):**
  - `NO_CITATION` (cited chunk 0)
  - `SOURCE_MISMATCH` (source_document_id ≠ retrieval index)
  - `EMPTY_SANITIZED_TEXT`
  - `UNSUPPORTED_FILTER` (SQL_ID 미보호 필터 입력)
  - `QUARANTINED_CONTEXT` (검역 chunk 다수)
  - `DIMENSION_MISMATCH` (BGE vector dim ≠ DB vector(N))
  - `LOW_FAITHFULNESS` (메트릭 임계값 미달)
  - `PROMPT_INJECTION_DETECTED`
- BLOCKED여도 redacted `ai_outputs` + `audit_logs` 행은 항상 persist (감사 흐름 보존).

### 4.3 Quarantine 정책 (Prompt-Injection 검역)
- **인덱싱 단계:** OWASP 패턴(정책 override, system prompt 참조, "ignore previous instructions", base64 인스트럭션, URL exfil 패턴) 정규식 + LLM-judge 점수 → `document_chunks.quarantine_flag`.
- **검색 단계:** quarantine_flag=true chunk는 prompt에 포함하지 않거나 spotlighting 마커로만 인용.
- **응답 단계:** 출력 sanitize (HTML/JS strip, Markdown 링크 화이트리스트, instruction echo 감지).
- **이중 LLM 패턴(권장):** privileged LLM은 도구 호출만, quarantined LLM은 untrusted text 처리 — rag_qa·email_draft·consultation_briefing에 우선 적용.

### 4.4 Vector/Embedding 거버넌스 (LLM08)
- 임베딩 차원 강제(AI-04와 일치): BGE_EMBEDDING_DIMENSIONS == DB `vector(N)`; mismatch 시 BLOCKED.
- 임베딩 batch 결과 vector 개수·dim 검증.
- 다중 source_type 혼재 시 retrieval filter는 SQL_ID로만; 사용자 input → filter 직결 금지.
- corpus 변경 시 content_hash 재검증 + 재임베딩; poisoned-corpus 의심 시 chunk 격리 + audit.

## 5. PoC Harness 보강 후보 (구체적 행동)
1. **Quarantine 메타데이터 컬럼 확장:** `document_chunks.quarantine_flag`, `quarantine_pattern_code`, `quarantine_score`, `quarantine_decision` (이미 일부 metadata 존재; column 명시 + index 추가).
2. **rag_qa BLOCKED reason taxonomy:** `ai_outputs.fail_closed_reason_code` enum 도입 (위 §4.2 코드).
3. **Golden snapshot 회귀 테스트:** `tests/ai/golden/*.yaml` × 7 에이전트; pytest fixture + DeepEval/직접 비교. CI에서 회귀 시 fail.
4. **Faithfulness/Groundedness 평가 hook:** rag_qa READY 응답에 메트릭 점수 기록 → `rag_answer_evidence.faithfulness_score`.
5. **Prompt-injection 패턴 라이브러리:** `prompts/INJECTION_PATTERNS.yaml` (정규식 + LLM-judge prompt) — 인덱싱·검색·응답 단계 공용.
6. **System prompt leakage 후처리:** 응답 vs system prompt 토큰 jaccard 임계값; 초과 시 redact + `LLM07_LEAKAGE_REDACTED` audit.
7. **Unbounded consumption 제한:** 사용자/세션별 분당 AI 호출·토큰 ceiling. `ai_jobs.consumption_block_reason`.
8. **Misinformation 라벨/평가 루프:** UI에 👍/👎 + 자유서술 → `ai_output_feedback` 테이블.
9. **NIST GAI Profile 매핑 문서:** 12 risk 카테고리 × 7 에이전트 매트릭스를 OBS-02·BACKLOG에 명시.
10. **EU AI Act 기술문서 패턴 차용:** 각 에이전트별 모델 카드(prompt 버전, 데이터 source_type, 평가 결과) → `docs/ai/MODEL_CARDS/agent-id.md`.
11. **금융 AI 7대 원칙 self-assessment:** PoC 시연 모드 종료 시 7원칙 통과 여부 보고서 자동 생성 (PoC_AUTO_APPROVAL audit과 별도).
12. **Azure Content Safety Prompt Shields 후보 통합:** Azure GPT5/mini 호출 전 옵션 hook (PoC scope는 토글, 기본 OFF; 실 사용 시 ON 권고).
13. **Groundedness Detection 후보:** Azure Content Safety Groundedness API를 rag_qa READY 응답 검증에 옵션 추가.
14. **Adversarial 시나리오 보강:** Round 10 적대적 시나리오에 "indirect prompt injection via DART body", "system prompt leak via long-context echo", "RAG empty citation despite high similarity" 추가.
15. **AI 사용 정책 페이지:** Korean copy "AI 생성물은 결정 지원이며 직원이 최종 책임" 명시; 인터넷망 노출 첫 화면.

## 6. BACKLOG Task 후보 (T260~T279)
| ID | 제목 | 카테고리 | 비고 |
|---|---|---|---|
| T260 | RAG golden snapshot 10건 + DeepEval pytest hook | AI/Test | rag_qa READY 회귀 |
| T261 | 7 에이전트 golden snapshot JSON-schema 회귀 | AI/Test | 결정성 평가 |
| T262 | `ai_outputs.fail_closed_reason_code` enum (NO_CITATION 등 8종) | DB/AI | §4.2 코드 |
| T263 | `document_chunks.quarantine_*` 컬럼 + index | DB/RAG | LLM01·LLM08 |
| T264 | `prompts/INJECTION_PATTERNS.yaml` + 인덱싱/검색/응답 hook | AI/Prompt | OWASP 패턴 |
| T265 | rag_qa dual-LLM(privileged/quarantined) 패턴 도입 | AI | LLM01 mitigation |
| T266 | rag_answer_evidence.faithfulness_score 기록 | DB/AI | groundedness |
| T267 | System prompt leakage 후처리 + LLM07_LEAKAGE_REDACTED audit | AI/Audit | LLM07 |
| T268 | 사용자/세션 AI 호출 ceiling + ai_jobs.consumption_block_reason | AI/Throttle | LLM10 |
| T269 | `ai_output_feedback` 테이블 + UI 👍/👎 | DB/UX | LLM09 overreliance |
| T270 | NIST GAI 12-risk × 7-agent 매트릭스 docs/ai/AI-06_nist_mapping.md | Docs | NIST 600-1 |
| T271 | `docs/ai/MODEL_CARDS/{agent}.md` 7건 | Docs | EU AI Act 기술문서 패턴 |
| T272 | 금융 AI 7대 원칙 self-assessment 자동 보고서 | Demo/Audit | 금융위 통합 가이드라인 |
| T273 | Azure Content Safety Prompt Shields 토글 hook (default OFF) | AI/Integration | Round 7 인터넷망 |
| T274 | Azure Content Safety Groundedness Detection 토글 hook | AI/Integration | rag_qa READY 검증 |
| T275 | Adversarial 시나리오 추가 3종 (indirect injection / leak / empty-citation) | Demo/Test | Round 10 적대적 |
| T276 | UI "AI는 결정 지원" 정책 페이지 + 7 에이전트 caveat 카피 회귀 | Frontend/Korean UX | 보조수단성 |
| T277 | OBS-02 audit code 보강 (LLM07_LEAKAGE_REDACTED, PROMPT_INJECTION_DETECTED 등) | Observability | 감사 코드 |
| T278 | Output sanitize 공용 유틸 (HTML strip, link allowlist, instruction echo) | Backend/AI | LLM05 |
| T279 | RAG quarantine 통계 대시보드(블록 비율·사유별 카운트) | Frontend/Ops | Batch Monitor 확장 |

## 7. 인용 (Sources)
- [OWASP Top 10 for LLM Applications 2025 (PDF v2025)](https://owasp.org/www-project-top-10-for-large-language-model-applications/assets/PDF/OWASP-Top-10-for-LLMs-v2025.pdf)
- [LLM01:2025 Prompt Injection — OWASP Gen AI Security Project](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
- [LLM08:2025 Vector and Embedding Weaknesses — OWASP Gen AI Security Project](https://genai.owasp.org/llmrisk/llm082025-vector-and-embedding-weaknesses/)
- [OWASP LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
- [NIST AI 600-1 Generative AI Profile (PDF)](https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf)
- [NIST AI Risk Management Framework](https://www.nist.gov/itl/ai-risk-management-framework)
- [EU AI Act — Regulation 2024/1689 (digital-strategy.ec.europa.eu)](https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai)
- [EBA — AI Act implications for the EU banking sector (Nov 2025, PDF)](https://www.eba.europa.eu/sites/default/files/2025-11/d8b999ce-a1d9-4964-9606-971bbc2aaf89/AI%20Act%20implications%20for%20the%20EU%20banking%20sector.pdf)
- [금융위 — 금융권 생성형 AI 활용 지원방안 (2024-12-12, PDF)](https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=83594&fileTy=ATTACH&fileNo=7)
- [금융위 — 금융분야 AI 가이드라인 개정방향 (PDF)](https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=85908&fileTy=ATTACH&fileNo=13)
- [김·장 — 금융분야 AI 가이드라인 개정안 공개 해설](https://www.kimchang.com/ko/insights/detail.kc?sch_section=4&idx=33825)
- [라이센스뉴스 — 금융 AI 7대 원칙 정리](https://www.lcnews.co.kr/news/articleView.html?idxno=119670)
- [파이낸셜뉴스 — 통합 AI 가이드라인 2026 1Q 시행](https://www.fnnews.com/news/202512221634163446)
- [Microsoft Learn — Prompt Shields in Azure AI Content Safety](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection)
- [Microsoft Learn — What is Azure AI Content Safety?](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview)
- [Microsoft Learn — Defend against indirect prompt injection attacks](https://learn.microsoft.com/en-us/security/zero-trust/sfi/defend-indirect-prompt-injection)
- [Microsoft Learn — Alerts for AI services (Defender for Cloud)](https://learn.microsoft.com/en-us/azure/defender-for-cloud/alerts-ai-workloads)
- [Microsoft Learn — AI security posture management (Defender for Cloud)](https://learn.microsoft.com/en-us/azure/defender-for-cloud/ai-security-posture)
- [Confident AI — DeepEval LLM Evaluation Framework (GitHub)](https://github.com/confident-ai/deepeval)
- [Atlan — RAGAS, TruLens, DeepEval Compared (2026)](https://atlan.com/know/llm-evaluation-frameworks-compared/)
- [arXiv — Mitigating Hallucination in LLMs: RAG/Reasoning/Agentic Survey (2025)](https://arxiv.org/html/2510.24476v1)
- [Stanford DHO — Legal RAG Hallucinations (2025)](https://dho.stanford.edu/wp-content/uploads/Legal_RAG_Hallucinations.pdf)
- [Goodwin — EU AI Act Key Points for Financial Services](https://www.goodwinlaw.com/en/insights/publications/2024/08/alerts-practices-pif-key-points-for-financial-services-businesses)
- [Hogan Lovells — AI regulation in financial services: EU AI Act layered landscape](https://www.hoganlovells.com/en/publications/ai-regulation-in-financial-services-navigating-the-eu-ai-act-in-a-layered-regulatory-landscape)
