# AI-01 Model Routing

## Available Models and Providers
| 환경변수 | 용도 | 특성 |
|---|---|---|
| AZURE_GPT5_DEPLOYMENT | House View 생성, 대용량 분석 | 고품질, 고비용 |
| AZURE_GPT5_MINI_DEPLOYMENT | Briefing, NBA script, Q&A 등 | 저지연, 저비용 |
| BGE_EMBEDDING_API_URL | 문서 청크 임베딩 | 내부 API, Bearer 인증, model은 BGE_EMBEDDING_MODEL |
| BGE_RERANK_API_URL | RAG 후보 재정렬 | 내부 API, Bearer 인증, model은 BGE_RERANK_MODEL |

## Routing Rules
- house_view_generation 에이전트: AZURE_GPT5_DEPLOYMENT 사용.
- 나머지 생성형 에이전트: AZURE_GPT5_MINI_DEPLOYMENT 사용.
- embedding/reranking: Azure가 아니라 내부 BGE API 사용.
- 내부 BGE API 인증: `Authorization: Bearer {key}`.
- 모델명, 배포명, URL, 인증 방식 코드 하드코딩 금지 → 환경변수만 사용.

## Fallback
- Azure 또는 내부 BGE API 오류 시 3회 재시도 (exponential backoff).
- 재시도 실패 시 에러 반환 + audit_logs 기록 (action_code=AI_CALL_FAILED 또는 EMBEDDING_CALL_FAILED).
- 사용자에게 "AI 서비스 일시 불가, 잠시 후 다시 시도" 메시지 표시.

## Cost Control
- max_tokens 상한: AI-02 각 에이전트 설정 준수.
- 동일 request_id 중복 호출 방지: 호출 전 in-flight 확인.
- 배치 embedding: BGE_EMBEDDING_BATCH_SIZE 단위 batch API 호출.
