# DB-06 RBAC Database Accounts

> **Naming note**: this file uses `DB-06` because `DB-03_physical.md` (physical schema)
> is already occupied. Task #14's body referenced `DB-03_account_separation.md`; the
> equivalent SoD content lives in `docs/security/SEC-04_account_separation.md` (security
> lens) and this file (DB lens).

## 1. Metadata
- 문서 ID: DB-06
- Scope: 4 PostgreSQL Harness 계정의 DB-layer 명세 (provisioning + grants + login string)
- 단일 소스 — GRANTs on `audit_logs`: V019 (ADR-006 §Layer B)
- 단일 소스 — 베이스라인 GRANTs on app/batch tables: `db/setup/roles.sql`
- Cross-refs: ADR-006, RUN-05 (PG hardening), SEC-04 (SoD), REG-05 §4

## 2. Provisioning

```bash
# 1) Set 4 strong passwords (scram-sha-256 friendly) — env or vault
export HARNESS_APP_PWD="..."
export HARNESS_BATCH_PWD="..."
export HARNESS_AUDIT_PWD="..."
export HARNESS_ADMIN_PWD="..."

# 2) Run as superuser ONCE per environment
psql "$DATABASE_URL_SUPERUSER" \
    -v HARNESS_APP_PWD="$HARNESS_APP_PWD" \
    -v HARNESS_BATCH_PWD="$HARNESS_BATCH_PWD" \
    -v HARNESS_AUDIT_PWD="$HARNESS_AUDIT_PWD" \
    -v HARNESS_ADMIN_PWD="$HARNESS_ADMIN_PWD" \
    -f db/setup/roles.sql

# 3) Apply migrations (V019 will GRANT to these roles if present; harmless otherwise).
/opt/conda/envs/wm_env/bin/python db/migrator.py
```

`roles.sql` 는 idempotent: 재실행 시 `CREATE ROLE` 대신 `ALTER ROLE WITH PASSWORD ...` 로 fallback.

## 3. Account Catalog

| role            | LOGIN | INHERIT      | conn_limit | 핵심 권한 (db/setup/roles.sql 베이스라인) | audit_logs (V019) |
|---|:---:|:---:|---:|---|---|
| `harness_app`   | ✅    | NOINHERIT    | 50         | SELECT/INSERT/UPDATE/DELETE on `public.*` tables (audit_logs 제외) + USAGE on sequences | `INSERT` only |
| `harness_batch` | ✅    | NOINHERIT    | 10         | SELECT/INSERT/UPDATE/DELETE on `public.*` tables (audit_logs 제외) + USAGE on sequences | `INSERT` only |
| `harness_audit` | ✅    | NOINHERIT    | 5          | SELECT on `public.*` 만                  | `SELECT` only |
| `harness_admin` | ✅    | NOINHERIT, CREATEROLE | 2 | SELECT on `public.*` + DDL (table owner) | `SELECT` only |

PUBLIC: `audit_logs` 에 대해 `UPDATE/DELETE/TRUNCATE` 0 (V019 + roles.sql 의 REVOKE 양쪽에서 확정).

## 4. audit_logs Special Handling (ADR-006 정합)

V019 + roles.sql 결합 시 invariant:

| 시나리오 | 기대 결과 |
|---|---|
| `psql -U harness_app -c "INSERT INTO audit_logs(...)"` | ✅ 성공 |
| `psql -U harness_app -c "UPDATE audit_logs SET ..."`   | ❌ permission denied (REVOKE) — 트리거 미발화 |
| `psql -U harness_app -c "DELETE FROM audit_logs ..."`  | ❌ permission denied (REVOKE) |
| `psql -U harness_app -c "TRUNCATE audit_logs"`         | ❌ permission denied (REVOKE) |
| superuser session: `UPDATE audit_logs SET ...`         | ❌ V008 row-level trigger → `audit_logs are append-only` |
| superuser session: `DELETE FROM audit_logs ...`        | ❌ V008 row-level trigger → `audit_logs are append-only` |
| superuser session: `TRUNCATE audit_logs`               | ❌ V019 BEFORE TRUNCATE trigger → `audit_logs TRUNCATE denied (PoC append-only invariant)` |

Defense in depth: privilege REVOKE catches role-scoped attempts; triggers catch superuser/owner attempts.

## 5. Connection String Template

```env
# .env (subset)
POSTGRES_HOST=db.internal.example
POSTGRES_PORT=5432
POSTGRES_DB=wm_db

# Application API pool
POSTGRES_USER=harness_app
POSTGRES_PASSWORD=${HARNESS_APP_PWD}

# Batch scheduler / pipeline
POSTGRES_BATCH_USER=harness_batch
POSTGRES_BATCH_PASSWORD=${HARNESS_BATCH_PWD}

# Audit dashboard (RO; PoC scope optional — API can use harness_app SELECT pathway)
POSTGRES_AUDIT_USER=harness_audit
POSTGRES_AUDIT_PASSWORD=${HARNESS_AUDIT_PWD}

# Migration / DDL admin (cert 인증 권장, RUN-05 §2)
POSTGRES_ADMIN_USER=harness_admin
POSTGRES_ADMIN_PASSWORD=${HARNESS_ADMIN_PWD}
```

## 6. Verification

```bash
# 1) Role existence
psql "$DATABASE_URL_SUPERUSER" -c "SELECT rolname, rolconnlimit FROM pg_roles WHERE rolname LIKE 'harness_%' ORDER BY rolname;"

# 2) audit_logs privilege matrix
psql "$DATABASE_URL_SUPERUSER" -c "
SELECT grantee, string_agg(privilege_type, ',' ORDER BY privilege_type) AS privs
  FROM information_schema.role_table_grants
 WHERE table_schema='public' AND table_name='audit_logs'
 GROUP BY grantee ORDER BY grantee;"

# 3) Negative tests (each must FAIL):
psql -U harness_app    "$DATABASE_URL_NO_AUTH" -c "TRUNCATE audit_logs"
psql -U harness_audit  "$DATABASE_URL_NO_AUTH" -c "INSERT INTO consultations DEFAULT VALUES"
psql -U harness_batch  "$DATABASE_URL_NO_AUTH" -c "DROP TABLE employees"

# 4) Trigger existence (V008 + V019)
psql "$DATABASE_URL_SUPERUSER" -c "SELECT tgname, tgenabled FROM pg_trigger WHERE tgrelid='audit_logs'::regclass ORDER BY tgname;"
```

## 7. 운영 격상 후보
- 비밀번호 회전 자동화 (Vault 통합).
- `harness_admin` cert 전용 (비밀번호 fallback 제거).
- Row-Level Security 정책 (현재는 API 레이어).
- 풀러(pgBouncer) 도입.

## 8. Reference
- ADR-006 (audit append-only invariant — 3-layer architecture).
- RUN-05 (`postgresql.conf`, `pg_hba.conf` 운영 베이스라인).
- SEC-04 (SoD invariants + Redis ACL).
- REG-05 §4 (계정 분리 요건).
