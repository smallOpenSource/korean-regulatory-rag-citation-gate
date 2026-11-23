# BATCH-05 Embedding Spec

## Target
- is_embedded=false 인 document_chunks.

## Provider
- 임베딩은 Azure embedding deployment가 아니라 사용자가 지정한 내부 BGE API를 사용한다.
- 필수 환경변수: BGE_EMBEDDING_API_URL, BGE_EMBEDDING_API_KEY, BGE_EMBEDDING_MODEL, BGE_EMBEDDING_DIMENSIONS.
- rerank 필수 환경변수: BGE_RERANK_API_URL, BGE_RERANK_API_KEY, BGE_RERANK_MODEL.
- 인증 방식: Bearer (`Authorization: Bearer {key}`).
- 선택 환경변수: BGE_EMBEDDING_BATCH_SIZE, BGE_EMBEDDING_TIMEOUT_SECONDS, BGE_BATCH_SIZE(검증 게이트 CLI 배치 크기), BGE_RERANK_TOP_N.

## Process
1. chunk_text를 BGE_EMBEDDING_BATCH_SIZE 단위로 내부 BGE embedding API 호출. 요청 JSON은 `model` + `texts`를 사용한다.
2. 응답의 `dense_embeddings` 벡터 길이가 BGE_EMBEDDING_DIMENSIONS와 같은지 검증한다. 현재 내부 BGE 설정 기준 N=1024.
3. embedding vector(N) 저장.
4. is_embedded=true 업데이트.

## Vector Index
- pgvector ivfflat 사용.
- `document_chunks.embedding vector(N)`의 N은 BGE_EMBEDDING_DIMENSIONS와 동일해야 한다.
- lists 파라미터: sqrt(row_count) 기준, 최소 10.
- probes: 쿼리 시 10.
- 행 수 10,000 미만: 순차 스캔 허용 (SET enable_indexscan=off 불필요).

## Rerank
- RAG 후보 재정렬은 BGE_RERANK_API_URL / BGE_RERANK_API_KEY / BGE_RERANK_MODEL을 사용한다.
- 재정렬 결과 상위 개수는 BGE_RERANK_TOP_N을 따른다.

## Throttle
- 내부 BGE API rate limit 준수: 운영 검증 게이트는 `BGE_BATCH_SIZE=16`, `BGE_EMBEDDING_TIMEOUT_SECONDS=300` 기준으로 실행한다.
- 청크 배치 간 기본 0.5초 sleep.
- 429/503 응답은 exponential backoff로 최대 3회 재시도.

## Implemented Client Contract
- `apps/api/harness/external/bge.py` calls the internal BGE API with `model` and `texts`, requires Bearer auth, extracts `dense_embeddings`, and validates vector count plus 1024-dimension compatibility before DB update.
- `apps/api/harness/batch/embedding.py` writes pgvector literals and marks chunks embedded only after validation succeeds.
- Embedding refresh only acts on `document_chunks.is_embedded=false`; chunks created by the transform
  stage stay pending until the real internal BGE API succeeds.
- No placeholder or zero vectors are permitted for readiness. If BGE is unavailable, the batch job
  must record sanitized SKIPPED/FAILED evidence instead of marking chunks embedded.

## Seed Interaction
- `db/seed.py --profile full-mvp` creates MANUAL chunks with `embedding=NULL` and `is_embedded=false`.
- The seed never fabricates vectors. The embedding refresh must call the configured internal BGE API and validate 1024 dimensions before updating pgvector columns.
- If BGE is unavailable, record sanitized SKIPPED/FAILED evidence in `batch_job_logs` and keep chunks unembedded.
