# SEC-01 Auth and RBAC Specification

## Authentication
- access_token은 JSON 응답으로 내려주고 브라우저 메모리(Zustand)에만 보관한다.
- refresh_token은 `/auth/login`에서 `harness_refresh_token` HttpOnly SameSite=Lax cookie로 설정한다.
- 브라우저 JavaScript 상태, `localStorage`, `sessionStorage`, TanStack Query cache에는 refresh
  token을 저장하지 않는다. Zustand는 access token과 employee metadata만 보유한다.
- `/auth/refresh`는 브라우저 cookie 또는 API 호환용 Bearer refresh token을 받아 access_token + employee metadata를 재발급한다.
- `/auth/logout`은 동일 cookie를 삭제한다.
- protected API는 계속 Authorization: Bearer access_token을 요구한다. refresh cookie는 권한 부여 cookie가 아니다.
- refresh JWT는 protected API에서 사용할 수 없다. `actor_from_authorization`은
  `token_type=access`만 허용하고 refresh token은 401로 정규화한다.
- access_token TTL: JWT_ACCESS_EXPIRE_SECONDS (env).
- refresh_token TTL: JWT_REFRESH_EXPIRE_SECONDS (env).
- `/auth/refresh` accepts either a refresh Bearer token for API compatibility or the configured
  refresh cookie (`AUTH_REFRESH_COOKIE_NAME`, default `harness_refresh_token`) for browser reload
  restore.
- `/auth/logout` clears the refresh cookie with the same configured name/path/SameSite/Secure
  attributes used by login.
- Refresh responses include `access_token` plus employee metadata so the SPA can rebuild memory
  auth state after a hard reload.
- 토큰 저장: access token은 메모리(Zustand) 전용이고 refresh token은 HttpOnly cookie 전용이다.
  `localStorage`/`sessionStorage` token persistence is prohibited.
- Cross-origin credentialed browser flows require explicit `CORS_ALLOWED_ORIGINS`; wildcard origins
  are rejected when CORS is enabled. Local same-origin proxy mode keeps CORS disabled.
- The refresh cookie may be sent only to `/auth/refresh` for session restoration and `/auth/logout`
  for clearing. Do not add cookie-auth fallback to business/protected routes; that would turn the
  refresh cookie into an authorization cookie and widen the CSRF surface.

## Role Code and Access Scope
| role_code | 접근 범위 |
|---|---|
| PB | 담당 고객만 조회/상담 생성, NBA 처리, 이메일 발송 |
| WM | 담당 고객 전체 + 타 PB 고객 열람 (자기 지점) |
| BRANCH_MANAGER | 지점 전체 고객, NBA 현황, KPI 대시보드 |
| ADMIN | 시스템/관리자 기능 전체 + House View 활성화 + 배치 관리 + 사용자 관리. 단, PB/WM 고객 권유·상담·주문 시뮬레이션 mutation은 별도 staff-delegate 권한이 승인되기 전까지 금지 |
| AUDIT_VIEWER | 감사로그 조회 전용 (읽기 전용) |
| COMPLIANCE_OFFICER | 준법감시 read-only 오버사이트: 감사로그 + 분쟁 + 이해상충(Chinese-wall) disclosure 전건 열람. 어떤 mutation도 불가하며 front-office 권유·상담·시뮬레이션 생성/자동승인·4-eye 승인자에서 제외 (인간 핸드오프 보존). 고객 행(PII) 직접 접근 없음. |

## Action-Level Authority
- ADMIN의 “전체 기능”은 운영/관리 기능을 의미하며, 고객별 권유·상담·주문 시뮬레이션 같은 front-office mutation 권한을 자동 부여하지 않는다.
- PB/WM만 상담 생성/수정, NBA/aftercare 처리, 이메일 draft/send, 추천/주문 시뮬레이션을 수행한다. BRANCH_MANAGER와 ADMIN은 별도 staff-delegate 비즈니스 결정 전까지 해당 mutation이 403이어야 한다.
- AUDIT_VIEWER는 audit_logs 조회 전용이며 고객 목록/상세, NBA, RAG, batch mutation을 수행하지 않는다.
- COMPLIANCE_OFFICER는 준법감시 read-only 오버사이트 역할이다: audit_logs / 분쟁(읽기) / 이해상충 disclosure(전건 읽기, ADMIN과 동일 see-all scope)를 열람하나, 상담·NBA·이메일 draft/send·추천/주문 시뮬레이션 생성·auto-approve·KYC write·분쟁 해결·house view 활성화 등 어떤 mutation도 수행하지 않으며, 4-eye 승인자/same-actor 통제점에 포함되지 않는다. POST auto-approve는 403이어야 한다(front-office 역할 아님). 고객 행(PII)에는 직접 접근하지 않는다(customer scope=FALSE, AUDIT_VIEWER와 동일).
- email draft/send는 PB/WM row scope와 APPROVED-only SMTP provider gate가 있는 current HTTP contract다. Full RAG generation은 backlog/not-current-contract이며 구현 전 API 계약에 포함하지 않는다.
- WebSocket backend foundation은 `/ws?token={access_token}`으로 구현되어 있으며 refresh token은
  허용하지 않고 이벤트별 RBAC/row-scope 필터를 적용한다.
- 현재 구현된 batch 운영 API는 ADMIN 읽기 전용 `GET /batch/status`이다. 로컬 배치 실행은
  서버-side ADMIN mutation endpoint가 아니라 `scripts/run_batch_pipeline.sh` 운영 명령으로 수행한다.
  `POST /batch/run` 또는 async queue/WebSocket 실행 계약은 구현 전까지 문서화하지 않는다.

## Row-Level Security
- PB: customer.assigned_pb_id = 본인 employee_id.
- WM: customer.branch_id = 본인 branch_id.
- BRANCH_MANAGER: customer.branch_id = 본인 branch_id.
- ADMIN: 전체.
- AUDIT_VIEWER: audit_logs만.
- COMPLIANCE_OFFICER: audit_logs + 분쟁/이해상충 disclosure 읽기. 고객 행 직접 접근 없음 (customer_scope_predicate → FALSE, AUDIT_VIEWER와 동일).

## API Middleware
- 모든 protected route: Authorization: Bearer {token} 헤더 필수.
- refresh cookie는 `/auth/refresh`와 `/auth/logout` cookie 삭제에만 사용하며 protected API
  authorization에는 사용하지 않는다.
- credentialed CORS is allowed only when `CORS_ENABLED=true` and `CORS_ALLOWED_ORIGINS` contains
  explicit origins. `*` is rejected with credentials because browsers must not send the refresh
  cookie to arbitrary origins.
- 역할 검사: role_code + row-level 조건 동시 적용.
- 권한 없음: 403 반환.

## Audit Required Routes
- GET /customers/{id}: customer_360_view
- POST /consultations: consultation_create
- PATCH /consultations/{id} (COMPLETED 전환): consultation_complete
- POST /house-views/{id}/activate: house_view_activate
- POST /email-drafts/{id}/send: email_draft_send (real SMTP delivery succeeds only; blocked provider paths leave status unchanged) — 본 PoC는 sandbox 전용(ADR-002 real-SMTP 금지)이라 실제 발송 성공 시 email_sent_via_sandbox 를 emit하며, email_draft_send 는 real-SMTP 활성 시 emit하도록 예약된 코드다
- POST /nba-actions/{id}/status (DONE/DISMISSED): nba_complete or nba_dismiss

- POST /recommendation-simulations: recommendation_simulation_create or recommendation_simulation_block
- POST /order-simulations: order_simulation_create or order_simulation_block
- POST /order-simulations/{id}/execute-simulated: order_simulation_execute_simulated


## Audit Code Source
- Canonical audit action_code 목록은 docs/observability/OBS-02_audit_action_codes.md를 따른다.

---

## Wave 1 Security Baseline (REG-05 T280-T283, T299)

### T281 — Password Policy
- Minimum length: **12 characters**.
- bcrypt cost factor: **≥ 12** (enforced at hash time; login verifies existing hash regardless of cost).
- HIBP breach check: **soft / non-blocking** — on login, the presented password is checked against the
  HaveIBeenPwned k-anonymity prefix API. A positive hit writes an `auth_login_failure`-adjacent
  audit row with `compromised_password: true` but does **not** block the login (PoC stage).
  Production policy: block on positive HIBP hit.

### T282 — JWT BCP (RFC 8725)
- Algorithm allowlist: `HS256`, `RS256`, `ES256`. `alg=none` is unconditionally rejected.
- Required claims on every token:
  - `iss` = `harness-poc` (rejected if mismatched)
  - `aud` = `harness-web` (rejected if mismatched)
  - `jti` = UUID4 (rejected if absent)
  - `nbf`, `exp`, `sub` (standard)
- Clock skew tolerance: **60 seconds** (`CLOCK_SKEW_SECONDS` env, default 60).
- Token types: `token_type=access` for protected APIs; `token_type=refresh` for `/auth/refresh` only.
  Protected routes reject refresh tokens (401).

### T280 — Rate Limit Policy
| Scope | Limit | Window | Key namespace |
|---|---|---|---|
| `/auth/login` per IP + username | 10 req | 1 min | `harness:auth:rl:{ip}:{username}:1m:{window}` |
| `/auth/login` per IP + username | 60 req | 15 min | `harness:auth:rl:{ip}:{username}:15m:{window}` |
| `/auth/refresh` per IP | 30 req | 1 min | `harness:auth:rl:refresh:{ip}:1m:{window}` |
| Global per IP (all routes) | 600 req | 1 min | `harness:global:rl:{ip}:api:1m:{window}` |
| `/docs`, `/redoc`, `/openapi.json` per IP | 10 req | 1 min | `harness:global:rl:{ip}:docs:1m:{window}` |
| `/health`, `/metrics` | exempt | — | no counter |

Implementation: Redis fixed-window INCR + EXPIRE pipeline (`apps/api/harness/core/rate_limit.py`).
On limit exceeded: 429 with `Retry-After` header; audit code `auth_login_rate_limited` (auth) or
`rate_limit_exceeded` (global).

### T283 — Refresh Token Rotation and Reuse Detection
- On every successful `/auth/refresh`, the consumed JTI is blocklisted in Redis:
  `harness:auth:refresh:jti:{jti}` with TTL = refresh token TTL.
- The new JTI is registered per-employee: `harness:auth:employee:{employee_id}:refresh_jti:{jti}`.
- **Reuse detection**: if a blocklisted JTI is presented again, **all** active refresh JTIs for that
  `employee_id` are mass-revoked (`SCAN + DEL` on the per-employee namespace), and a
  `auth_refresh_reuse` audit row is written with the detected JTI and IP hash.
- The reused token attempt returns 401 `refresh token has been revoked`.

### T283.1 — Blocklist Grace Window (OQ-5, 2026-05-23)

**Decision**: introduce a `JTI_BLOCKLIST_GRACE_SECONDS = 5` window before
the blocklist is enforced for reuse-detection. The blocklist key is
populated with the unix timestamp of consumption instead of a sentinel,
and `_is_jti_blocklisted` only returns True when the timestamp is older
than the grace window.

**Motivation**: two near-concurrent refreshes from the same browser
session (e.g. tab waking from sleep + automatic restore-session
refresh) can race the immediate-blocklist semantics — T1 succeeds and
blocklists; T2 (in flight, holding the old token) sees the blocklist
and gets 401 + triggers mass-revoke, evicting the user despite no
attacker being involved. The grace window absorbs this race without
weakening reuse-detection beyond a 5-second window.

**Security trade-off**:
- **Loss**: stolen refresh tokens that are replayed within 5 seconds
  of the legitimate rotation succeed once. The attacker receives one
  set of access + refresh tokens.
- **Retained**: any reuse attempt PAST the grace window triggers
  mass-revoke + 401 + `auth_refresh_reuse` audit row exactly as
  before. The attacker's foothold lasts at most one access-token
  lifetime before the next refresh attempt fires mass-revoke.
- **Net**: the audit-e2e environmental ceiling (ADR-009
  §"audit-e2e environmental ceiling") drops away because the
  in-flight refresh race no longer trips reuse-detection. The
  reuse-detection window contracts by 5 seconds (negligible vs the
  hour-long access-token lifetime for which a stolen token would be
  exploitable anyway).

**Rollback**: write the legacy sentinel `"revoked"` into the
blocklist key; `_is_jti_blocklisted` treats unparseable values as
immediately-enforced (no grace).

**Empirical post-implementation note (2026-05-23 R4 audit-e2e)**:
the grace window's expected lift on the audit-e2e environmental
ceiling was NOT observed (R4 = 84 passed / 3 failed / 5 flaky vs
R1-R3 baseline 84-87/3-4/1-5). The dominant audit-e2e race is at
a higher layer (browser-context / page-load timing), not the JTI
blocklist immediate-enforcement that this section addresses. The
grace window remains in place because:
- Timestamp-based blocklist is structurally cleaner (Redis values
  carry meaningful consumption time vs opaque sentinel).
- 5s window absorbs SOME legitimate-race scenarios (SPA tab wake,
  parallel restoreSession) even if not the dominant audit-e2e one.
- Reverting would re-introduce immediate-enforcement code for a
  marginal security gain (5s vs hour-long access-token lifetime).

See ADR-009 §"audit-e2e environmental ceiling" → "OQ-5 resolution
(measured: NO LIFT)" for the full empirical table.


### T299 — PoC_AUTO_APPROVAL Separation from Production Auth
- The PoC auto-approval path is gated by three independent conditions:
  1. `system_flags.demo_mode.enabled = true` (DB; default `false` per V020 seed).
  2. `X-Poc-Demo-Mode: true` request header.
  3. `POC_AUTO_APPROVAL_ENABLED=true` environment variable.
- Without all three conditions, auto-approval returns 403.
- `governance_marker` column on `audit_logs` (V021) records `PoC_AUTO_APPROVAL` for auto-approved
  paths; `HUMAN_REVIEW` for standard paths. CHECK constraint enforces the allowlist.
- **PoC_AUTO_APPROVAL does not bypass endpoint authentication.** Protected routes still require a
  valid Bearer access token regardless of demo-mode state. The 4-gate simulation flow uses the same
  `actor_from_authorization` dependency as production paths.
