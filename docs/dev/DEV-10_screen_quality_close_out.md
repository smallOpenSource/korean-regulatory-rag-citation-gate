# DEV-10 — Screen Quality Close-out (DI-2 verification follow-up)

**Status:** delivered (2026-05-17)
**Plan source:** [.omc/plans/ralplan-wmah-screen-quality-fixes.md](../../.omc/plans/ralplan-wmah-screen-quality-fixes.md)
**Wave:** 5 (post-Wave-4 polish)

---

## 1. Background

Verification of the demo-ready PoC at commit `ca6bd7e` discovered ten screen-quality issues across the PB-visible surface. They were captured by Playwright `qa-audit.spec.ts` (16 routes) and recorded in `apps/web/qa-audit-out/*.txt`. This close-out summarises the in-place targeted fix (Option A in the ralplan) that brought the rendered text to operations-handover quality.

## 2. Issues resolved (10/10)

| # | Severity | Location | Before | After |
|---|---|---|---|---|
| 1 | HIGH | Dashboard 시장 상태 메시지 | `"Domestic market evidence is ready for staff display."` | `"국내 시장 기준 데이터가 화면 표시 준비를 마쳤습니다."` (한국어, source-of-truth는 `services/readiness/serviceable.py`) |
| 2 | HIGH | Dashboard 차단 사유 | `"No DOMESTIC_TOP200_MARKET_CAP universe snapshot is persisted. / Selected universe count 0 is below required 200. / No official KRX expected member-day denominator is persisted."` | `"공식 KRX 상위 200 종목 기준 데이터가 아직 준비되지 않았습니다. / 선택된 종목 0개가 요구 기준 200개에 못 미칩니다. / 공식 KRX 기준 종목·거래일 산정 기준이 아직 준비되지 않았습니다."` |
| 3 | HIGH | `/aftercare`, `/email-drafts` Dashboard fallback | 두 라우트가 `*` fallback 으로 Dashboard 컴포넌트를 렌더 | `AftercarePage` (분기 사후관리 큐) / `EmailDraftsPage` (이메일 초안 승인 절차) 신규 구현. 백엔드 `GET /email-drafts` 추가, `SQL_ID: list_scoped_email_drafts` |
| 4 | HIGH | 하우스뷰 목록 (PB) | `GOLDEN_TEST`, `RALPH`, `RALPH-QA`, `Synthetic boundary test.` 픽스처 노출 | `LIST_HOUSE_VIEWS_SQL` 에 fixture exclude 절. ADMIN/AUDIT_VIEWER 는 `?include_test_fixtures=true` 로 옵트인 가능 |
| 5 | MEDIUM | RAG 질의응답 | `W2-T1/W3-T6 dual-LLM`, `ADR-005 Fail-Closed` 등 내부 식별자 노출 | `<DevReference>` 컴포넌트로 wrap. PB 화면에는 한국어 카피, ADMIN/AUDIT_VIEWER 만 식별자 표시 |
| 6 | MEDIUM | AI 사용 정책 / 인공지능기본법 / AI 모델 카드 | `AI-04 §Wave 3 Hardening · W3-T6`, `REG-04 §3` 식별자 본문에 노출 | 본문 한국어화. 식별자는 페이지 footer의 `<DevReference>` 박스에만 노출 |
| 7 | MEDIUM | 고객 목록 / 대시보드 / 고객 360 | ISO microsecond `2026-04-20T13:52:53.650391Z` + `(source_as_of)` 변수명 노출 | `formatBankerTimestamp(value)` 헬퍼로 `"2026-04-20 13:52"` (Asia/Seoul) 변환. `(source_as_of)` 라벨 제거 |
| 8 | MEDIUM | 대시보드 metric 숫자·단위 | `긴급1`, `7일 이내 만기0`, `오늘 상담42` (붙어 표시) | `formatBankerNumber(value, "건")` 헬퍼로 `"긴급 1건"`, `"7일 이내 만기 0건"`, `"오늘 상담 45건"` |
| 9 | MEDIUM | 대시보드 / 하우스뷰 / 고객 360 빈 상태 카피 | `"API 응답을 기다리는 중입니다."`, `"AI 생성 · 생성 대기 · 모델 대기"` 개발자 톤 | `"정보를 불러오는 중입니다."`, `"최신 생성 정보 준비 중"` |
| 10 | LOW | 권리 고지 / 상담 워크스페이스 | 버튼 `"취소 (나중에 확인)"`; `/consultations/SYN-CUST-001` 진입 시 `"상단 고객 목록에서 고객을 선택하세요"` 노출 | 버튼 `"다음에 확인"`; `SYN-CUST-` 경로 패턴을 customer_id 로 인식하도록 ConsultationPage 라우트 해석 강화 |

## 3. New / changed components

### Backend
- `apps/api/harness/repositories/house_views.py` — `LIST_HOUSE_VIEWS_SQL` 에 fixture exclude 절 + `include_test_fixtures` 매개변수
- `apps/api/harness/api/routers/house_views.py` — `include_test_fixtures` 쿼리 매개변수 (ADMIN/AUDIT_VIEWER 만 허용)
- `apps/api/harness/repositories/email.py` — `LIST_SCOPED_EMAIL_DRAFTS_SQL` (`sql_id: list_scoped_email_drafts`) + `list_email_drafts_for_actor` 함수, PB 화면용 fixture/내부 식별자 본문 exclude 절
- `apps/api/harness/api/routers/email.py` — `GET /email-drafts` 신규 (PB/WM 스코프)
- `apps/api/harness/services/readiness/serviceable.py` — `blocking_reasons` 와 메시지 한국어 평어체로 변경

### Frontend
- `apps/web/src/lib/format.ts` (신규) — `formatBankerTimestamp`, `formatBankerNumber`
- `apps/web/src/components/DevReference.tsx` (신규) — RBAC 가드 식별자 표시 컴포넌트
- `apps/web/src/pages/AftercarePage.tsx` (신규) — 분기 사후관리 큐
- `apps/web/src/pages/EmailDraftsPage.tsx` (신규) — 이메일 초안 승인 절차
- `apps/web/src/App.tsx` — `/aftercare`, `/email-drafts` 라우트 추가
- `apps/web/src/lib/types.ts`, `apps/web/src/lib/access.ts` — `aftercare`, `emailDrafts` route key + RBAC 등록
- `apps/web/src/components/Layout.tsx` — 페이지 헤더 합성 데이터 워터마크 + `사후관리 (분기)`, `이메일 초안` 메뉴
- `apps/web/src/pages/DashboardPage.tsx` — `formatBanker*` 적용, 영어 변수명 제거, fallback 카피 한국어화
- `apps/web/src/pages/CustomersPage.tsx`, `Customer360Page.tsx` — timestamp 변환 + `(source_as_of)` 라벨 제거
- `apps/web/src/pages/HouseViewsPage.tsx`, `HouseViewDetailPage.tsx` — fallback 카피 + 워터마크
- `apps/web/src/pages/RagPage.tsx`, `AIPolicyPage.tsx`, `AIModelCardsPage.tsx`, `KoreanAIBasicActPage.tsx` — `<DevReference>` 적용 + 한국어 카피 통일
- `apps/web/src/pages/RightsNoticePage.tsx` — 버튼 `다음에 확인`
- `apps/web/src/pages/ConsultationPage.tsx` — `SYN-CUST-` 경로 패턴을 customer_id 로 해석
- `apps/web/src/lib/labels.ts` — `SUPERSEDED: "이전 버전"`

### Tests
- `apps/web/e2e/qa-audit-quality.spec.ts` (신규) — 16 페이지 × 4 banned regex + 합성 워터마크 + Rights notice 버튼 + Consultation 진입 검증
- `apps/web/src/lib/copy_allowlist.json` — 영어 banned 단어, 내부 식별자 regex, 테스트 픽스처 regex, ISO microsecond regex, 필수 합성 워터마크 등록
- `tests/test_screen_quality_filters.py` (신규) — house_views/email_drafts SQL 필터 invariant + 헬퍼 존재 검사

## 4. Acceptance criteria (12/12)

| # | Criterion | Verification command | Status |
|---|---|---|---|
| 1 | PB 페이지 캡쳐에 영어 banned words 0건 | `grep -lE '\b(evidence\|persisted\|snapshot\|universe\|denominator\|staff display)\b' apps/web/qa-audit-out/*.txt` → empty | ✓ |
| 2 | PB 페이지 캡쳐에 내부 식별자 0건 | `grep -lE 'ADR-[0-9]\|W[0-9]-T[0-9]\|REG-0[0-9]' apps/web/qa-audit-out/*.txt` → empty | ✓ |
| 3 | house_views.txt 에 `GOLDEN_TEST/RALPH/Synthetic boundary` 0건 | `grep -cE 'GOLDEN_TEST\|RALPH\|Synthetic boundary' apps/web/qa-audit-out/house_views.txt` → `0` | ✓ |
| 4 | aftercare.txt 와 dashboard.txt 내용 다름 | `diff -q apps/web/qa-audit-out/aftercare.txt apps/web/qa-audit-out/dashboard.txt` → differ | ✓ |
| 5 | email_drafts.txt 와 dashboard.txt 내용 다름 | `diff -q apps/web/qa-audit-out/email_drafts.txt apps/web/qa-audit-out/dashboard.txt` → differ | ✓ |
| 6 | customers.txt 에 ISO microsecond timestamp 0건 | `grep -cE '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+' apps/web/qa-audit-out/customers.txt` → `0` | ✓ |
| 7 | dashboard.txt 에 `긴급 \d+건`, `오늘 상담 \d+건` 형식 | `grep -E '(긴급 [0-9]+건\|오늘 상담 [0-9]+건)' apps/web/qa-audit-out/dashboard.txt` → match | ✓ |
| 8 | Rights Notice 버튼 텍스트 `다음에 확인` | `grep -c '다음에 확인' apps/web/qa-audit-out/rights_notice.txt` → ≥ 1 | ✓ |
| 9 | `consultations_SYN_CUST_001.txt` 에 `상단 고객 목록에서 고객을 선택하세요` 부재 | `grep -c '상단 고객 목록' apps/web/qa-audit-out/consultations_SYN_CUST_001.txt` → `0` | ✓ |
| 10 | DEV-10 close-out 문서 작성 | `ls docs/dev/DEV-10_screen_quality_close_out.md` | ✓ (본 문서) |
| 11 | pytest 455+ passed 유지 + Playwright 58+ passed 유지 | 본 close-out 5절 참조 | ✓ |
| 12 | qa-audit-quality.spec.ts 16/16 pass | 본 close-out 5절 참조 | ✓ |

## 5. Regression evidence

- `pytest tests/ --ignore=tests/test_azure_model.py -q` — full suite 결과는 본 wave 후 `459 passed / 37 skipped` (baseline 454 → +5: `test_screen_quality_filters.py` 5건 추가)
- `apps/web/e2e/qa-audit.spec.ts` — 16/16 pass (PB role 캡쳐, banned regex 0건)
- `apps/web/e2e/qa-audit-quality.spec.ts` — PB role × 13 페이지 × 4 banned regex + 합성 워터마크 + Rights notice 버튼 + Consultation 진입 = 16 tests, all pass
- 기존 Playwright suite (`role-matrix-wave4`, `adversarial`, `ws-realtime` 등) — 58+ pass 유지

## 6. Architectural notes

- **Source-of-truth 분리**: Dashboard readiness 메시지는 backend (`services/readiness/serviceable.py`) 에서 한국어로 직접 생성합니다. Frontend 표시 레이어에서 i18n key lookup 하지 않아 향후 i18n centralization 시 backend 메시지는 재작업 없이 그대로 사용 가능합니다.
- **테스트 픽스처 격리**: 합성 시드 데이터에는 GOLDEN_TEST / RALPH / golden regression 패턴이 의도적으로 포함되어 있어 회귀 테스트를 보조합니다. PB 가시 SQL 필터 한 줄로 운영 화면에서 분리하고, ADMIN/AUDIT_VIEWER 는 명시적 `?include_test_fixtures=true` 옵트인으로 접근합니다.
- **합성 데이터 워터마크 일관성**: `Layout.tsx` 헤더 레벨에 워터마크 배너를 두어 모든 PB-가시 페이지에 자동 표시됩니다. 페이지 본문에 이미 있던 합성 데이터 안내 (`SyntheticCustomerNotice`) 와 중복되지 않도록 톤을 차별화했습니다.

## 7. Follow-ups (out of scope for this wave)

- 운영 핸드오프 후 frontend `lib/i18n.ts` 중심의 i18n centralization (Option B trade study)
- a11y 심층 audit (axe-core full sweep)
- copy 변경 리뷰 프로세스 (`docs/frontend/FE-02_copy_review.md`)
- Layout 워터마크의 ADMIN 토글 (현재는 always-on)
