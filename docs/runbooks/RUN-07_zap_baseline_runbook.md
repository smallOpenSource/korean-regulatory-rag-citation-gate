# RUN-07 OWASP ZAP Baseline Runbook

## 1. Metadata
- 문서 ID: RUN-07
- Scope: REG-05 T296 — PoC 데모 모드 1회 ZAP baseline 스캔.
- Cross-refs: `scripts/run_zap_baseline.sh`, `docs/security/SEC-03_zap_baseline.md`, REG-05 §3·§7.

## 2. When to Run
- **PoC 데모 직전 한 번** (REG-05 T296 의 "demo 모드 1x" 정의).
- 인터넷망 노출 origin 변경 시.
- Stage 7 close-out 직전 (운영 격상 평가용).
- 운영 격상 후보(아래 §9): 매 릴리즈 후 자동.

## 3. Pre-flight Checklist
- [ ] FastAPI 가 `http://localhost:8000` 또는 `${HARNESS_API_URL}` 로 응답한다 (`/health` 200).
- [ ] DB 마이그레이션 V001~V022 적용 완료 (혹은 PoC seed 적용).
- [ ] `CORS_ENABLED` 가 운영 의도와 일치 (보통 `false` + same-origin 프록시).
- [ ] 합성 직원 계정만 사용중. 실 고객 데이터 없음 (SEC-02).
- [ ] docker 데몬 동작중 (`docker info` 0 rc).
- [ ] `.omx/reports/zap/` 디렉토리 쓰기 가능.

## 4. Run

```bash
cd <repo-root>
# 기본: 로컬 PoC
scripts/run_zap_baseline.sh
echo $?   # 0 pass / 2 fail (HIGH 잔존) / 3 config error

# 또는 데모 도메인 명시
HARNESS_API_URL=https://demo.example.invalid scripts/run_zap_baseline.sh
```

산출물 (3개):
- `.omx/reports/zap/zap-baseline-<TS>.json` — ZAP 원본
- `.omx/reports/zap/zap-baseline-<TS>.html` — ZAP HTML 리포트(공유 금지: 인증 endpoint URL 포함)
- `.omx/reports/zap/zap-baseline-<TS>.summary.json` — **sanitized** 요약 (host 마스킹, request body/payload 제거, CWE/severity/플러그인 id 만 유지). SEC-03 발행에 사용.

## 5. Acceptance Gate
- `high_count == 0` → PASS, exit 0.
- `high_count > 0` → FAIL, exit 2 (PR/릴리즈 차단). 우선 HIGH 잔존 항목을 해결한 뒤 재실행.

## 6. Sanitization Rules (SEC-03 발행 시)
다음 항목은 산출물에 절대 포함되지 않는다 (스크립트 자동 적용 + 리뷰어 재확인):

| 항목 | 처리 |
|---|---|
| 요청 본문(body) | 제거 — 응답 payload 도 제거 |
| URL 의 hostname | `***target-host***` 로 마스킹 |
| Authorization 헤더 값 | 제거 (gitleaks 게이트와 정합) |
| 내부 IP / private subnet | 제거 |
| cookie 값 | 제거 |
| stack trace / framework internal | 제거 |
| 보존되는 항목 | alert name, riskdesc, confidence, CWE id, WASC id, plugin id, instance count, solution/reference 요약(<=280자) |

## 7. SEC-03 Publication

```bash
# 1) 최신 sanitized summary 확인
ls -t .omx/reports/zap/*.summary.json | head -1

# 2) SEC-03 본문 갱신: 표·counts·CWE 항목 인용. 원본 zap-baseline-*.json/html 은 게시 금지.
# (수동 편집 — 리뷰어가 sanitization 누락 확인)
```

SEC-03 본문이 갖춰야 할 섹션 (Template):
- Metadata: scan target (sanitized host), scanner version, run timestamp, scan mode (baseline -I)
- Severity counts 표 (High/Medium/Low/Informational)
- HIGH findings — 항목별 alert name, CWE, remediation reference (URL 제거)
- Remediation tracker — 각 HIGH 항목의 후속 BACKLOG task ID
- 운영 격상 후보 (active scan, authenticated scan, fuzzing, full ZAP API)

## 8. Troubleshooting

| 증상 | 원인 | 조치 |
|---|---|---|
| `[zap] config error: docker not on PATH` | docker 미설치 | host 에서 `dnf install docker` + `systemctl start docker` |
| `Unable to find image 'owasp/zap2docker-stable:latest'` | 인터넷 차단/오프라인 | 사전 `docker pull owasp/zap2docker-stable` |
| `[zap] config error: target ... unreachable` | API 미기동 | `scripts/status.sh --deep` 으로 진단 |
| ZAP timeout | 타겟이 너무 많은 페이지 노출 | `-T <minutes>` 추가, 또는 spider 범위 축소 (`-d` debug) |
| HTML 보고서 공유 요청 | 인증 URL / IP 노출 위험 | **금지**. `.summary.json` 만 공유 + SEC-03 만 게시 |

## 9. 운영 격상 후보 (PoC scope 밖)
- ZAP **active scan** (취약점 실 호출) — 합성 환경에서만, 실 트래픽 절대 금지.
- ZAP **authenticated scan** — synthetic 직원 JWT 주입 (단, refresh cookie 노출 우려로 PoC 에선 제외).
- ZAP **API scan** (OpenAPI/Swagger 기반) — Harness 의 API spec 합본 완성 후 도입.
- CI 정기 실행 (주 1회) + Slack 알림.

## 10. Reference
- OWASP ZAP Baseline: https://www.zaproxy.org/docs/docker/baseline-scan/
- OWASP ZAP API: https://www.zaproxy.org/docs/api/
- REG-05 §3 항목 9 (Error Surface), §7 (PoC scope vs 운영 격상).
- ADR-007 (validator JSON triple convention).
