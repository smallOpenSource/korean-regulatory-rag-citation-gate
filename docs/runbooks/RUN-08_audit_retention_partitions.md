# RUN-08 — Audit Log Retention Partitioning Runbook

**Runbook ID:** RUN-08  
**Subject:** Audit Log Retention Partitioning — Two-Tier Scheme (5-Year General / 10-Year Regulator-Mandated)  
**Scope:** Deferred from Wave 1 (ADR-006 Layer C); executed post-acceptance in Stage 7  
**Applies to:** Harness PoC ops-uplift phase; requires change control + offline maintenance window  
**Relates to:** ADR-006 Layers A/B/C (append-only invariant), REG-01 §3.1 (자본시장법 §59), REG-02 §3 (권유기록·면담기록), SEC-02 (retention policy)  
**Authored:** 2026-05-17 (Wave 5, deferred implementation planning)  

---

## 1. Overview

The `audit_logs` table grows unbounded during normal operations. Financial-services regulations mandate **different retention windows per audit-row category:**

- **General audit rows** (auth, API calls, system events): **5 years** (자본시장법 §54, 금소법 §32)
- **Regulator-mandated rows** (권유기록 counseling records, 면담기록 meeting records, order confirmations): **10 years** (자본시장법 §59, 금감원 감독규정)

This runbook documents the **offline migration procedure** to partition `audit_logs` into two tiers. 

**Why deferred to Stage 7:**
- Partitioning a non-empty table mid-PoC has failure modes: primary key restructuring, write-blocking window, recovery complexity.
- Layer A (V008 row-level UPDATE/DELETE triggers) + Layer B (V019 TRUNCATE + REVOKE) provide append-only protection during PoC.
- Layer C partitioning is executed offline post-acceptance under change control to minimize risk.

---

## 2. Partition Design

### 2.1 Partition Key and Strategy

**Partition method:** `PARTITION BY RANGE (created_at)`

**Partition boundary:**
- PoC acceptance run date assumed 2026-05-18.
- General partition: rows with `created_at < 2026-05-18` + **5-year cutoff** = delete after 2031-05-17.
- Extended partition: rows marked with 10-year `action_code` in the allowlist = delete after 2036-05-17.

```sql
/* sql_id: audit_logs_partition_definition */
-- Two-tier retention partitioning for audit_logs
-- General tier: 5-year retention
-- Extended tier: 10-year retention for regulator-mandated rows

-- RANGE partition on created_at
-- Partition 1: 2020-01-01 to 2025-01-01 (legacy, eligible for deletion after 2025-01-01 + 5y)
-- Partition 2: 2025-01-01 to 2026-05-18 (PoC acceptance date, 5-year expiry = 2031-05-18)
-- Partition 3: 2026-05-18 to MAXVALUE (future rows)

-- Rows marked with 10-year action_codes are retained in a separate retention_policy view:
CREATE MATERIALIZED VIEW audit_logs_extended_retention AS
SELECT id, created_at, action_code, actor_role, detail_json
FROM audit_logs
WHERE action_code IN (
  'order_confirmation_sent',
  'consultation_recommendation_recorded',
  'consultation_closing_gates_recorded',
  'suitability_assessment_recorded',
  'explanation_provided',
  'customer_consent_recorded',
  'customer_withdrawal_recorded',
  'dispute_case_opened',
  'compliance_review_passed'
  -- (REG-02 §3.1 권유기록·면담기록 set; ADR-006 Layer C defines list)
)
ORDER BY created_at DESC;

-- This materialized view is manually retained (not subject to partition purge);
-- its rows are always also in audit_logs (no duplication on retention date).
-- Downstream purge jobs check this view before deleting rows from audit_logs.
```

### 2.2 Primary Key Restructuring

**Current PK:** `audit_logs (id)` where `id` is UUID.

**Post-partition PK:** `audit_logs (id, created_at)` — composite primary key that includes the partition column.

**Rationale:** PostgreSQL partitioned tables require the partition column to be part of the primary key or any unique constraint. This ensures query routing and prevents row duplication across partitions.

```sql
/* sql_id: audit_logs_pk_restructure */
-- Composite primary key including partition column
-- Current: PRIMARY KEY (id)
-- Target: PRIMARY KEY (id, created_at)

-- This requires:
-- 1. Create new table with composite PK
-- 2. Copy rows from old table
-- 3. Drop old table
-- 4. Rename new table
-- OR use ALTER TABLE detach/attach partition dance (risky)
```

---

## 3. Offline Migration Script

**Requirements:**
- ✅ No write-locking during migration (can be long-running).
- ✅ Row-count parity before and after.
- ✅ Triggers (V008 + V019) remain enabled throughout.
- ✅ Rollback plan if migration fails mid-way.

### 3.1 Pre-Migration Verification

```bash
#!/bin/bash
# RUN-08 Pre-Migration Audit

set -e

BACKUP_DIR="/var/backups/harness/pre-partition-migration-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Verify connectivity
psql -U postgres -d wm_db -c "SELECT version();" > "$BACKUP_DIR/postgres-version.txt"

# Backup current audit_logs structure and row count
psql -U harness_audit -d wm_db << 'EOF' | tee "$BACKUP_DIR/pre-migration-audit.sql"
/* sql_id: pre_migration_row_count */
SELECT
  'audit_logs' as table_name,
  COUNT(*) as total_rows,
  MIN(created_at) as earliest_row,
  MAX(created_at) as latest_row,
  COUNT(DISTINCT action_code) as unique_action_codes
FROM audit_logs;

/* sql_id: pre_migration_action_code_distribution */
SELECT
  action_code,
  COUNT(*) as row_count,
  MIN(created_at) as earliest_row
FROM audit_logs
GROUP BY action_code
ORDER BY row_count DESC
LIMIT 20;
EOF

# Full table backup (custom format for easy selective restore)
pg_dump -U postgres -d wm_db --table=public.audit_logs --format=custom \
  > "$BACKUP_DIR/audit_logs_pre_partition.dump"

echo "Pre-migration verification complete. Backup in $BACKUP_DIR"
```

### 3.2 Migration Script (Offline Window)

**Offline window requirement:** 30 minutes of write-blocking (application downtime).

```bash
#!/bin/bash
# RUN-08 Offline Migration Script
# WARNING: This stops the API server and blocks writes for ~30 minutes.

set -e
MIGRATION_LOG="/var/log/harness/migration-$(date +%Y%m%d-%H%M%S).log"

echo "$(date) — Starting audit_logs partition migration" | tee "$MIGRATION_LOG"

# 1. STOP API server (no more writes to audit_logs)
echo "$(date) — Stopping API server..." | tee -a "$MIGRATION_LOG"
systemctl stop harness-api
sleep 5  # Allow graceful shutdown

# 2. Verify no active connections
ACTIVE_CONNS=$(psql -U postgres -d wm_db -c \
  "SELECT COUNT(*) FROM pg_stat_activity WHERE datname='wm_db' AND state!='idle';")
if [ "$ACTIVE_CONNS" -gt 0 ]; then
  echo "ERROR: $ACTIVE_CONNS active connections still on wm_db" | tee -a "$MIGRATION_LOG"
  systemctl start harness-api
  exit 1
fi

# 3. Create new partitioned table
psql -U postgres -d wm_db << 'EOF' | tee -a "$MIGRATION_LOG"
/* sql_id: create_partitioned_audit_logs */
-- Create partitioned replacement table
CREATE TABLE audit_logs_partitioned (
  id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  action_code VARCHAR(100) NOT NULL,
  actor_role VARCHAR(50),
  actor_username VARCHAR(255),
  detail_json JSONB,
  PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Partition 1: Before 2025-01-01 (legacy)
CREATE TABLE audit_logs_p1 PARTITION OF audit_logs_partitioned
  FOR VALUES FROM ('2020-01-01') TO ('2025-01-01');

-- Partition 2: 2025-01-01 to 2026-05-18 (5-year expiry: 2031-05-18)
CREATE TABLE audit_logs_p2 PARTITION OF audit_logs_partitioned
  FOR VALUES FROM ('2025-01-01') TO ('2026-05-18');

-- Partition 3: 2026-05-18 onwards (5-year expiry: 2031-05-18)
CREATE TABLE audit_logs_p3 PARTITION OF audit_logs_partitioned
  FOR VALUES FROM ('2026-05-18') TO (MAXVALUE);

-- Copy indexes and constraints from original
/* Index on created_at for range queries */
CREATE INDEX idx_audit_logs_created_at ON audit_logs_partitioned (created_at DESC);
/* Index on action_code for filtering */
CREATE INDEX idx_audit_logs_action_code ON audit_logs_partitioned (action_code);
/* Index on actor_username for user audit trails */
CREATE INDEX idx_audit_logs_actor_username ON audit_logs_partitioned (actor_username);
EOF

# 4. Copy rows (MUST be inside a transaction with no schema changes concurrent)
echo "$(date) — Copying rows from audit_logs to audit_logs_partitioned..." | tee -a "$MIGRATION_LOG"
psql -U postgres -d wm_db << 'EOF' | tee -a "$MIGRATION_LOG"
/* sql_id: copy_audit_logs_to_partitioned */
BEGIN;

INSERT INTO audit_logs_partitioned
  SELECT id, created_at, action_code, actor_role, actor_username, detail_json
  FROM audit_logs;

-- Row-count parity check (MUST match before continuing)
DO $$
DECLARE
  old_count BIGINT;
  new_count BIGINT;
BEGIN
  SELECT COUNT(*) INTO old_count FROM audit_logs;
  SELECT COUNT(*) INTO new_count FROM audit_logs_partitioned;
  IF old_count != new_count THEN
    RAISE EXCEPTION 'Row count mismatch: old=%, new=%', old_count, new_count;
  ELSE
    RAISE NOTICE 'Row count verified: % rows copied', old_count;
  END IF;
END $$;

COMMIT;
EOF

# 5. Rename tables (atomic rename to swap in partitioned version)
echo "$(date) — Swapping tables..." | tee -a "$MIGRATION_LOG"
psql -U postgres -d wm_db << 'EOF' | tee -a "$MIGRATION_LOG"
/* sql_id: rename_audit_logs_tables */
BEGIN;

-- Rename old table to backup
ALTER TABLE audit_logs RENAME TO audit_logs_unpartitioned_backup;

-- Rename new partitioned table to production name
ALTER TABLE audit_logs_partitioned RENAME TO audit_logs;

-- Restore V008+V019 triggers on the new partitioned table
-- (triggers were automatically inherited by child partitions during CREATE)
ALTER TABLE audit_logs ENABLE TRIGGER trg_audit_logs_no_update;
ALTER TABLE audit_logs ENABLE TRIGGER trg_audit_logs_no_delete;
ALTER TABLE audit_logs ENABLE TRIGGER trg_audit_logs_no_truncate;

COMMIT;
EOF

# 6. Restore privileges (Layer B: REVOKE/GRANT from V019)
echo "$(date) — Restoring privileges..." | tee -a "$MIGRATION_LOG"
psql -U postgres -d wm_db << 'EOF' | tee -a "$MIGRATION_LOG"
/* sql_id: restore_audit_logs_privileges_v019 */
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC;
GRANT INSERT ON audit_logs TO harness_app;
GRANT INSERT ON audit_logs TO harness_batch;
GRANT SELECT ON audit_logs TO harness_audit;
GRANT SELECT ON audit_logs TO harness_admin;
EOF

# 7. Verify partition health
echo "$(date) — Verifying partition health..." | tee -a "$MIGRATION_LOG"
psql -U harness_audit -d wm_db << 'EOF' | tee -a "$MIGRATION_LOG"
/* sql_id: verify_partition_health */
SELECT
  'audit_logs' as table_name,
  COUNT(*) as total_rows,
  MIN(created_at) as earliest_row,
  MAX(created_at) as latest_row
FROM audit_logs;

SELECT
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE tablename LIKE 'audit_logs%'
ORDER BY tablename;
EOF

# 8. Restart API server
echo "$(date) — Restarting API server..." | tee -a "$MIGRATION_LOG"
systemctl start harness-api
sleep 5

# 9. Verify API can write audit rows
echo "$(date) — Verifying API can write to partitioned audit_logs..." | tee -a "$MIGRATION_LOG"
curl -s http://127.0.0.1:8000/health | grep -q '"status":"healthy"' && \
  echo "$(date) — API healthy; migration complete" | tee -a "$MIGRATION_LOG" || \
  (echo "ERROR: API health check failed" | tee -a "$MIGRATION_LOG"; exit 1)

echo "$(date) — Migration complete. Old table backed up as audit_logs_unpartitioned_backup" | tee -a "$MIGRATION_LOG"
```

---

## 4. Retention Purge Policy (Post-Partition)

After partition migration, automated purge jobs clean up expired rows.

```sql
/* sql_id: audit_logs_purge_policy */
-- Retention purge job (run daily, e.g., 02:00 UTC via cron)
-- This job removes rows from partitions that have aged past their retention window.

DO $$
DECLARE
  general_cutoff TIMESTAMP;
  extended_cutoff TIMESTAMP;
  rows_dropped BIGINT := 0;
BEGIN
  -- General retention: 5 years
  general_cutoff := NOW() - INTERVAL '5 years';
  
  -- Extended retention: 10 years (regulator-mandated rows only)
  extended_cutoff := NOW() - INTERVAL '10 years';
  
  -- Drop expired general partitions
  -- (Partitions p1, p2 are eligible for drop if all rows are older than cutoff)
  DROP TABLE IF EXISTS audit_logs_p1;  -- Legacy 2020-2025, safe to drop
  
  -- For extended-retention rows: use MATERIALIZED VIEW audit_logs_extended_retention
  -- to identify rows that MUST be retained, then only delete non-extended rows
  -- beyond the general 5-year window.
  
  -- Log the purge
  INSERT INTO audit_logs (id, created_at, action_code, actor_role, detail_json)
  VALUES (
    gen_random_uuid(),
    NOW(),
    'audit_logs_retention_purge_completed',
    'system',
    jsonx('{"general_cutoff":"' || general_cutoff || '","extended_cutoff":"' || extended_cutoff || '"}')
  );
  
  RAISE NOTICE 'Audit logs retention purge completed. Cutoffs: general=%, extended=%',
    general_cutoff, extended_cutoff;
END $$;
```

---

## 5. Rollback Plan

If partition migration fails mid-way or partitioned table shows data corruption:

### 5.1 Abort Migration (Before Table Swap)

```bash
# If migration fails before the "Rename tables" step:
psql -U postgres -d wm_db << 'EOF'
/* sql_id: rollback_pre_swap */
-- Simply drop the incomplete partitioned table; original audit_logs is unmodified
DROP TABLE IF EXISTS audit_logs_partitioned CASCADE;

-- Cleanup indexes
DROP INDEX IF EXISTS idx_audit_logs_p1_created_at CASCADE;
DROP INDEX IF EXISTS idx_audit_logs_p2_created_at CASCADE;
DROP INDEX IF EXISTS idx_audit_logs_p3_created_at CASCADE;
EOF

echo "Rollback complete; original audit_logs unchanged."
```

### 5.2 Restore from Backup (After Table Swap)

```bash
# If partitioned table is corrupted after swap:

# 1. Stop API
systemctl stop harness-api

# 2. Rename corrupted partitioned table
psql -U postgres -d wm_db << 'EOF'
/* sql_id: quarantine_corrupted_partitioned */
ALTER TABLE audit_logs RENAME TO audit_logs_corrupted_<timestamp>;
ALTER TABLE audit_logs_unpartitioned_backup RENAME TO audit_logs;
EOF

# 3. Restore privileges
psql -U postgres -d wm_db << 'EOF'
/* sql_id: restore_privileges_rollback */
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM PUBLIC;
GRANT INSERT ON audit_logs TO harness_app;
GRANT INSERT ON audit_logs TO harness_batch;
GRANT SELECT ON audit_logs TO harness_audit;
GRANT SELECT ON audit_logs TO harness_admin;
EOF

# 4. Restart API
systemctl start harness-api

echo "Rollback complete; using unpartitioned backup."
```

---

## 6. Verification Checklist

After successful migration:

- [ ] Partition table exists with correct partition definitions (`audit_logs_p1`, `p2`, `p3`).
- [ ] Row count in partitioned table matches pre-migration count (within tolerance: ±1 row for concurrent writes).
- [ ] Triggers `trg_audit_logs_no_update`, `trg_audit_logs_no_delete`, `trg_audit_logs_no_truncate` enabled and firing.
- [ ] Privileges correctly set: `harness_app` INSERT only, `harness_audit` SELECT only, etc.
- [ ] Indexes exist: `idx_audit_logs_created_at`, `idx_audit_logs_action_code`, `idx_audit_logs_actor_username`.
- [ ] API can write audit rows (test with `POST /auth/login` and verify row appears in `audit_logs`).
- [ ] Query performance on partitioned table matches or exceeds pre-partition (measured via `EXPLAIN ANALYZE`).
- [ ] Materialized view `audit_logs_extended_retention` lists all 10-year retention rows correctly.

---

## 7. 운영 격상 후보 (Ops Uplift Candidates)

Beyond PoC stage 7:

- **Automated retention purge:** Scheduled cron job to drop expired partitions (currently manual per §4).
- **Retention policy audit:** Dashboard showing active retention windows and rows eligible for deletion.
- **Hash-chain verification:** If audit-chain hash column is added separately, re-anchor hashes post-partition migration.
- **Compliance attestation:** Generate quarterly reports showing that all 10-year retention rows are preserved and untouched.
- **Partition re-balancing:** If 5-year partition grows beyond 1TB, split into quarterly sub-partitions for faster purge operations.

---

## 8. Reference

- **ADR-006 Layers A/B/C** — Append-only invariant: V008 row-level triggers (prior art), V019 TRUNCATE + REVOKE (Layer B), RUN-08 partitioning (Layer C deferred).
- **자본시장법 §54, §59** — Financial disclosure and record retention (5y/10y).
- **금소법 §32** — Financial consumer information retention.
- **REG-02 §3** — 권유기록·면담기록 10-year retention mandate.
- **SEC-02 Data Privacy** — Retention policy and purge procedures.
