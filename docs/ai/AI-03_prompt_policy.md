# AI-03 Prompt Policy

## Structure Rules
모든 프롬프트는 prompts/ 디렉토리의 PROMPT-XX 파일을 참조한다.
코드 내 프롬프트 문자열 직접 작성 금지.

## Injection Rules
- 고객 실명, 주민번호, 계좌번호 등 PII 원문 프롬프트 포함 금지.
- customer_id, portfolio_id 등 식별자만 사용 (이름은 익명화 또는 role로 대체).
- 예외: customer_no (내부 번호)는 포함 허용.

## Output Policy
- AI 응답은 항상 JSON 구조 반환 (prompts/ 파일에 output_schema 정의).
- 응답에 citations 포함 시 document_chunk_id 기반 출처 추적.
- 응답을 DB 저장 시 generated_at + model_name 함께 저장.
- 화면 표시 시 "AI 생성 · {generated_at} · {model}" 배지 필수.

## Audit
- 모든 AI 생성 에이전트: AI 호출 전후 audit_logs 기록. audit=false 예외 금지.
- 기록 필드: actor_id, action_code=AI_CALL_STARTED/AI_CALL_SUCCEEDED/AI_CALL_FAILED, resource_type, resource_id, model_name.


## Audit Code Source
- Canonical audit action_code 목록은 docs/observability/OBS-02_audit_action_codes.md를 따른다.
