# SEC-03 OWASP ZAP Baseline Report (Sanitized)

## 1. Metadata
- 문서 ID: SEC-03
- Scope: REG-05 T296 demo-mode ZAP baseline 결과 게시 (sanitized)
- 마지막 스캔: **<not-run-yet>** (Wave 1 close-out 직전 PoC 데모 시 1회)
- 도구: `owasp/zap2docker-stable` (docker), baseline 모드 (`zap-baseline.py -I`)
- 게시 정책: 본 문서는 **sanitized** summary 만 게시. 원본 `.omx/reports/zap/zap-baseline-*.json`/`*.html` 은 git 비포함.
- Cross-refs: RUN-07 (runbook), `scripts/run_zap_baseline.sh`, REG-05 §3·§7

## 2. Sanitization Contract
RUN-07 §6 의 sanitization 규칙을 따른다. 발행 시 다음 항목이 본 문서에 존재하지 않아야 한다:
- 요청/응답 본문
- 실제 hostname / 내부 IP / private subnet
- Authorization 헤더, cookie, refresh token, JWT
- stack trace / framework internal path

## 3. Severity Counts (template)
첫 PoC 데모 스캔 후 아래 표를 갱신한다.

| Severity | Count |
|---|---|
| High | _<n>_ |
| Medium | _<n>_ |
| Low | _<n>_ |
| Informational | _<n>_ |

수락 조건: **High == 0**.

## 4. High Findings (template)
| Alert | CWE | Confidence | Instance Count | Remediation Reference (요약) | 후속 BACKLOG |
|---|---|---|---|---|---|
| _<alert>_ | _<CWE-id>_ | _<conf>_ | _<n>_ | _<<=280자 요약>_ | _<task id>_ |

## 5. Medium Findings (요약만)
| Alert | CWE | 잔존 사유 / 후속 BACKLOG |
|---|---|---|
| _<alert>_ | _<CWE-id>_ | _<note>_ |

## 6. Mitigation Already In Place (참조)
| 통제 | 적용 위치 |
|---|---|
| HTTP security headers (HSTS, CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy, COOP, CORP) | task #11 middleware |
| CORS guard (wildcard 거부, credentialed origin 명시) | SEC-01, task #11 |
| Rate limit (global + `/auth/*`) | task #10, task #13 |
| JWT BCP (alg allowlist, aud/iss, jti, rotation, reuse-detection) | task #10 |
| Secret hygiene (gitleaks gate) | DEV-04, task #17 |
| Append-only audit (V008 + V019) | ADR-006 |
| Account separation (PG 4 / Redis 3) | SEC-04 |
| HTTPS strict transport | task #13 |

## 7. Operational Uplift Candidates
- ZAP active scan (취약점 실 호출 — 합성 환경에서만).
- ZAP authenticated scan (synthetic JWT 주입).
- ZAP API scan (OpenAPI spec 합본 완성 시).
- CI 정기 실행 + Slack 알림.

## 8. Reference
- RUN-07 OWASP ZAP Baseline Runbook (실행 절차).
- REG-05 §3 항목 9 (Error Surface), §7 (운영 격상 후보).
- ADR-007 (validator JSON triple).
- OWASP ZAP: https://www.zaproxy.org/docs/
