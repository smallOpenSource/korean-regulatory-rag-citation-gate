# BATCH-07 Monitoring

## Metrics to Track
| 지표 | 알림 조건 |
|---|---|
| job 실패 | `/batch/status`와 verification report에서 즉시 확인 |
| rows_failed > 0 | 10% 초과 시 알림 |
| 수집 건수 급감 | 전일 대비 50% 미만 시 알림 |
| embedding 적체 | is_embedded=false 청크 > 5,000 시 알림 |

## Batch Status API
GET /batch/status → 최근 20개 batch_job_logs 반환.
Frontend Batch Monitor 화면에서 조회한다. WebSocket `batch_status_change` transport is implemented as an ADMIN-scoped `/ws` event, while current acceptance evidence remains `batch_job_logs`, `/batch/status`, `/data/readiness`, and `scripts/run_batch_pipeline.sh --report ...` JSON files.

## Operator Evidence
- `scripts/run_batch_pipeline.sh --profile full-mvp --all-stages --report .omx/reports/batch/latest.json`
  executes the local seed/provider/transform/embed/derived/house-view evidence path.
- `DONE`, `SKIPPED`, and `FAILED` are all meaningful terminal evidence. SKIPPED/FAILED provider
  rows must be shown as blocked/degraded evidence, not green success.
- Postcondition queries in the runner use `/* sql_id: ... */` comments and verify recent
  `batch_job_logs`, readiness counts, and RAG readiness.

## Retention
- batch_job_logs: 90일 보존 후 파티션 삭제.
- raw_documents (is_processed=true): 30일 후 raw_text 컬럼 NULL 처리 (메타데이터 유지).
