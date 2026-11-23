# ADR-013 — OpenAPI Enum Policy: Backend 영문 유지 + Frontend Single SoT 한국어 Label

**Date**: 2026-05-24
**Status**: Accepted
**Deciders**: project maintainer + svc-viability-v2 team
**Cycle context**: service-viability v2 T3-3 F15 enum type drift 6 surface audit (commit 2f6d19d) → T4-1 policy 박제
**Note**: ADR-012 slot 사용 중 (`ADR-012_consultation_audit_row_density.md`); 본 ADR은 -013 slot 사용.

---

## Decision

**backend OpenAPI enum value는 영문 SCREAMING_SNAKE_CASE를 유지하고,
UI 한국어 label은 `apps/web/src/lib/labels.ts` `STATUS_LABELS` single SoT를 통해서만 제공한다.**

모든 frontend component는 enum 값을 직접 DOM에 노출하지 않고 `statusLabel(code)` 함수를 호출하여
한국어 label을 얻는다.

---

## Context

### OpenAPI 30+ enum 영문 현황

`apps/api/harness/` 전반에 걸쳐 30개 이상의 OpenAPI enum 필드가 영문 SCREAMING_SNAKE_CASE로 정의되어 있다.
예시: `status_code` (OPEN / IN_PROGRESS / CLOSED / COMPLETED / CANCELLED), `gate_status`
(PASSED / ACKNOWLEDGED / BLOCKED), `decision` (MARKETING_REVIEW_PASS / MARKETING_REVIEW_BLOCK),
`freshness_status_code` (FRESH / STALE / MISSING), `role_code` (PB / WM / ADMIN / AUDIT_VIEWER).

### T3-3 F15 — 6 surface enum type drift (commit 2f6d19d)

service-viability v2 사전 audit(T3-3)에서 frontend type alias 6개 surface에서 enum drift가 발견됨:

| Surface | Component / Page | Drift 유형 | 처리 |
|---|---|---|---|
| `gate_status` | ConsultationGates | ACKNOWLEDGED / PASSED 미정의 | CLOSE — STATUS_LABELS 추가 (2f6d19d) |
| `status` (dispute) | DisputeStatus | EXPIRED / RESPONDED 미정의 | CLOSE — STATUS_LABELS 추가 (2f6d19d) |
| `status_code` (email drafts) | EmailDraftsPage | 정합 확인 | 정합 |
| `status_code` (nba) | NbaPage | 정합 확인 | 정합 |
| `status` (aftercare) | AftercareStatus | 정합 확인 | 정합 |
| ARCHIVED / ACTIVATED / ACTIVE | HouseView | 정합 확인 | 정합 |

T3-3 조치 전에는 `statusLabel("ACKNOWLEDGED")` 호출 시
`STATUS_LABELS` miss → `unmappedLabel("상태", "ACKNOWLEDGED")` → `"상태 미확정 (코드: ACKNOWLEDGED)"` 폴백이
DOM에 노출되었다 (PB perspective Axis 4 raw enum 노출 16 hit 원인).

### 근본 문제: enum 추가 시 STATUS_LABELS 동기화 미흡

backend enum 확장(migration V*.sql CHECK constraint 추가) 시 `STATUS_LABELS` 동기 업데이트가 명문화된
프로세스 없이 암묵적 관례에만 의존하여, drift가 감지되지 않고 UI에 영문 enum이 노출되는 회귀가 반복됨.

### ADR-010 패턴 연장

ADR-010 §4 (service-viability baseline — frontend label single SoT 원칙)에서 `STATUS_LABELS`
단일 진실 공급원(SoT) 원칙이 처음 명시되었으나 enum 추가 절차는 기술되지 않았다.
본 ADR은 이를 확장하여 신규 enum 추가 프로토콜을 명문화한다.

---

## Drivers (top 3)

| # | Driver | 근거 |
|---|---|---|
| D1 | **Machine-readable contract** | backend API를 소비하는 타 client(향후 모바일 / B2B API 소비자)가 영문 enum을 신뢰할 수 있어야 한다. 영문을 한국어로 교체하면 OpenAPI contract 파괴. |
| D2 | **i18n future-proof** | 향후 다국어(영어, 일본어 등) 지원 시 `STATUS_LABELS`에 language map만 추가하면 되어 component 변경 0. |
| D3 | **Single SoT drift 방지** | T3-3 6 surface 동시 drift 사건의 재발 방지. `STATUS_LABELS` 1개 파일이 coverage map이 되고 coverage test가 1차 회귀 catch. |

---

## Alternatives (거부)

### (a) backend enum 한국어로 교체
- **거부 이유**: OpenAPI machine-readable contract 파괴. REST API를 소비하는 비-UI client(스크립트, BI 도구, 외부 연동)가 enum 비교 로직을 전부 재작성해야 함. DB CHECK constraint (`V*.sql`) 마이그레이션도 필요하여 데이터 무결성 위험 수반.

### (b) frontend type alias를 한국어 string union으로 직접 교체
- **거부 이유**: component 다수 수정 cost(T3-3 6 surface 전체) + TypeScript strict 모드에서 enum ↔ 한국어 string union 타입 불일치로 tsc 오류 발생. `statusLabel()` 단일 호출 패턴 대비 유지보수 열위.

---

## Decision Detail

### 1. Backend enum value 규칙

모든 backend API response의 enum field는 영문 SCREAMING_SNAKE_CASE를 사용한다.

```
✓  OPEN, IN_PROGRESS, CLOSED, ACKNOWLEDGED, PASSED, BLOCKED
✓  MARKETING_REVIEW_PASS, MARKETING_REVIEW_BLOCK
✓  FRESH, STALE, MISSING
✓  DRAFT, PENDING_APPROVAL, PENDING_REVIEW, APPROVED, REJECTED
```

### 2. Frontend 한국어 label SoT

`apps/web/src/lib/labels.ts`의 `STATUS_LABELS` 객체가 유일한 enum→한국어 label 매핑 SoT이다.

**현재 STATUS_LABELS coverage (2026-05-24, HEAD b981ad3 기준)**:

| enum code | 한국어 label | 추가 경위 |
|---|---|---|
| ACKNOWLEDGED | "확인" | T3-3 F15 (2f6d19d) |
| ACTIVE | "활성" | 초기 |
| ACTIVATED | "활성" | 초기 |
| APPROVED | "승인" | 초기 |
| ARCHIVED | "보관" | 초기 |
| BLOCKED | "차단" | 초기 |
| CANCELLED | "취소" | 초기 |
| CLOSED | "종결" | 초기 |
| COMPLETED | "완료" | 초기 |
| DEGRADED | "주의" | 초기 |
| DISMISSED | "해제" | 초기 |
| DONE | "완료" | 초기 |
| DRAFT | "초안" | 초기 |
| EXPIRED | "기한 만료" | T3-3 F15 (2f6d19d) |
| FAILED | "실패" | 초기 |
| GENERATED | "생성됨" | 초기 |
| IN_PROGRESS | "진행 중" | 초기 |
| LOADING | "불러오는 중" | 초기 |
| OPEN | "진행 필요" | 초기 |
| PASSED | "통과" | T3-3 F15 (2f6d19d) |
| PENDING | "대기" | 초기 |
| PENDING_APPROVAL | "승인 대기" | 초기 |
| PENDING_REVIEW | "검토 대기" | 초기 |
| READY | "준비 완료" | 초기 |
| RESOLVED | "해결" | 초기 |
| RESPONDED | "답변 완료" | T3-3 F15 (2f6d19d) |
| REVIEWED | "검토" | 초기 |
| SAVED | "저장" | 초기 |
| SENT | "발송 완료" | 초기 |
| SIMULATED_EXECUTED | "모의 실행 완료" | 초기 |
| SKIPPED | "건너뜀" | 초기 |
| SNOOZED | "보류" | 초기 |
| SUCCEEDED | "성공" | 초기 |
| SUPERSEDED | "이전 버전" | 초기 |
| SYNTHETIC_ONLY | "합성 데이터" | 초기 |
| FRESH | "신선" | 초기 |
| STALE | "오래됨" | 초기 |
| MISSING | "상태 미확정" | 초기 |
| ACCEPTED | "검증 통과" | 초기 |
| UNVERIFIED | "검증 전" | 초기 |

### 3. 신규 enum 추가 프로토콜 (3-step)

backend migration(`V*.sql`) 또는 router에 신규 enum value가 추가될 때마다 다음 순서를 준수한다:

```
Step 1. backend V*.sql CHECK constraint에 신규 enum value 추가 + migration 적용
Step 2. apps/web/src/lib/labels.ts STATUS_LABELS에 동기 추가
         예) MARKETING_REVIEW_PASS: "마케팅 심사 통과"
Step 3. apps/web/src/tests/status-labels-coverage.test.ts에 커버리지 테스트 추가
         → statusLabel("MARKETING_REVIEW_PASS") === "마케팅 심사 통과" assertion
```

Step 2–3를 같은 commit에 포함하여, coverage test가 CI에서 drift를 즉시 catch할 수 있도록 한다.

### 4. component 작성 규칙

모든 React component에서 enum 값을 DOM에 직접 노출하지 않는다.

```tsx
// ✓ correct
<StatusBadge label={statusLabel(item.status_code)} />

// ✗ incorrect — raw enum DOM 노출
<span>{item.status_code}</span>
```

`statusLabel()` 함수는 `STATUS_LABELS[normalized]` miss 시
`unmappedLabel("상태", normalized)` → `"상태 미확정 (코드: XXXX)"` 폴백을 반환한다.
이 폴백이 UI에 노출되면 coverage 미비로 간주하여 즉시 STATUS_LABELS에 추가한다.

---

## Consequences

### 긍정
- backend OpenAPI contract 안정성 유지 (consumer 하위 호환)
- UI한국어 label 회귀를 coverage test가 1차 catch → T3-3 6 surface 재발 방지
- i18n 확장 시 labels.ts 1개 파일만 수정

### 부정 / 제약
- 신규 enum 추가 시 Step 2–3를 동일 commit에 포함해야 하는 절차 overhead
- STATUS_LABELS 파일이 도메인 범위를 초과해 비대해질 수 있음 (향후 namespace 분리 후보)

### 검증됨 (2026-05-24)
- T3-3 ACKNOWLEDGED / EXPIRED / PASSED / RESPONDED 추가 후 Axis 4 PB perspective raw enum hit 16 → 0 (commit 2f6d19d + svc-viability-v2 T2-3 재측정)
- Axis 1 UI matrix fresh_baseline 70/112 → 106/112 (+36셀, 주 원인: T3-2 __wmahPageReady + T3-3 STATUS_LABELS 추가)

---

## Follow-ups

| ID | 내용 | Owner | Cycle |
|---|---|---|---|
| F-1 | **T5-2 ADR slot 정합성** — ADR-011/ADR-012/ADR-013 file:ADR-NNN 번호 일관성 확인 + 필요 시 rename | worker-3 | svc-viability-v2 W5 |
| F-2 | `apps/web/src/tests/status-labels-coverage.test.ts` 신규 생성 — backend V*.sql enum 목록 vs STATUS_LABELS key 자동 비교 | 차기 cycle | svc-viability-v3 후보 |
| F-3 | OpenAPI yaml 자동 enum check script — `scripts/` 추가 후보 (enum 추가 시 Step 3 자동화) | 차기 cycle | svc-viability-v3 후보 |

---

## References

- `apps/web/src/lib/labels.ts` — STATUS_LABELS SoT (현재 40+ entries)
- `apps/web/src/lib/labels.ts:171` — `export function statusLabel(code?: string | null): string`
- T3-3 commit `2f6d19d` — F15 enum type drift 6 surfaces audit + ACKNOWLEDGED/EXPIRED/PASSED/RESPONDED 추가
- ADR-010 §4 — service-viability baseline, frontend label single SoT 원칙 (최초 명시)
- svc-viability-v2 plan §3 T4-1 — 본 ADR 작성 지시
