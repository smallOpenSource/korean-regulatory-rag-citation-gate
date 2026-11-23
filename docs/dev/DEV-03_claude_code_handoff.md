# DEV-03 Claude Code 인수인계 문서

- **작성일:** 2026-05-16 (Asia/Seoul)
- **작성 목적:** Codex/OMX 크레딧 소진으로 인해 남은 검토·개선 작업을 Claude Code가 안전하게 이어받기 위한 단일 인수인계 문서
- **대상 경로:** `<repo-root>`
- **현재 Git HEAD:** `defab4f` (`omx(team): merge worker-1`)
- **현재 상태 요약:** 최신 전체 검증 게이트와 총제품 readiness validator는 통과했으나, `BACKLOG.md`에는 일부 과거 partial/open 표기가 남아 있으므로 Claude Code의 첫 작업은 **실제 구현/검증 증거와 문서 상태를 재대조**하는 것이다.

---

## 1. 절대 준수 규칙

1. **ORM/Mapper 금지:** JPA/Hibernate/MyBatis Mapper/SQLAlchemy ORM 사용 금지.
2. **마이그레이션 프레임워크 금지:** Flyway/Liquibase/Alembic 사용 금지. `db/migrator.py`와 raw SQL만 사용.
3. **SQL_ID 필수:** DDL/DML/쿼리 파일 및 코드 내 SQL은 첫 줄 또는 SQL 시작부에 `/* sql_id: short_human_readable_id */` 형식 주석이 있어야 한다.
4. **PostgreSQL 17 + Redis 필수:** 우회/mock/fake cache 사용 금지.
5. **고객·포트폴리오·직원 데이터:** 합성 데이터만 허용. 실제 개인정보를 로그/프롬프트/문서에 쓰지 않는다.
6. **시장·공시·거시 데이터:** 실제 provider row만 허용. provider row를 합성하거나 성공으로 위장하지 않는다.
7. **AI 생성물:** 생성 시각, 모델명, 근거/인용, 감사로그가 있어야 하며 설명의무·적합성 gate 없이 권유 흐름을 열지 않는다.
8. **문서 동기화:** DB/API/AI/배치/프론트 변경은 관련 `docs/`와 루트 `PLANS.md`, `MEMORIES.md`, `BACKLOG.md`를 함께 갱신한다.
9. **비밀정보:** `.env`는 이미 사용자 제공 정보가 들어 있는 로컬 파일이다. 값을 출력하거나 커밋하지 말고, 문서에는 변수명과 목적만 기록한다.

---

## 2. 먼저 읽을 파일

Claude Code는 새 작업을 시작하기 전에 아래 순서로 읽어야 한다.

1. `AGENTS.md`
2. `docs/product/PRD-01_product_overview.md`
3. `docs/product/PRD-04_user_scenarios.md`
4. `docs/business/BIZ-02_pb_wm_workflow.md`
5. `docs/business/BIZ-06_compliance.md`
6. `docs/db/DB-02_logical.md`
7. `docs/api/API-01_contracts.yaml`
8. `docs/ai/AI-02_agent_spec.yaml`
9. `docs/batch/BATCH-01_pipeline_overview.md`
10. `docs/dev/DEV-01_dev_conventions.md`
11. `.omx/plans/ralplan-production-readiness-total-completion.md`
12. 최신 검증 산출물:
    - `.omx/reports/verification/gate-20260516T144732Z.md`
    - `.omx/reports/verification/total-product-readiness-result-20260516T145428Z.json`
    - `.omx/specs/autoresearch-service-readiness-top200-30d/result.json`
    - `.omx/reports/verification/serviceable-canonical-run-latest.json`
    - `.omx/reports/verification/serviceable-top200-30d-latest.json`
    - `.omx/reports/verification/krx-source-governance-latest.json`

---

## 3. 검증된 현재 기준선

### 3.1 전체 검증 게이트

최근 실행된 명령:

```bash
cd <repo-root>
export HARNESS_ROOT=<repo-root>
export PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
./scripts/run_verification_gate.sh
```

결과 산출물:

- `.omx/reports/verification/gate-20260516T144732Z.md`
- `failures=0`
- 완료 시각: `2026-05-16T14:54:20Z` (UTC)
- 통과 항목:
  - Runtime status
  - Ruff
  - Pytest
  - Web typecheck
  - Web lint
  - Web unit tests
  - Web build
  - Playwright E2E
  - Batch pipeline all-provider diagnostic
  - Batch pipeline required-provider acceptance

### 3.2 총제품 readiness validator

최근 실행된 명령:

```bash
cd <repo-root>
/opt/conda/envs/wm_env/bin/python scripts/verify_total_product_readiness.py \
  --verification-gate-report <repo-root>/.omx/reports/verification/gate-20260516T144732Z.md \
  --serviceable-result-json <repo-root>/.omx/specs/autoresearch-service-readiness-top200-30d/result.json \
  --result-json <repo-root>/.omx/reports/verification/total-product-readiness-result-20260516T145428Z.json
```

결과:

- `.omx/reports/verification/total-product-readiness-result-20260516T145428Z.json`
- `status=passed`
- `passed=true`
- 주요 component:
  - `verification_gate`: passed
  - `serviceable_readiness`: passed
  - `false_green_controls`: passed

### 3.3 국내시장 serviceable evidence

최신 증거 기준:

- 공식 KRX top-200 selected count: `200`
- 30일 커버리지: `coverage_ratio=1.0`
- 누락 member-day: `missing_member_days=0`
- real provider rows only
- fabricated provider rows 없음
- Redis/PostgreSQL 기반 canonical wrapper 통과

대표 산출물:

- `.omx/specs/autoresearch-service-readiness-top200-30d/result.json`
- `.omx/reports/verification/serviceable-canonical-run-latest.json`
- `.omx/reports/verification/serviceable-top200-30d-latest.json`
- `.omx/reports/verification/krx-source-governance-latest.json`

---

## 4. 실행 환경과 운영 명령

### 4.1 Python / Node / Playwright

- Python: `/opt/conda/envs/wm_env/bin/python`
- Playwright CLI: `/opt/conda/envs/playwright/bin/playwright`
- Browser cache: `/opt/playwright-browsers`

권장 환경 변수:

```bash
cd <repo-root>
export HARNESS_ROOT=<repo-root>
export PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
```

### 4.2 기동/중지/상태

```bash
./scripts/status.sh
./scripts/start.sh
./scripts/stop.sh
```

주의:

- 포트와 DB/Redis/API/provider 설정은 `.env`를 준용한다.
- `.env` 값을 출력하지 않는다.
- 서비스가 이미 떠 있으면 포트 기준으로 충돌 프로세스를 확인하고 재기동한다.

### 4.3 배치/검증 스크립트

주요 스크립트:

- `scripts/run_batch_pipeline.sh`
- `scripts/run_batch_scheduler.py`
- `scripts/run_serviceable_canonical_readiness.py`
- `scripts/capture_krx_source_governance.py`
- `scripts/capture_serviceable_top200_30d_artifact.py`
- `scripts/capture_data_readiness.py`
- `scripts/verify_serviceable_readiness.py`
- `scripts/verify_total_product_readiness.py`
- `scripts/run_verification_gate.sh`
- `scripts/qa_hostile_checks.sh`

권장 최종 검증:

```bash
cd <repo-root>
export HARNESS_ROOT=<repo-root>
export PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
./scripts/run_verification_gate.sh
/opt/conda/envs/wm_env/bin/python scripts/verify_total_product_readiness.py \
  --verification-gate-report "$(ls -t .omx/reports/verification/gate-*.md | head -1)" \
  --serviceable-result-json .omx/specs/autoresearch-service-readiness-top200-30d/result.json \
  --result-json .omx/reports/verification/total-product-readiness-result-$(date -u +%Y%m%dT%H%M%SZ).json
```

---

## 5. 이미 완료된 핵심 구현

최신 산출물 기준으로 다음 영역은 구현 및 검증이 완료되었거나 게이트를 통과했다.

1. **공식 KRX OpenAPI provider readiness**
   - `HARNESS_BATCH_KRX_SOURCE=KRX`
   - `HARNESS_BATCH_KRX_POLICY=OFFICIAL_KRX_APPROVED`
   - `KRX_API_KEY`/base URL 기반 공식 KRX rows
   - top-200/30일 coverage 통과
2. **OpenDART/ECOS/Data.go.kr/BROKER provider evidence**
   - OpenDART document body/chunk lineage
   - ECOS 관측치
   - Data.go.kr/BROKER 보조 evidence
3. **합성 고객/포트폴리오 seed 현실성 개선**
   - 고객명/포트폴리오명 placeholder 제거
   - PB/WM 문맥에 맞는 plausible persona
4. **프론트 reload-safe session 및 한국어 UX 개선**
   - 새로고침 후 재로그인 문제 수정
   - `URGENT NBA` 등 부자연스러운 영어 UI copy 한글화
5. **배치 runner와 readiness artifact**
   - `required` acceptance와 `all` diagnostic 분리
   - provider-window postconditions 저장
6. **WebSocket foundation**
   - `/ws` backend foundation, JWT auth, ping/pong, subscribe ack, Redis channel fanout loop, RBAC/row-scope filtering 기반 구현
7. **Email draft/send backend foundation**
   - `POST /email-drafts`
   - `POST /email-drafts/{draft_id}/send`
   - PB/WM row scope, APPROVED-only send, SMTP fail-closed, delivery audit
8. **최종 verification gate**
   - backend/web/E2E/batch/readiness/false-green checks 통과

---

## 6. Claude Code가 우선 확인해야 할 잔여/불일치

아래는 “반드시 미구현”이라는 뜻이 아니라, **최신 코드와 최신 문서/백로그가 서로 완전히 일치하는지 재검증해야 하는 항목**이다. 중복 개발 전에 먼저 증거를 확인한다.

### 6.1 루트 문서와 최신 구현 증거 불일치 가능성

`BACKLOG.md`에는 아직 과거 partial/open 표현이 남아 있다. 예:

- T14~T20 일부 partial 설명
- T22~T25 일부 provider/batch/RAG 표현
- T27~T30 frontend/workflow 표현
- T37~T39 provider/data readiness 표현

하지만 최신 `.omx/reports/verification/*`와 `.omx/plans/ralplan-production-readiness-total-completion.md`의 팀 구현 이후 증거는 더 최신일 수 있다. Claude Code는 먼저 다음을 수행한다.

1. 실제 route/screen/batch/job inventory 생성
2. `BACKLOG.md`의 partial/open 항목별로 “완료/잔여/문서 stale” 판정
3. 구현이 완료된 항목은 `BACKLOG.md`, `PLANS.md`, `MEMORIES.md`, 관련 `docs/`에 반영
4. 구현이 안 된 항목만 별도 task로 남김

### 6.2 Live SMTP green path

- email send workflow는 fail-closed backend 경로와 audit는 구현되었다.
- 실제 SMTP delivery green path는 환경 의존이며, 최신 인수인계 기준에서 “실제 외부 SMTP 전송 성공” 증거는 없다.
- 운영 전 필요 시 실제 SMTP sandbox/allowlist 환경에서 green-path evidence를 별도로 남긴다.

### 6.3 RAG/embedding coverage

- readiness는 통과했지만 최신 gate report에는 embedded/pending chunk 수가 함께 기록되어 있다.
- Claude Code는 RAG 답변 품질, citation coverage, pending chunk 처리 정책, prompt-injection quarantine을 사용자 시나리오 기준으로 다시 확인한다.

### 6.4 WebSocket producer/UI realtime completion

- backend foundation은 구현되었지만, 실제 producer 이벤트와 UI realtime 반영이 모든 화면에서 완전한지 확인해야 한다.
- 특히 `nba_created`, `nba_updated`, `price_tick`, `batch_status_change`, `ai_job_done` 이벤트가 backend docs, frontend types, E2E와 일치해야 한다.

### 6.5 프론트 기능별 role matrix

- Playwright E2E는 최신 gate에서 통과했다.
- 그래도 Claude Code는 권한별 전체 화면/동작을 다시 점검한다.
- 최소 계정군: PB, WM, manager, admin, audit viewer, anonymous.

### 6.6 npm advisory와 build warning

최신 검증에서 치명 실패는 아니었지만 다음은 운영 전 점검 후보다.

- `npm ci` 계열에서 moderate vulnerability 경고가 있었던 이력
- Vite build에서 `src/lib/api.ts`가 static/dynamic import 양쪽에 걸려 chunk 분리 경고를 낸 이력
- npm의 `Unknown env config python` 경고 이력

---

## 7. Claude Code 권장 작업 순서

### 7.1 절대 먼저 할 것

```bash
cd <repo-root>
git status --short --branch --untracked-files=all
./scripts/status.sh
```

- worktree가 더럽다면 사용자/이전 agent 변경인지 확인하고 덮어쓰지 않는다.
- `.env` 출력 금지.

### 7.2 기준선 재현

```bash
export HARNESS_ROOT=<repo-root>
export PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers
./scripts/run_verification_gate.sh
```

- 실패하면 새 기능 개발보다 재현 실패 root cause를 우선 해결한다.
- provider/API rate limit이나 외부 provider 일시 장애는 fabricated row로 우회하지 말고 BLOCKED/DEGRADED 증거로 남긴다.

### 7.3 문서/백로그 truth reconciliation

1. FastAPI routes와 `docs/api/API-01_contracts.yaml` 비교
2. WebSocket docs와 frontend/backend event taxonomy 비교
3. DB migrations와 `docs/db/*` 비교
4. batch scripts/jobs와 `docs/batch/*` 비교
5. frontend screens와 `docs/frontend/*`, `docs/ui/*` 비교
6. 결과를 `BACKLOG.md`, `PLANS.md`, `MEMORIES.md`에 반영

### 7.4 실제 잔여 개발

잔여가 확인된 항목만 개발한다. 예상 우선순위:

1. 문서 stale 정리 및 completion matrix 갱신
2. live SMTP green-path evidence 또는 sandbox transport policy 명확화
3. RAG answer quality/citation/pending chunk 보강
4. WebSocket producer/UI realtime E2E 보강
5. role-based full user journey E2E 보강
6. npm advisory/build warning 검토 및 필요 시 패치
7. 최종 verification gate 재실행 및 결과 문서화

---

## 8. 변경 시 파일별 주의사항

### 8.1 DB / SQL

- `db/migrations/V*.sql`은 버전 충돌 없이 forward-only로 추가한다.
- 모든 SQL은 `/* sql_id: ... */`로 시작한다.
- DB 변경 시 함께 갱신:
  - `docs/db/DB-02_logical.md`
  - 필요 시 `docs/db/DB-04_batch_tables.md`
  - 필요 시 `docs/db/DB-05_migration_guide.md`

### 8.2 API

- FastAPI route 추가/변경 시 함께 갱신:
  - `docs/api/API-01_contracts.yaml`
  - 필요 시 `docs/api/API-02_websocket.md`
  - 필요 시 `docs/api/API-03_route_screen_backlog_matrix.md`
- route/doc drift gate를 반드시 통과시킨다.

### 8.3 AI / RAG

- AI 기능 변경 시 함께 갱신:
  - `docs/ai/*`
  - `prompts/*`
  - audit/generated metadata 테스트
- prompt에는 고객 개인정보 원문을 넣지 않는다.

### 8.4 Batch / Provider

- batch 변경 시 함께 갱신:
  - `docs/batch/*`
  - `docs/integration/*provider*`
  - runbook
- no-data/skip/fail은 실제 provider evidence로 보존하고, 성공으로 바꾸지 않는다.

### 8.5 Frontend

- 사용자-facing copy는 한국어를 기본으로 한다.
- `URGENT NBA`, raw synthetic ID, placeholder 고객명/포트폴리오명 재등장 방지 테스트를 유지한다.
- AI 생성 UI에는 생성 시각과 모델명을 표시한다.

---

## 9. OMX/Team 상태 관련 주의

- 과거 팀 ID `implement-omx-plans-r-82c653e8`는 shutdown 완료된 상태로 보고되었다.
- 이전 hook 메시지에는 이미 삭제된 mailbox를 읽으라는 문구가 남아 있을 수 있다.
- 현재 기준으로 팀 상태 디렉터리나 mailbox가 없으면, 이를 실패로 간주하지 말고 최신 Git/검증 산출물을 source of truth로 삼는다.
- `omx team list`는 이 환경에서 새 팀 invocation으로 오해될 수 있었던 이력이 있으므로, 필요하지 않으면 실행하지 않는다.
- 새 작업은 Claude Code 단독으로 수행해도 되며, OMX를 쓸 경우 반드시 현재 상태를 먼저 확인한다.

---

## 10. 최종 완료 정의

Claude Code가 후속 작업을 완료했다고 말하려면 최소한 다음을 충족해야 한다.

1. `git status --short --branch --untracked-files=all`에서 의도하지 않은 변경이 없다.
2. `./scripts/run_verification_gate.sh`가 `failures=0`으로 종료된다.
3. `scripts/verify_total_product_readiness.py` 결과가 `passed=true`다.
4. 공식 KRX top-200/30일 serviceable validator가 여전히 통과한다.
5. Playwright E2E가 권한별 주요 화면/동작을 커버하고 통과한다.
6. no mock / no fake provider row / raw SQL / SQL_ID / no-secret / no-PII 검사가 통과한다.
7. `BACKLOG.md`, `PLANS.md`, `MEMORIES.md`, 관련 `docs/`가 실제 구현 상태와 일치한다.
8. 남은 예외가 있다면 사용자 승인된 명시적 cutline으로 문서화한다.

---

## 11. 빠른 체크리스트

```text
[ ] AGENTS.md와 필수 문서 읽음
[ ] git status 확인
[ ] runtime status 확인
[ ] 최신 verification gate 재현
[ ] total-product readiness 재현
[ ] BACKLOG partial/open 항목별 실제 구현 증거 대조
[ ] route/API doc sync 확인
[ ] DB migration/docs sync 확인
[ ] batch/provider docs sync 확인
[ ] frontend/user journey/role E2E 확인
[ ] no secrets/PII/log leakage 확인
[ ] 최종 산출물과 루트 tracking docs 갱신
```
