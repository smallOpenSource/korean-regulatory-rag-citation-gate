# WMAH UX G-Eval 한국어 평가 루브릭 (Stage 2 Lane 4)

본 루브릭은 WMAH 화면 23종 × 4 role (PB, WM, ADMIN, AUDIT_VIEWER) 스냅샷에 대해
한국어 PB persona LLM-judge가 6 카테고리로 평가하기 위한 SoT 입니다.

- 평가자 persona 강제: **"나는 한국 시중은행 자산관리 본부의 PB(Private Banker)이다. 화면을 처음 보는 사용자의 시선으로 평가한다."**
- 모든 영어 출력 금지. JSON key 외 모든 rationale 한국어로만 작성.
- self-consistency N=3 sampling 의무 (동일 입력 3회 평가 후 majority vote 또는 평균 점수).
- LLM-as-evaluator limitation ([[llm-as-evaluator-limitation]]) 준수: 사용자 panel substitute 불가. 결과에 `limitation_notice: "framework_side termination, 사용자 panel ground truth absent"` 필수 기록.

---

## 카테고리 a — 영어 키 / camelCase / snake_case identifier 사용자 노출

### definition
화면 본문(레이블, 값, 알림 메시지)에 raw 영어 식별자가 한국어 설명 없이 노출됨.
예: `source_as_of`, `created_at`, `actor_id`, `NBA_GENERATED`, `risk_grade_code`,
`T243`, raw UUID(`3f5a-...`), camelCase JS key(`statusCode`), URL path(`/api/v1/...`)가
화면 본문에 그대로 보이는 경우.

### exclude_examples (디자인 의도 영역 — 위반 아님)
- AuditViewerPage 컬럼/필터 영역: 감사관 영문 field name 요구사항 → `업무 코드 (action_code)`, `수행자 ID (actor_id)`, `리소스 (resource_type)` 같이 한국어 label + parenthetical raw DB field name은 design intent
- AIModelCardsPage / AIAdminDashboardPage 의 `<code>consultation_briefing</code> 상담 브리핑` 같이 영문 agentId + 한국어 agentLabel parenthetical 은 design intent
- ADMIN role 전용 페이지(/batch, /quarantine, /audit, /ai-admin-dashboard)에서 ADMIN 화면 boundary 안의 DevReference 컴포넌트가 노출한 `ADR-005`, `REG-04` 같은 internal ID
- `/forbidden`, `/login` 의 영문 status code (`401`, `403`) - 시스템 메시지 컨벤션

### positive_examples (실제 위반 — FAIL)
- PB 대시보드 본문에 `기준시각(source_as_of) 2026-05-16` 노출
- 상담 카드에 `status_code: SAVED` 라는 raw enum 그대로 노출
- 고객 360 본문에 `created_at: 2026-05-...` 표시
- NBA 페이지에 `NBA_GENERATED` 라는 raw enum 본문 노출
- AftercarePage 본문에 raw UUID `a3b1-...` 노출

### severity_scale (1=경미, 5=치명)
- 1: parenthetical 보조 표기로 동반된 영문 (예: `잔액 (balance)`)
- 2: tooltip / 미세 영역 raw key
- 3: 카드 본문 raw enum 하나
- 4: 대시보드 1차 페이지에 raw timestamp / UUID 노출
- 5: 다수 페이지에 걸쳐 raw key가 한국어 label 없이 노출 (시스템 전반 결함)

---

## 카테고리 b — 마이크로초 또는 ISO 원본 timestamp 노출

### definition
사용자 본문에 ISO-8601 원본 timestamp가 가공 없이 노출됨.
예: `2026-05-16T14:52:16.847752+00:00`, `2026-05-16 14:52:16.847752+00`,
`+00` 타임존 표기, epoch 정수(`1715865136`), 마이크로초 정밀도.

### exclude_examples (디자인 의도 영역)
- AuditViewerPage 의 감사 timestamp 컬럼: 감사 추적 정확성 요구 → ISO timestamp design intent (단, parenthetical 한국어 label 동반 권장)
- ADMIN role 의 /batch, /quarantine 페이지 디버깅 영역
- 시스템 로그 raw 영역 (`<pre>` 또는 `<code>` 컴포넌트 안)

### positive_examples (실제 위반)
- PB DashboardPage `기준시각(source_as_of) 2026-05-16 14:52:16.847752+00`
- HouseViewsPage 본문 카드에 `created_at 2026-05-16T14:52:16.847752`
- 상담 페이지에 `2026-05-16 14:52:16.847752+00` 마이크로초 timestamp
- 어떤 페이지든 본문 가시 영역에 `+00`, `+09:00` 타임존 raw

### severity_scale
- 1: ADMIN 전용 페이지에 마이크로초 (허용 영역이지만 PB로 role 전환 시 안 보여야 함)
- 2: tooltip 영역
- 3: 카드 본문에 마이크로초 한 곳
- 4: 1차 대시보드에 마이크로초 노출
- 5: 다수 페이지 본문에 마이크로초 + 타임존 raw

---

## 카테고리 c — 폴백 placeholder 노출

### definition
시연 데이터 부재 / loading state / 폴백 상태가 본문에 그대로 노출됨.
금칙 문자열: `"0%"`, `"—"`, `"…"`, `"대기 중"`, `"불러오는 중"`, `"미확인"`, `"정보 없음"`,
`"placeholder"`, `"N/A"`, `"undefined"`, `"null"`.

### exclude_examples (디자인 의도 영역)
- "대기 중인 X가 없습니다", "이번 분기 대기 중인 사후관리가 없습니다" 같은 **자연 empty-state 문구** (placeholder fallback 이 아님; 카운트가 0임을 정상적으로 안내)
- 로그인 페이지 / 권한 거부 페이지의 시스템 메시지 (디자인 의도 영역)
- 진행 중인 상담의 `진행률 0%` 가 실제 데이터로 0%인 경우 (단, 화면 전반에 0%만 있으면 fixture 미시드 신호 → FAIL)

### positive_examples (실제 위반)
- DashboardPage 카드 5개 중 3개가 `—` 또는 `0%`
- 고객 360 페이지에 `미확인` 또는 `정보 없음` 다발
- HouseViewsPage 콘텐츠가 `불러오는 중...` 으로 시연 시작 후 5초 이상 유지
- 본문 어디에든 raw `null` 또는 `undefined` 노출
- consultation 페이지에 `대기 중` 만 보임 (실제 카운트 없음)

### severity_scale
- 1: 1개 컴포넌트 의 1개 셀에 `—`
- 2: 카드 하나가 전부 fallback
- 3: 1차 페이지 컨텐츠 영역의 절반 이상 fallback
- 4: 다수 페이지에 fallback 다발
- 5: 시스템 전반이 placeholder만 노출 (시연 데이터 미시드)

---

## 카테고리 d — 한국어 label + (raw 영문) 패턴

### definition
한국어 사용자 레이블 뒤에 raw 영문 식별자가 parenthetical 로 부착되어 PB/WM 본문 가독성을 해침.
예: `잔액 (balance_krw)`, `상태 (status_code)`, `유형 (resource_type)`.

### exclude_examples (AuditViewerPage 디자인 의도 영역 EXCLUDE 명시)
- **AuditViewerPage** 의 모든 컬럼/필터/카드: 감사관 본업이 영문 DB field 추적이므로 design intent
  - `업무 코드 (action_code)`, `수행자 ID (actor_id)`, `감사 해시 (audit_hash)`, `리소스 (resource_type)` → 정상
- AuditPage (감사 로그 raw 영역) 일부 컬럼
- AIModelCards / AIAdminDashboard 의 `<code>consultation_briefing</code> 상담 브리핑` (영문 agentId + 한국어 agentLabel parenthetical) → design intent
- ADMIN role boundary 안의 DevReference 컴포넌트

### positive_examples (실제 위반 — PB/WM 본문 영역)
- PB DashboardPage 카드에 `총자산 (total_assets_krw)` parenthetical
- ConsultationPage 본문에 `상태 (status_code)` parenthetical
- Customer360Page 본문에 `위험등급 (risk_grade_code)`
- NbaPage 본문에 `행동 코드 (action_code)`
- HouseViewsPage 본문에 `발효일 (effective_at)`

### severity_scale
- 1: 1개 카드 1개 필드
- 2: 1개 페이지 1개 섹션 전반
- 3: 1차 페이지 다수 필드
- 4: PB/WM 다수 페이지에서 반복
- 5: 시스템 전반 한국어 label + (raw 영문) 패턴

---

## 카테고리 e — Role-gating 누수

### definition
ACCESS_RULES SoT (`apps/web/src/lib/access.ts`) 에 정의된 role 권한 경계가 화면에서 누수됨.
- PB role 으로 ADMIN-only / AUDIT_VIEWER-only UI 또는 버튼이 보임
- AUDIT_VIEWER role 로 PB-only 상담 수정 버튼이 보임
- ADMIN-only 버튼이 BRANCH_MANAGER 또는 PB 에 보임
- ACCESS_RULES 위반 route 에 직접 navigate 했을 때 ForbiddenPage 가 아닌 콘텐츠가 보임

### exclude_examples
- 모든 role 이 동일하게 허용된 페이지 (`dashboard`, `houseViews`, `aiModelCards`, `aiPolicy`, `koreanAIAct`, `disputeCase`) 에서 동일 UI 가 보이는 경우 → 정상
- 네비게이션 메뉴에서 비활성화된 항목이 회색 처리로 보이는 경우 (단, 클릭 가능하면 위반)

### positive_examples (실제 위반)
- PB 로 `/batch` 또는 `/quarantine` 접근 시 ForbiddenPage 가 아닌 콘텐츠 노출
- AUDIT_VIEWER 로 `/consultation` 또는 `/nba` 접근 시 200 응답
- PB 화면에 `정책 활성화` 같은 ADMIN-only 버튼 가시
- AUDIT_VIEWER 화면에 `상담 저장` 같은 PB-only 액션 버튼 가시
- `houseViewActivation` (ADMIN-only) UI 가 PB 의 HouseViewDetailPage 에 활성화

### severity_scale
- 1: 비활성화된 버튼이 회색으로 보이지만 클릭 시 ForbiddenPage 로 리다이렉트
- 2: 메뉴 항목이 보임 (클릭 가능)
- 3: ADMIN-only 페이지가 PB 에 콘텐츠로 노출 (1개 페이지)
- 4: 다수 ADMIN-only 페이지가 PB 에 노출
- 5: 시스템 전반 role-gating 누수 (보안 사고급)

---

## 카테고리 f — Untranslated error / status code

### definition
HTTP / 검증 error code 가 한국어 메시지 없이 노출됨.
예: `VALIDATION_ERROR`, `422`, `NOT_FOUND`, `INTERNAL_SERVER_ERROR`, `UNAUTHORIZED`,
`Bad Request`, `Failing row contains`.

### exclude_examples
- ForbiddenPage / LoginPage 의 시스템 메시지 (디자인 의도 영역)
- ADMIN role 의 batch / quarantine / audit 페이지 raw error 영역 (디버깅 의도)
- `<pre>` / `<code>` block 안의 stack trace (ADMIN 전용)

### positive_examples (실제 위반)
- 사용자 본문 alert / toast 에 `422 Unprocessable Entity` 그대로 노출
- ConsultationPage 저장 실패 시 `VALIDATION_ERROR` 만 노출 (한국어 설명 없음)
- DashboardPage 에 `INTERNAL_SERVER_ERROR` 본문 노출
- PB 본문 어디든 `Failing row contains (...)` PG raw error

### severity_scale
- 1: 한국어 메시지 + parenthetical error code
- 2: 영문 코드 단독 노출 1회
- 3: 영문 stack trace 본문 노출
- 4: 다수 페이지에서 영문 error code 만 노출
- 5: PB/WM 본문에 PG raw `Failing row` 등 시스템 누수

---

## Prompt Template (judge-runner 가 inject)

```
당신은 한국 시중은행 자산관리 본부의 PB(Private Banker)입니다.
WMAH 시스템 화면을 처음 보는 사용자의 시선으로 평가하세요.

[화면 context]
- route: {route}
- role (ACCESS_RULES SoT): {role}
- 이 role 의 의도된 사용자: {role_persona}

[입력 — accessibility tree 또는 screenshot]
{snapshot}

[평가 — 6 카테고리]
a) 영어 키 / camelCase / snake_case identifier 사용자 노출 (audit-viewer 디자인 의도 EXCLUDE)
b) 마이크로초 또는 ISO 원본 timestamp 노출
c) "0%" / "—" / "대기 중" / "미확인" / "정보 없음" 폴백 placeholder
d) 한국어 label + (raw 영문) 패턴 (AuditViewerPage 디자인 의도 EXCLUDE)
e) Role-gating 누수 (PB 가 AUDIT_VIEWER-only UI 발견, ADMIN-only 버튼이 PB 에 보임)
f) Untranslated error / status code (VALIDATION_ERROR, 422 등)

[EXCLUDE — FAIL 판정 금지]
- 가독성 / 색상 / 글꼴 / 대비 / 터치 영역 / 스크롤 / 정보 위계 / 컬럼 폭 (v8 PRD scope 외부)
- "동일 카드 반복 list" / "정보 밀도 높음" → list-based UI 자체는 spec OK
- 자연 empty-state 문구 ("대기 중인 X가 없습니다") → placeholder 아님
- 디자인 의도 영역 (각 카테고리 exclude_examples 참조)

[출력 — JSON 만]
{{
  "judge_persona": "PB 한국어",
  "scores": {{
    "a_english_identifier":   {{"score": 1~5 (1=정상, 5=치명), "rationale": "한국어 근거 (concrete instance 인용)"}},
    "b_iso_microsecond":      {{"score": 1~5, "rationale": "..."}},
    "c_fallback_placeholder": {{"score": 1~5, "rationale": "..."}},
    "d_korean_paren_english": {{"score": 1~5, "rationale": "..."}},
    "e_role_gating_leak":     {{"score": 1~5, "rationale": "..."}},
    "f_untranslated_code":    {{"score": 1~5, "rationale": "..."}}
  }},
  "overall_pass": true|false,
  "confidence": 0.0~1.0,
  "limitation_notice": "framework_side termination, 사용자 panel ground truth absent"
}}

판정 기준:
- 카테고리별 score=1: 위반 없음 (정상)
- score=2~3: 경미~중간 위반
- score=4~5: 심각~치명 위반
- overall_pass=true 조건: 모든 카테고리 score ≤ 2 AND e/f 카테고리 score=1
- 애매하면 score 낮게 (false positive 차단 우선)
```

### self-consistency 지시
동일 입력 (`role`, `route`, `snapshot`)에 대해 N=3 sampling 실행 (temperature ≈ 0.4).
3개 verdict 가 모두 동일 → confidence 1.0. 2/3 동일 → confidence 0.67. 1/1/1 분기 → confidence 0.33 +
flag `unstable_judge=true`.
최종 score = N=3 의 median (per category). overall_pass = N=3 majority.

### LLM-as-evaluator limitation 주석
- 본 루브릭의 판정은 `limitation_notice` 가 항상 부착됨.
- 사용자 panel ground truth 와 결과가 다를 수 있음을 grade 출력에 명시.
- 80%+ FAIL rate 가 측정되면 BFS extraction artifact 또는 broader interpretation 의심.
- deterministic L1/L3/L4 detector 결과와 cross-validate 의무.
