# OPS-04 Operations Status and Observability Runbook

## Current Operations Contract
Current operational truth is pull-based and report-based:

1. `scripts/status.sh --deep --no-fail` for local process, HTTP, PostgreSQL, and Redis status.
2. `GET /health` and `GET /health/config` for API liveness and sanitized runtime config.
3. `GET /batch/status` for ADMIN-visible batch evidence.
4. `GET /data/readiness` for data readiness, provider mode, top-200 coverage, and synthetic boundary.
5. Batch/verification reports under `.omx/reports/` for durable evidence.

WebSocket push alerts are `backlog/not-current-contract`; do not page operators or claim green
runtime status from a WebSocket event until ADR-001 is implemented.

## Standard Local Status Check
```bash
cd <repo-root>
./scripts/status.sh --deep --no-fail
```

Interpretation:
- `status=ok`: process, HTTP, PostgreSQL, and Redis checks passed.
- `status=blocked failures=N no_fail=1`: one or more dependencies are unavailable; this is honest
  blocked evidence, not success.
- Failure lines print class-level reasons only. They must not include `.env` secrets, bearer tokens,
  provider keys, SMTP credentials, or database passwords.

## Readiness API Evidence
Use real employee access tokens and keep tokens out of logs:

```bash
curl -H "Authorization: Bearer <access_token>" http://127.0.0.1:8000/data/readiness
curl -H "Authorization: Bearer <admin_access_token>" http://127.0.0.1:8000/batch/status
```

Expected operator fields:
- top-level `status_code`,
- `domestic_market.status_code`, `source_code`, `source_policy_code`, and `source_as_of`,
- `domestic_market.top200_coverage.coverage_ratio`, `selected_count`, and `missing_member_days`,
- provider recent-batch status with sanitized `SKIPPED`, `FAILED`, or `BLOCKED` reasons.

## Batch Evidence
For acceptance evidence, prefer required-provider mode and name the report path:

```bash
./scripts/run_batch_pipeline.sh \
  --profile full-mvp \
  --all-stages \
  --lookback-days 30 \
  --as-of-date 2026-05-16 \
  --provider-strictness required \
  --report .omx/reports/batch/full-mvp-latest.json
```

Use `--provider-strictness all` only for diagnostics. Optional-provider failures from an all-provider
run must not be reported as acceptance blockers unless the required run also fails.

## Alert Mapping
| condition | current evidence path | future push path |
|---|---|---|
| API unavailable | `scripts/status.sh` + `/health` | WebSocket not applicable |
| PostgreSQL/Redis unavailable | `scripts/status.sh --deep --no-fail` | WebSocket not applicable |
| batch provider failed | `/batch/status`, batch report, ERROR log | `batch_status_change` after ADR-001 implementation |
| data readiness blocked | `/data/readiness`, verification report | optional ADMIN notification after ADR-001 implementation |
| AI job failed | `/ai-jobs/{job_id}` and redacted audit/log evidence | `ai_job_done` after ADR-001 implementation |

## Secret Handling
- Never paste `.env`, bearer tokens, SMTP credentials, provider keys, or database URLs into reports.
- Redact `AUTH_KEY`, `KRX_API_KEY`, `AZURE_OPENAI_API_KEY`, `BREVO_API_KEY`, `SMTP_PASSWORD`, bearer
  tokens, and database passwords as `<redacted>`.
- If a command leaks a secret, invalidate the artifact and rerun after fixing redaction.

## Handoff Checklist
- Status command output captured with timestamp.
- Relevant API/readiness payload summarized without tokens or raw PII.
- Batch or verification report path named.
- Any blocked provider/dependency is labelled blocked/skipped/failed; no fabricated provider row is
  used to close readiness.
