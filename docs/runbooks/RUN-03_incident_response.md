# RUN-03 — PoC Incident Response Runbook

**Runbook ID:** RUN-03  
**Subject:** Operational Incident Response — Authentication Lock, Demo Abort, Token Budget Breach, Audit Chain Break  
**Scope:** Harness PoC production-like environment (Stage 6+)  
**Relates to:** REG-05 (security), REG-06 (PoC governance), ADR-006 (audit append-only), RUN-11 (token budget)  
**Authored:** 2026-05-17 (Wave 5, final operations handoff)  
**Note:** This runbook is for PoC operational support. Production incidents require separate incident command escalation per enterprise SOC2/ISMS procedures.

---

## 1. Overview

The Harness PoC is an internet-exposed demonstration of financial-services workflow automation. During demo or acceptance runs, four critical failure modes may occur:

1. **Authentication Lock** — Rate limit breach or password policy violation locks employee accounts.
2. **Demo Abort** — PoC_AUTO_APPROVAL governance gate detects unsafe state; all auto-approval paths reject.
3. **Token Budget Breach** — Azure LLM token consumption exhausted; all AI calls fail-closed.
4. **Audit Chain Break** — Database trigger failure or permission regression prevents audit rows from persisting.

Each has a runbook below. **Severity escalates from Demo Abort (pause demo) → Token Breach (demo degraded) → Audit Break (CRITICAL, halt all operations).**

---

## 2. Incident: Authentication Lock

### 2.1 Detection

**Symptoms:**
- Employee cannot log in: `POST /auth/login` returns `401 Unauthorized` with body `{"error": "account_locked", "locked_until": "2026-05-17T16:45:00Z"}`.
- Multiple failed login attempts in rapid succession (within 1 minute).

**Root causes:**
- Rate limit breach: `auth_login_*` action code audit rows show ≥10 failed attempts from same IP+username in 60 seconds.
- Password policy violation: account created with weak password, then first login attempt triggers policy check.

### 2.2 Resolution

**Step 1: Verify rate limit vs policy**
```bash
# SSH to API server
ssh deploy@harness-api.internal

# Check audit log for login failures (last 10 min)
psql -U harness_audit -d wm_db -c "
  SELECT created_at, action_code, actor_username, detail_json->>'error'
  FROM audit_logs
  WHERE action_code IN ('auth_login_failed', 'auth_login_rate_limit_exceeded')
    AND created_at >= NOW() - INTERVAL '10 min'
  ORDER BY created_at DESC
  LIMIT 20;
"
```

**If rate limit breach:**
```bash
# Wait 60 seconds for the rate limit window to reset (per REG-05 T292)
# OR manually reset the employee's failed-attempt counter in Redis:
redis-cli -a "${REDIS_PASSWORD}" \
  DEL "auth:login_attempts:${EMPLOYEE_EMAIL}:$(date +%s -d 'now - 1 minute')"

# Notify employee: "Your account is temporarily locked due to rate limiting. Please try again after 60 seconds."
```

**If password policy violation:**
```bash
# Generate temporary password (≥12 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special):
TEMP_PASS="HarnessTempAuth!$(date +%s | tail -c 6)"

# Admin must manually reset the employee's password (via secure channel, not email):
psql -U postgres -d wm_db << 'EOF'
/* sql_id: reset_auth_lock_password */
ALTER USER harness_app LOGIN;
UPDATE employees SET password_reset_required=true, failed_login_count=0
  WHERE email='employee@example.com';
EOF

# Notify employee to use $TEMP_PASS on next login; they will be prompted to change it immediately.
```

**Step 3: Verify unlock**
```bash
# Test login with curl
curl -X POST https://harness-api.internal/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"employee@example.com","password":"<new-password>"}' \
  -w '\nHTTP Status: %{http_code}\n'

# Expected: 200 with JWT token
```

### 2.3 Escalation

- **If unlock fails after 2 attempts:** Escalate to the API on-call engineer (see §5 Contact Matrix).
- **If multiple accounts locked simultaneously:** Possible coordinated attack or configuration drift; halt demo, escalate to tech lead.

---

## 3. Incident: Demo Abort

### 3.1 Detection

**Symptoms:**
- Employee clicks "Simulate Order Approval" button; UI shows: `"This action is blocked. PoC governance check failed: demo_mode flag is disabled or expired."` HTTP 403.
- All `/api/simulations/*` endpoints return `403 Forbidden` with body `{"error": "poc_auto_approval_disabled_or_expired"}`.

**Root causes:**
- `system_flags.demo_mode` row has `enabled=false` or `expires_at` is in the past (per ADR-004, V020).
- PoC_AUTO_APPROVAL access token was revoked (e.g., policy change mid-demo).

### 3.2 Resolution

**Step 1: Check demo_mode flag**
```bash
ssh deploy@harness-api.internal

psql -U harness_audit -d wm_db << 'EOF'
/* sql_id: check_demo_mode_flag */
SELECT id, enabled, expires_at, updated_by, detail_json->'change_reason'
FROM system_flags
WHERE flag_name = 'demo_mode'
ORDER BY updated_at DESC
LIMIT 1;
EOF
```

**If `enabled=false`:**
```bash
# Re-enable demo mode with 24-hour expiry
psql -U harness_admin -d wm_db << 'EOF'
/* sql_id: reenable_demo_mode */
UPDATE system_flags
SET enabled=true, expires_at=NOW() + INTERVAL '24 hours', updated_by='ops-support'
WHERE flag_name='demo_mode'
  AND updated_at=(SELECT MAX(updated_at) FROM system_flags WHERE flag_name='demo_mode');

/* sql_id: audit_demo_mode_reenable */
INSERT INTO audit_logs (id, action_code, actor_role, actor_username, detail_json, created_at)
VALUES (
  gen_random_uuid(),
  'system_flag_toggled',
  'harness_admin',
  'ops-support',
  jsonx('{"flag":"demo_mode","action":"reenable","reason":"Demo abort recovery"}'),
  NOW()
);
EOF
```

**If `expires_at` is past:**
```bash
# Extend expiry by 24 hours
psql -U harness_admin -d wm_db << 'EOF'
/* sql_id: extend_demo_mode_expiry */
UPDATE system_flags
SET expires_at=NOW() + INTERVAL '24 hours', updated_by='ops-support'
WHERE flag_name='demo_mode';
EOF
```

**Step 2: Verify fix**
```bash
# Test the simulation endpoint (no actual order, just verify 403 is gone)
curl -X POST https://harness-api.internal/api/simulations \
  -H 'Authorization: Bearer <valid-jwt>' \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"...","items":[]}' \
  -w '\nHTTP Status: %{http_code}\n'

# Expected: 200 (or 422 for validation, not 403)
```

### 3.3 Escalation

- **If demo_mode cannot be re-enabled:** Check PostgreSQL account separation (harness_admin role permissions per SEC-04); escalate to DBA.
- **If re-enabling succeeds but 403 persists:** Possible JWT token revocation; ask employee to re-authenticate (`GET /auth/refresh`).

---

## 4. Incident: Token Budget Breach

### 4.1 Detection

**Symptoms:**
- AI endpoint returns `503 Service Unavailable` with body: `{"error":"AI_TOKEN_BUDGET_EXHAUSTED","retry_after":"2026-06-17T00:00:00Z"}`.
- Dashboard shows `AI 운영현황` meter at 100% (or beyond if monitoring lag).
- Audit log shows `ai_call_budget_abort` action codes.

**Root cause:**
- Azure LLM monthly token ceiling (per RUN-11 §3) reached 100% (default 560K input + 112K output).

### 4.2 Resolution

**Step 1: Verify token budget status**
```bash
ssh deploy@harness-api.internal

# Check audit ledger (past 24 hours)
psql -U harness_audit -d wm_db << 'EOF'
/* sql_id: audit_token_consumption_24h */
SELECT
  DATE_TRUNC('hour', created_at) AS hour,
  detail_json->'token_consumption'->>'agent' AS agent,
  SUM((detail_json->'token_consumption'->>'tokens_in')::int) AS total_in,
  SUM((detail_json->'token_consumption'->>'tokens_out')::int) AS total_out
FROM audit_logs
WHERE action_code IN ('AI_CALL_SUCCEEDED', 'AI_CALL_FAILED', 'AI_CALL_BUDGET_THROTTLED')
  AND created_at >= NOW() - INTERVAL '24 hours'
GROUP BY 1, 2
ORDER BY 1 DESC, total_in DESC;
EOF

# Check remaining headroom
grep -E "AZURE_TOKEN_CEILING|AZURE_TOKEN_ALERT" <repo-root>/.env
```

**If breach confirmed:**
```bash
# Option A: Wait for month rollover (automatic reset at 2026-06-01 00:00:00 UTC)
# Notify demo participants: "AI features are temporarily unavailable. Full service resumes after 2026-05-31 EOD."

# Option B: Emergency reset (requires tech lead approval + audit log entry)
# Contact on-call engineer to execute manual reset procedure per RUN-11 §6.
```

**Step 2: Degrade gracefully**
```bash
# Tell the API team to set environment variable for demo run:
# export AZURE_TOKEN_ABORT_MODE=cassette_only

# This causes all subsequent AI calls to use pre-recorded cassettes instead of live Azure calls.
# Demo can continue with canned responses.
```

### 4.3 Escalation

- **If budget breach occurs before acceptance run is scheduled to complete:** Escalate to Wave 5 integrator immediately. May invoke cutline-negotiation gate (ralplan §14) to defer lower-priority AI agents.
- **If breach is due to runaway loop or test:** Investigate and kill the offending batch job; document in post-mortem.

---

## 5. Incident: Audit Chain Break

### 5.1 Detection

**Symptoms (CRITICAL):**
- Employee performs an action (login, order approval, etc.); action should emit an audit row, but audit log is empty or frozen at a prior timestamp.
- API logs show: `ERROR: audit_logs TRUNCATE denied (PoC append-only invariant)` or `permission denied for table audit_logs`.
- `POST /api/simulations/{id}/approve` returns `500 Internal Server Error` with body `{"error":"audit_persistence_failed"}`.

**Root cause:**
- V008/V019 append-only triggers disabled or removed (should never happen; indicates migration/rollback error or operator mistake).
- Privilege REVOKE on audit_logs was reversed, allowing unauthorized UPDATE/DELETE.
- PostgreSQL crashed or audit_logs table corrupted.

### 5.2 Resolution

**HALT all operations immediately. This is a data-integrity failure.**

**Step 1: Verify trigger state**
```bash
ssh deploy@harness-api.internal

psql -U postgres -d wm_db << 'EOF'
/* sql_id: verify_audit_triggers_exist */
SELECT trigger_name, event_object_table, event_manipulation, tgenabled
FROM information_schema.triggers
WHERE trigger_schema='public' AND event_object_table='audit_logs'
ORDER BY trigger_name;

/* Expected output:
trg_audit_logs_no_delete | audit_logs | DELETE | O
trg_audit_logs_no_truncate | audit_logs | TRUNCATE | O
trg_audit_logs_no_update | audit_logs | UPDATE | O
*/
EOF
```

**If triggers are DISABLED (tgenabled='D'):**
```bash
# This is a serious problem. Do not re-enable triggers without investigation.
# Escalate immediately to the DBA and Wave 5 integrator.

psql -U postgres -d wm_db << 'EOF'
/* sql_id: audit_trigger_integrity_check */
-- Do NOT modify. Call DBA immediately.
SELECT COUNT(*) as audit_row_count FROM audit_logs;
SELECT COUNT(*) as potentially_orphaned_rows FROM audit_logs
  WHERE action_code NOT IN (SELECT action_code FROM audit_action_codes);
EOF
```

**If triggers are ENABLED (tgenabled='O'):**
```bash
# Triggers are healthy. Check if UPDATE/DELETE somehow succeeded anyway.
psql -U postgres -d wm_db << 'EOF'
/* sql_id: audit_immutability_check */
SELECT COUNT(*) as rows_modified_in_last_hour
FROM audit_logs
WHERE updated_at > NOW() - INTERVAL '1 hour'
  OR (updated_at IS NOT NULL AND updated_at != created_at);

/* Expected: 0 (audit rows are created once, never updated) */
EOF
```

**Step 2: Restore from backup**

If audit rows were deleted despite triggers:
```bash
# STOP the API server immediately
systemctl stop harness-api

# Restore from the last clean backup (typically daily automated backup)
# This operation requires:
#   1. Backup location and credentials
#   2. Write-lock on the database (no other connections)
#   3. Verification of backup integrity before restore

# Contact the on-call DBA with:
#   - Time of the suspected corruption
#   - Last clean backup timestamp
#   - Confirmation to proceed with restore (this will lose recent transactions)

# After restore, verify:
psql -U harness_audit -d wm_db -c "
  SELECT COUNT(*) as audit_rows_restored, MAX(created_at) as latest_audit_timestamp
  FROM audit_logs;
"

# Restart the API server
systemctl start harness-api
```

### 5.3 Escalation

**CRITICAL INCIDENT — Escalate immediately to:**
- Wave 5 integrator (on-call via §5 Contact Matrix)
- Tech lead
- DBA (for backup/restore coordination)
- PoC owner (for user notification)

**Do not resume demo until audit chain integrity is verified.**

---

## 6. Contact Matrix

| Incident | Primary | Secondary | Channel |
|---|---|---|---|
| Auth Lock | API on-call | Tech lead | Slack `#harness-ops-critical` + phone |
| Demo Abort | Demo facilitator (pause) | Tech lead | Slack + in-person |
| Token Breach | Wave 5 integrator | Tech lead + Finance (cost notification) | Slack + email |
| Audit Chain Break | **CRITICAL** DBA | Wave 5 integrator + Tech lead | Slack **@channel** + phone + email |

**On-call rotation:** See `.env` file or `/api/health/config` for current on-call contact info (never hardcode in docs).

---

## 7. Verification Checklist

After resolving any incident:

- [ ] Root cause documented in `.omx/incidents/` with timestamp and resolution steps.
- [ ] Audit log shows the incident action code (`auth_login_rate_limit_exceeded`, `system_flag_toggled`, `ai_call_budget_abort`, `audit_chain_integrity_alert`).
- [ ] Employee/user can reproduce the original action and it succeeds.
- [ ] No related errors in API logs (`<repo-root>/.omx/logs/runtime/api.log`).
- [ ] Incident marked resolved in Slack thread; all participants notified.

---

## 8. 운영 격상 후보 (Ops Uplift Candidates)

Beyond PoC scope; candidate features for production handoff:

- **Automated incident detection:** SIEM rules to trigger PagerDuty alerts on audit_logs INSERT failures, token budget thresholds, auth lock patterns.
- **Self-service password reset:** LDAP/Active Directory integration for employee password changes without admin intervention.
- **Token budget auto-refill:** Approval workflow for emergency Azure token cap increases during demo window.
- **Audit chain forensics:** Hash-chain verification view for regulatory post-incident review.
- **Runbook automation:** Infrastructure-as-code (Ansible/Terraform) to redeploy clean PoC image if audit corruption cannot be recovered.

---

## 9. Reference

- **REG-05 §4** — PoC security baseline (auth locks, rate limiting)
- **REG-06 §5** — PoC governance (demo_mode flag, auto-approval guards)
- **ADR-006 Layers A/B/C** — Audit append-only invariant (triggers, privileges, partition deferral)
- **RUN-11 §3~5** — Token budget thresholds and alert recipients
- **SEC-04** — PostgreSQL account separation (harness_admin role permissions)
