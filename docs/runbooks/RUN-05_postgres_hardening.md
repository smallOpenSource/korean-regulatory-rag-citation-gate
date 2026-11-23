# RUN-05 PostgreSQL Hardening Runbook

## 1. Metadata
- 문서 ID: RUN-05
- Scope: Harness PoC `wm_db` PostgreSQL 17 인스턴스 하드닝 베이스라인 (REG-05 T290)
- 적용: 인터넷망 노출 PoC 데모 + 운영 격상 후보 표시
- Cross-refs: REG-05 §4·§7, ADR-006 V019 audit-append-only, SEC-04 account separation, OPS-01 server setup

## 2. Network Surface
PostgreSQL는 절대로 인터넷망에 직접 노출되지 않는다. API 서버(FastAPI/asyncpg)만 접속한다.

`postgresql.conf` 권장 (data directory: `$PGDATA/postgresql.conf`):
```ini
listen_addresses = 'localhost,<db-private-ip>' # 내부 주소로 바꿈
port = 5432
max_connections = 80                         # SEC-04 per-role 합계 + 여유분
ssl = on
ssl_cert_file = '/etc/postgresql/17/ssl/server.crt'
ssl_key_file  = '/etc/postgresql/17/ssl/server.key'
ssl_ca_file   = '/etc/postgresql/17/ssl/root.crt'
ssl_min_protocol_version = 'TLSv1.2'
password_encryption = scram-sha-256
log_connections = on
log_disconnections = on
log_statement = 'ddl'
log_min_error_statement = 'error'
log_line_prefix = '%t [%p] %q%u@%d/%a '
shared_preload_libraries = 'pgcrypto'
```

`pg_hba.conf` 엄격 모드 (`trust` / `md5` 절대 금지):
```hba
# TYPE  DATABASE    USER             ADDRESS          METHOD
local   all         postgres                          peer
host    wm_db       harness_app      <internal-cidr>  scram-sha-256
hostssl wm_db       harness_app      <internal-cidr>  scram-sha-256
hostssl wm_db       harness_batch    <internal-cidr>  scram-sha-256
hostssl wm_db       harness_audit    <internal-cidr>  scram-sha-256
hostssl wm_db       harness_admin    <internal-cidr>  cert        clientcert=verify-full
host    all         all              0.0.0.0/0        reject
```

체크리스트:
- [ ] `listen_addresses` 가 `*` 또는 `0.0.0.0` 이 아니다.
- [ ] `pg_hba.conf` 에 `trust` 가 0건.
- [ ] `pg_hba.conf` 에 `md5` 가 0건 (scram-sha-256 또는 cert 만).
- [ ] `ssl = on` 이고 `ssl_min_protocol_version = 'TLSv1.2'`.
- [ ] `password_encryption = scram-sha-256`.
- [ ] `log_connections`, `log_disconnections`, `log_statement=ddl` 활성.

검증 명령 (read-only):
```sql
/* sql_id: verify_password_encryption */
SHOW password_encryption;
/* sql_id: verify_ssl */
SHOW ssl;
/* sql_id: verify_listen_addresses */
SHOW listen_addresses;
/* sql_id: verify_log_connections */
SHOW log_connections;
```

## 3. Account Inventory (SEC-04 정합)
W1-T8 (V019) 가 적용되면 4 계정이 생성된다. RUN-05는 그 계정들의 connection limit·search_path·default privileges 만 다룬다 (GRANT 자체는 V019 소관).

| role | 용도 | connection_limit | search_path | 비고 |
|---|---|---|---|---|
| `harness_app` | FastAPI API 풀 (asyncpg) | 50 | `public` | LOGIN, NOINHERIT. `SELECT/INSERT/UPDATE/DELETE` on app 테이블, audit_logs는 INSERT only. |
| `harness_batch` | scheduler / batch runner | 10 | `public` | LOGIN, NOINHERIT. `SELECT/INSERT/UPDATE/DELETE` on batch & data 테이블, audit_logs INSERT only. |
| `harness_audit` | 감사뷰어 / audit dashboard | 5  | `public` | LOGIN, NOINHERIT. `SELECT` on audit_logs, audit_action_codes, system_flags만. |
| `harness_admin` | DDL / migration | 2  | `public` | LOGIN, cert 인증 (pg_hba). `CREATE`, `ALTER` 권한. 일상 트랜잭션 금지. |

권장 ALTER (V019 이후 적용):
```sql
/* sql_id: alter_connection_limit_harness_app */
ALTER ROLE harness_app    CONNECTION LIMIT 50;
/* sql_id: alter_connection_limit_harness_batch */
ALTER ROLE harness_batch  CONNECTION LIMIT 10;
/* sql_id: alter_connection_limit_harness_audit */
ALTER ROLE harness_audit  CONNECTION LIMIT 5;
/* sql_id: alter_connection_limit_harness_admin */
ALTER ROLE harness_admin  CONNECTION LIMIT 2;
```

## 4. Password Rotation
- 비밀번호는 `.env`/Vault 의 `POSTGRES_*_PASSWORD` 값을 통해서만 주입.
- 코드/로그/마이그레이션에 평문 비밀번호 금지 (gitleaks 게이트 — SEC-03).
- 90일 회전 권장 (PoC 범위에선 데모 종료 후 회전). 회전 절차:
  1. `ALTER ROLE <role> PASSWORD '<new>';` (psql admin 세션).
  2. API 서버 `.env` 갱신 → `scripts/start.sh` 재시작.
  3. `audit_logs` 에 `actor_role_change` (V008 baseline 아님; PoC scope 밖) 또는 운영 격상 시 `role_password_rotated` action_code 신설.

## 5. Backup / Audit Log Retention
- 일일 `pg_dump --format=custom --no-owner` → `/var/backups/harness/wm_db_<ts>.dump` 권장.
- audit_logs 5년 보존 (SEC-02). DROP/TRUNCATE 는 V008+V019 트리거로 차단.
- PITR / WAL archiving 은 운영 격상 후보.

## 6. Quick Verification
- 인증 강제: `psql "host=... user=harness_app password=WRONG"` → `FATAL: password authentication failed`.
- TLS 강제: `psql "sslmode=disable host=... user=harness_app"` → `pg_hba.conf` reject.
- append-only: V019 적용 후 `psql -U harness_app -c "TRUNCATE audit_logs"` → `permission denied for table audit_logs` 또는 `cannot TRUNCATE audit_logs`.

## 7. 운영 격상 후보 (PoC scope 밖)
- pgBouncer / pgcat 풀러 도입.
- Row-Level Security (RLS) 로 row scope DB 단까지 강제 (현재는 API 레이어).
- 운영 SIEM 으로 PostgreSQL log forwarder.
- KMS / Azure Key Vault 기반 비밀 주입 (현재는 .env).
- Streaming replication + standby + PITR.

## 8. Reference
- PostgreSQL 17 — Authentication: https://www.postgresql.org/docs/17/auth-methods.html
- PostgreSQL 17 — Server Configuration: https://www.postgresql.org/docs/17/runtime-config.html
- REG-05 §4 (PoC 베이스라인), ADR-006 (V019 append-only), SEC-04 (account separation).
