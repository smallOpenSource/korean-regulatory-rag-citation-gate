# SEC-04 Account Separation (SoD)

## 1. Metadata
- 문서 ID: SEC-04
- Scope: PostgreSQL 4 계정 + Redis 3 ACL 사용자 SoD (Segregation of Duties) 명세
- Cross-refs: ADR-006 (V019 append-only + GRANT), RUN-05 (PG hardening), RUN-06 (Redis hardening), REG-05 §3·§4, REG-06 §SoD

## 2. Principle
- 모든 비밀번호는 `.env` (운영 격상 시 KMS/Vault) 만을 통해 주입한다.
- 모든 계정은 최소 권한(least privilege) 원칙을 따른다.
- DDL 권한(`harness_admin`) 과 일상 트랜잭션 권한(`harness_app`/`harness_batch`/`harness_audit`) 은 절대 같은 계정에 부여하지 않는다 (SoD).
- audit_logs 는 모든 4 계정에 대해 `UPDATE/DELETE/TRUNCATE` 가 금지된다 (V008 + V019, ADR-006).
- 계정 escalation / 비밀번호 회전 / 권한 변경 은 audit 로깅 (운영 격상 시 `actor_role_change` action_code).

## 3. PostgreSQL Accounts

| role | 용도 | LOGIN | INHERIT | 인증 방식 | conn limit | 핵심 권한 | audit_logs |
|---|---|---|---|---|---|---|---|
| `harness_app`   | FastAPI API 풀 (asyncpg) | yes | NOINHERIT | scram-sha-256 | 50 | `SELECT/INSERT/UPDATE/DELETE` on app 테이블 (employees, customers, consultations, nba_*, email_drafts, recommendation_*, order_simulations, ai_*, ...) | `INSERT` only |
| `harness_batch` | scheduler / batch runner | yes | NOINHERIT | scram-sha-256 | 10 | `SELECT/INSERT/UPDATE/DELETE` on batch/data 테이블 (batch_*, market_data_*, document_chunks, dart_*, house_views) | `INSERT` only |
| `harness_audit` | audit dashboard / 감사뷰어 | yes | NOINHERIT | scram-sha-256 | 5  | `SELECT` on `audit_logs`, `audit_action_codes`, `system_flags` 만 | `SELECT` only |
| `harness_admin` | DDL / migration / 운영 점검 | yes | NOINHERIT | **cert** (pg_hba `clientcert=verify-full`) | 2  | `CREATE/ALTER/DROP` (DDL). 일상 트랜잭션 사용 금지 | `SELECT` only (운영 점검) |

비밀번호 env 키 (RUN-05 정합):
```env
POSTGRES_APP_PASSWORD=<scram_password>
POSTGRES_BATCH_PASSWORD=<scram_password>
POSTGRES_AUDIT_PASSWORD=<scram_password>
POSTGRES_ADMIN_PASSWORD=<scram_password>   # cert 인증 사용 시 비밀번호 자체는 fallback / 비활성
```

GRANT SQL 의 원천은 V019 (task #14). SEC-04 는 그 결과를 invariant 로 기술한다.

## 4. Redis ACL Users (RUN-06 §3 정합)

| user | 용도 | 키 패턴 | 명령 카테고리 | DB |
|---|---|---|---|---|
| `default`      | (legacy)        | —                 | **off**                              | — |
| `harness_api`  | FastAPI API     | `~harness:*`      | `+@read +@write -@admin -@dangerous` | 0, 1 |
| `harness_batch`| 배치 스케줄러   | `~harness:batch:*`| `+@read +@write -@admin`             | 0    |
| `harness_ops`  | 운영자 (RO)     | `~harness:*`      | `+@read +monitor -@write -@admin`    | 0, 1 |

비밀번호 env 키:
```env
HARNESS_API_REDIS_PWD=<acl_password>
HARNESS_BATCH_REDIS_PWD=<acl_password>
HARNESS_OPS_REDIS_PWD=<acl_password>
```

## 5. Code Mapping (API Code Paths → DB/Redis Account)

PostgreSQL (asyncpg 풀):
| 코드 경로 | 사용 계정 | env var 풀 설정 |
|---|---|---|
| `apps/api/harness/core/db.py` (메인 풀) | `harness_app` | `POSTGRES_USER=harness_app` + `POSTGRES_APP_PASSWORD` |
| `apps/api/harness/api/routes/audit.py` 의 audit 조회 (있을 시) | `harness_app` (read 권한으로 충분) — `harness_audit` 직접 풀은 운영 격상 후보 | `POSTGRES_AUDIT_PASSWORD` (예약) |
| `scripts/run_batch_scheduler.py`, `scripts/run_batch_pipeline.sh` | `harness_batch` | `POSTGRES_BATCH_PASSWORD` |
| `db/migrator.py` | `harness_admin` (cert 권장) | `POSTGRES_ADMIN_PASSWORD` (cert 인증 시 unused) |

Redis (`apps/api/harness/core/redis_client.py`):
| 코드 경로 | 사용 ACL 사용자 | 사용 DB |
|---|---|---|
| `create_redis_client` (auth blocklist, WS ticket, distributed lock) | `harness_api` | 0 |
| 동일 — rate-limit 카운터 | `harness_api` | 1 |
| `scripts/run_batch_scheduler.py` 의 lock | `harness_batch` | 0 |
| 운영 점검 (`MONITOR`, `INFO`, `ACL LIST`) | `harness_ops` | — |

## 6. Audit Trail
- 모든 인증 성공/실패: `auth_login_success`, `auth_login_failure`, `auth_refresh`, `auth_logout`, `auth_refresh_reuse`, `auth_login_rate_limited` (V022).
- WebSocket ticket 발급/소진: `ws_ticket_issued`, `ws_ticket_consumed` (V022).
- 데모 모드 토글: `demo_mode_toggle_on/off` (V022, system_flags trigger 와 정합).
- SoD 증적 팩 발행: `sod_evidence_published` (V022, REG-06).
- 운영 격상 후보: `actor_role_change` (PostgreSQL/Redis 계정 비밀번호 회전 / ACL 변경 시), `db_grant_changed`.

## 7. Verification Checklist (PoC)
- [ ] `psql -U harness_app -c "TRUNCATE audit_logs"` → permission denied (V019).
- [ ] `psql -U harness_app -c "DROP TABLE employees"` → permission denied.
- [ ] `psql -U harness_audit -c "INSERT INTO consultations(...) VALUES (...)"` → permission denied.
- [ ] `psql -U harness_batch -c "TRUNCATE audit_logs"` → permission denied.
- [ ] `redis-cli -u $REDIS_URL_AUTH FLUSHALL` → NOPERM.
- [ ] `redis-cli -u "redis://harness_ops:...@..." SET harness:test x` → NOPERM.
- [ ] `redis-cli ACL WHOAMI` 결과가 `default` 가 아님.

## 8. 운영 격상 후보
- 4 PG 계정 비밀번호를 Azure Key Vault / HashiCorp Vault 로 이관.
- `harness_admin` 을 OS-level cert 만으로 가능하게 하고 비밀번호 fallback 제거.
- audit dashboard 가 `harness_audit` 풀을 별도로 갖도록 분리.
- Redis Sentinel/TLS 도입 후 ACL 사용자별 client cert pin.

## 9. Reference
- ADR-006 (audit append-only + V019 GRANT 단일 소스).
- RUN-05 (PostgreSQL hardening).
- RUN-06 (Redis hardening).
- REG-05 §3 항목 7 (audit), §4 (계정 분리), §7 (운영 격상).
- REG-06 (SoD evidence pack).
