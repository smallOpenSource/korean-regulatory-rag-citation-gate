# RUN-10 — PoC Final Operations Handoff

**Runbook ID:** RUN-10  
**Subject:** PoC Final Operations Handoff — Environment Setup, Secrets Rotation, Monitoring, Escalation  
**Scope:** Harness PoC production-like environment (Stage 6+), ops team transition  
**Relates to:** RUN-03 (incident response), RUN-04~09 (hardening runbooks), ADR-003 (dependency gate), REG-06 (PoC governance)  
**Authored:** 2026-05-17 (Wave 5, final operations handoff)  
**Note:** This runbook is for PoC operations team onboarding. Production operations require enterprise ITSM/SOC2 escalation per separate runbooks.

---

## 1. Overview

The Harness PoC is handed off to the operations team after acceptance testing completes. The ops team assumes responsibility for:

1. **Environment configuration** — `.env` file management, secrets storage, dependency credentials
2. **Secrets rotation** — quarterly Azure LLM tokens, API keys, database passwords, JWT signing keys
3. **Monitoring and alerting** — dashboard health checks, log aggregation, alert routing
4. **Daily operations** — health checks, log review, incident response
5. **Compliance and audit** — monthly attestation, audit log retention, data privacy verification

This runbook establishes the handoff checklist, ops procedures, and escalation paths.

---

## 2. Pre-Handoff Checklist

Before accepting PoC operations, verify:

### 2.1 Access and Credentials

| Item | Verification | Pass/Fail |
|---|---|---|
| SSH access to API server (`harness-api.internal`) | Test: `ssh deploy@harness-api.internal 'hostname'` | — |
| Database admin access (PostgreSQL) | Test: `psql -U postgres -d wm_db -c "SELECT version();"` | — |
| Redis admin access | Test: `redis-cli -a $REDIS_PASSWORD PING` | — |
| Azure LLM credentials (AZURE_OPENAI_KEY, endpoint) | Test: `curl -s -H "api-key: $AZURE_OPENAI_KEY" https://...embeddings HTTP/1.1` returns 2xx | — |
| Batch provider credentials (BROKER, PyKRX, etc.) | Test: `scripts/external_dependency_attestation.py --env-profile poc` exits 0 | — |
| SMTP credentials (if email enabled) | Test: `nc -zv smtp.example.com 587` | — |
| PoC admin account email/password | Stored in secure vault (e.g., 1Password, AWS Secrets Manager) | — |
| On-call rotation contact info (Slack, phone) | Verify against `.env` or contact-matrix.json | — |

### 2.2 Environment File

Verify `.env` file exists and is **not committed to git**:

```bash
# Check .env is in .gitignore
grep -w .env <repo-root>/.gitignore

# Verify .env has all required variables (grep for HARNESS_* and AZURE_*)
wc -l <repo-root>/.env
# Expected: ~150–200 lines
```

### 2.3 Monitoring and Dashboards

Verify monitoring infrastructure is live:

| Component | Endpoint/Command | Expected |
|---|---|---|
| Prometheus | `curl -s http://localhost:9090/api/v1/query?query=up \| jq .data.result` | List of targets with `value: ["1", "..."]` |
| Grafana | `curl -s http://localhost:3000/api/health` | `{"database":"ok","version":"..."}` |
| Application logs | `tail -f <repo-root>/.omx/logs/runtime/api.log` | New entries every 10–60 seconds |
| Audit logs | `psql -U harness_audit -d wm_db -c "SELECT COUNT(*) FROM audit_logs;"` | Row count > 0 |

---

## 3. Environment Variables Checklist

Before go-live, confirm all critical `.env` variables are set. Use this table as a reference:

### 3.1 FastAPI Core

| Variable | Example | Required | Rotation | Notes |
|---|---|---|---|---|
| `APP_ENV` | `production` | ✓ | — | Must be `production` or `stage`; never `development` |
| `APP_HOST` | `0.0.0.0` | ✓ | — | Bind address |
| `APP_PORT` | `8000` | ✓ | — | FastAPI internal port (nginx proxies 443→8000) |
| `APP_LOG_LEVEL` | `INFO` | ✓ | — | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `APP_CORS_ORIGINS` | `https://harness.internal.example.com` | ✓ | — | Comma-separated list; include all UI origins |

### 3.2 Authentication (REG-05 T280–T299)

| Variable | Example | Required | Rotation | Notes |
|---|---|---|---|---|
| `JWT_SECRET_KEY` | `<64-char hex>` | ✓ | Quarterly | Used to sign JWT tokens; rotate every 90 days |
| `JWT_ALGORITHM` | `HS256` | ✓ | — | HMAC with SHA-256 |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | ✓ | — | Access token lifetime |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | `7` | ✓ | — | Refresh token lifetime |
| `AUTH_REFRESH_COOKIE_SECURE` | `true` | ✓ | — | Must be `true` in production |
| `AUTH_REFRESH_COOKIE_SAMESITE` | `lax` | ✓ | — | Prevent CSRF; use `lax` or `strict` |
| `AUTH_RATE_LIMIT_ENABLED` | `true` | ✓ | — | Rate limit protection for `/auth/login` |
| `AUTH_RATE_LIMIT_ATTEMPTS` | `10` | ✓ | — | Max login attempts per window |
| `AUTH_RATE_LIMIT_WINDOW_SECONDS` | `60` | ✓ | — | Rate limit window (seconds) |

### 3.3 Database (REG-05 T285–T289)

| Variable | Example | Required | Rotation | Notes |
|---|---|---|---|---|
| `DATABASE_URL` | `postgresql://harness_app:...@localhost:5432/wm_db` | ✓ | Quarterly (password) | Use `harness_app` role; never `postgres` |
| `DATABASE_AUDIT_USER` | `harness_audit` | ✓ | — | Read-only audit role |
| `DATABASE_ADMIN_USER` | `harness_admin` | ✓ | Quarterly (password) | For migrations only; keep offline |
| `DATABASE_POOL_SIZE` | `20` | ✓ | — | Max connections |
| `DATABASE_ECHO_SQL` | `false` | ✓ | — | Set to `true` only for debugging; disables in production |

### 3.4 Redis (REG-05 T290–T292)

| Variable | Example | Required | Rotation | Notes |
|---|---|---|---|---|
| `REDIS_HOST` | `localhost` | ✓ | — | Redis server address |
| `REDIS_PORT` | `6379` | ✓ | — | Redis port |
| `REDIS_PASSWORD` | `<64-char random>` | ✓ | Quarterly | Strong password; never hardcode in logs |
| `REDIS_DB` | `0` | ✓ | — | Database index |
| `REDIS_TIMEOUT_SECONDS` | `5` | ✓ | — | Connection timeout |

### 3.5 Azure LLM (RUN-11 §3, token budget)

| Variable | Example | Required | Rotation | Notes |
|---|---|---|---|---|
| `AZURE_OPENAI_API_KEY` | `<36-char UUID>` | ✓ | Quarterly | Rotate every 90 days; use key rotation in Azure Portal |
| `AZURE_OPENAI_ENDPOINT` | `https://<your-resource>.openai.azure.com/` | ✓ | — | Azure OpenAI service endpoint |
| `AZURE_OPENAI_DEPLOYMENT_EMBEDDING` | `harness-embedding-3-large` | ✓ | — | Embedding model deployment name |
| `AZURE_OPENAI_DEPLOYMENT_LLM` | `harness-gpt4-turbo` | ✓ | — | LLM deployment name (GPT-4 Turbo or GPT-4o) |
| `AZURE_TOKEN_CEILING_MONTHLY` | `560000` | ✓ | — | Monthly input token limit |
| `AZURE_TOKEN_ALERT_PERCENT` | `80` | ✓ | — | Alert threshold (% of ceiling) |
| `AZURE_TOKEN_ABORT_MODE` | `fail_closed` | ✓ | — | `fail_closed` (halt AI) or `cassette_only` (pre-recorded responses) |

### 3.6 Email (RUN-09 batch scheduler, notification delivery)

| Variable | Example | Required | Rotation | Notes |
|---|---|---|---|---|
| `SMTP_HOST` | `smtp.example.com` | ✓ | — | SMTP server |
| `SMTP_PORT` | `587` | ✓ | — | SMTP port (usually 587 TLS, 465 SSL) |
| `SMTP_USERNAME` | `harness-noreply@example.com` | ✓ | — | SMTP authentication user |
| `SMTP_PASSWORD` | `<generated by sysadmin>` | ✓ | Quarterly | Rotate with email provider |
| `SMTP_USE_TLS` | `true` | ✓ | — | Enable STARTTLS |
| `SMTP_FROM_ADDRESS` | `harness-noreply@example.com` | ✓ | — | Sender address for transactional mail |
| `EMAIL_ENABLED` | `true` | ✓ | — | Master gate for email notifications |

### 3.7 PoC Governance (ADR-004, REG-06 §5)

| Variable | Example | Required | Rotation | Notes |
|---|---|---|---|---|
| `POC_AUTO_APPROVAL_ENABLED` | `true` | ✓ | — | PoC-only flag; gates simulation endpoints |
| `POC_DEMO_MODE_ENABLED` | `true` | ✓ | — | Enable demo features (safe order simulation) |
| `POC_DEMO_MODE_EXPIRES_AT` | `2026-05-31T23:59:59Z` | ✓ | — | Demo mode expiration (UTC) |

### 3.8 Observability and Auditing

| Variable | Example | Required | Rotation | Notes |
|---|---|---|---|---|
| `AUDIT_LOG_ENABLED` | `true` | ✓ | — | Enable audit trail (never disable) |
| `AUDIT_SENSITIVE_FIELDS_REDACTED` | `true` | ✓ | — | Redact SSN, account numbers from logs |
| `LOG_RETENTION_DAYS` | `90` | ✓ | — | Application log retention (RUN-08 for audit logs) |

---

## 4. Secrets Rotation Schedule

Secrets must be rotated on a fixed calendar to prevent key compromise.

### 4.1 Quarterly Rotation (Every 90 days: Jan, Apr, Jul, Oct)

**What:** Azure LLM API key, JWT secret, database password, Redis password, SMTP password  
**Who:** Ops team + backup (stored in escalation contacts)  
**Procedure:**

1. **Generate new secrets** (use a secure password generator):
   ```bash
   # Generate 64-char random hex for JWT_SECRET_KEY
   openssl rand -hex 32
   
   # Generate 64-char random password for database/Redis
   openssl rand -base64 48 | tr -d '\n'
   ```

2. **Update .env file** (offline, in a secure editor):
   ```bash
   # Edit <repo-root>/.env on a secure machine (never via SSH)
   # Replace:
   # JWT_SECRET_KEY=<old_key>
   # with:
   # JWT_SECRET_KEY=<new_key>
   ```

3. **Update backend services:**
   ```bash
   # Restart API service (invalidates old JWTs; users must re-login)
   ssh deploy@harness-api.internal 'systemctl restart harness-api'
   
   # Verify health
   curl -s https://harness-api.internal/health | jq .
   ```

4. **Update database role password:**
   ```bash
   ssh deploy@harness-api.internal
   psql -U postgres -d wm_db << 'EOF'
   /* sql_id: rotate_app_password */
   ALTER USER harness_app WITH PASSWORD 'new_password_here';
   EOF
   ```

5. **Update Azure LLM key in Azure Portal:**
   - Navigate to Azure OpenAI → Keys and Endpoint → Rotate Primary Key
   - Verify new key works: `curl -H "api-key: $NEW_KEY" https://.../embeddings`
   - Update `.env` with new key

6. **Update SMTP password with email provider.**

7. **Document rotation in audit log:**
   ```bash
   ssh deploy@harness-api.internal
   psql -U harness_audit -d wm_db << 'EOF'
   INSERT INTO audit_logs (id, action_code, actor_role, actor_username, detail_json, created_at)
   VALUES (
     gen_random_uuid(),
     'secrets_rotated_quarterly',
     'ops_team',
     'ops-<username>',
     jsonb_build_object('rotated_keys', ARRAY['JWT_SECRET_KEY', 'DATABASE_PASSWORD', 'REDIS_PASSWORD', 'AZURE_API_KEY', 'SMTP_PASSWORD']),
     NOW()
   );
   EOF
   ```

8. **Verify all services are healthy:**
   - Check API logs for JWT decode errors
   - Check database connections in `pg_stat_activity`
   - Check Redis connectivity
   - Verify AI endpoint calls succeed

### 4.2 Annual Key Regeneration (January or post-incident)

**What:** Complete re-issuance of all keys after security audit  
**Who:** Ops team + Security team + DBA  
**Procedure:**

- Same as Quarterly Rotation, but all keys are regenerated simultaneously
- Notify all stakeholders 48 hours in advance
- Plan for ~30 minutes of API unavailability (users re-login, batch jobs restart)
- Verify no data loss in audit logs post-rotation

---

## 5. Monitoring and Alerting

The Harness PoC exposes metrics and logs via Prometheus + Grafana and centralizes audit logs in PostgreSQL.

### 5.1 Dashboards and Metrics

| Dashboard | Location | Refresh | Key Metrics |
|---|---|---|---|
| **PoC Health** | `http://localhost:3000/d/harness-poc-health` | 30 sec | API uptime, DB connections, Redis uptime, token budget |
| **Authentication** | `http://localhost:3000/d/harness-auth` | 1 min | Login success/failure rate, rate limit triggers, JWT validation errors |
| **Batch Scheduler** | `http://localhost:3000/d/harness-batch` | 5 min | RAG refresh completion time, derived stage duration, house-view generation lag |
| **Audit Compliance** | `http://localhost:3000/d/harness-audit` | 1 hour | Audit row count, append-only violations, data privacy redaction checks |

### 5.2 Alert Thresholds

| Alert | Threshold | Action |
|---|---|---|
| **API Down** | No response for 2 minutes | Page on-call engineer; check `/health` endpoint |
| **Database Connection Pool Exhausted** | Connections ≥ 18/20 | Investigate slow queries; restart API if stuck |
| **Redis Down** | Connection timeout | Page on-call engineer; check Redis service status |
| **Token Budget at 80%** | `ai_call_usage >= 0.8 * AZURE_TOKEN_CEILING_MONTHLY` | Notify tech lead; consider degrading to cassette-only mode |
| **Token Budget at 95%** | `ai_call_usage >= 0.95 * AZURE_TOKEN_CEILING_MONTHLY` | CRITICAL: Halt AI calls; notify Wave 5 integrator |
| **Audit Log Integrity Alert** | Trigger disabled or INSERT failure | CRITICAL: Page DBA immediately; see RUN-03 §5 |
| **Authentication Lock** | ≥10 failed logins in 60 sec from same IP | Investigate; may indicate brute-force or user password reset needed |
| **High Error Rate** | >5% of API requests returning 5xx | Page on-call engineer; check application logs |

### 5.3 Log Aggregation

Centralize logs in a single location for post-incident review:

```bash
# Application logs (API, batch scheduler)
tail -f <repo-root>/.omx/logs/runtime/api.log
tail -f <repo-root>/.omx/logs/runtime/batch.log

# System logs
journalctl -u harness-api -f
journalctl -u harness-batch -f

# Database logs (PostgreSQL)
tail -f /var/log/postgresql/postgresql-*.log

# nginx logs
tail -f /var/log/nginx/access.log /var/log/nginx/error.log

# Audit logs (primary source — PostgreSQL)
psql -U harness_audit -d wm_db << 'EOF'
SELECT action_code, COUNT(*) as count, MAX(created_at) as last_occurrence
FROM audit_logs
WHERE created_at >= NOW() - INTERVAL '1 hour'
GROUP BY action_code
ORDER BY count DESC;
EOF
```

### 5.4 Health Check Command

Run this every morning to verify the PoC is healthy:

```bash
#!/bin/bash
# <repo-root>/scripts/daily_health_check.sh

set -e

echo "=== Daily Health Check ($(date)) ==="

# 1. API health
echo "✓ Checking API..."
curl -s https://harness-api.internal/health | jq .

# 2. Database connections
echo "✓ Checking Database..."
psql -U harness_app -d wm_db -c "SELECT version(), COUNT(*) as connections FROM pg_stat_activity;" 

# 3. Redis
echo "✓ Checking Redis..."
redis-cli -a "$REDIS_PASSWORD" PING

# 4. Audit log freshness (should have entries from the past hour)
echo "✓ Checking Audit Logs..."
psql -U harness_audit -d wm_db -c "
  SELECT COUNT(*) as audit_rows_this_hour
  FROM audit_logs
  WHERE created_at >= NOW() - INTERVAL '1 hour';
"

# 5. Azure LLM connectivity (lite test)
echo "✓ Checking Azure LLM..."
curl -s -H "api-key: $AZURE_OPENAI_KEY" \
  "$AZURE_OPENAI_ENDPOINT/openai/deployments/$AZURE_OPENAI_DEPLOYMENT_EMBEDDING/embeddings?api-version=2024-02-15-preview" \
  -H "Content-Type: application/json" \
  -d '{"input":"health check"}' | jq '.usage.total_tokens'

# 6. Token budget status
echo "✓ Checking Token Budget..."
psql -U harness_audit -d wm_db -c "
  SELECT
    SUM((detail_json->'token_consumption'->>'tokens_in')::int) as total_tokens_in,
    SUM((detail_json->'token_consumption'->>'tokens_out')::int) as total_tokens_out
  FROM audit_logs
  WHERE action_code IN ('ai_call_succeeded', 'ai_call_failed')
    AND created_at >= DATE_TRUNC('month', NOW());
"

echo "=== Health Check Complete ==="
```

Run as a cron job:

```cron
# 08:00 daily
0 8 * * * <repo-root>/scripts/daily_health_check.sh >> <repo-root>/.omx/logs/daily-health-check.log 2>&1
```

---

## 6. Daily Operations Checklist

Every business day, the ops team should:

- [ ] **08:00** — Run `daily_health_check.sh` (above); review for any failures
- [ ] **10:00** — Check Grafana dashboards for anomalies (connection pool, error rate, token budget)
- [ ] **12:00** — Review audit logs for any `_failed`, `_rate_limit_exceeded`, or `_integrity_alert` action codes
- [ ] **16:00** — Verify batch scheduler jobs completed (RAG refresh, derived stages, house-view generation)
- [ ] **End of day** — Archive logs if retention threshold approaching
- [ ] **On-call** — Watch Slack `#harness-ops-critical` for alerts; respond within SLA

---

## 7. Monthly Compliance Checklist

Once per month (e.g., first business day), perform:

### 7.1 Security Compliance

- [ ] Verify `AUTH_RATE_LIMIT_ENABLED=true` (no bypass)
- [ ] Verify `APP_ENV=production` (never `development`)
- [ ] Verify no hardcoded secrets in logs or error messages
- [ ] Run `gitleaks` scan: `gitleaks detect --source <repo-root> --verbose`
- [ ] Run `OWASP ZAP` baseline scan against API (see RUN-07)
- [ ] Verify HTTPS is enforced (no plain-HTTP access to admin endpoints)

### 7.2 Data Privacy and Audit

- [ ] Verify audit logs are not truncated or deleted:
  ```bash
  psql -U postgres -d wm_db -c "
    SELECT COUNT(*) as audit_rows FROM audit_logs;
  "
  # Expected: increasing over time
  ```
- [ ] Verify sensitive fields are redacted in logs (SSN, account numbers):
  ```bash
  grep -v 'ssn\|account_number' <repo-root>/.omx/logs/runtime/api.log > /dev/null
  ```
- [ ] Verify `AUTH_SENSITIVE_FIELDS_REDACTED=true`
- [ ] Check data retention policy is being followed (see RUN-08 §5):
  ```bash
  psql -U harness_audit -d wm_db -c "
    SELECT
      DATE_TRUNC('month', created_at) as month,
      COUNT(*) as audit_rows
    FROM audit_logs
    GROUP BY 1
    ORDER BY 1 DESC
    LIMIT 12;
  "
  ```

### 7.3 Dependency Attestation

- [ ] Run external dependency attestation (see RUN-09 §3):
  ```bash
  python scripts/external_dependency_attestation.py \
    --env-profile poc \
    --allow-degraded broker,pykrx_fdr \
    --out .omx/reports/verification/ext-dep-attest.json
  ```
- [ ] Review any downgraded or unavailable providers
- [ ] Notify finance if Azure LLM token consumption exceeds budget threshold (RUN-11 §4)

### 7.4 Backup Verification

- [ ] Verify last backup completed successfully:
  ```bash
  ssh deploy@harness-api.internal 'ls -lh /backups/wm_db_*.sql.gz | tail -1'
  ```
- [ ] Test restore from backup (offline, in a staging DB):
  ```bash
  # This is a DBA task; coordinate with on-call DBA
  ssh deploy@harness-api.internal
  createdb wm_db_test
  gunzip -c /backups/wm_db_latest.sql.gz | psql -d wm_db_test
  ```

---

## 8. Escalation Contacts and Procedures

### 8.1 Escalation Matrix

| Incident | Primary | Secondary | Channel | SLA |
|---|---|---|---|---|
| API Down / 5xx errors | On-call Engineer | Tech Lead | Slack `#harness-ops-critical` + page | 15 min |
| Database Locked / Slow Queries | DBA | Tech Lead | Slack + page | 30 min |
| Redis Down | On-call Engineer | Tech Lead | Slack + page | 15 min |
| Token Budget Breach (95%+) | Wave 5 Integrator | Finance + Tech Lead | Slack `@channel` + email | 1 hour |
| Audit Chain Break (CRITICAL) | **DBA (CRITICAL)** | Wave 5 Integrator + Tech Lead | Slack `@channel` + phone | **5 min** |
| Security Incident (secrets leaked, unauthorized access) | CISO | Tech Lead + Ops Lead | Slack + email + phone | **Immediate** |

### 8.2 Incident Response Protocol

1. **Detect** — Alert triggers in Grafana or manual discovery
2. **Assess** — Determine severity (Low/Medium/High/CRITICAL)
3. **Notify** — Page primary contact; escalate if no response within SLA
4. **Remediate** — Follow incident runbook (RUN-03) or escalation contact's guidance
5. **Verify** — Confirm issue is resolved; verify audit log entry was created
6. **Document** — Post-mortem in `.omx/incidents/` directory within 24 hours

---

## 9. Post-Handoff Support

### 9.1 Wave 5 Integrator (30-day tail support)

The Wave 5 integrator remains available for 30 days post-launch to:
- Answer operational questions
- Advise on incident response
- Perform emergency remediations if ops team is blocked
- Provide knowledge transfer sessions (weekly 30 min call)

**Contact:** (See team roster in MEMORIES.md)

### 9.2 Production Handoff Preparation (NOT in PoC scope)

If the PoC is approved for production migration, the following items must be addressed:

- **Secrets management** — Migrate to enterprise vault (AWS Secrets Manager, HashiCorp Vault, Azure Key Vault)
- **Audit retention** — Extend retention policy per regulatory requirements (자본시장법 §59 = 10-year archival)
- **High availability** — Add database replication, load-balanced API instances, failover Redis
- **Disaster recovery** — Document RTO/RPO targets and test recovery procedures
- **Compliance** — Update incident response runbooks for SOC2 / ISMS / enterprise escalation procedures
- **Monitoring** — Integrate with enterprise SIEM (Splunk, Datadog, etc.)

---

## 10. Verification Checklist

After handoff is complete:

- [ ] Ops team has SSH access to API server and can run diagnostic commands
- [ ] `.env` file is secure (not in git, not world-readable)
- [ ] All critical environment variables are set and verified
- [ ] Monitoring dashboards are accessible and showing live data
- [ ] Daily health check script runs successfully
- [ ] Monthly compliance checklist has been executed at least once
- [ ] Escalation contacts are confirmed and on-call rotation is active
- [ ] Incident response runbooks (RUN-03~09) have been reviewed by ops team
- [ ] Backup and disaster recovery procedures have been documented and tested (DBA task)
- [ ] 30-day Wave 5 tail support agreement is acknowledged

---

## 11. 운영 격상 후보 (Ops Uplift Candidates)

Beyond PoC scope; candidate features for production ops:

- **Automated health check dashboard** — Self-healing alerts (auto-restart API on critical failure)
- **Secrets management integration** — Replace `.env` with enterprise vault (AWS Secrets Manager, Azure Key Vault)
- **Advanced monitoring** — Machine learning anomaly detection for token budget, error rates, connection pool
- **Disaster recovery automation** — RTO <30 min via automated failover to standby database
- **Audit log archival** — Automatically partition and compress audit logs to S3/Azure Blob for long-term retention
- **Compliance attestation** — Automated monthly report generation for regulatory audits
- **Incident automation** — PagerDuty integration, auto-escalation based on severity
- **ChatOps integration** — Slack commands for ops tasks (health checks, log queries, secrets rotation)

---

## 12. Reference

- **RUN-03** — PoC Incident Response (detection, resolution, escalation)
- **RUN-04~09** — Hardening runbooks (HTTPS, PostgreSQL, Redis, ZAP, batch scheduler, token budget)
- **ADR-003** — Dependency gate and contract verification
- **ADR-004** — PoC_AUTO_APPROVAL attestation pattern
- **ADR-006** — Audit append-only invariant (Layer A/B/C)
- **REG-05** — PoC security baseline (auth, rate limiting, HTTPS)
- **REG-06** — PoC governance (demo mode, auto-approval guards)
- **MEMORIES.md** — Ops team roster, escalation contacts, post-mortem

