# REG-06 PoC 시뮬레이션 거버넌스 + PoC_AUTO_APPROVAL 패턴 Best Practice

## 1. 메타데이터
- 문서 ID: REG-06
- Lane: Phase 2 외부 리서치 L6 (시뮬레이션 거버넌스)
- 작업 디렉토리: `<repo-root>`
- 생성: 2026-05-17 (Asia/Seoul)
- 입력 컨텍스트: BIZ-09 (Recommendation/Order Simulation 4-gate), BIZ-06 (compliance action_code), REG-01 (legal impact), REG-02 (supervisor rules), REG-04 (AI governance), REG-05 (인터넷망 baseline), SEC-01 (5 roles + row scope), OBS-02 (canonical action_code)
- Scope: 인터넷망 PoC가 "고객 권유 + 모의 주문 4-gate + 7 AI 에이전트 실호출 + autopilot 시연"을 운영 사고 없이 외부 관계자에게 시연하기 위한 시뮬레이션 거버넌스 baseline + `PoC_AUTO_APPROVAL` action_code 패턴 명세
- Non-goal: 실 주문/실 계좌 연계, 실 고객 식별 데이터 사용, 운영 환경 격상 후 거버넌스(별도 문서로 이관)
- 출력 산출물 제한: 본 파일만 작성. REG-01/02/04/05만 참조. BIZ-09/BIZ-06은 읽기 전용 참조

## 2. PoC 거버넌스 표준 매트릭스
| 표준/출처 | 핵심 통제 (PoC 관련) | Harness 현행 적용 | 차이/Gap (보강 후보) |
|---|---|---|---|
| Stripe Test Mode (`sk_test_`/`pk_test_` vs `sk_live_`/`pk_live_` 분리, restricted keys, IP 제한) | 결제·인증 자원을 test/live 별 namespace 분리, 시크릿 vault, IP allowlist | 합성 고객·합성 포트폴리오·모의 주문 row가 별도 status_code(SIMULATED_EXECUTED) namespace로 격리, JWT secret env 분리 | 시연용 secret/실 provider key의 `.env` 단일 폴더 공존 → POC vs PROD prefix 강제(env_naming gate) 미문서 |
| AWS Sandbox OU (Innovation Sandbox, SCP-기반 preventive guardrail, lifecycle/cost cap) | Sandbox 계정은 prod와 OU 분리, SCP로 위험 액션 거부, 시한·예산 제한 | 단일 PoC 배포 환경, batch budget guard 일부 존재 | demo_mode SCP-유사 가드 (예: prod DSN 차단, real_send=false 강제) 명문화 필요 |
| SOC2/ISO 27001 — 자동화된 결정 audit + Segregation of Duties (immutable WORM 로그, reviewer ≠ author) | 자동 승인/거부의 evidence·timestamp·reviewer 분리 보관, append-only | audit_logs 5년, action_code canonical, AUDIT_VIEWER 읽기 전용 | `PoC_AUTO_APPROVAL`은 사람 reviewer 부재 — SoD 결손을 명시적 코드로 노출 + 시연 종료 후 PROD에서는 차단 |
| Chaos Engineering (Netflix Chaos Monkey + Principles of Chaos) — opt-in, blast radius 한정, abort 조건, working-hour window | non-critical 우선, 즉시 비활성 토글, 명시적 환경/리전/% 한정, P99/error rate abort | autopilot 자율 시연·provider degraded fault injection 부분 존재 | `demo_mode=true` AND working-hour AND admin attest 삼중 조건 미문서; abort 조건 (error rate >X%) docs 결손 |
| Paper Trading (Alpaca, Schwab thinkorswim, QuantConnect) — 시세는 real, 라우팅·정산은 simulated, CAT-style log, 합성 자금/계정 | 동일 흐름(Order entry→risk check→fill simulation)·실 시세 + 가상 자금, immutable ledger | order_simulations.status_code=SIMULATED_EXECUTED + market_prices 실시세 + 합성 자금 | UI에 "SIMULATED — no real order routed" 배지 강제·screenshot 회귀 미문서 |

## 3. `PoC_AUTO_APPROVAL` 패턴 권장 (action_code · gate_evidence_json · UI 노출)
PoC는 직원 4-eyes 결재(BRANCH_MANAGER 승인)를 시연 흐름에서 자동화한다. 이 자동화는 **운영 환경에서는 금지**이며, audit에서 사람 reviewer 부재를 명시적으로 노출해야 한다.

### 3.1 `action_code` 명명 (OBS-02 canonical 정합)
신규 action_code (모두 audit_logs.action_code에 enum 등록 권장):
- `recommendation_simulation_auto_approve` — 추천 시뮬레이션 자동 승인 (4-gate 통과 + demo_mode=true)
- `order_simulation_auto_approve` — 모의 주문 자동 승인
- `order_simulation_auto_execute_simulated` — 가상 체결까지 자동 완료
- `poc_auto_approval_blocked` — 게이트 실패로 자동 승인이 차단됨
- `poc_auto_approval_denied_in_prod` — 운영 환경에서 시도된 자동 승인 거부(고정 fail-closed)
- `demo_mode_toggle_on` / `demo_mode_toggle_off` — admin toggle 변경 이벤트 (actor=ADMIN, 사유 필수)

명명 규칙:
- 접두 `PoC_AUTO_APPROVAL`을 `detail_json.governance_marker` 필드에 항상 포함하여 grep·관제 쿼리에서 격리 가능하도록 한다.
- 운영 격상 시 `recommendation_simulation_auto_approve` 등은 enum에서 **제거**한다(코드 dead-letter 보존).

### 3.2 `gate_evidence_json` 구조 (audit_logs.detail_json 하위)
```json
{
  "governance_marker": "PoC_AUTO_APPROVAL",
  "demo_mode": true,
  "demo_mode_attested_by": "EMP_ADMIN_001",
  "environment": "poc-internet",
  "auto_approval_reason_code": "FOUR_GATES_PASSED_NO_HUMAN_REVIEWER",
  "four_gates": {
    "suitability_check": {"status": "PASSED", "rule_id": "SUIT-2024-03", "score": 0.92},
    "explanation_duty": {"status": "PASSED", "doc_versions": ["MIFID-KR-2026Q1"], "ack_at": "2026-05-17T09:12:03+09:00"},
    "synthetic_consent": {"status": "PASSED", "consent_id": "SYN-C-00184", "synthetic": true},
    "employee_approval": {"status": "AUTO_APPROVED", "approver_role": "PoC_AUTO_APPROVAL", "human_reviewer": null}
  },
  "blocked_reason_codes": [],
  "sod_warning": "human_reviewer=null; this transition is invalid in production",
  "prod_guard": {"would_block_in_prod": true, "guard_env_var": "POC_AUTO_APPROVAL_ENABLED"}
}
```
필수 불변식:
1. `governance_marker == "PoC_AUTO_APPROVAL"` 그리고 `demo_mode == true`인 행만 자동 승인을 기록할 수 있다.
2. `four_gates.*.status` 모두 `PASSED` 이외 값이면 audit row는 `poc_auto_approval_blocked`로 기록되어야 하며 simulation row의 status_code는 `BLOCKED`로 fail-closed 한다.
3. `human_reviewer`는 null이 아닌 값이 들어오는 경우 즉시 일반 `recommendation_simulation_approve`/`order_simulation_approve` 행으로 분기 — 두 코드의 cross-talk 금지.
4. `prod_guard.would_block_in_prod=true`는 정적 상수. 코드에서 prod env 식별 시 동일 path는 401/403 → `poc_auto_approval_denied_in_prod`.

### 3.3 UI 표시 (PoC 시연 시 오인 방지)
- 추천/주문 시뮬레이션 카드 우상단 배지: **"PoC AUTO APPROVAL · 데모 모드"** (배경 amber-500, 텍스트 11px, 좌측 자물쇠 아이콘). 운영 격상 후 자동 제거.
- 상태칩: 기존 `SIMULATED_EXECUTED` 옆에 보조칩 `자동 승인됨 (검토자 없음)`.
- 상세 패널 하단 메시지: "이 화면의 결재는 PoC 데모 환경에서 자동으로 승인됩니다. 실제 주문/계좌 반영은 발생하지 않습니다. 운영 환경에서는 BRANCH_MANAGER의 명시적 결재가 필요합니다."
- aria-label: `data-poc-auto-approval="true"` 속성 + screen reader 텍스트 동일 메시지. E2E 회귀로 배지 존재 검증.
- 인쇄/PDF export 시 워터마크 "POC SIMULATION — NOT A REAL ORDER" 강제(60° 회전, opacity 0.18).

## 4. 5-role 골든패스 + 적대적 시나리오 체크리스트
SEC-01 5 roles × 시뮬레이션 거버넌스 시나리오. 각 셀의 기대 결과(`ALLOW`/`DENY`/`AUDIT-ONLY`)와 회귀 테스트 hook을 명시한다.

| 시나리오 | PB | WM | BRANCH_MANAGER | ADMIN | AUDIT_VIEWER |
|---|---|---|---|---|---|
| G1. 본인 담당 고객 추천 시뮬레이션 생성 (4-gate PASS) → `PoC_AUTO_APPROVAL` 발급 | ALLOW (action_code=recommendation_simulation_create + recommendation_simulation_auto_approve) | ALLOW (동일) | ALLOW | DENY (front-office mutation 금지, REG-05 §A01) | DENY (read only) |
| G2. 4-gate 중 suitability 실패 | DENY(BLOCKED row 저장) + audit `poc_auto_approval_blocked` | 동일 | 동일 | DENY | DENY |
| G3. 모의 주문 시뮬레이션 SIMULATED_EXECUTED 전이 | ALLOW + `order_simulation_auto_execute_simulated` | ALLOW | ALLOW | DENY | DENY |
| G4. 데모 모드 토글 변경 (활성/비활성) | DENY | DENY | DENY | ALLOW (`demo_mode_toggle_on/off` + 사유 필수) | DENY |
| G5. audit_logs 조회·CSV export (PoC_AUTO_APPROVAL governance_marker 필터) | DENY | DENY | DENY | DENY | ALLOW (read-only, row-scope 무제한 within PoC) |
| A1. 다른 PB의 고객 추천 시뮬레이션 생성 시도 (row-scope 위반) | DENY 403 | DENY 403 | ALLOW (branch 내) | DENY | DENY |
| A2. `demo_mode=false`에서 `PoC_AUTO_APPROVAL` 호출 | DENY 409 `poc_auto_approval_denied_in_prod` | DENY | DENY | DENY (toggle 변경 별도) | DENY |
| A3. AUDIT_VIEWER가 추천/주문 mutation 시도 (REG-05 SEC-01 회귀) | n/a | n/a | n/a | n/a | DENY 403 (모든 write endpoint) |
| A4. ADMIN이 front-office mutation 우회 시도 (예: order_simulation POST) | n/a | n/a | n/a | DENY 403 (운영 격상 시에도 영구) | n/a |
| A5. JWT 변조로 role 상승 (PB→ADMIN) | DENY (alg whitelist + iss/aud 검증, REG-05 §JWT) | DENY | DENY | DENY | DENY |
| A6. 동일 시뮬레이션을 1초 내 N회 자동승인 spam (LLM10/ASVS V13 rate-limit) | DENY 429 (사용자별 분당 ceiling) | DENY 429 | DENY 429 | DENY | DENY |
| A7. 합성 고객이 아닌 외부 PII 입력 시도 (synthetic_consent 미존재) | DENY BLOCKED + audit | DENY | DENY | DENY | DENY |
| A8. autopilot 데모가 실 SMTP 발송 시도 | DENY (REG-04 LLM06, BIZ-09 green-path만) + audit `email_draft_send_blocked` | 동일 | 동일 | DENY | DENY |
| A9. demo_mode=false에서 chaos/fault injection 호출 | DENY 409 | DENY | DENY | DENY | DENY |
| A10. PoC_AUTO_APPROVAL audit row tamper (UPDATE/DELETE) | DENY (append-only constraint, DB trigger) | DENY | DENY | DENY | DENY (read만) |

회귀 테스트 hook: `tests/sec/test_poc_auto_approval_matrix.py` (5 roles × 14 시나리오 fixture), `tests/e2e/poc_auto_approval_badge.spec.ts`.

## 5. PoC 데모 모드 admin toggle 안전성
운영 환경에서 우발적으로 `demo_mode=true`가 되어 자동 승인이 켜지면 SOC2 SoD 위반·금융 사고로 직결된다. 다단계 fail-closed가 필요하다.

1. **3-layer attestation (Chaos Monkey opt-in 패턴 차용):**
   - Layer A: `POC_AUTO_APPROVAL_ENABLED=true` 환경변수 (서버 부팅 시 고정, runtime 변경 불가).
   - Layer B: DB `system_flags.demo_mode=true` row (ADMIN가 사유 + ticket_id 입력 시에만 update; trigger가 audit `demo_mode_toggle_on` 기록).
   - Layer C: 요청별 `X-Poc-Demo-Mode: 1` 헤더 (web 정적 빌드에서 환경 식별로 자동 첨부; 운영 빌드에서는 미첨부).
   - 3 layer가 **모두 true**일 때만 `PoC_AUTO_APPROVAL` 경로가 활성. 하나라도 false면 일반 인간 결재 경로로 fallback.
2. **환경 namespace 분리 (Stripe test/live 패턴):**
   - DSN/secret 명명 규칙 강제: `POC_*` vs `PROD_*` prefix. 부팅 시 cross-prefix 결합 감지 → fail-fast.
   - JWT issuer claim `iss=harness-poc` 강제. `iss=harness-prod` 토큰은 PoC 경로에서 거부, 역도 성립.
3. **AWS Sandbox OU 차용 — preventive guardrail:**
   - 운영 빌드 산출물(`pnpm build:prod`)은 컴파일 시점에 `PoC_AUTO_APPROVAL` 핸들러를 dead-code-eliminate (트리쉐이킹 + ESLint `no-poc-auto-approval-in-prod` 룰).
   - 백엔드는 `if env != "poc": raise HTTP_403(code="poc_auto_approval_denied_in_prod")` 가드 함수 통과 후에만 핸들러 진입.
4. **시간·blast radius 한정 (Chaos Engineering):**
   - demo_mode 활성 윈도우 ≤ 8h, 자동 만료. 만료 5분 전 ADMIN 알림 + audit `demo_mode_expiry_warning`.
   - per-employee 자동 승인 빈도 상한 (예: 분당 10, 시간당 60) — 초과 시 일반 결재로 강제 전환.
5. **즉시 abort 조건 (chaos abort criteria 차용):**
   - 4-gate fail-closed 비율 > 30% (10분 sliding window) → demo_mode 자동 OFF + 알림.
   - audit_logs 적재 지연 > 5초 또는 적재 실패 1건 → demo_mode 자동 OFF.
   - rate_limit 초과 행 > 5% → 자동 OFF.

## 6. 합성 데이터·합성 동의·모의 직원 승인 거버넌스
1. **합성 고객 식별:**
   - `customers.is_synthetic=true` 컬럼 + `customer_no` prefix `SYN-` 강제. 시드 외 INSERT 차단(role-level SQL).
   - PII regex(주민번호·계좌번호·실명 패턴)가 합성 고객 row에 매칭되면 fail-fast — 시드 검증 단계(`scripts/check_synthetic_seed.py`).
2. **합성 동의 (synthetic_consent):**
   - `customer_consents.synthetic=true`만 PoC에서 활성. 4-gate `synthetic_consent` 게이트는 `synthetic=true AND consent_status=ACKED`만 PASS.
   - 동의 evidence는 정적 문구 + `acked_at` + `doc_version`을 detail_json에 저장. 실 고객 서명 이미지·음성 녹취 저장 금지.
3. **모의 직원 승인 (PoC_AUTO_APPROVAL 대체 인격):**
   - 자동 승인 actor는 `employee_id=SYS_POC_AUTO_APPROVAL` (실 직원과 구분되는 합성 ID).
   - 4-eyes 외관을 위해 author employee와 approver employee가 같아도 audit row는 둘 모두 `governance_marker=PoC_AUTO_APPROVAL`로 분리 기록 (SoD 결손을 가리지 않는다).
4. **합성 시세·합성 포트폴리오:**
   - 시세는 실(KRX/PYKRX), 평가/주문 결과만 simulated. paper trading 패턴과 일치.
   - `order_simulations.routed_to_exchange=false` 불변식, DB CHECK 제약.
5. **데이터 분리 라벨:**
   - 모든 시뮬레이션 산출물(PDF/CSV/이메일 본문)에 워터마크/푸터 "POC SIMULATION — SYNTHETIC CUSTOMER — NO REAL ORDER".
   - 외부 공유 시 PDF 메타데이터 `Subject`에 동일 문구 강제.

## 7. PoC 종료 후 운영 전환 마이그레이션 체크리스트
운영 격상 시 다음을 **순서대로** 수행. 한 항목이라도 미완이면 demo_mode를 끄지 못한다.

1. [ ] `POC_AUTO_APPROVAL_ENABLED` 환경변수 제거 + 빌드 산출물에 `PoC_AUTO_APPROVAL` 핸들러 부재 자동 검증(`grep -r PoC_AUTO_APPROVAL dist/` empty).
2. [ ] action_code enum에서 `*_auto_approve`·`*_auto_execute_simulated`·`demo_mode_toggle_*` 제거 (DB enum + 코드 상수). audit_logs 기존 행은 보존.
3. [ ] `system_flags.demo_mode` 컬럼 default=false + UPDATE 트리거 disabled (운영에서 raise).
4. [ ] 합성 고객 namespace(`SYN-` prefix) 운영 DB에서 격리/제거. 실 고객 시드/API 연결 검증.
5. [ ] PoC UI 배지/워터마크/`data-poc-auto-approval` 자동 제거 — 운영 빌드 시 E2E 회귀로 부재 확인.
6. [ ] 4-gate `employee_approval`는 반드시 `human_reviewer != null` AND `approver_role IN {BRANCH_MANAGER}`로 강제 (DB CHECK).
7. [ ] SMTP·메시징·결제 등 외부 인터페이스 키를 `POC_*` → `PROD_*` rotation. cross-prefix 사용 시 부팅 거부.
8. [ ] JWT `iss=harness-prod` 발급으로 전환 + PoC 토큰 blocklist.
9. [ ] audit_logs read-access를 AUDIT_VIEWER만 유지하고 PoC governance_marker row를 별도 archive partition으로 cold-storage 이관(5년 보존).
10. [ ] 운영 격상 전 SOC2 evidence pack 생성: SoD 매트릭스, 자동 승인 부재 증명, immutable 로그 evidence.
11. [ ] REG-04 LLM06(excessive agency)·LLM09 회귀 — autopilot이 운영에서는 도구 호출 권한이 더 좁아지는지 검증.
12. [ ] REG-05 §A05 보안 misconfig 회귀(HSTS/CSP/rate-limit) 운영 환경 baseline 통과.
13. [ ] 운영 환경에서 `poc_auto_approval_denied_in_prod` 응답이 모든 시뮬레이션 엔드포인트에서 발생하는지 chaos 테스트.
14. [ ] PoC 데모용 chaos/fault injection 엔드포인트 제거 또는 SRE-전용 인증 게이트로 격상.
15. [ ] 모든 4-gate audit row schema 마이그레이션 검증 (synthetic_consent → real_consent 컬럼 명 변경 등).

## 8. BACKLOG task 후보 T300~T319
신규 epic 후보 — **E20 — PoC Simulation Governance Hardening**.

- T300 audit_logs `governance_marker` 필드 표준화 + index — PoC_AUTO_APPROVAL 격리 쿼리 가능 (BIZ-06, OBS-02 정합).
- T301 `action_code` enum 확장: `recommendation_simulation_auto_approve`, `order_simulation_auto_approve`, `order_simulation_auto_execute_simulated`, `poc_auto_approval_blocked`, `poc_auto_approval_denied_in_prod`, `demo_mode_toggle_on/off`, `demo_mode_expiry_warning` (V0xx 마이그레이션).
- T302 `gate_evidence_json` JSON Schema + Pydantic 모델 + 5종 BLOCKED reason_code (`SUITABILITY_FAIL`, `EXPLANATION_FAIL`, `CONSENT_MISSING`, `EMPLOYEE_APPROVAL_REQUIRED_IN_PROD`, `ENV_MISMATCH`).
- T303 `system_flags.demo_mode` 컬럼 + UPDATE 트리거 + ADMIN 사유 필수 enforcement.
- T304 3-layer attestation guard (`POC_AUTO_APPROVAL_ENABLED` env + DB flag + `X-Poc-Demo-Mode` header) FastAPI 의존성.
- T305 운영 빌드 산출물에서 `PoC_AUTO_APPROVAL` 핸들러 부재 검증 — CI gate (`scripts/check_no_poc_in_prod.sh`).
- T306 UI `PoC AUTO APPROVAL · 데모 모드` 배지 + 상세 메시지 + aria 속성 + screenshot 회귀.
- T307 PDF/CSV/이메일 워터마크 `POC SIMULATION — NOT A REAL ORDER` 강제 + 메타데이터 검증.
- T308 5 roles × 14 시나리오 행렬 회귀 (`tests/sec/test_poc_auto_approval_matrix.py`).
- T309 Playwright E2E: 배지/상태칩/메시지/print preview 4종 회귀.
- T310 합성 고객 `customer_no` `SYN-` prefix CHECK 제약 + 시드 검증 스크립트.
- T311 `order_simulations.routed_to_exchange=false` CHECK 제약 + 우회 차단 단위 테스트.
- T312 demo_mode 8h 자동 만료 + 5분 전 경고 batch hook + audit row.
- T313 자동 abort 조건(4-gate 실패율 30%, audit 적재 지연 5s, rate-limit 초과 5%) — 모니터링 룰 + auto-off.
- T314 per-employee 자동 승인 ceiling rate-limit (분당 10, 시간당 60) + 429 응답 회귀.
- T315 audit_logs append-only DB 트리거(UPDATE/DELETE raise) + 회귀 (REG-04 §Audit Backbone, SOC2 immutable 요건).
- T316 SoD evidence pack 생성기 — PoC_AUTO_APPROVAL 행 + human reviewer 부재 명시 보고서(주간 batch).
- T317 운영 격상 마이그레이션 체크리스트 자동화 스크립트 (`scripts/poc_to_prod_migration_check.sh`) — §7의 15항 cover.
- T318 chaos/fault injection 엔드포인트 demo_mode 가드 + working-hour 윈도우 검증.
- T319 REG-06 회귀: REG-04(LLM06 Excessive Agency)·REG-05(SEC-01 row scope)·BIZ-09(4-gate)·BIZ-06(action_code canonical) cross-link 회귀 테스트 인덱스.

## 9. 인용
검색일: 2026-05-17 (Asia/Seoul).

1. Stripe Documentation — *Best practices for managing secret API keys*. https://docs.stripe.com/keys-best-practices (test vs live 분리, restricted keys, secret 보관, IP 제한, dev/staging/prod 키 분리).
2. AWS Cloud Operations Blog — *Best practices for creating and managing sandbox accounts in AWS*. https://aws.amazon.com/blogs/mt/best-practices-creating-managing-sandbox-accounts-aws/ (Sandbox OU, SCP preventive guardrail, lifecycle/cost 한정, prod와 격리). 보조: AWS Whitepaper — *Sandbox OU (Experimental)*. https://docs.aws.amazon.com/whitepapers/latest/organizing-your-aws-environment/sandbox-ou.html
3. Workstreet / Hyperproof — *SOC 2 Type 2 Audit*. https://hyperproof.io/resource/soc-2-type-2-preparing-for-your-first-audit/ 및 Liquibase — *SOC 2 Compliance for Database Security*. https://www.liquibase.com/resources/guides/soc-2-compliance-for-database-security-trust-services-criteria-best-practices (자동화된 결정 audit, immutable WORM 로그, SoD reviewer ≠ author, append-only).
4. Netflix Chaos Engineering — *Principles of Chaos Engineering* + Coralogix *How Netflix Uses Fault Injection*. https://principlesofchaos.org/ 및 https://coralogix.com/blog/how-netflix-uses-fault-injection-to-truly-understand-their-resilience/ (opt-in, blast radius 한정, working-hour 윈도우, 즉시 abort 조건, 비활성 토글).
5. Alpaca Markets — *Paper Trading API Docs*. https://docs.alpaca.markets/us/docs/paper-trading 및 ETNA — *Best Paper Trading Platform for U.S. Broker-Dealers*. https://www.etnasoft.com/best-paper-trading-platform-for-u-s-broker-dealers-why-advanced-simulation-sets-the-2025-standard/ (실 시세 + 가상 자금, 라우팅·정산 simulated, CAT-style log, immutable ledger, 합성 데이터 거버넌스).
