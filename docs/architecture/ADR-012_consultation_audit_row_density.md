# ADR-012 — Consultation Audit Row Density & Retention Policy

**Date**: 2026-05-24
**Status**: Accepted
**Deciders**: project maintainer + svc-follow-up-v1 team
**Cycle context**: service-viability audit v1 F4 finding → follow-up v1 Wave 4 Q2
**Note**: ADR-011 slot already occupied by `ADR-011_idempotency_key_middleware.md`; this ADR uses -012.

---

## Decision

**raw row 유지 + 명시적 retention 정책 + partition tuning 을 채택한다 (Option B).**
consultation workflow 1건당 최대 12–14 audit_logs row를 허용하되, 향후 production
진입 전 retention window 설정 및 partition scheme 수립을 의무화한다.

---

## Context (Finding Evidence — file:LINE 직접 인용)

### F4 원래 finding (service-viability audit v1)

> consultation 1건 처리 시 `consultation_create` + 4× `four_gate_acknowledged` = 5 audit row.
> consultations.py:73 + consultation_gates.py:374. audit_logs storage 효율성 review 후보.

출처: `.omc/handoffs/wave-fix-service-viability-audit-v1.md` §3 F4 (indirect — handoff 인용)

### D3 fix (commit d7b79af) 추가 발견

Wave 3 D3 작업 (commit `d7b79af` — "D3 (F6): 4-gate pre-check 흐름 문서화 + marketing gate row persist")에서
4-gate pre-check endpoint 각각도 audit_logs row를 emit함이 확인됨:

| Step | Endpoint | Emitted action_code | File:LINE |
|------|----------|---------------------|-----------|
| 1 | POST /consultations | `consultation_create` | `consultations.py:71` |
| 2a | GET /four-gate/suitability/check | `suitability_confirmed` OR `suitability_grade_blocked` | `consultation_gates.py:132` |
| 2b | GET /four-gate/explanation/check | `explanation_confirmed` | `consultation_gates.py:285` |
| 2c | GET /four-gate/unfair-solicitation/check | `unfair_solicitation_blocked` (BLOCK 시만) | `consultation_gates.py:459` |
| 3a | POST /four-gate/suitability/acknowledge | `four_gate_acknowledged` | `consultation_gates.py:377` |
| 3b | POST /four-gate/explanation/acknowledge | `four_gate_acknowledged` | `consultation_gates.py:377` |
| 3c | POST /four-gate/unfair-solicitation/acknowledge | `four_gate_acknowledged` | `consultation_gates.py:377` |
| 3d | POST /four-gate/marketing/acknowledge | `four_gate_acknowledged` | `consultation_gates.py:377` |
| 4 | POST /kyc-edd/evaluate | `kyc_edd_evaluated` | `kyc_edd.py` |
| 5 | POST /email-drafts | `email_drafted` | `email.py` |
| 6 | POST /email-drafts/{id}/submit-for-approval | `marketing_review_submitted` (auto) + `email_draft_submitted` | `email.py` |
| 7 | POST /email-drafts/{id}/approve | `email_draft_approved` | `email.py` |

**PASS path (no BLOCK) 최솟값**: 12 row / 9 distinct codes
(`four_gate_acknowledged` ×4 + 3 pre-check confirms + 4 email chain + `kyc_edd_evaluated`)

출처: `scripts/audit_v1_workflow_e2e.py` comment
("Runtime emits 12 row / 9 distinct codes (four_gate_acknowledged ×4 + kyc_edd_evaluated + marketing_review_submitted auto-emit)")

**BLOCK path 추가**: `unfair_solicitation_blocked` 또는 `suitability_grade_blocked` emit 시
+1~2 row → 최대 14 row.

### 현재 audit_logs 규모

service-viability audit v1 Axis 3 측정값:
- audit_logs total (cycle 진입 직전): 25,519 row (psql 실측)
- cycle 내 HP1 full 실행 시 delta: 6 row (revised — 4-gate ack 제외한 shortened path)
- full path (D3 fix 후) HP1: ~12 row 예상

출처: `.omc/handoffs/svc-via-audit-v1__step0-ops-pause.md` §3.3 audit_logs total;
`scripts/audit_v1_workflow_e2e.py` HP1_EXPECTED_ROW_COUNT_REVISED = 6

---

## Drivers

1. **audit completeness**: `audit_logs`는 ADR-006 + V008 + V019 append-only trigger로
   보호됨. 각 row가 별도 비즈니스 event (pre-check 결과 + ack 기록)를 대표하며
   분쟁 발생 시 증거 chain으로 필요.

2. **regulatory context**: REG-01 §3.1 / REG-02 §3 / REG-03 §광고규제 — regulator-mandated
   retention. audit_logs 압축은 규제 감사 trail 손상 위험.
   출처: `ADR-002_email_authority_and_schema_contract.md:264-266`

3. **PoC scale**: 현재 25,519 row = PoC 범위. full production scale (수천 consultation/월)
   에서는 consultation당 12-14 row × volume이 table growth 문제가 됨.

4. **four_gate_acknowledged distinct code 부재**: 4개 gate ack가 동일 `four_gate_acknowledged`
   code를 공유 → audit 분석 시 gate별 구분 불가. row density 문제와 별개로 code
   granularity 개선 후보 (본 ADR scope 외).

---

## Alternatives Considered

### Option A — composite row 통합 (4-gate ack → single composite event)

- **설명**: 4× `four_gate_acknowledged` row를 단일 `four_gate_all_acknowledged`
  composite row로 교체. schema `detail_json`에 4 gate 결과 inline.
- **거부 이유**:
  - schema 변경: `audit_logs` action_code enum 추가 + migration 필요 (V071+)
  - gate-level timestamp 손실: 어느 gate를 언제 ack했는지 개별 추적 불가
  - ADR-006 append-only 원칙과 충돌 — event log는 개별 event 단위로 기록이 원칙
  - regulatory audit trail 세분화 손실

### Option B — raw row 유지 + retention 정책 + partition tuning *(CHOSEN)*

- **설명**: 현행 per-event 1 row 구조 유지. production 진입 전 `audit_logs` retention
  window (예: 7년 compliance tier / 90일 operational tier) 설정 및 `created_at` 기준
  partition scheme 수립.
- **선택 이유**:
  - schema/코드 변경 없음 (backward-compatible)
  - audit completeness 100% 보존
  - retention + partition으로 storage growth 통제 가능
  - PoC 현 scale (25K row)에서는 즉각 조치 불필요

### Option C — audit_logs 분리 (high-volume operational vs low-volume compliance)

- **설명**: `audit_logs`를 `compliance_audit_logs` (규제 대상, 장기 보관) +
  `operational_logs` (four_gate_acknowledged 등 고빈도, 단기 보관)로 테이블 분리.
- **거부 이유**:
  - 가장 큰 schema 변경 (migration + router 전체 변경 + ADR-006 계약 갱신)
  - 어떤 action_code가 compliance vs operational인지 분류 기준 불명확
  - PoC에서 over-engineering

---

## Why Chosen (Option B)

consultation audit row density는 현재 **PoC scale에서 즉각 블로커가 아니다** (25K row,
full HP1 +12 row). production volume 도달 전 retention 정책과 partition scheme을 수립하면
충분히 통제 가능하다. schema 무변경 + audit completeness 보존이 Option A/C 대비 압도적
우위다. four_gate_acknowledged code granularity 문제는 별도 Follow-up으로 분리한다.

---

## Consequences

### 즉시 적용 없음

- Option B는 schema/코드 변경 없음. PoC 현 scale에서 즉각 조치 불필요.

### Production 진입 전 의무화 항목

1. **retention window 설정**: compliance tier (규제 요건 — 최소 5년) / operational tier
   (four_gate_acknowledged 등 — 90일 권고) 분리 정책 문서화.

2. **partition scheme**: `audit_logs.created_at` 기준 monthly 또는 quarterly partition.
   25K/PoC → production 예상 volume 계산 후 partition key 결정.

3. **four_gate_acknowledged code granularity** (별도 Follow-up): 4개 gate ack를
   `four_gate_suitability_acknowledged` / `four_gate_explanation_acknowledged` /
   `four_gate_unfair_solicitation_acknowledged` / `four_gate_marketing_acknowledged`
   로 분리. OBS-02 action_code 카탈로그 갱신 필요.

### 관련 계약 변경 없음

- ADR-006 (append-only) 무변경
- ADR-002 (email audit trail) 무변경
- V008 / V019 trigger 무변경

---

## Follow-ups

| # | 항목 | Priority | 참조 |
|---|------|----------|------|
| F1 | retention window policy 문서화 | Production gate | ADR-002:266, REG-01 §3.1 |
| F2 | audit_logs partition scheme 설계 | Production gate | 본 ADR §Consequences |
| F3 | four_gate_acknowledged code granularity (4개 분리) | Nice-to-have | consultation_gates.py:377, OBS-02 |

---

## References

| 항목 | 파일 / 위치 |
|------|-------------|
| F4 finding 박제 | `.omc/handoffs/wave-fix-service-viability-audit-v1.md` §3 F4 |
| consultation_create emit | `apps/api/harness/api/routers/consultations.py:71` |
| suitability pre-check emit | `apps/api/harness/api/routers/consultation_gates.py:132` |
| explanation pre-check emit | `apps/api/harness/api/routers/consultation_gates.py:285` |
| unfair_solicitation blocked emit | `apps/api/harness/api/routers/consultation_gates.py:459` |
| four_gate_acknowledged emit | `apps/api/harness/api/routers/consultation_gates.py:377` |
| HP1 12-row script comment | `scripts/audit_v1_workflow_e2e.py` HP1_EXPECTED_ROW_COUNT_REVISED |
| D3 pre-check flow fix | commit `d7b79af` ("D3 (F6): 4-gate pre-check 흐름 문서화 + marketing gate row persist") |
| ADR-006 append-only | `docs/architecture/ADR-006_audit_append_only_trigger.md` |
| ADR-002 retention cross-ref | `docs/architecture/ADR-002_email_authority_and_schema_contract.md:264-266` |
| audit_logs total (PoC baseline) | `.omc/handoffs/svc-via-audit-v1__step0-ops-pause.md` §3.3 (25,519 row) |
