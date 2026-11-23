# ADR-010 — Service Viability Baseline Assumption & Cycle-Entry Measurement Protocol

**Date**: 2026-05-24
**Status**: Accepted
**Deciders**: project maintainer + svc-follow-up-v1 team
**Cycle context**: service-viability audit v1 → follow-up v1 (M1 cycle-meta item)

---

## Decision

**Plan §baseline 표는 "incremental +N row" 형태로만 기술한다. 실측 baseline은 cycle 진입
직전 별도 측정으로 확보하며, plan 표에 hardcode하지 않는다.**

---

## Context (Why this decision is needed)

### 배경 사실 (file:LINE / commit 직접 인용)

#### 1. plan v1.2 §3.3 Step 1 baseline 표 (plan SoT)

파일: `.omc/plans/ralplan-wmah-service-viability-audit-v1.2.md:273-276`

```
| Table                    | V067 baseline | V068 incremental | Cycle target |
|--------------------------|---------------|------------------|--------------|
| dispute_cases (OPEN)     | 2             | +3               | 5            |
| kyc_edd_triggers (OPEN)  | 3             | +3               | 6            |
| house_views (GENERATED)  | 0             | +3               | 3            |
| email_drafts (DRAFT)     | 0             | +3               | 3            |
```

plan v1.2:273-276은 V067 INSERT rows를 baseline으로 가정했다.
근거: `V067:155-169` (dispute_cases 2건), `V067:22-39` (kyc_edd_triggers 3건).

#### 2. 직전 cycle (backend bug hunt v3) 영향

commit `730242b` ("PATCH /nba-actions/{id}/status snoozed_until str→datetime fix")
commit `473b2cb` ("Backend bug hunt v3 종결: 5-phase + 1 real bug fix + handoff")

backend bug hunt v3 cycle의 status-transition matrix test가 V067 시드된 OPEN row들을
전이시켰다:

```
# dispute_cases — psql 실측 (prefix 88888888-8888-8888-8888-880000001*)
id 1201 → RESOLVED  (V067 가정: OPEN)
id 1202 → RESPONDED
id 1203 → RESOLVED  (V067 가정: OPEN)
id 1204 → RESOLVED

# kyc_edd_triggers — psql 실측 (prefix 88888888-8888-8888-8888-880000000*)
id 601 → CLOSED      (V067 가정: OPEN)
id 602 → CLOSED      (V067 가정: OPEN)
id 603 → IN_PROGRESS
id 604 → CLOSED
id 605 → CLOSED      (V067 가정: OPEN)
```

출처: `.omc/handoffs/svc-via-audit-v1__step0-ops-pause.md` §1.1

#### 3. cycle 진입 시 실측값 (BEFORE V068 적용)

출처: `.omc/handoffs/svc-via-audit-v1__step0-ops-pause.md` §1 baseline divergence 표

```
| Table                   | plan v1.2 가정 | psql 실측 (BEFORE V068) |
|-------------------------|---------------|-------------------------|
| dispute_cases (OPEN)    | 2             | 0   ← 전부 전이됨       |
| kyc_edd_triggers (OPEN) | 3             | 0   ← 전부 전이됨       |
| house_views (GENERATED) | 0             | 63  ← 예상 외 surplus   |
| email_drafts (DRAFT)    | 0             | 98  ← 예상 외 surplus   |
```

plan 가정 대비 dispute_OPEN/kyc_OPEN 둘 다 **0** (Δ -2, -3). house_views/email_drafts는
반대로 63/98 surplus (출처 미파악 — runtime mutation 추정, 본 ADR 범위 외).

#### 4. 대응 (V068 incremental re-seed)

plan SoT 의도를 살려 V068 (+3건/테이블) incremental re-seed 실행:
파일: `db/migrations/V068__service_viability_audit_seeds.sql:1-148`

AFTER V068 실측:
- dispute_cases OPEN: 0→3 (+3) ✓
- kyc_edd_triggers OPEN: 0→3 (+3) ✓
- house_views GENERATED: 63→66 (+3) ✓
- email_drafts DRAFT: 98→101 (+3) ✓
- audit_logs total: 25519→25519 (0, append-only 무손상) ✓

출처: `.omc/handoffs/svc-via-audit-v1__step0-ops-pause.md` §3.3

---

## Drivers

1. **cycle-time variable**: fixture row의 status는 다른 cycle이 변경할 수 있다. plan
   작성 시점과 cycle 진입 시점 사이에 status-transition이 발생하면 hardcode 가정이
   틀려진다.

2. **test cycle integrity**: V067 OPEN row 보존을 위해 backend bug hunt v3의
   status-transition matrix test를 회피하는 것은 test cycle 의도 훼손이다 (Option A
   거부 근거).

3. **plan SoT 혼란 방지**: plan v1.2:273-276처럼 절댓값을 hardcode하면 다음 cycle 진입
   시 실측값과 불일치 → cycle worker가 plan 신뢰성 상실 또는 잘못된 cycle target 설정.

4. **incremental delta는 안전**: V068 +3건씩의 incremental은 BEFORE baseline에
   더해지므로 BEFORE baseline이 무엇이든 delta assertion은 정확하게 유지된다.

---

## Alternatives Considered

### Option A — V067 OPEN row 보존 (status-transition test 회피)

- **설명**: V067 seed row의 status를 reset하거나, backend test에서 해당 row를 건드리지
  않도록 exclusion filter 추가.
- **거부 이유**: test cycle이 production-like status-transition을 검증하는 것이 의도.
  특정 row를 "test 금지" 처리하면 test coverage 왜곡 + fixture와 실측 간 이중 관리
  부담 발생.

### Option B — cycle 진입 시 baseline 측정 mandatory + plan 표는 incremental delta만 기술 *(CHOSEN)*

- **설명**: plan §baseline 표는 `V068 incremental: +N row` 형태로만 기술한다. 실측
  baseline은 cycle 진입 직전 Step 0에서 psql 직접 측정 후 handoff에 박제.
- **선택 이유**: plan SoT는 delta 의도를 정확히 표현하고, 실측값은 cycle 시점에 확보.
  BEFORE/AFTER 측정으로 incremental delta assertion이 cycle-time variable 영향 없이
  정확하게 동작한다.

---

## Why Chosen

baseline은 cycle-time variable (다른 cycle의 mutation으로 변한다). plan에 hardcode하면
작성 시점의 snapshot이 되어 다음 cycle 진입 시 틀릴 가능성이 높다. 반면 incremental
delta는 V068의 INSERT 건수처럼 cycle 내에서 발생하는 순수 변화량이므로 plan에 안전하게
기술할 수 있다. 실측 baseline은 cycle Step 0에서 직접 측정해 handoff에 박제하는 것이
단일 SoT 역할을 한다.

---

## Consequences

### 즉시 적용 (svc-follow-up-v1 M1)

- **plan v1.2 in-place 미수정**: plan v1.2는 직전 cycle(service-viability audit v1)의
  SoT로 보존. 본 ADR이 자체 SoT 역할을 대신한다.
- **plan v1.2:273-276 표의 "V067 baseline" 열**: 사후 검증 결과 가정값임이 확인됨.
  실측값은 `.omc/handoffs/svc-via-audit-v1__step0-ops-pause.md` §1 참조.

### 향후 cycle plan 작성 규칙

1. §baseline 표의 "V067 baseline" 같은 절댓값 열은 **작성 금지**.
2. 대신 `"incremental +N row"` 열만 기술. cycle target은 `BEFORE + N` 수식으로 표현.
3. cycle Step 0에서 반드시 BEFORE baseline을 psql 직접 측정 → handoff §baseline 섹션에
   박제.
4. PASS criterion은 `AFTER - BEFORE = N` (delta assertion) 형태로 기술.

예시:
```markdown
| Table                   | V0XX incremental | Step 0 BEFORE (측정) | Step N AFTER (측정) | Δ assert |
|-------------------------|------------------|-----------------------|----------------------|----------|
| dispute_cases (OPEN)    | +3               | (cycle 진입 시 측정)  | (cycle 종료 시 측정) | +3       |
| kyc_edd_triggers (OPEN) | +3               | (cycle 진입 시 측정)  | (cycle 종료 시 측정) | +3       |
```

### 관련 memory rules 연결

- `[[stale-os-env-shadowing]]` — 가정(static plan값)보다 실측 우선 원칙과 동일 패턴.
- `[[critic-finds-factual-errors-planner-misses]]` — Planner가 작성한 baseline 표도
  factual error 포함 가능. cycle 진입 시 file inspection으로 교차 검증 필요.

---

## Follow-ups

| # | 항목 | 담당 | 참조 |
|---|------|------|------|
| F1 | service-viability audit v2 진입 시 Step 0 baseline 측정 mandatory 적용 | 차기 cycle worker | 본 ADR §Consequences |
| F2 | house_views GENERATED 63 / email_drafts DRAFT 98 baseline 출처 추적 | Optional (cycle 결과 영향 없음) | step0-ops-pause.md §4 Follow-up 2 |
| F3 | V067 sql_id validator pre-existing fail 보정 (별도 task #11) | worker-3 | step0-ops-pause.md §4 Follow-up 1 |

---

## References

| 항목 | 파일 / 위치 |
|------|-------------|
| plan v1.2 baseline 표 (가정값) | `.omc/plans/ralplan-wmah-service-viability-audit-v1.2.md:273-276` |
| step0 실측 divergence 박제 | `.omc/handoffs/svc-via-audit-v1__step0-ops-pause.md` §1 |
| V067 dispute_cases INSERT | `db/migrations/V067__service_readiness_fixture_seeds.sql:155-169` |
| V067 kyc_edd_triggers INSERT | `db/migrations/V067__service_readiness_fixture_seeds.sql:22-39` |
| V068 incremental re-seed | `db/migrations/V068__service_viability_audit_seeds.sql:1-148` |
| backend bug hunt v3 종결 commit | `473b2cb` ("Backend bug hunt v3 종결: 5-phase + 1 real bug fix + handoff") |
| status-transition commit (snoozed_until fix) | `730242b` ("PATCH /nba-actions/{id}/status snoozed_until str→datetime fix") |
| 직전 cycle closure handoff | `.omc/handoffs/wave-fix-service-viability-audit-v1.md` §4 M1 |
| 본 follow-up cycle plan SoT | `.omc/plans/ralplan-wmah-follow-up-v1.md` §3 Wave 1 M1 |
