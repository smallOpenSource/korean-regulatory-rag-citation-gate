# RUN-12 — Measurement Collection Cron Registration

UltraQA Cycle 2 (commit `d352da0`) introduced 3 measurement-related scripts
that require periodic execution to keep the composite gate
(`scripts/verify_total_product_readiness.py`) in strict fail-closed mode
rather than the bootstrap `not_yet_collected` state. This runbook covers
crontab registration, log paths, environment variables, and failure modes.

## Scripts overview

| Script | Purpose | Cadence | Exit semantics |
|---|---|---|---|
| `scripts/collect_seven_principles_measurements.py` | Wrapper that calls `aggregate_principle_runtime_metrics.py` per principle/metric and writes JSON files to `docs/ai/measurements/` | Daily | exit 0 on success, exit 1 on DB connection failure, exit 2 on invalid args |
| `scripts/cleanup_stale_measurements.py` | Scans `docs/ai/measurements/*.json`, archives entries with `expires_at` past OR mtime > 30d into `docs/ai/measurements/archive/` | Daily | exit 0 (idempotent) |
| `scripts/audit_ai06_measurement_freshness.py` | Parses `docs/ai/AI-06_nist_ai_rmf_mapping.md` threshold lines, asserts each has citation or `[PENDING_MEASUREMENT]` marker, checks citation freshness ≤ 7d | Daily (alerting) | exit 0 if all fresh/PENDING, exit 1 if stale/missing → MAILTO triggers |

## Prerequisites

1. **Python environment**: `/opt/conda/envs/wm_env/bin/python` (project standard per memory rule `project-python-interpreter`).
2. **DB role**: `harness_audit` (read-only on `audit_logs`, V019:38-44).
   - Connection string set via `DATABASE_URL_HARNESS_AUDIT` env var.
   - Format: `postgresql://harness_audit:<password>@<host>:<port>/<db>`.
   - **DO NOT** use `harness_app` — V019 grant scope excludes it from `audit_logs SELECT`.
3. **Working directory**: `<repo-root>` (scripts use `Path(__file__).resolve().parents[1]` for repo root).
4. **Log directory**: `<repo-root>/.omc/logs/cycle2/` (gitignored under `.omc/logs/`).

## Recommended crontab entries

Pick slots that don't collide with the existing `ai-dashboard` batches at
02:00 / 02:30 / 02:45 / 02:50 / 03:00 / 04:00. The proposal below uses
03:15 / 03:45 / 04:30:

```cron
# === wmah UltraQA cycle 2 measurement cron (RUN-12) ===
SHELL=/bin/bash
PATH=/opt/conda/envs/wm_env/bin:/opt/conda/bin:/usr/local/bin:/usr/bin:/bin
MAILTO=ops@localhost

# 03:15 daily — collect runtime metrics for current UTC calendar day
15 3 * * * cd <repo-root> && DATABASE_URL_HARNESS_AUDIT="${DATABASE_URL_HARNESS_AUDIT:-}" /opt/conda/envs/wm_env/bin/python scripts/collect_seven_principles_measurements.py --window=$(date -u +\%Y-\%m-\%d) >> <repo-root>/.omc/logs/cycle2/collect.log 2>&1

# 03:45 daily — archive stale measurements (>30d) into archive/
45 3 * * * cd <repo-root> && /opt/conda/envs/wm_env/bin/python scripts/cleanup_stale_measurements.py >> <repo-root>/.omc/logs/cycle2/cleanup.log 2>&1

# 04:30 daily — alert on stale/missing AI-06 measurement citations (exit 1 mails ops@)
30 4 * * * cd <repo-root> && /opt/conda/envs/wm_env/bin/python scripts/audit_ai06_measurement_freshness.py >> <repo-root>/.omc/logs/cycle2/freshness.log 2>&1
```

### Why these slots
- **03:15**: 15 min buffer after the 03:00 ai-dashboard external batch finishes. Enough time for any tail-end `audit_logs` writes to commit before aggregation reads them.
- **03:45**: 30 min after collect — measurement JSON files are written; cleanup can safely scan them.
- **04:30**: 30 min after the 04:00 ai-dashboard verify batch. Daily freshness audit alert window.

## Registration steps (current `ops` shell)

1. **Pre-flight check** (recommended before activating):
   ```bash
   # Verify Python env + scripts are runnable
   /opt/conda/envs/wm_env/bin/python -c "import asyncpg; print(asyncpg.__version__)"
   ls -la <repo-root>/scripts/{collect_seven_principles_measurements,cleanup_stale_measurements,audit_ai06_measurement_freshness}.py

   # Test each script in dry mode (collect needs DATABASE_URL_HARNESS_AUDIT; others don't)
   /opt/conda/envs/wm_env/bin/python scripts/audit_ai06_measurement_freshness.py
   # → expected: exit 0 + "all 8 thresholds carry PENDING_MEASUREMENT (deadline=2026-06-15)"
   ```

2. **Add to crontab** (interactive — only if user authorizes):
   ```bash
   crontab -l > /tmp/wmah-crontab-backup.txt   # backup current entries
   crontab -e   # opens editor; paste the 3 entries from "Recommended crontab entries" above
   crontab -l   # verify
   ```

   Or non-interactively via stdin (use a heredoc):
   ```bash
   (crontab -l 2>/dev/null; cat <<'CRON'

   # === wmah UltraQA cycle 2 measurement cron (RUN-12) ===
   15 3 * * * cd <repo-root> && /opt/conda/envs/wm_env/bin/python scripts/collect_seven_principles_measurements.py --window=$(date -u +\%Y-\%m-\%d) >> <repo-root>/.omc/logs/cycle2/collect.log 2>&1
   45 3 * * * cd <repo-root> && /opt/conda/envs/wm_env/bin/python scripts/cleanup_stale_measurements.py >> <repo-root>/.omc/logs/cycle2/cleanup.log 2>&1
   30 4 * * * cd <repo-root> && /opt/conda/envs/wm_env/bin/python scripts/audit_ai06_measurement_freshness.py >> <repo-root>/.omc/logs/cycle2/freshness.log 2>&1
   CRON
   ) | crontab -
   ```

3. **Ensure log directory exists**:
   ```bash
   mkdir -p <repo-root>/.omc/logs/cycle2
   ```

4. **Verify after first run** (next morning):
   ```bash
   ls -la <repo-root>/docs/ai/measurements/*.json   # collect output
   tail <repo-root>/.omc/logs/cycle2/collect.log
   /opt/conda/envs/wm_env/bin/python scripts/verify_total_product_readiness.py | jq '.composite_gate'
   # → should transition from "not_yet_collected" to either "passed" or "failed" with concrete numbers
   ```

## Failure modes + alert behavior

| Symptom | Likely cause | Action |
|---|---|---|
| `MAILTO` mail "FAILED: ai06 freshness" | One or more measurement JSON > 7d stale OR missing | Re-run `collect_seven_principles_measurements.py` manually; if persists, investigate AI traffic absence (no `AI_CALL_STARTED` rows in window) |
| `collect.log` shows `asyncpg.exceptions.InvalidAuthorizationSpecificationError` | `DATABASE_URL_HARNESS_AUDIT` unset or wrong password | Set env var; if role doesn't exist, run `CREATE ROLE harness_audit ...` per V019 |
| `collect.log` shows `permission denied for table audit_logs` | DB role lacks SELECT grant | Re-run V019 migration; verify `\dp audit_logs` shows harness_audit has `r` |
| Composite gate stuck in `not_yet_collected` after collector runs | `docs/ai/measurements/` empty — collector may have exited 1 before writing | Check `collect.log`; rerun manually with `--window=YYYY-MM-DD` |
| `cleanup.log` shows nothing archived but disk filling | `expires_at` field missing in collector output | Check `aggregate_principle_runtime_metrics.py` schema — should emit `expires_at = last_measured_at + 7d` |

## Composite gate state machine (cycle 2 context)

```
[deploy day]          measurements/ empty
                              │
                              ├─ verify_total_product_readiness.py
                              │  → composite_gate.status = "not_yet_collected"
                              │  → composite_passed = True (bootstrap)
                              │
[+ 24h: first collect run]    measurements/p3_faithfulness.json + 6 others
                              │
                              ├─ verify_total_product_readiness.py
                              │  → composite_gate.status = "passed" | "failed"
                              │  → strict fail-closed AND gate active:
                              │      STATIC AND RUNTIME AND freshness≤7d AND denominator≥1
                              │
[+ 8 days: no recent activity] all measurements > 7d stale
                              │
                              ├─ audit_ai06_measurement_freshness.py exit 1
                              ├─ MAILTO ops@ alert
                              └─ verify_total_product_readiness.py → "failed" (freshness exceeded)
```

## Off-cycle manual run (incident response)

When investigating a failing composite gate or stale measurements outside cron:

```bash
cd <repo-root>

# Force fresh collection for yesterday's window
/opt/conda/envs/wm_env/bin/python scripts/collect_seven_principles_measurements.py \
  --window=$(date -u -d 'yesterday' +%Y-%m-%d)

# Inspect freshness without modifying anything
/opt/conda/envs/wm_env/bin/python scripts/audit_ai06_measurement_freshness.py

# Rerun composite gate
/opt/conda/envs/wm_env/bin/python scripts/verify_total_product_readiness.py | jq .composite_gate
```

## Removal / rollback

```bash
crontab -l > /tmp/wmah-crontab-backup-$(date +%s).txt
crontab -l | grep -v "wmah UltraQA cycle 2 measurement cron" | grep -v "<repo-root>/scripts/collect_seven_principles_measurements" | grep -v "<repo-root>/scripts/cleanup_stale_measurements" | grep -v "<repo-root>/scripts/audit_ai06_measurement_freshness" | crontab -
```

After rollback, composite gate naturally returns to `not_yet_collected`
once existing measurement JSONs age past 7d (or run `cleanup_stale_measurements.py`
with adjusted age threshold to force).

## Cross-references

- Cycle 2 plan: `.omc/plans/ralplan-dr-ultraqa-cycle2-v3.md`
- Wave 6 placeholder: `.omc/plans/ralplan-wmah-wave6-prod-readiness.md` (Activation Checklist items 11-13)
- ADR-007 §4: `docs/architecture/ADR-007_validator_contract_specs.md` (measurement collection cadence contract)
- ADR-007.1 sidecar: `docs/architecture/ADR-007.1_validator_io_schema.yaml` (measurement JSON schema)
- V019 audit_logs grants: `db/migrations/V019__audit_append_only_trigger.sql:38-44`
- RUN-09 (existing batch scheduler): `docs/runbooks/RUN-09_batch_scheduler.md`
