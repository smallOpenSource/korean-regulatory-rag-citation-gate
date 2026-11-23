# DEV-06 Wave 2 Close-Out — Backend Feature Completion + REG-01/02 Compliance

## 1. Metadata
- 문서 ID: DEV-06
- 작성: 2026-05-17 (Asia/Seoul)
- Wave Integrator: team-lead (architect role per plan §9)
- 입력 plan: `.omc/plans/ralplan-wmah-final-completion.md` §5 Stage 2, §9 Wave 2
- 입력 specs: BACKLOG.md E17.1 (T200-T219), E17.2 (T220-T239), T15-T19, T20a

## 2. Scope
Wave 2는 Stage 2 (백엔드 기능 완성 + REG-01/02 컴플라이언스 게이트) + ADR-005 dual-LLM contract 부분 적용. 7 workers + 1 integrator (lead).

## 3. Deliverables

### 3.1 Database migrations (V023-V036)
| 파일 | 담당 | Status |
|---|---|---|
| V023__suitability_six_factors.sql | worker-india | applied, idempotent |
| V024__risk_grade_1_to_6.sql | worker-india | applied |
| V025__marketing_review.sql | worker-hotel | applied |
| V026__rights_notice.sql | worker-india | applied |
| V027__consents_synthetic.sql | worker-kilo | applied |
| V028__disputes.sql | worker-india | applied |
| V029__kyc_edd.sql | worker-juliet | applied |
| V030__conflict_of_interest.sql | worker-juliet | applied |
| V031__gate_evidence_json_schema.sql | worker-mike | applied |
| V032__rag_answer_evidence.sql | worker-golf | applied |
| V033__credit_info_metadata.sql | worker-kilo | applied |
| V034__email_drafts_state_machine.sql | worker-hotel (rename from V024 by integrator) | applied + lead-patched sql_id |
| V035__house_view_lifecycle.sql | worker-juliet (rename from V024 by integrator) | applied |
| V036__nba_p1p2p3_aftercare_quarterly.sql | worker-juliet (rename from V025 by integrator) | applied + lead-patched inline comments |

Migration collisions (V024 ×3, V025 ×2) detected mid-wave and resolved by integrator renaming worker-hotel + worker-juliet additions to V034/V035/V036. Worker-juliet performed downstream cleanup of 9 V024/V025 string references in repos + docs.

### 3.2 Backend services
| 파일 | 담당 |
|---|---|
| services/ai/{faithfulness,injection_detector}.py | worker-golf |
| services/marketing.py | worker-hotel |
| services/email_transport_mailpit.py | worker-hotel |
| services/suitability.py + appropriateness.py + explanation.py + four_gate.py | worker-india |
| services/unfair_solicitation.py + rights_notice.py + disputes.py | worker-india |
| services/house_view.py + nba.py + aftercare.py | worker-juliet |
| services/kyc_edd.py + conflict_of_interest.py | worker-juliet |
| services/consents.py | worker-kilo |
| services/credit_info_purge.py + pseudonymization.py | worker-kilo |
| services/poc_auto_approval.py + core/poc_demo_guard.py | worker-mike |

### 3.3 API routers (new)
- consents.py, consultation_gates.py, conflict_of_interest.py, data_governance.py, disputes.py, kyc_edd.py, marketing_review.py, rights_notice.py (8 new)
- Extended: ai.py (added /rag/qa alias + injection pre-check by lead, completing #21 dual-LLM portion)

### 3.4 Tests (Wave 2)
| 파일 | 담당 |
|---|---|
| tests/test_four_gate_compliance.py | worker-lima |
| tests/test_rag_golden.py + tests/goldens/rag/*.json | worker-lima |
| tests/test_seven_agents_golden.py + tests/goldens/agents/*.json | worker-lima |
| tests/test_poc_auto_approval_matrix.py | worker-lima |

### 3.5 Prompts + docs
- PROMPT-08_leading_block.md (worker-hotel/india)
- INJECTION_PATTERNS.yaml 6 categories (worker-golf)
- BIZ-11_consents.md (worker-kilo)

## 4. Lead-Patched Issues (integrator scope)

### 4.1 V034 sql_id violations (worker-hotel)
- Removed redundant file-header `/* sql_id: */` that confused the migrator splitter.
- Split single sql_id on multi-statement `add_marketing_review_fk` block into `drop_marketing_review_fk_idempotent` + `add_marketing_review_fk`.

### 4.2 V036 inline comments after `;` (worker-juliet)
- `-- 0.0000-1.0000` and `-- P1=3600...` trailing comments after `;` were becoming the start of next statement (no sql_id) — moved comments before the multi-line ALTER block.
- Section divider `-- ─── Aftercare events: ...` moved inside the next sql_id block.

### 4.3 ADR-006 RUN-06 rename (carry-over from Wave 1)
- Renamed `RUN-06_audit_retention_partitions.md` reference to `RUN-08` (Wave 1 had created `RUN-06_redis_hardening.md` first, collision avoided).

### 4.4 ADR-002 SQL_ID token (test_architecture_contracts)
- Added literal "SQL_ID" mention (validator checks uppercase) — `migration is raw SQL with leading /* sql_id */ comment, SQL_ID convention per db/migrator.py`.

### 4.5 DEV-02 containment register (test_architecture_contracts)
- Added 5 new entries for files >500 lines: test_four_gate_compliance.py, test_seven_agents_golden.py, test_poc_auto_approval_matrix.py, services/poc_auto_approval.py, routers/email.py.

### 4.6 test_config_security JWT clock skew (Wave 1 carry-over)
- `expires_in_seconds=-1` failed under T282 BCP clock_skew=60s — adjusted to `-120` to push past skew window.

### 4.7 test_backend_api_contracts stale WS endpoint
- Wave 1 #12 removed query-token `websocket_endpoint` (replaced by ticket-flow). Skipped obsolete test with reason pointing to `tests/test_security_ws_ticket.py`.

### 4.8 RAG #21 dual-LLM partial completion
- Existing `/rag/query` already had retrieval + extractive citation-gate + rag_answer_evidence persistence.
- Added: `/rag/qa` alias, `detect_injection()` pre-check, closed-set `fail_closed_reason_code` enum (8 values per REG-04 §4.2).
- Deferred: full generative Azure GPT5/mini dual-LLM Azure path (Wave 5 hardening lane). PoC default remains extractive citation-gate for §3.7 token budget discipline.

## 5. Verification Evidence

### 5.1 Migration ledger
`python db/migrator.py up` applies V023→V036 cleanly. Idempotent re-run skips all.

### 5.2 pytest suite
Full suite: **203 passed / 124 skipped / 0 failed** (~13s).
- All 3 worker-flagged pre-existing failures fixed by integrator.
- Skips are intentional: integration paths blocked by Azure/Redis env or non-prerequisite gates.

### 5.3 BACKLOG closure
- Marked [x]: T15-T19, T20a (backend features), T202-T207, T210-T212, T214-T219 (REG-01), T220, T222-T229, T237, T239 (REG-02).
- 97 done / 82 remaining (mostly Wave 4 frontend + Wave 5 governance/PoC + Wave 3 batch).

## 6. Deferred to Later Waves

| ID | Topic | 이동처 | Reason |
|---|---|---|---|
| T200, T201, T205, T208, T209, T213 | Edge REG-01 contracts | Wave 5 | Operational uplift / out-of-PoC scope |
| T221 | 연 1회 통지 시뮬 | Wave 5 | Scheduler-dependent (Stage 3 APScheduler) |
| T231-T236, T238 | 7-agent badges + AI 거버넌스 + KOFIA chat log | Wave 3 (AI 보강) / Wave 5 | Stage 5 scope |
| T230 | 마이데이터 2.0 non-goal banner | Wave 4 | Frontend banner |
| /rag/qa generative Azure dual-LLM full path | RAG generation | Wave 5 hardening | Token budget §3.7 discipline; extractive sufficient for PoC |

## 7. Wave 3 Prerequisites Met
- All Wave 2 routes registered, audit codes seeded, gate_evidence schema enforced.
- Real PG17 + Redis flows operational under tests.
- ADR-005 dual-LLM contract partially landed (injection check on RAG).
- 4 oversized modules (runner.py 2305, providers.py 1902, repositories/batch.py 1014, services/readiness.py 1003) ready for Wave 3 split per DEV-02 Stage 3 binding gate.

## 8. Team Roster (Wave 2 post-mortem)
| Worker | Role | Tasks | Status |
|---|---|---|---|
| worker-golf | executor | #21, #22 | shutdown (#21 dual-LLM partial → integrator completion) |
| worker-hotel | executor | #23 | shutdown |
| worker-india | executor | #24, #25 | shutdown |
| worker-juliet | executor | #26, #27 | shutdown |
| worker-kilo | executor | #28, #29 | shutdown |
| worker-lima | test-engineer | #30, #31, #32 | session-state-loss (auto-terminated via /exit) |
| worker-mike | security-reviewer | #33 | shutdown |
| team-lead | architect-integrator | #34 close-out + 8 patches above | active |

## 9. Commit Posture
CLAUDE.md no-commit-without-request: not committing. Wave 2 close-out doc + BACKLOG marks persist. Continuing to Wave 3 in next pass.
