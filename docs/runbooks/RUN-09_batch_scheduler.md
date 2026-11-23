# RUN-09 Batch Scheduler Runbook

## Overview

`apps/api/harness/batch/scheduler.py` exposes two scheduling modes:

| Mode | Command | Default state |
|---|---|---|
| Interval-based (built-in) | `python -m apps.api.harness.batch.scheduler --run-once` | enabled when `HARNESS_BATCH_SCHEDULER_ENABLED=true` |
| APScheduler cron-based | `python -m apps.api.harness.batch.scheduler --apscheduler` | **DISABLED** by default |

## Environment Variables

### Global gates

| Variable | Default | Effect |
|---|---|---|
| `HARNESS_BATCH_SCHEDULER_ENABLED` | `false` | Master gate for interval-based scheduler |
| `HARNESS_BATCH_APSCHEDULER_ENABLED` | `false` | Gate for APScheduler cron-daemon mode |

### APScheduler cron expressions (5-field standard cron)

| Variable | Job | Example (weekday 18:00 KST) |
|---|---|---|
| `CRON_BATCH_RAG_REFRESH` | RAG embed refresh | `0 9 * * 1-5` |
| `CRON_BATCH_DERIVED_REFRESH` | derived + house-view stages | `30 18 * * 1-5` |
| `CRON_BATCH_SERVICEABLE_TOP200` | serviceable top-200 pipeline | `0 20 * * 1-5` |
| `CRON_BATCH_HOUSE_VIEW` | house-view generation only | `0 19 * * 1-5` |

All cron variables are **empty by default** (disabled).  
APScheduler uses `Asia/Seoul` timezone for all expressions.

### Interval-based cron (built-in, no APScheduler dependency)

| Variable | Default | Effect |
|---|---|---|
| `HARNESS_BATCH_RAG_REFRESH_INTERVAL_SECONDS` | `3600` | Interval for rag_refresh job |
| `HARNESS_BATCH_DERIVED_REFRESH_INTERVAL_SECONDS` | `3600` | Interval for derived_refresh job |
| `HARNESS_BATCH_SERVICEABLE_TOP200_INTERVAL_SECONDS` | `86400` | Interval for serviceable top-200 |

## PoC Demo — Manual One-Shot Triggers

Run all enabled scheduler jobs once:
```bash
python -m apps.api.harness.batch.scheduler --run-once
```

Run a specific named job (e.g., `rag_refresh` only):
```bash
python -m apps.api.harness.batch.scheduler --run-once rag_refresh
```

Inspect the scheduler plan without running:
```bash
python -m apps.api.harness.batch.scheduler --plan-only
```

Or via the scripts wrapper:
```bash
/opt/conda/envs/wm_env/bin/python scripts/run_batch_scheduler.py --run-once rag_refresh
```

## APScheduler daemon mode (PoC stub — DISABLED by default)

APScheduler is **wired but disabled** for the PoC.  
To activate for a demo window:

1. Install the optional dependency:
   ```bash
   pip install apscheduler>=3.10
   ```
2. Configure at least one `CRON_BATCH_*` variable in `.env`.
3. Set `HARNESS_BATCH_APSCHEDULER_ENABLED=true` in `.env`.
4. Start the daemon:
   ```bash
   python -m apps.api.harness.batch.scheduler --apscheduler
   ```

The daemon blocks the process; run it in a supervised process or tmux pane.  
APScheduler cron jobs call `run_scheduler_once()` internally — the same
Redis-locked, provider-governance-checked pipeline as the manual trigger.

## External Dependency Attestation

Run the ADR-007 §1 attestation script (requires live providers):
```bash
python scripts/external_dependency_attestation.py \
    --env-profile poc \
    --allow-degraded broker,pykrx_fdr \
    --out .omx/reports/verification/ext-dep-attest.json
```

Exit codes: `0`=pass, `2`=failed, `3`=config error, `4`=token budget exhausted.

Report is written to `--out` path and also to `.omx/reports/verification/attest-*.json`
(one file per dependency checked).

## Token Budget

Azure calls made by the attestation script are bounded by:

| Variable | Default | Trigger |
|---|---|---|
| `AZURE_TOKEN_CEILING_IN` | `100000` | Exit 4 when exceeded mid-run |
| `AZURE_TOKEN_CEILING_OUT` | `20000` | Exit 4 when exceeded mid-run |

Monthly cumulative AI token cap is enforced at the service layer via
`services/ai/token_meter.py` (see `AI_TOKEN_CEILING_MONTHLY=560000`).

## See Also

- `docs/architecture/ADR-007_validator_contract_specs.md` — attestation JSON contract
- `docs/architecture/ADR-005_dual_llm_quarantine.md` — token meter + LLM10
- `apps/api/harness/batch/scheduler.py` — implementation
- `scripts/external_dependency_attestation.py` — live provider attestation
