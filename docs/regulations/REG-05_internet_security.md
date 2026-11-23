# REG-05 인터넷망 외부 노출 PoC 서비스 보안 Best Practice

## 1. 메타데이터
- 문서 ID: REG-05
- Lane: Phase 2 외부 리서치 L5 (인터넷망 보안)
- 작업 디렉토리: `<repo-root>`
- 생성: 2026-05-17 (Asia/Seoul)
- 입력 컨텍스트: deep-interview-wmah Round 7 — `id/password 1-factor` 결정, SEC-01/SEC-02, ADR-001 (WebSocket), ADR-002 (Email), ADR-003 (Dependency Gate)
- Scope: Harness PoC가 인터넷망에 노출될 때(공개 도메인/HTTPS) id/password 1-factor 기반에서 안전하게 운영하기 위한 baseline + 향후 운영 격상 후보 분리
- Non-goal: MFA/FIDO2/MDM/IP whitelist 등 추가 인증 게이트 즉시 도입 (PoC scope 밖, 운영 격상 후보로 분리)
- 출력 산출물 제한: 본 파일만 수정

## 2. 보안 표준 매트릭스
| 표준 | 핵심 통제 | Harness 현행 적용 | 차이/Gap |
|---|---|---|---|
| OWASP Top 10 (2021, 2024 후보 안정) A01 Broken Access Control | 역할/객체 수준 인가, deny-by-default | SEC-01 5-role + row-scope + 403 정규화, audit 라우트 명시 | ADMIN front-office mutation 차단은 적용; AUDIT_VIEWER 읽기 전용 회귀 테스트 강화 필요 |
| OWASP Top 10 A02 Cryptographic Failures | HTTPS 강제, 키/비밀 보관, TLS 1.2+ | refresh cookie Secure+HttpOnly+SameSite=Lax 명시 | TLS 종단/HSTS 헤더 명시(런타임) 항목 docs 미문서 |
| OWASP Top 10 A03 Injection | parameterized SQL, prompt-injection 검역 | asyncpg raw SQL + `/* sql_id */`, AI prompt-injection 격리(Round 3) | 정적 SQL_ID 검증 + AI 인용 정합성 검증 진행 중 |
| OWASP Top 10 A04 Insecure Design | threat model, secure-by-default | ADR-001 (WS) / ADR-002 (Email) / SEC-01 두-단계 권한 | 인터넷망 노출 threat-model 단일 문서(REG-05) 신설로 보강 |
| OWASP Top 10 A05 Security Misconfiguration | secure defaults, error 마스킹 | CORS_ENABLED=false 동시 same-origin 프록시, 403/401 정규화 | CSP/Permissions-Policy/HSTS header 정책 docs 결손 |
| OWASP Top 10 A07 Identification & Auth Failures | brute-force 방지, session lifecycle | JWT memory access + HttpOnly refresh cookie, refresh→protected 차단 | rate-limit, lockout, password policy 항목 docs 미문서 |
| OWASP Top 10 A08 Software & Data Integrity | dependency gate, SRI | ADR-003 dependency allowlist 정적 검증 | SRI(스크립트 정합성) Vite 빌드 산출물 적용 미문서 |
| OWASP Top 10 A09 Logging & Monitoring | audit, PII 차단 | SEC-02 PII 차단, audit_logs 5년 보존 | 로그 redaction 규칙 단일 진실 항목 별도 정리 필요 |
| OWASP Top 10 A10 SSRF | 외부 호출 화이트리스트 | 외부 provider는 KRX/OpenDART/ECOS/Data.go.kr/BROKER/Azure만 명시 | egress allowlist 환경변수 강제 + 검증 항목 미문서 |
| OWASP ASVS 4.0 L1 V2 Authentication | password 길이/리스트, 잠금 | password policy 미문서 | L1 충족을 위한 최소 정책(길이≥12, breached list 차단) 신규 필요 |
| OWASP ASVS 4.0 L1 V3 Session Management | secure cookie, rotation | refresh HttpOnly+SameSite+rotation 권고 | rotation 구현 여부 명시 필요(refresh 사용 시 회전) |
| OWASP ASVS 4.0 L1 V13 API Sec | 인가/속도제한 | 인가 OK, rate limit 미문서 | rate limit middleware 필수 |
| RFC 7519 / RFC 8725 JWT BCP | alg whitelist, exp, audience | JWT 사용 명시 | `alg=none` 거부, kid 검증, aud/iss 검증 docs 필요 |
| KISA/금융보안원 (전자금융감독규정 §15·§28·§37 일반 요지) | 인증, 통신, 로그 5년 | audit_logs 5년, HTTPS, RBAC | 전자금융감독규정상 'MFA/공인인증/MDM'은 PoC scope 밖이며 운영 격상 후보로 명시 |

## 3. id/password 1-factor 안전 운영 체크리스트
Round 7 결정에 따라 추가 인증 게이트 없이도 인터넷망에서 baseline을 유지하기 위한 최소 통제.

1. **Password Policy (ASVS V2.1)**
   - 최소 길이 12자, 한글/공백 허용, 최대 길이 128 이상.
   - 사전 등록 시 breached list(HIBP API offline 해시 prefix) 거부; 외부 API 호출이 PoC에서 불가하면 로컬 dump 검증.
   - 복잡도 강요 금지(ASVS 권고: 길이 우선); 회전 강요 금지.
   - 저장: bcrypt cost≥12 또는 argon2id (memory≥64MB, t=3, p=1).
2. **Brute-force / Rate Limit**
   - `/auth/login`: IP+username 키 기반 토큰 버킷 (예: 10/min, 60/15min). 초과 시 401 + 백오프.
   - `/auth/refresh`, `/auth/logout`: cookie 기반 IP rate limit (예: 30/min).
   - 모든 protected API: 글로벌 IP rate limit (예: 600/min).
   - 잠금은 username이 아닌 (IP, username) 페어로 적용해 enumeration 회피.
3. **Account Enumeration 방지**
   - login 실패 응답: 401 + `{"error_code":"invalid_credentials"}`. 사용자 존재 여부 누설 금지.
   - 가입/비번 재설정 미구현 PoC 범위; 신규 직원 추가는 ADMIN side script로만.
4. **Session / JWT TTL**
   - `JWT_ACCESS_EXPIRE_SECONDS`: 권고 600–900s (10–15분).
   - `JWT_REFRESH_EXPIRE_SECONDS`: 권고 14일 이하. refresh 회전(rotation) 적용.
   - `/auth/refresh` 매 호출 시 새 refresh cookie 발급 + 이전 refresh jti revoke(redis blocklist).
   - 동시 세션 제한: PoC scope 밖 (운영 격상 후보).
5. **Secure Cookie 속성**
   - `harness_refresh_token`: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/auth`, `Domain` 미지정(host-only).
   - `__Host-` prefix 권고(향후): `__Host-harness_refresh_token` 도입 시 Domain 금지 + Path=/ 필수.
6. **CSRF**
   - access JWT는 Authorization 헤더 전용 → 일반 API CSRF 영향 없음.
   - refresh cookie는 `/auth/refresh`·`/auth/logout`만 송신 → SameSite=Lax + cross-origin POST/JSON 거부 + Origin/Referer 검증 추가 권고.
7. **Audit**
   - 모든 로그인 성공/실패: `audit_logs.action_code` 신설 `auth_login_success`, `auth_login_failure`, `auth_refresh`, `auth_logout`. detail_json은 ip_hash, user_agent_hash, employee_id만(원문 IP/UA 저장 금지 또는 prefix masking).
   - 5년 보존 정책 유지(SEC-02).
8. **HTTPS / Transport**
   - TLS 1.2+ (TLS 1.3 권장), HSTS `max-age=15552000; includeSubDomains; preload`.
   - HTTP→HTTPS 301 강제, 평문 cookie 거부.
9. **Error Surface**
   - stack trace, asyncpg 원문, prompt 원문, provider error body는 클라이언트 응답 금지. sanitized error_code만.

## 4. JWT memory access + HttpOnly refresh cookie Best Practice 점검
SEC-01 결정과 RFC 8725 (JWT BCP) 정합성 검증.

| 항목 | RFC/Best Practice | Harness 현황 | 권고 |
|---|---|---|---|
| 알고리즘 | RFC 8725: HS256/RS256/ES256, `none` 거부, alg 허용 목록 강제 | 단일 secret HS256 가정 | 검증 시 `alg` allowlist만 수용. 향후 운영 격상 시 RS256 + JWKs rotation 후보 |
| `exp` | 짧게 (≤15분 access) | TTL env 제어 | env 기본값 access=900s, refresh=1209600s(14d) |
| `iat`, `nbf` | 시계 skew ±60s 허용 | 미문서 | clock_skew=60s 허용 명시 |
| `aud`, `iss` | 검증 필수 | 미문서 | `iss=harness`, `aud=harness-web` 강제 |
| `jti` | rotation/revocation 키 | 미문서 | refresh JWT는 `jti` 필수 + Redis blocklist(만료 시까지 키 보존) |
| token_type | access/refresh 분리 | SEC-01: refresh는 protected API 차단 | 유지. claim `token_type` 외부 노출 금지(payload 외 별 claim) |
| Storage (access) | 메모리 only | Zustand 메모리 only, localStorage 금지 | 유지 |
| Storage (refresh) | HttpOnly cookie | `harness_refresh_token` HttpOnly+Secure+SameSite=Lax | `__Host-` prefix 검토 |
| Rotation | refresh 회전 + 이전 무효화 | 미명시 | `/auth/refresh` 매 호출 회전 + 이전 jti revoke |
| Reuse detection | 회전된 refresh 재사용 시 전체 세션 무효 | 미명시 | reuse 감지 시 employee_id 모든 refresh jti revoke + audit `auth_refresh_reuse` |
| 로그/프롬프트 redaction | token 원문 로깅 금지 | SEC-02 일반 PII 차단 | logging filter에 `Authorization`, `set-cookie`, `harness_refresh_token`, `access_token` 키 마스킹 명시. AI 프롬프트에 token 주입 금지 |
| 토큰 크기 | claim 최소화 | 미문서 | role_code, branch_id, employee_id, exp, jti, iss, aud, token_type만. PII(성명) 금지 |

## 5. CORS / CSP / SRI 권장 설정
### CORS
- 기본: same-origin 프록시(Vite→FastAPI), `CORS_ENABLED=false`.
- 인터넷망 노출 시 별 origin이 필요할 때만 `CORS_ENABLED=true` + `CORS_ALLOWED_ORIGINS=https://harness.example.com` (와일드카드 거부 — SEC-01 기존 결정).
- `Access-Control-Allow-Credentials: true`는 명시 origin 매칭 시에만.
- preflight: `Access-Control-Max-Age=600`, allow-methods 명시.

### CSP (Content-Security-Policy)
PoC 단일 도메인 + Azure OpenAI 직호출 backend-only 가정.
```
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';  # Tailwind injected runtime styles 부득이; 운영 격상 시 nonce 적용 후보
img-src 'self' data:;
connect-src 'self' wss://harness.example.com;
font-src 'self';
frame-ancestors 'none';
form-action 'self';
base-uri 'self';
object-src 'none';
upgrade-insecure-requests;
```
- 추가 헤더: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: geolocation=(), microphone=(), camera=()`, `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`.

### SRI
- Vite 빌드 산출물에 `<script>`/`<link>` `integrity` 속성 부여(빌드 플러그인 없이 빌드 후 정적 후처리 가능).
- CDN 사용 금지(ADR-003 dependency gate와 정합). 외부 폰트/스크립트 금지.

## 6. WebSocket 보안 — ADR-001 정합성 검토
| ADR-001 조항 | 정합 평가 | 추가 권고 |
|---|---|---|
| `/api/ws` same-origin proxy → `/ws` | 정합 | 운영 시 nginx에서 `Upgrade`/`Connection` 헤더 화이트리스트 |
| access token only, refresh cookie 금지 | 정합 (SEC-01과 일치) | 토큰을 query string 대신 단명 ticket으로 격상 권고: HTTP `POST /ws/ticket` 발급 → 30초 ticket → `wss://.../ws?ticket=...` 또는 첫 메시지로 access token 전달. 사유: 서버 access log, browser history, proxy log에 query token 노출 회피 |
| event envelope (event_id, trace_id, row_scope) | 정합 | payload에 PII/secret/refresh 절대 금지 (이미 명시) — logging redactor에 envelope 그대로 통과 시 안전한 fields 화이트리스트 적용 |
| RBAC/row-scope fanout | 정합 | 클라이언트 측 필터에 의존 금지, 서버 fanout 전 필터링. 가입 시 token claim re-validate |
| 재연결/하트비트 | ADR-001 미명시 | ping 30s, idle timeout 120s, exponential backoff 재연결, replay safety는 `event_id` 멱등성 활용 |
| Origin 검증 | ADR-001 미명시 | WS handshake `Origin` 헤더가 `CORS_ALLOWED_ORIGINS`에 포함될 때만 수락 |
| Subprotocol | ADR-001 미명시 | `Sec-WebSocket-Protocol: harness.v1` 고정으로 미래 버전 게이트 |

## 7. PoC scope 적합 vs 운영 격상 후보 분리
| 통제 | PoC scope (현재) | 운영 격상 후보 | 사유 |
|---|---|---|---|
| 인증 factor | id/password 1-factor (Round 7) | MFA (TOTP/WebAuthn FIDO2), 공인인증/금융인증 | Round 7 결정 — 추가 게이트 없음 baseline. 운영 시 전자금융감독규정/내부 통제 |
| 네트워크 | 인터넷망 노출 + HTTPS | IP whitelist, VPN gateway, WAF, mTLS | PoC는 데모 접근 필요 |
| 단말 | 통제 없음 | MDM, EDR, 단말 인증서 | PoC scope 밖 |
| Session | refresh rotation + blocklist | 동시 세션 1개 강제, 강제 logout, 위치/디바이스 이상 탐지 | rotation/blocklist만 PoC 포함 |
| 비밀 보관 | `.env` 파일 + gitignore + 로그 마스킹 | KMS/Vault(Azure Key Vault 등) 통합, dynamic secrets | PoC는 파일 기반 |
| Rate limit | in-process or Redis 기반 (예: slowapi) | API gateway/CDN 엣지 차단, Captcha, 봇 차단 | PoC는 in-process 충분 |
| 로그 | 5년 audit_logs, PII redaction | SIEM 연동, UEBA, 무결성 서명 | append-only로 충분 |
| CSP | 위 권장 헤더 | nonce 기반 strict CSP, Report-Only → Enforce 단계화 | 'unsafe-inline' 부득이 |
| Backups | PostgreSQL/Redis 기본 | 암호화된 오프사이트, RPO/RTO 약정 | PoC scope 밖 |
| Penetration test | self check + OWASP ZAP baseline | 외부 침투/취약점 진단 | 운영 격상 |

### PostgreSQL 17 (인터넷망 노출 가정) 베이스라인
- `listen_addresses` localhost 또는 internal subnet only. 인터넷망 직접 노출 금지(앱 서버 경유).
- `ssl=on`, scram-sha-256 인증, `pg_hba.conf`에 host ssl + cidr 화이트리스트.
- 별 DB 계정: `harness_app`(read/write minimum)·`harness_batch`·`harness_audit`(append/read), `harness_admin`(DDL). audit_logs는 row-level RLS 또는 트리거로 update/delete 차단.
- 비밀번호 회전 정책(env-driven), `log_statement='ddl'` + slow log, PII column은 view + role grant로 노출 최소.

### Redis 베이스라인
- 인터넷망 직접 노출 금지. Unix socket 또는 internal subnet only.
- `requirepass` + ACL, `rename-command FLUSHALL ""`, `protected-mode yes`, TLS 사용 시 Redis 7 TLS.
- 키 네임스페이스: `harness:auth:refresh:jti:{jti}`(TTL=refresh_exp), `harness:rl:{ip}:{username}`(TTL window).
- maxmemory + LFU policy.

## 8. Secret Hygiene
1. `.env`/`*.env`/`secrets/*`는 `.gitignore` 강제. pre-commit hook + git secret scan(예: gitleaks 정적 desktop 실행) — PoC 범위.
2. validator(`scripts/validate_architecture_contracts.py`) 확장: `password|secret|token|api_key|smtp_pass` 정규식 코드 내 하드코딩 차단(ADR-003 정합).
3. 로그 redaction filter (logging middleware): `Authorization`, `Cookie`, `Set-Cookie`, `access_token`, `refresh_token`, `harness_refresh_token`, `password`, `smtp_pass`, `azure_api_key`, `broker_app_secret`, `*_api_key`, `*_secret`. 마스킹 정책: 앞 4자 + `***`.
4. AI 프롬프트 필터(AI-03 / ADR-002 정합 확장): system prompt + RAG context 합치기 직전에 env-var pattern, JWT pattern(`eyJ`), bearer prefix 차단.
5. SEC-02 PII rules와 합쳐 단일 redaction utility 권고.
6. 운영 격상 시: Azure Key Vault + workload identity, secret rotation cron, audit on secret access.

## 9. BACKLOG Task 후보 (T280~T299)
다음은 본 REG-05 기반 BACKLOG 추가 후보. 실제 등록은 ralplan/팀 lane에서 진행.

- [ ] T280 [security] login rate limit + lockout (IP+username) middleware + `auth_login_failure` audit code 추가
- [ ] T281 [security] password policy enforcement (length≥12, breached prefix list offline), bcrypt cost≥12 또는 argon2id 전환 검토
- [ ] T282 [security] JWT claim 검증 강화: `alg` allowlist, `iss`, `aud`, `nbf`, `jti` + clock_skew=60s, refresh `jti` Redis blocklist
- [ ] T283 [security] refresh token rotation + reuse-detection (재사용 감지 시 전체 jti revoke + audit `auth_refresh_reuse`)
- [ ] T284 [security] HTTP security headers middleware: HSTS, CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, COOP, CORP
- [ ] T285 [security] Vite 빌드 산출물 SRI 정합성 자동화 (static post-process or vite plugin allowlist 추가 + ADR-003 갱신)
- [ ] T286 [security] CORS 동적 검증 강화: wildcard 거부 회귀 테스트 + Origin 비매칭 시 401/403 명확화
- [ ] T287 [security] WebSocket short-lived ticket flow: `POST /ws/ticket` (≤30s, jti, one-shot) + `Origin` 화이트리스트 + `Sec-WebSocket-Protocol=harness.v1`
- [ ] T288 [security] Logging redaction filter (Auth/Cookie/Token/Secret 키 마스킹) + AI prompt redaction extension
- [ ] T289 [security] secret 정적 스캔 게이트 (gitleaks 또는 자체 regex) validator 통합
- [ ] T290 [security] PostgreSQL 인터넷망 비노출 + scram-sha-256 + 최소 권한 계정 분리(`harness_app`/`harness_batch`/`harness_audit`/`harness_admin`) docs/runbooks 반영
- [ ] T291 [security] Redis ACL + requirepass + protected-mode + key namespace 표준화 (harness:auth:rl:*, harness:auth:refresh:*)
- [ ] T292 [security] global API rate limit middleware (per-IP) + 별도 `/auth/*` 강화 버킷
- [ ] T293 [security] audit_logs append-only DB 보호 (UPDATE/DELETE deny via trigger 또는 RLS) + 감사 회귀 테스트
- [ ] T294 [security] error response sanitizer: stack trace, asyncpg 메시지, provider 응답 본문 제거 + sanitized `error_code` 단일 진실
- [ ] T295 [security] HTTPS 강제 + HSTS preload, HTTP→HTTPS 301 + secure cookie 회귀 테스트
- [ ] T296 [security] OWASP ZAP baseline scan PoC 데모 모드 1회 + 결과 sanitized report `docs/security/SEC-03_zap_baseline.md`
- [ ] T297 [security] WebSocket reconnect/heartbeat 정책 명시 (ping 30s, idle 120s, exponential backoff, event_id 멱등 재생) + ADR-001 patch note
- [ ] T298 [security] 운영 격상 후보 항목(MFA/FIDO2/IP whitelist/MDM/KMS/SIEM) backlog T299+ 별도 lane으로 분리 placeholder
- [ ] T299 [security] 합성 직원 token + PoC_AUTO_APPROVAL과 외부 노출 인증 분리 회귀 테스트 (PoC 데모 모드에서도 password policy/rate limit 작동 확인)

## 10. 인용 (Citations)
| 표준/문서 | URL | 사용 항목 |
|---|---|---|
| OWASP Top 10 (2021) | https://owasp.org/Top10/ | §2 매트릭스 A01–A10 |
| OWASP ASVS v4.0.3 | https://owasp.org/www-project-application-security-verification-standard/ | §2 ASVS L1 V2/V3/V13, §3 password policy |
| OWASP Cheat Sheet — JWT for Java | https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html | §4 JWT 검증 |
| OWASP Cheat Sheet — Authentication | https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html | §3 brute-force, lockout |
| OWASP Cheat Sheet — Session Management | https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html | §3 cookie 속성, §4 rotation |
| OWASP Cheat Sheet — REST Security | https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html | §3 rate limit, §5 CORS |
| OWASP Cheat Sheet — Content Security Policy | https://cheatsheetseries.owasp.org/cheatsheets/Content_Security_Policy_Cheat_Sheet.html | §5 CSP |
| OWASP Cheat Sheet — HTTP Security Response Headers | https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html | §5 HSTS, Referrer-Policy 등 |
| OWASP Secure Headers Project | https://owasp.org/www-project-secure-headers/ | §5 COOP, CORP, Permissions-Policy |
| OWASP API Security Top 10 (2023) | https://owasp.org/API-Security/editions/2023/en/0x00-toc/ | §2 A01/A02/A04 |
| RFC 7519 — JSON Web Token | https://datatracker.ietf.org/doc/html/rfc7519 | §4 claim |
| RFC 8725 — JSON Web Token Best Current Practices | https://datatracker.ietf.org/doc/html/rfc8725 | §4 alg whitelist, kid, aud/iss |
| RFC 6797 — HTTP Strict Transport Security | https://datatracker.ietf.org/doc/html/rfc6797 | §3 HSTS |
| RFC 6749 — OAuth 2.0 (refresh token rotation 가이드) | https://datatracker.ietf.org/doc/html/rfc6749#section-10.4 | §4 rotation |
| W3C Subresource Integrity | https://www.w3.org/TR/SRI/ | §5 SRI |
| MDN — `__Host-` cookie prefix | https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie#cookie_prefixes | §3 cookie |
| MDN — SameSite cookies | https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie/SameSite | §3 cookie |
| KISA 암호이용 안내서 / 정보보호 가이드 | https://www.kisa.or.kr | §2 표준 매트릭스 |
| 금융보안원 (FSEC) 자료실 / 전자금융 보안 가이드 | https://www.fsec.or.kr | §2 매트릭스, §7 운영 격상 |
| 금융감독원 전자금융감독규정 (참고: §15 접근통제, §28 인증, §37 로그) | https://www.fss.or.kr | §2 KISA/금융보안원 행, §7 운영 격상 |
| Microsoft Learn — Azure App Service security baseline | https://learn.microsoft.com/azure/app-service/overview-security | §7 운영 격상 |
| Microsoft Learn — Azure Key Vault best practices | https://learn.microsoft.com/azure/key-vault/general/best-practices | §8 secret hygiene 운영 격상 |
| PostgreSQL 17 Docs — Authentication / SSL | https://www.postgresql.org/docs/17/auth-methods.html | §7 PostgreSQL baseline |
| Redis 7 Security | https://redis.io/docs/latest/operate/oss_and_stack/management/security/ | §7 Redis baseline |
| RFC 6455 — WebSocket Protocol (Origin 검증) | https://datatracker.ietf.org/doc/html/rfc6455#section-10.2 | §6 WS Origin |
| OWASP WebSocket Security | https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html#websockets | §6 WS |

---
요약: REG-05는 Round 7 id/password 1-factor 결정을 baseline으로 두고 인터넷망 노출 PoC가 OWASP Top 10 / ASVS L1 / RFC 8725 / KISA·금융보안원 가이드의 핵심 통제를 어떻게 충족하는지 매트릭스로 정렬한 뒤, rate limit·password policy·JWT rotation·secure cookie·CSP/HSTS·SRI·WebSocket ticket·secret hygiene·PostgreSQL/Redis 베이스라인을 정의하고 MFA·FIDO2·IP whitelist·MDM·KMS·SIEM을 운영 격상 후보로 분리, T280~T299 후속 BACKLOG 후보를 도출한다.
