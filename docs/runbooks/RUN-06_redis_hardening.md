# RUN-06 Redis Hardening Runbook

## 1. Metadata
- 문서 ID: RUN-06
- Scope: Harness PoC Redis 7+ 인스턴스 하드닝 베이스라인 (REG-05 T291)
- 적용: 인터넷망 노출 PoC 데모 + 운영 격상 후보 표시
- Cross-refs: REG-05 §3·§7, SEC-04 account separation, `apps/api/harness/core/redis_client.py`

## 2. Network Surface
Redis는 절대로 인터넷망에 직접 노출되지 않는다. unix socket 또는 internal subnet 만 허용.

`redis.conf` 권장:
```conf
bind 127.0.0.1 <redis-private-ip> # 내부 주소로 바꿈. 또는 unixsocket /var/run/redis/redis.sock
protected-mode yes
port 6379
tls-port 0                          # 또는 6380 + TLS cert 적용 (운영 격상)
requirepass ${REDIS_PASSWORD}       # env 주입 (.env 파일 권한 600)
appendonly no                       # 캐시 용도 — RDB 스냅샷만 (auth 키는 휘발성)
maxmemory 2gb
maxmemory-policy noeviction         # auth keys DB (auth blocklist 절대 evict 금지)
rename-command FLUSHALL  ""
rename-command FLUSHDB   ""
rename-command CONFIG    "CONFIG_HARNESS_a1b2c3"   # admin only
rename-command DEBUG     ""
rename-command SHUTDOWN  ""
```

체크리스트:
- [ ] `bind` 에 `0.0.0.0` 가 없다.
- [ ] `protected-mode yes`.
- [ ] `requirepass` 가 설정되어 있고 코드/git 에는 평문 없음 (gitleaks 게이트).
- [ ] `FLUSHALL`, `FLUSHDB`, `DEBUG`, `SHUTDOWN` 이 `rename-command` 로 차단/은닉.
- [ ] `maxmemory-policy = noeviction` (auth keys DB).

## 3. Redis 7 ACL (Per-Service)
`default` 사용자는 비활성화하고 서비스별 ACL 사용자만 살린다.

`users.acl` (또는 `redis.conf` ACL 직접 기재):
```acl
# disable legacy 'default' user — only forces per-service auth
user default off

# harness_api: app server (FastAPI) — read/write harness:* 만; 위험 명령 금지
user harness_api on >${HARNESS_API_REDIS_PWD} ~harness:* +@read +@write -@admin -@dangerous

# harness_batch: scheduler/batch — read/write harness:batch:* 만
user harness_batch on >${HARNESS_BATCH_REDIS_PWD} ~harness:batch:* +@read +@write -@admin

# harness_ops: 운영자 (read+monitor) — write 금지
user harness_ops on >${HARNESS_OPS_REDIS_PWD} ~harness:* +@read +monitor -@write -@admin
```

체크리스트:
- [ ] `ACL LIST` 에 `default` 가 `off`.
- [ ] `harness_api`, `harness_batch`, `harness_ops` 3 사용자 존재.
- [ ] `~harness:*` (또는 더 좁은 prefix) 외 키 패턴 거부.
- [ ] `+@dangerous` 또는 `+@admin` 부여된 비-admin 사용자 0건.

검증:
```bash
redis-cli -u "redis://harness_ops:${HARNESS_OPS_REDIS_PWD}@localhost:6379" ACL WHOAMI
redis-cli -u "redis://harness_ops:${HARNESS_OPS_REDIS_PWD}@localhost:6379" SET harness:test:probe x  # → NOPERM
redis-cli -u "redis://harness_api:${HARNESS_API_REDIS_PWD}@localhost:6379" SET other:probe x       # → NOPERM (~harness:*)
redis-cli -u "redis://harness_api:${HARNESS_API_REDIS_PWD}@localhost:6379" FLUSHDB                  # → NOPERM (-@dangerous)
```

## 4. Key Namespace Standard
모든 키는 `harness:` prefix 로 시작하고 의미별 segment 를 사용. ACL `~harness:*` 매칭과 정합.

| 패턴 | TTL | 용도 | DB |
|---|---|---|---|
| `harness:auth:rl:{ip}:{username}` | window (예: 60s, 900s) | 로그인 rate-limit 카운터 | 1 (eviction 허용) |
| `harness:auth:refresh:jti:{jti}` | refresh_exp (≤14d) | refresh token blocklist (rotation 후 이전 jti revoke) | 0 (noeviction) |
| `harness:auth:employee:{employee_id}:refresh_jti` | refresh_exp | 직원별 활성 refresh jti SET (reuse-detection 시 일괄 revoke) | 0 (noeviction) |
| `harness:ws:ticket:{jti}` | 30s | WebSocket 단명 ticket (single-use, SETNX) | 0 (noeviction) |
| `harness:ws:conn:{employee_id}:{conn_id}` | 통화 시간 | 활성 WS 연결 메타데이터 | 0 |
| `harness:rl:global:{ip}` | 60s | 글로벌 IP rate-limit | 1 |
| `harness:lock:{resource}` | 작업별 lock_ttl | distributed lock (SETNX) — `redis_client.acquire_lock` | 0 |

규칙:
- TTL 미적용 키 금지 (ACL 정책으로 `PERSIST` 차단 권고). 코드 리뷰에서 `set(...) ... ex=` 또는 `setex` 강제.
- payload 에 PII, raw token, 평문 비밀번호 금지. JWT 자체를 값으로 저장 금지 — jti 만 키로 사용.
- 한국어/특수문자 segment 금지. 모든 segment 는 `[a-z0-9:_-]+` 범위.

## 5. DB Index Separation
- DB 0: auth blocklist, refresh jti set, WS ticket/conn, distributed lock — `noeviction` (절대 evict 금지).
- DB 1: rate-limit 카운터 — `allkeys-lru` 또는 `allkeys-lfu` (overload 시 evict 허용).
- 분리 사유: rate-limit 키 폭발이 auth blocklist 를 evict 해 토큰 reuse-detection 을 우회하지 못하게 한다.

`config.py` / `.env` 반영:
```env
REDIS_URL_AUTH=redis://harness_api:${HARNESS_API_REDIS_PWD}@redis.internal.example:6379/0
REDIS_URL_RATELIMIT=redis://harness_api:${HARNESS_API_REDIS_PWD}@redis.internal.example:6379/1
```

## 6. Logging / Monitoring
- `slowlog-log-slower-than 10000` (10ms) — 운영 격상 시 5000.
- `latency-monitor-threshold 100`.
- 운영 격상 시: Redis exporter → Prometheus, `INFO replication` 알람.
- `MONITOR` 명령은 ACL `+monitor` 가 부여된 `harness_ops` 만 사용 가능 — 운영 디버깅용 단발 실행.

## 7. Quick Verification (PoC)
```bash
# 1) protected-mode + requirepass
redis-cli -h redis.internal.example PING                 # → NOAUTH
redis-cli -u "redis://harness_api:wrong@redis.internal.example:6379" PING # → WRONGPASS / invalid username-password

# 2) ACL key prefix
redis-cli -u "$REDIS_URL_AUTH" SET other:bad x               # → NOPERM
redis-cli -u "$REDIS_URL_AUTH" SET harness:auth:probe x EX 10
redis-cli -u "$REDIS_URL_AUTH" GET harness:auth:probe        # → "x"

# 3) dangerous command blocked
redis-cli -u "$REDIS_URL_AUTH" FLUSHALL                      # → NOPERM
```

## 8. 운영 격상 후보 (PoC scope 밖)
- Redis TLS (`tls-port 6380`, cert+key+ca) — 인터넷망 경유 시 필수.
- Sentinel / Cluster HA (`apps/api/harness/core/redis_client.py` 는 이미 Sentinel 코드 경로 보유 — config 만 추가하면 됨).
- 운영 KMS/Vault 비밀 주입 (현재는 .env).
- ACL 변경 audit 자동 export (`ACL LOG` → SIEM).

## 9. Reference
- Redis 7 Security: https://redis.io/docs/latest/operate/oss_and_stack/management/security/
- Redis ACL: https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/
- REG-05 §3 (id/password baseline 항목 7~9, §7 운영 격상), SEC-04 (account separation).
