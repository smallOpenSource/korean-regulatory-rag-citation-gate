# BATCH-06 RAG Refresh

## Trigger
- Implemented operator path: `scripts/run_batch_scheduler.py --run-once` or
  `scripts/run_batch_pipeline.sh --stages transform,embed` after provider/raw-document collection.
- Scheduler controls are opt-in: `HARNESS_BATCH_SCHEDULER_ENABLED=true`,
  `HARNESS_BATCH_RAG_REFRESH_ENABLED=true`, and `HARNESS_BATCH_RAG_REFRESH_INTERVAL_SECONDS`. The
  scheduler reuses the batch runner, Redis owner locks, and `batch_job_logs`; it is not a separate
  mock green path.

## Process
1. ivfflat 인덱스 재생성 여부 확인 (신규 청크 > 1000개 시 REINDEX).
2. BM25 full-text index (tsvector) 갱신.
3. 검색 결과 샘플 품질 검증 (top-1 cosine similarity > 0.7).

## Quality Check Failure
- 검증 실패 시 batch_job_logs에 WARN 기록.
- 자동 ADMIN WebSocket 알림은 ADR-001 구현 후 future path이다. 현재 운영 알림은 로그, `/batch/status`, `/data/readiness`, batch report로 확인한다.

## Implemented Readiness Contract
- `apps/api/harness/batch/documents.py::rag_readiness_snapshot` classifies persisted state as:
  `READY` when at least one chunk is embedded, `PENDING_EMBEDDING` when chunks exist but embedding
  is not complete, `PROVIDER_BLOCKED` when transform/embed/RAG batch logs are SKIPPED/FAILED and no
  embedded chunks exist, and `EMPTY` when no source data exists.
- This readiness status is evidence only; it does not synthesize RAG answers or mark provider paths
  successful.
- When BGE credentials are absent, scheduled RAG refresh records `EMBEDDING_REFRESH` as `SKIPPED`
  with a redacted reason and keeps readiness at `PENDING_EMBEDDING`/`PROVIDER_BLOCKED` rather than
  fabricating embeddings.
