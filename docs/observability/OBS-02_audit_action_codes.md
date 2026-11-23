# OBS-02 Audit Action Codes

Source of truth: `audit_action_codes` lookup table. `audit_logs.action_code` is FK-constrained.
Seeding migrations: V008 (baseline), V022 (REG-01/02/04/05/06 expansion), V027 (consents T214-T217), V033 (파기 T219).

## Canonical Codes

The table order below **must** match `CANONICAL_AUDIT_ACTION_CODES` in `apps/api/harness/core/audit.py` exactly —
`test_canonical_audit_codes_match_docs` enforces this.

### Baseline (V008)
| action_code | 발생 조건 |
|---|---|
| AI_CALL_STARTED | AI 호출 시작 |
| AI_CALL_SUCCEEDED | AI 호출 성공 |
| AI_CALL_FAILED | AI 호출 실패 |
| EMBEDDING_CALL_FAILED | 내부 BGE embedding/rerank 실패 |
| customer_360_view | Customer 360 조회 |
| consultation_create | 상담 생성 |
| consultation_complete | 상담 COMPLETED 전환 |
| nba_complete | NBA DONE 전환 |
| nba_dismiss | NBA DISMISSED 전환 |
| house_view_activate | House View ACTIVE 전환 |
| email_draft_send | 이메일 발송 (real-SMTP 전송 성공 시 emit 예약; 본 PoC는 sandbox 전용이라 미emit — 실제 발송 성공은 §REG-02 `email_sent_via_sandbox`) |
| risk_assessment_create | 위험성향 평가 생성 |
| aftercare_event_resolve | aftercare event RESOLVED 전환 |
| recommendation_simulation_create | 추천 시뮬레이션 생성/승인 |
| recommendation_simulation_block | 추천 시뮬레이션 4-gate 차단 |
| recommendation_simulation_cancel | 추천 시뮬레이션 취소 |
| order_simulation_create | 주문 시뮬레이션 생성/승인 |
| order_simulation_block | 주문 시뮬레이션 4-gate 차단 |
| order_simulation_execute_simulated | 주문 시뮬레이션 실행 상태 기록 |
| order_simulation_cancel | 주문 시뮬레이션 취소 |

### REG-05 인증 / WebSocket / 레이트리밋 (V022)
| action_code | 발생 조건 |
|---|---|
| auth_login_success | 로그인 성공 |
| auth_login_failure | 로그인 실패 (자격증명 불일치, 잠금 등) |
| auth_login_rate_limited | 로그인 레이트리밋 차단 |
| auth_refresh | 액세스 토큰 갱신 (유효 refresh token) |
| auth_refresh_rate_limited | /auth/refresh per-IP 429 차단 (V056, B5) |
| auth_refresh_reuse | refresh 토큰 재사용 탐지 (체인 폐기) |
| auth_logout | 로그아웃 (refresh 토큰 폐기) |
| rate_limit_exceeded | 라우트 레이트리밋 초과로 거부 |
| ai_token_rate_limited | AI 토큰 한도 초과 (LLM10 per-employee ceiling) |
| ws_ticket_issued | WebSocket 단명 ticket 발급 |
| ws_ticket_consumed | handshake 시 ticket 소진 (single-use) |
| ws_connection_opened | WebSocket 연결 수립 |
| ws_connection_closed | WebSocket 연결 종료 |
| ws_reconnect | 클라이언트 재접속 (backoff) |

### T16 House View 생애주기 (V035)
| action_code | 발생 조건 |
|---|---|
| house_view_drafted | House View 초안 생성 |
| house_view_generated | House View AI 생성 완료 |
| house_view_reviewed | House View 검토 완료 |
| house_view_activated | House View ACTIVE 전환 (V035 상세) |
| house_view_archived | House View 아카이브 |

### T17/T243 NBA 카드 생애주기
| action_code | 발생 조건 |
|---|---|
| nba_card_created | NBA 카드 생성 |
| nba_card_acknowledged | NBA 카드 확인 |
| nba_card_dismissed | NBA 카드 기각 |
| nba_card_completed | NBA 카드 완료 |

### T244/T257 Aftercare 분기 생애주기
| action_code | 발생 조건 |
|---|---|
| aftercare_queued | aftercare 분기 큐 등록 |
| aftercare_completed | aftercare 분기 완료 |
| aftercare_skipped | aftercare 분기 건너뜀 |

### T248 KYC/EDD 트리거 (V029)
| action_code | 발생 조건 |
|---|---|
| kyc_edd_triggered | KYC/EDD 강화 심사 트리거 |
| kyc_edd_reassessed | KYC/EDD 재평가 완료 |
| kyc_edd_completed | KYC/EDD trigger 종결 (V060, C2; split from kyc_edd_reassessed) |
| kyc_edd_trigger_listed | KYC/EDD triggers list 조회 (V060, C2) |
| kyc_edd_trigger_detail_viewed | KYC/EDD trigger 상세 조회 (V060, C2) |
| kyc_edd_evaluated | KYC/EDD trigger 평가 (V060, C2) |

### T249 이해상충 사전신고 (V030)
| action_code | 발생 조건 |
|---|---|
| conflict_disclosed | 이해상충 사전 공시 완료 |
| conflict_of_interest_blocked | 이해상충으로 인한 추천/주문 차단 |

### REG-01 신용정보법 §32/§37/§38 동의·열람정정·연락중지 (V027, T214-T217, T229)
| action_code | 발생 조건 |
|---|---|
| consent_recorded | 고객 동의 기록 (신용정보법 §32) |
| consent_withdrawn | 고객 동의 철회 (신용정보법 §37) |
| marketing_consent_withdrawn | MARKETING_CONTACT 동의 철회 / 연락중지청구 (§37) |
| info_access_requested | 열람·정정 청구 생성 (신용정보법 §38) |
| info_access_responded | 열람·정정 청구 응답 (신용정보법 §38) |
| general_bundle_consent | 자본시장법·신용정보법·금소법 일괄동의 (§32, T229) |

### REG-01 신용정보법 §20-2 파기 (V033, T219)
| action_code | 발생 조건 |
|---|---|
| credit_info_purge_simulated | 파기 스케줄 기록 (Stage 7 runbook이 실제 삭제 수행) |

### REG-04 AI 거버넌스 / Dual-LLM (V022)
| action_code | 발생 조건 |
|---|---|
| ai_quarantine_triggered | quarantined LLM 컨텍스트 적용 (OWASP LLM01) |
| quarantine_released | 격리된 document_chunk를 ADMIN이 명시적 해제 (V045) |
| ai_job_get | /ai-jobs/{id} GET 민감 read (V058, B7) |
| ai_output_get | /ai-outputs/{id} GET 민감 read (V058, B7) |
| citation_gate_failed | RAG citation gate 차단 (no-citation; V058, B9) |
| provider_failure | Azure AI provider 호출 실패 (V058, B9) |
| consultation_status_changed | consultation 비-COMPLETED 상태 전이 (V058, B10) |
| nba_ws_broadcast_failed | NBA WS broadcast 실패 (V058, B12) |
| nba_script_generated | NBA conversational script가 Azure GPT 호출로 동기 생성됨 (2026-05-24 W2 신설, POST /nba-cards/{id}/generate-script) |
| ai_fail_closed | AI 출력이 fail_closed_reason_code에 의해 차단 |
| ai_injection_detected | INJECTION_PATTERNS.yaml 패턴 매칭 |
| model_card_published | 모델 카드 발행 |
| model_card_revised | 모델 카드 개정 |

### REG-01 권리고지 / 분쟁 (V022)
| action_code | 발생 조건 |
|---|---|
| rights_notice_issued | 투자자 권리고지 발급 |
| rights_notice_acknowledged | 권리고지 PB 확인 (V058, C6) |
| dispute_case_opened | 분쟁 사건 개시 |
| dispute_responded | 분쟁 사건 응답 단계 전이 (V059, C7) |
| dispute_case_resolved | 분쟁 사건 종결 |

### REG-02 광고심의 / 이메일 (V022, V034)
| action_code | 발생 조건 |
|---|---|
| marketing_review_submitted | 광고문안 심의 제출 |
| marketing_review_approved | 광고문안 심의 승인 |
| marketing_review_rejected | 광고문안 심의 반려 |
| marketing_review_blocked | 마케팅 동의 철회로 발송 차단 |
| email_drafted | 이메일 초안 생성 |
| email_draft_submitted | 이메일 초안 심의 제출 |
| email_draft_approved | 이메일 초안 심의 승인 |
| email_draft_rejected | 이메일 초안 심의 반려 |
| email_sent_via_sandbox | 이메일 sandbox(Mailpit) 전송 성공 |
| email_send_failed | 이메일 전송 실패 (SMTP fail-closed) |
| email_send_blocked | 이메일 차단 (마케팅 동의 철회 / 게이트 미통과) |

### SoD human_reviewer_required set (ADR-021)

다음 4개 action_code는 distinct 제2검토자가 코드 경로상 실재·강제되는 review-decision 지점으로,
emit이 `detail_json.human_reviewer`(검토자 id)를 기록한다. `scripts/generate_sod_evidence_pack.py`의
`HUMAN_REVIEWER_REQUIRED_ACTION_CODES`가 이 목록을 SoT로 따른다(ADR-021).

| action_code | human_reviewer 값 | distinctness 보장 |
|---|---|---|
| `email_draft_approved` | 승인자(actor) + `original_creator`=작성자 | 마케팅 four-eye 403 보장 / 비마케팅 caveat |
| `email_draft_rejected` | 반려 검토자(actor) + `original_creator`=작성자 | 상동 |
| `email_sent_via_sandbox` | 사전 승인자(`approved_by_id`, sender 아님) | 승인 단계에서 보장 |
| `dispute_case_resolved` | 응답자(`previous_actor_id`) | RESOLVED 전 same-actor 4-eye 블록이 resolver≠responder 보장 |

단일행위자·자동게이트·ADMIN 단독 코드(`consultation_complete`, `suitability_confirmed`,
`explanation_confirmed`, `four_gate_acknowledged`, `marketing_review_approved/rejected`,
`house_view_activated/reviewed`, `kyc_edd_triggered/reassessed`, `conflict_disclosed`,
`info_access_responded`, `credit_info_purge_simulated`)는 distinct reviewer가 없어 이 set에서
**제외**된다(ADR-021 Phase 1 — 과거엔 phantom Bucket C 위반을 유발).

### REG-02 부당권유 (V022)
| action_code | 발생 조건 |
|---|---|
| unfair_solicitation_blocked | 부당권유 패턴 차단 |

### REG-06 거버넌스 / SoD (V022)
| action_code | 발생 조건 |
|---|---|
| demo_mode_toggle_on | system_flags.demo_mode ON (PoC_AUTO_APPROVAL) |
| demo_mode_toggle_off | system_flags.demo_mode OFF 또는 8h 자동 만료 |
| poc_auto_approval_used | PoC_AUTO_APPROVAL 경로 사용 |
| poc_auto_approval_aborted | PoC_AUTO_APPROVAL 중단 (gate 실패 / lag / 레이트) |
| sod_evidence_published | SoD 증적 팩 발행 |

### REG-01/02 적합성 / 적정성 / 설명의무 4-gate (T220, T222, V023)
| action_code | 발생 조건 |
|---|---|
| suitability_confirmed | 적합성 6항목 확인 완료 (금소법 §17) |
| suitability_grade_block | 위험등급 불일치로 추천 차단 (금소법 §17) |
| appropriateness_warning_acknowledged | 적정성 경고 확인 (금소법 §18) |
| explanation_confirmed | 설명의무 체크리스트 확인 완료 (금소법 §19) |
| four_gate_acknowledged | 4-gate 전체 통과 확인 |

### svc-viability-v3 + v4 보안 / 거버넌스 코드 (V071, V074, V076, V077)

각 action_code 는 이 문서 전체에서 **정확히 한 행**으로만 등재한다 (canonical 레지스트리
유일성 — `test_canonical_audit_codes_match_docs` 가 OBS-02 첫 컬럼 집합 == CANONICAL_AUDIT_ACTION_CODES
+ 중복 0 + count 일치를 강제). 한 코드가 여러 emit_source / resource_type / detail_json key 로
emit되면 그 행의 셀 안에 `/` · `+` 로 나열한다 (예: `role_forbidden`, `four_eyes_violation_blocked`,
`same_actor_mutation_blocked`). 행을 코드별로 분리하지 말 것.

| action_code | emit_source(file:LINE) | resource_type | detail_json meta_keys | 발생 조건 |
|---|---|---|---|---|
| four_eyes_violation_blocked | `routers/email.py:421-436` (v3) + `routers/consultations.py:107-130` (v4 I4 preventive) | `email_draft` / `consultation` | `approver_id`; `original_creator_id`(email) / `creator_id`(consultation); +`preventive_path`(consultation) | PB1 이 PB1 작성 이메일 draft self-approve 시도 / PB1 이 PB1 PENDING_APPROVAL consultation 을 COMPLETED 시도 (preventive 4-eye; consultation 은 Input-6 SKIP) |
| same_actor_mutation_blocked | `routers/consultations.py:144-152` (v3 detective) + `routers/kyc_edd.py:reassess+complete` (v4 I1) + `routers/disputes.py:update_dispute_status` (v4 I3) | `consultation` / `kyc_edd_trigger` / `dispute_case` | `original_creator_id`; `previous_actor_id`, `current_actor_id`, `transition_path`/`transition_to` | 동일 actor 가 직전 작성자/reassessor/responder 와 동일 (consultation=audit-only HTTP 200 detective; kyc_edd·disputes=preventive tx-wrapped; EXPIRED out-of-scope F-V5-8) |
| role_forbidden | `routers/kyc_edd.py` 5 sites (v3 B6) + `routers/simulations.py:approve_order_simulation` (P1-b MEDIUM) | `kyc_edd_trigger` / `order_simulation` | `role_code`, `rejected_for`, `endpoint_path` | ADMIN/WM/BRANCH_MANAGER 외 role 의 KYC/EDD 접근 차단; order simulation 승인은 BRANCH_MANAGER 외 role 차단 (supervisory 4-eye) |
| house_view_regenerated_by_admin | `routers/house_views.py:generate_house_view` (v4 I2) | `house_view` | `previous_generated_by_actor_id`, `current_actor_id`, `ai_job_id` | ADMIN_A → ADMIN_B 가 동일 house_view 를 regenerate (ai_jobs SQL lookup OFFSET 1, schema 변경 0) |
| consultation_submitted_for_approval | `routers/consultations.py:158-179` (v4 I4) | `consultation` | `submitted_by_actor_id`, `transition_from` | DRAFT|SAVED → PENDING_APPROVAL 전환 (4-eye gate 진입) |
| ai_compliance_mock_used | `services/marketing/core.py:230+` (v4 I7 singleton) | `ai_compliance_mode_toggle` | `mode`, `pid`, `started_at`, `mode_first_seen_at` | AI_COMPLIANCE_MODE != live 인 process 의 첫 invocation (process 당 1 row, N=10 후속은 0 row — ADR-019.1 cardinality contract) |
| order_simulation_approved | `routers/simulations.py:approve_order_simulation` (P1-b V080) | `order_simulation` | `creator_id`, `approver_id` | 다른 actor 가 PENDING_APPROVAL order simulation 을 승인 (second-person 4-eye, 승인자 ≠ 작성자) |
| house_view_activation_blocked | `routers/house_views.py:217` (/activate) + `:399` (/activate-lifecycle) (ADR-020 F2 V083) | `house_view` | `reason`, `endpoint` | 단일-전역-live-view 불변식(ADR-020 app 가드 또는 V082 인덱스 `idx_house_views_single_live`)이 활성화를 거부 — 활성화는 롤백되고 409 반환, refusal audit row 는 fresh tx 로 append-only 잔존 (reason=single_live_invariant, endpoint=activate|activate-lifecycle) |

### CANONICAL/DB 등재분 — 문서 누락 보완 (emit 상태 코드별 표기)

아래 코드들은 `audit_action_codes`(DB) + `CANONICAL_AUDIT_ACTION_CODES` 에 등재돼 있으나
(drift 게이트 · `require_audit_action` 통과) 본 문서에는 누락돼 있던 것을 일괄 보완 문서화한다.
**emit 상태는 코드별로 다르다** — `demo_mode_*` 2개만 현재 live emit(`services/poc_auto_approval.py`
`write_governance_audit_row`)이고, 나머지 7개는 모듈/상수만 정의돼 미연동이거나 migration 등재만
된 상태(emit 경로 미구현, forthcoming)다. 발생 조건은 `audit_action_codes` 설명 SoT 인용, emit
상태는 2026-05-31 코드 직접 확인.

| action_code | 발생 조건 (emit 상태) |
|---|---|
| ai_output_final_approved | AI 출력(7 agent 중)에 employee_final_approval=true 마킹 — 고객 전달 전 (REG-02 §5 보조수단성). (DB/CANONICAL 등재만, emit 미연동) |
| ai_output_final_approval_revoked | AI 출력 최종 승인 취소. (DB/CANONICAL 등재만, emit 미연동) |
| prohibited_phrase_blocked | AI 출력/발송 이메일이 자본시장법 §55 금지문구(손실보전·이익보장·확정수익 등) 매칭으로 차단. (`services/prohibited_phrase.py` 정의됐으나 라우터/서비스에서 미호출 → 현재 emit 안 됨) |
| gate_evidence_recorded | 게이트 증빙 기록. (DB/CANONICAL 등재만, emit 미연동) |
| poc_auto_approval_rate_limited | PoC 자동 승인 속도 제한 초과. (`poc_auto_approval.py` 상수 `ACTION_RATE_LIMITED` 정의됐으나 audit emit 미호출 → 현재 emit 안 됨) |
| demo_mode_expiring_soon | 데모 모드 만료 임박(5분 전 사전 경고). emit call site: `poc_auto_approval.py` `run_governance_sweep`→`write_governance_audit_row(ACTION_EXPIRING_SOON)`. 단 ① sweep 미연결(production caller 없음) ② demo mode dormant(flag off·활성화 경로 없음) → **runtime 0 rows** |
| demo_mode_expired | 데모 모드 만료. emit call site: `poc_auto_approval.py` `auto_expire_demo_mode_if_due`→`write_governance_audit_row(ACTION_EXPIRED)`. 단 ① sweep 미연결 ② demo mode dormant → **runtime 0 rows** |
| v8_cell_visited | v8 BFS visitor — 상태 셀 방문 로그(90d 보존 후 archive 복제). (DB/CANONICAL 등재만, emit 미연동) |
| v8_unreachable_marked | v8 BFS visitor — 도달 불가 셀 manifest 마킹 로그. (DB/CANONICAL 등재만, emit 미연동) |

## Rules
- 코드에 없는 action_code를 새로 쓰려면 이 문서와 `audit_action_codes` 시드 마이그레이션을 함께 갱신한다.
- 테이블 행의 순서는 `CANONICAL_AUDIT_ACTION_CODES` tuple 순서와 정확히 일치해야 한다.
- audit_logs.detail_json 에는 secret, raw PII, 외부 API token/body 원문을 저장하지 않는다 (OBS-01 redaction 규칙 적용).
- governance_marker 컬럼(V021)은 PoC_AUTO_APPROVAL / HUMAN_REVIEW / AUTO_SYSTEM 중 하나여야 한다.
- audit_logs 는 V008 row-level + V019 statement-level (TRUNCATE) 트리거에 의해 append-only 이다 (ADR-006 참조).
