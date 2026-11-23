# ADR-021: 감사로그 SoD `human_reviewer` 기록 모델 (distinct-reviewer 한정)

## Status

Accepted (2026-06-01) — Phase 1(set 17→4 축소) + Phase 2(유지 4코드 emit이 human_reviewer 기록)
적용·**라이브 검증 완료**. A-4 결정 반영(아래 §A-4 결정). SoD 게이트 `not_operational→operational`
전환 확인(Bucket B populate). OBS-02 human_reviewer_required 동기화만 잔여.

라이브 검증 증거(2026-06-01): dispute RESPOND(PB)→distinct RESOLVE(ADMIN) → `human_reviewer=PB≠resolver`;
email create(PB1)→submit→approve(WM1 distinct)→send → `email_draft_approved.human_reviewer=WM1,
original_creator=PB1`(distinct), `email_sent_via_sandbox.human_reviewer=WM1(approver)≠sender(PB1)`;
SoD 팩 Bucket B 0→4, hr_dim=operational. (과거 Phase-2 이전 행은 human_reviewer NULL이라 Bucket C
위반으로 집계 — 정직한 동작; 미래 윈도 또는 `--allow-exception`으로 처리.)

## Context

`scripts/generate_sod_evidence_pack.py`는 Segregation-of-Duties 증거 팩을 생성하며,
`HUMAN_REVIEWER_REQUIRED_ACTION_CODES` 집합에 속한 action_code의 감사로그 행을
세 버킷으로 분류한다.

- Bucket A: `governance_marker = 'PoC_AUTO_APPROVAL'`
- Bucket B: `governance_marker IS NULL` + `detail_json->>'human_reviewer' IS NOT NULL` (정상)
- Bucket C: `governance_marker IS NULL` + `detail_json->>'human_reviewer' IS NULL` (위반, 기대 0)

문제: 원래 집합 17개 코드 중 다수가 **단일 actor의 자기 확인**(예: PB가 본인 상담을
COMPLETED 전환) 또는 **ADMIN 단독 거버넌스**(예: house view 활성화)였다. 이들 emit
경로에는 초기 actor와 구별되는 제2의 인간 검토자가 코드상 존재하지 않으며, 어떤 emit도
`detail_json.human_reviewer` 키를 기록하지 않는다(apps/api는 `governance_marker`만 기록).
그 결과 해당 코드의 정상 emit은 매번 `human_reviewer` NULL → Bucket C(거짓 위반)로
떨어지고, `not_operational` 부트스트랩(스크립트의 #4 수정, B=0 & C>0)이 그 위반을 가려
게이트 PASS를 위장하는 구조였다.

근거: #4-A 분류는 17개 코드 각각의 emit site를 직접 read하여 distinct reviewer 유무를
판정했다(file:LINE는 §Decision 참조).

## Decision Drivers

- **False attestation 금지**: distinct reviewer가 없는데 initiator를 reviewer로 기재하면
  존재하지 않는 4-eye를 허위 입증한다(법적 통제점 신뢰 훼손).
- fail-closed 부트스트랩이 진짜 통제 갭을 가리는 마스킹 제거.
- audit action code 2-source 등록 규칙(V*.sql + Python CANONICAL + OBS-02)과 정합.
- 시간/토큰은 driver가 아니라 Risk로만 취급.

## Decision

### Phase 1 (적용됨) — 집합 축소

`HUMAN_REVIEWER_REQUIRED_ACTION_CODES`를 **distinct reviewer가 코드 경로상 실재/강제되는
4개**로 축소하고, 단일행위자·자동게이트·ADMIN 단독 13개는 제거한다.

**유지 (genuine review-decision points):**

| code | emit site | distinct reviewer 필드 | 보장 |
|---|---|---|---|
| `dispute_case_resolved` | `routers/disputes.py:220` | `previous_actor_id`(=responder) | 선제 same-actor 4-eye 블록(`disputes.py:171-194`)이 resolver≠responder 보장 |
| `email_draft_approved` | `routers/email.py:455` | `actor.employee_id`(승인자) vs `draft['employee_id']`(작성자) | 마케팅은 403 hard-enforce(`email.py:420-440`); 비마케팅 미보장(caveat) |
| `email_draft_rejected` | `routers/email.py:503` | `actor.employee_id`(반려 reviewer) | approve와 동일 통제점; reject path는 actor≠author 미강제(caveat) |
| `email_sent_via_sandbox` | `routers/email.py:655` | `draft['approved_by_id']`(사전 승인자, sender 아님) | A-4 미결 |

**제거 (distinct reviewer 부재):**

- 단일행위자 자기 확인: `consultation_complete`, `suitability_confirmed`,
  `explanation_confirmed`, `four_gate_acknowledged`, `kyc_edd_triggered`,
  `kyc_edd_reassessed`, `conflict_disclosed`, `info_access_responded`
- 자동게이트 / ADMIN 단독: `marketing_review_approved`, `marketing_review_rejected`,
  `house_view_activated`, `house_view_reviewed`, `credit_info_purge_simulated`

### Phase 2 (미적용, 후속) — emit이 `detail_json.human_reviewer` 기록 시작

유지 4개 코드의 emit site가 distinct reviewer id를 `str()`-coerce하여
`detail_json.human_reviewer`에 기록하면(=[[audit-emit-uuid-coercion]]), Bucket B가
populate되고 게이트가 `not_operational`에서 strict pass/fail로 자동 전환된다. 백엔드
다파일 변경 + 재기동 + 통합검증이 필요하므로 별도 작업으로 분리한다. 가장 견고한 단일
적용 대상은 `dispute_case_resolved`(previous_actor_id, distinct 보장).

### A-4 결정 (반영됨 2026-06-01 — 권고안 위임 판단)

**채택**: #1 → `email_sent_via_sandbox.human_reviewer = str(approved_by_id)`(사전 승인자, sender 아님).
#2 → email approve/reject가 `human_reviewer=str(actor.employee_id)`(검토자) + `original_creator=
str(draft.employee_id)` 동시 기록(Bucket B가 per-row distinctness 평가 가능; 마케팅은 four_eyes
403으로 보장, 비마케팅은 caveat로 잔존). #3 → `house_view_*`는 invariant 미도입(스키마 변경 범위
밖) → Phase 1대로 DROP 유지. 원 옵션 분석은 아래와 같다.

#### 원 옵션 (사용자 결정 필요했던 항목)

1. `email_sent_via_sandbox`: 의미상 reviewer는 sender(actor)가 아니라 사전 승인자
   (`approved_by_id`). 집합 유지 + `human_reviewer=approved_by_id` 기록 vs 집합 제거 +
   별도 `prior_approver` 메타만 기록.
2. email approve/reject 비마케팅 distinctness 미보장: Bucket 판정을 `marketing_classified`
   에 게이팅할지, `original_creator`(=`draft['employee_id']`)를 함께 stamp해 per-row
   actor≠creator를 검증할지.
3. `house_view_*`에 per-tuple drafter≠reviewer invariant(스키마 actor 컬럼)를 도입해
   진짜 2인 통제로 승격할지(현재 없음 → Phase 1에서는 DROP).

## Alternatives Considered

- (기각) 17개 전부 `actor_id`를 `human_reviewer`로 복제: false 4-eye 입증, 의미 0.
- (기각) `house_view_*`에 즉시 drafter≠reviewer invariant 강제: 스키마 변경 필요, PoC 범위
  초과 → A-4 #3로 분리.
- (기각) 집합 무변경 + not_operational 부트스트랩만 유지: 13개 코드가 영구 거짓 위반으로
  남아 emit 기록을 추가해도 절대 operational이 안 됨.

## Consequences

- (+) Bucket C phantom 위반 소멸; 부트스트랩 마스킹 의존 해소; 게이트가 진짜 distinct
  reviewer 유무를 측정.
- (+) Phase 2 emit 기록이 들어오면 4개 코드만으로 게이트가 깨끗하게 operational 전환.
- (−) Phase 2 적용 전까지는 4개 코드도 `not_operational`(Bucket B=0)로 남는다.
- (−) 비마케팅 email approve/reject는 distinctness 미보장이라 caveat 주석 필수.
- (후속) `docs/observability/OBS-02_audit_action_codes.md`의 human_reviewer_required
  표기를 4개로 동기화; V*.sql / Python CANONICAL과 3-source 정합 점검.

## Follow-ups

- [x] Phase 2: `disputes.py` emit `human_reviewer=str(previous_actor_id)` (commit c154224) — 라이브 검증.
- [x] A-4 #1/#2/#3 결정 + email approve/reject/send emit 반영 — 라이브 검증(Bucket B=4).
- [ ] OBS-02 human_reviewer_required 컬럼을 4코드로 동기화 (잔여, doc-sync).
- [x] SoD 라이브 윈도 Bucket B populate + operational 전환 확인.
- [ ] (운영) Phase-2 이전 dispute/email 행(현재 윈도 56건)은 Bucket C 집계 — audit 윈도를 배포
  이후로 잡거나 `--allow-exception`으로 처리.

References: #4-A 분류(svc-quality audit workflow `wb7az5apy`), [[audit-emit-uuid-coercion]],
[[audit-action-code-two-source-registration]], [[aspirational-doc-vs-poc-reality]].
