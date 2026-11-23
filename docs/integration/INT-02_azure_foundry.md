# INT-02 Azure AI Foundry Integration

## Scope
- Azure OpenAI / Microsoft Foundry는 생성형 LLM 호출에만 사용한다.
- 문서 임베딩과 rerank는 내부 BGE API를 사용한다 (BATCH-05, AI-04 참조).

## Client Setup
- SDK: openai-python async client.
- Endpoint/key: AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY 환경변수.
- v1 API base URL: AZURE_OPENAI_BASE_URL (`{AZURE_OPENAI_ENDPOINT}/openai/v1/`).
- Deployment names: AZURE_GPT5_DEPLOYMENT, AZURE_GPT5_MINI_DEPLOYMENT.
- dated AZURE_OPENAI_API_VERSION은 legacy client 호환이 필요한 경우에만 사용한다.

## Rate Limit Handling
- 429 응답: exponential backoff (1s, 2s, 4s, 최대 3회).
- 재시도 실패 시 에러 반환 + audit_logs AI_CALL_FAILED.

## Response Validation
- AI 응답 JSON 파싱 실패 시 재시도 1회.
- 재시도 실패 시 에러 반환 (빈 결과 저장 금지).
