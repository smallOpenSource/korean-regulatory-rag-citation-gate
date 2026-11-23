# SEC-02 Data Privacy

## PII Fields (암호화 또는 접근 통제 대상)
| 필드 | 테이블 | 보호 방법 |
|---|---|---|
| 고객 성명 | customers | 역할별 접근 통제 |
| 주민번호 | (Harness 미저장) | 수집 금지 |
| 계좌번호 | (Harness 미저장) | 수집 금지 |
| 이메일 | customers | 역할별 접근 통제 |
| 전화번호 | customers | 역할별 접근 통제 |
| 자산 규모 | customers.total_assets_krw | PB/WM 본인 담당 고객만 조회 |

## Data Retention
| 데이터 | 보존 기간 | 처리 방법 |
|---|---|---|
| consultations | 5년 | 법령 준수, 삭제 불가 |
| audit_logs | 5년 | append-only |
| batch_job_logs | 90일 | 파티션 삭제 |
| raw_documents.raw_text | 30일 | NULL 처리 (메타데이터 유지) |
| email_drafts | 1년 | 소프트 삭제 |

## Logging Rules
- 로그에 고객 성명, 계좌번호, 주민번호 원문 포함 금지.
- customer_id, customer_no만 로그에 기록.
- AI 프롬프트에 PII 원문 포함 금지 (AI-03 참조).


## Simulation Data Boundary
- recommendation_simulations와 order_simulations는 합성 고객/포트폴리오/주문 데이터만 사용한다.
- 실제 고객 주문, 실제 계좌번호, 실제 고객 이메일/전화 원문을 저장하지 않는다.
- 로그와 프롬프트에는 customer_id 등 내부 식별자만 사용한다.

---

## Wave 1 Logging Redaction (REG-05 T288)

### Sensitive Key Pattern
`SecretRedactionFilter` (in `apps/api/harness/core/logging.py`) intercepts all `logging` calls.
Any log record whose message or `extra` dict contains a key matching the following pattern is masked:

```
(password|passwd|secret|token|api[_-]?key|auth[_-]?key|client[_-]?secret|authorization|service[_-]?key)
```
(case-insensitive, regex)

Examples of matched keys: `password`, `Authorization`, `api_key`, `client_secret`, `service_key`,
`auth_key`. **Not matched**: `smtp_pass`, `_pass` suffix (not in pattern — use `password` or `passwd`).

### Mask Format
Matched values are replaced with `***REDACTED***` (fixed string, no length leak).
The `redact_mapping` helper uses `<redacted>` for structured dict redaction at ingestion time.

### AI Prompt Redactor Scope
The AI prompt redactor applies redaction before any LLM system prompt or RAG context concatenation
is assembled. Scope:
- System prompt template variables
- RAG-retrieved document chunks (injected into the LLM context window)
- Customer-facing advice text in the prompt (before external provider call)

The redactor does **not** retroactively clean provider response bodies; those must not contain PII
at the point of assembly (SEC-02 PII fields above must not be passed to external LLM APIs).

### Audit Log Redaction
`audit_logs.detail_json` must not store: SMTP credentials, JWT/bearer tokens, raw PII, or external
API response bodies. Apply `redact_mapping` before inserting into `detail_json`.
