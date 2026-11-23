# RUN-11 Token Budget Runbook

## Metadata
- **Runbook ID**: RUN-11
- **Subject**: Azure LLM Token Budget Management — Monthly Cap, Abort Thresholds, Audit Ledger, Manual Reset
- **Relates to**: ADR-005 §4, ADR-007 §1, REG-04 §3-bis (LLM10 Unbounded Consumption), AI-06 MS-2.7
- **Authored**: 2026-05-17 (Wave 3, W3-T8 §3.7 token budget meter wiring)
- **Note**: RUN-07 is the ZAP baseline runbook. This runbook (RUN-11) owns token budget. Do not confuse.

---

## 1. Overview

The Harness PoC calls Azure GPT-5/mini from 6 of 7 AI agents (compliance_check is rule-based and
generates no tokens). Left uncontrolled, a runaway async job or a test loop could exhaust the
monthly allocation, generating unexpected cost and triggering Azure rate-limit errors.

This runbook defines:
- Monthly token cap and the three escalating abort thresholds (§3).
- How the audit ledger accumulates and is swept (§4).
- Alert recipients and on-call protocol (§5).
- Manual reset procedure for emergency (§6).

---

## 2. Token Budget Configuration

All values are controlled via environment variables. **Never hardcode values in application code.**

| Env Var | Default | Description |
|---|---|---|
| `AZURE_TOKEN_CEILING_MONTHLY` | `560000` (input) / `112000` (output) | Monthly rolling cap for all agents combined. Input and output are tracked separately. |
| `AZURE_TOKEN_ALERT_70_PCT` | `392000` / `78400` | 70 % threshold — warning alert, no abort. |
| `AZURE_TOKEN_ALERT_85_PCT` | `476000` / `95200` | 85 % threshold — throttle non-critical agents (portfolio_analysis, email_draft drafts). |
| `AZURE_TOKEN_ABORT_100_PCT` | `560000` / `112000` | 100 % threshold — hard abort; all AI calls blocked until reset or new month. |
| `AZURE_TOKEN_CEILING_PER_WINDOW` | `100000` (input) + `20000` (output) | Per-acceptance-window cap used by `external_dependency_attestation.py` (ADR-007 §1). |
| `AZURE_TOKEN_WINDOW_HOURS` | `24` | Rolling window in hours for the per-window cap. |

### §3.7 Monthly Cap Derivation

| Agent | Estimated calls/day (PoC) | Avg tokens/call (in + out) | Monthly total |
|---|---|---|---|
| rag_qa | 20 | 1 500 + 300 | 54 000 |
| email_draft | 5 | 800 + 200 | 15 000 |
| consultation_briefing | 5 | 1 200 + 250 | 22 250 |
| house_view_generation | 2 | 3 000 + 500 | 10 500 |
| nba_script | 10 | 600 + 150 | 22 500 |
| portfolio_analysis | 3 | 2 500 + 400 | 86 700 |
| Faithfulness judge (rag_qa) | 20 | 800 + 100 | 27 000 |
| **Total estimate** | | | **238 000** (input + output combined) |
| **Monthly cap (560K input + 112K output)** | | | **≈ 2.4× safety margin** |

The 560K/112K cap provides approximately 2.4× headroom above the daily PoC estimate, accommodating
acceptance-window burst runs, adversarial test executions, and `external_dependency_attestation.py`
runs (7 Azure calls per attestation run).

---

## 3. Abort Thresholds and Agent Throttle Policy

### 70 % Alert (Warning Only)

- **Trigger**: `audit_logs` monthly token accumulation crosses 70 % of `AZURE_TOKEN_CEILING_MONTHLY`.
- **Action**: Alert dispatched to recipients in §5. No automated throttle.
- **Operator response**: Review which agent is consuming most tokens; consider deferring
  non-critical async jobs (`portfolio_analysis`).

### 85 % Threshold (Partial Throttle)

- **Trigger**: Accumulation crosses 85 %.
- **Automated action**:
  - `portfolio_analysis` async jobs: new jobs rejected with `consumption_block_reason=BUDGET_85PCT`.
  - `email_draft` generation: new draft calls rejected with the same reason.
  - All other agents continue unthrottled.
- **Audit**: Each rejected call writes an `ai_outputs` row with `fail_closed_reason_code=BUDGET_85PCT`
  and a paired `audit_logs` row (action_code = `AI_CALL_BUDGET_THROTTLED`).
- **Operator response**: Escalate to on-call if trend continues toward 100 %.

### 100 % Abort (Hard Block)

- **Trigger**: Accumulation reaches or exceeds 100 % of `AZURE_TOKEN_CEILING_MONTHLY`.
- **Automated action**:
  - All AI agent calls are immediately rejected: HTTP 503 with body
    `{"error": "AI_TOKEN_BUDGET_EXHAUSTED", "retry_after": "<next_reset_UTC>"}`.
  - No Azure calls are made; the rejection is local and instant.
  - Compliance_check (rule-based) continues to function normally.
- **Audit**: Each rejected call writes `fail_closed_reason_code=BUDGET_EXHAUSTED`.
- **Operator response**: Execute manual reset procedure in §6 if approved; or wait for
  month rollover (automatic reset at 00:00 UTC on the 1st of the following month).

---

## 4. Audit Ledger Sweep

Token consumption is persisted in two places:

### 4.1 Per-Call Ledger (`audit_logs.detail_json.token_consumption`)

Every Azure AI call writes a JSON field:
```json
{
  "token_consumption": {
    "agent": "rag_qa",
    "model": "gpt5-mini",
    "tokens_in": 1245,
    "tokens_out": 280,
    "cumulative_monthly_in": 84500,
    "cumulative_monthly_out": 16800
  }
}
```

### 4.2 Monthly Accumulator (`ai_jobs` table)

The `ai_jobs` table carries a `monthly_token_in` and `monthly_token_out` counter updated atomically
after each successful Azure call. The accumulator resets automatically at month rollover.

### 4.3 Sweep Query (monitoring dashboard)

```sql
SELECT
  DATE_TRUNC('month', created_at) AS month,
  detail_json->'token_consumption'->>'agent' AS agent,
  SUM((detail_json->'token_consumption'->>'tokens_in')::int) AS total_in,
  SUM((detail_json->'token_consumption'->>'tokens_out')::int) AS total_out
FROM audit_logs
WHERE action_code IN ('AI_CALL_SUCCEEDED', 'AI_CALL_FAILED')
  AND created_at >= DATE_TRUNC('month', NOW())
GROUP BY 1, 2
ORDER BY 1, total_in DESC;
```

---

## 5. Alert Recipients

| Level | Recipients | Channel |
|---|---|---|
| 70 % Warning | Batch operations team | Slack `#harness-ops-alerts` |
| 85 % Throttle | Batch ops + Tech lead | Slack `#harness-ops-alerts` + direct DM |
| 100 % Abort | Batch ops + Tech lead + PoC owner | Slack + email (`HARNESS_ALERT_EMAIL` env var) |

Alert dispatch is handled by `apps/api/harness/core/alert.py` (post-Wave-3 hook); the env var
`HARNESS_ALERT_EMAIL` must be set to a non-example address in production. **Do not commit real
email addresses** — reference the env var name only.

---

## 6. Manual Reset Procedure

**Prerequisite**: Approval from PoC owner documented in the change log.

```bash
# 1. Verify current accumulation before reset
psql $DATABASE_URL -c "
  SELECT
    SUM((detail_json->'token_consumption'->>'tokens_in')::int) AS total_in,
    SUM((detail_json->'token_consumption'->>'tokens_out')::int) AS total_out
  FROM audit_logs
  WHERE action_code IN ('AI_CALL_SUCCEEDED', 'AI_CALL_FAILED')
    AND created_at >= DATE_TRUNC('month', NOW());
"

# 2. Reset the monthly accumulator (does NOT delete audit_logs — append-only)
psql $DATABASE_URL -c "
  UPDATE ai_jobs
  SET monthly_token_in = 0, monthly_token_out = 0,
      consumption_reset_at = NOW(),
      consumption_reset_reason = 'MANUAL_OPERATOR_RESET'
  WHERE period_month = TO_CHAR(NOW(), 'YYYY-MM');
"

# 3. Record the reset in audit_logs (required for ADR-006 append-only invariant)
psql $DATABASE_URL -c "
  INSERT INTO audit_logs (action_code, actor_type, detail_json)
  VALUES (
    'AI_TOKEN_BUDGET_MANUAL_RESET',
    'operator',
    '{\"reason\": \"manual reset approved by PoC owner\", \"prev_monthly_in\": <VALUE>, \"prev_monthly_out\": <VALUE>}'
  );
"

# 4. Restart the API to clear the in-memory accumulator cache
systemctl restart harness-api  # or kubectl rollout restart deployment/harness-api
```

**Important**: The `audit_logs` table must never be truncated or modified. The reset only zeroes
the accumulator counter in `ai_jobs`; the historical call records in `audit_logs` are permanent
(ADR-006 append-only trigger).

---

## 7. Related Documents
- `docs/architecture/ADR-005_dual_llm_quarantine.md` — per-agent token budget reference
- `docs/architecture/ADR-007_validator_contract_specs.md §1` — `external_dependency_attestation.py` per-window cap
- `docs/ai/AI-06_nist_ai_rmf_mapping.md` — MS-2.7 performance metric
- `docs/observability/OBS-02_audit_action_codes.md` — `AI_CALL_BUDGET_THROTTLED`, `AI_TOKEN_BUDGET_MANUAL_RESET` codes
- `scripts/external_dependency_attestation.py` — exit code 4 (token budget exhausted)
