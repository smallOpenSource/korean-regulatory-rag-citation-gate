# DEV-11 P2 Close-Out — 실데이터/베이스라인 위생 (silent-synthetic 제거 + faithfulness 정합)

## 1. Metadata
- 문서 ID: DEV-11
- 작성: 2026-05-31 (Asia/Seoul)
- Cycle: P2 (실데이터/베이스라인 위생) — svc-viability 스레드 후속, P0(AI 출력 품질)·P1(HITL UI / native dispatch / marketing window) 다음 단계
- 범위 도출: `p2-scope-derivation` Workflow (5차원 코드증거 매핑 → 10 item 인벤토리, file:LINE 근거) + 사용자 확정 "Tier-1+2+3 전량 + P2-8/P2-9 포함"
- 적대적 리뷰: Tier-1 3-렌즈 Workflow `wf_00c78765` (보안 GO / 정확성·완결성 NO_GO → 21 findings 전건 종결)
- HEAD: `2cd39bc` (main, 완전 push) · migration_versions: 81

## 2. Scope
합성-only PoC가 PB/WM 직원에게 데이터를 노출할 때 **silent-synthetic**(합성·미검증 AI 텍스트/수치가 데이터품질 고지 없이 검증된 사실처럼 노출)을 제거하고, faithfulness 신호를 모든 노출 경로에 일관 적용한다. 충족해야 하는 계약(재도출):
1. 합성·미검증 수치(SYNTHETIC_HOLDING_VALUE / freshness=MISSING / quality=UNVERIFIED / valuation BLOCKED)는 노출 경로마다 freshness·quality·provenance 정직 표기.
2. AI 생성 텍스트(NBA script / house_view 본문 / RAG answer)는 *그것을 노출하는 모든 surface*에서 `data_quality_notice` + faithfulness 동반.
3. 실데이터 미연동 영역은 silent-synthetic이 아니라 fail-closed(BLOCKED) 또는 UNVERIFIED로 정합.

## 3. Deliverables

### 3.1 Database migration
| 파일 | 내용 | Status |
|---|---|---|
| V081__house_view_faithfulness.sql | `house_views.faithfulness_json` (additive nullable JSONB) | applied, migration_versions=81 |

### 3.2 항목별 (10 item)
| ID | Tier | 항목 | 핵심 변경 |
|----|------|------|----------|
| P2-1 | 1 | NBA list silent-synthetic | `script_text` 노출 7경로에 `script_disclosure`(`SYNTHETIC_ADVISORY_NOTICE`) 부착 + `NbaPage` amber 렌더 |
| P2-2 | 1 | RAG QA 무-신호 | `POST /rag/qa` READY·BLOCKED 4 return에 `data_quality_notice` + 결정성 faithfulness (`_rag_quality_fields`) |
| P2-3 | 1 | house_view 무-품질스킴 | V081 `faithfulness_json` 영속 + 생성 시 `assess_faithfulness` + `attach_house_view_quality`(services 공유) 7경로 + `HouseViewDetailPage` 렌더 + fail-closed 마커 |
| P2-4 | 2 | briefing/nba provenance 비대칭 | `synthetic_portfolio_provenance`(공유, disclosure-only projection) → 2 dispatcher output_json+model_input+dry_run |
| P2-5 | 2 | nba faithfulness gate 불일치 | `require_disclosure=True` + notice를 assessed text에만 append(고객대면 script_text 본문 불변) |
| P2-6 | 2 | Dashboard 하우스뷰 신호 누락 | dashboard latest_house_view에 공유 헬퍼 + repo SQL `faithfulness_json` + `DashboardPage` 렌더 |
| P2-7 | 2 | simulation provenance 미표기 | `_attach_sim_provenance`를 recommendation/order sim create·execute·approve 전 return에 |
| P2-8 | 2 | customers/products list 고지 누락 | `GET /customers`·`/products` top-level `synthetic_customer_notice` (detail은 기존 정합, list 누락이었음) |
| P2-9 | 3 | email/compliance 무-고지 | `email_draft`·`compliance_check` 출력에 `data_quality_notice` (관찰성) |
| P2-10 | 3 | 비-RAG faithfulness baseline 부재 | `scripts/wave_g_nonrag_faithfulness_baseline.py`(결정성 recompute + per-dispatcher 집계 + no-silent-cap) + `scripts/wave_g_nonrag_generate_traces.py`(live Azure generate-run 드라이버) — **N≥50 실측 충족(§8)** |

### 3.3 Follow-up (적대적 리뷰·검증 중 표면화)
| | 항목 | 변경 |
|---|------|------|
| F1 (`cc2cec6`) | ACTIVE/ACTIVATED 읽기 불일치 | dashboard·get_active를 `IN ('ACTIVE','ACTIVATED')`로 broaden (T16 lifecycle terminal ACTIVATED 인식) — 기존 ARCHIVE_ACTIVE_TUPLE/프론트 canArchive precedent와 정합 |
| F2 (`2cd39bc`) | 읽기 경로 픽스처 미제외 | LIST 픽스처-제외를 공유 상수 `NON_FIXTURE_HOUSE_VIEW_PREDICATE`로 추출 → LIST + GET_ACTIVE + dashboard 일관 적용 (QA probe가 banker dashboard에 노출되던 문제 해소) |

### 3.4 신규 공유 자산 / 문서
- 헬퍼: `attach_house_view_quality` (services/house_view.py), `synthetic_portfolio_provenance` (services/readiness/core.py), `NON_FIXTURE_HOUSE_VIEW_PREDICATE` (repositories/house_views.py), 라우터 로컬 `_attach_script_disclosure`/`_rag_quality_fields`/`_attach_sim_provenance`. **신규 상수 0** — 전부 기존 `SYNTHETIC_ADVISORY_NOTICE`/`build_portfolio_valuation_payload`/`assess_faithfulness` 재사용.
- Doc Sync: DB-02 house_views 컬럼(leading_block_json/faithfulness_json) + API-01 응답 스키마(data_quality_notice/script_disclosure/faithfulness + 공유 `Faithfulness` 컴포넌트).

### 3.5 Tests (신규 6 파일)
| 파일 | 대상 |
|---|---|
| tests/test_nba_script_disclosure.py | P2-1 |
| tests/test_rag_qa_quality_fields.py | P2-2 |
| tests/test_house_view_quality.py | P2-3 |
| tests/test_dispatcher_data_provenance.py | P2-4 / P2-5 |
| tests/test_simulation_provenance.py | P2-7 |
| tests/test_house_view_active_status_unification.py | F1 / F2 (DB-rollback) |

## 4. Verification
- **정적**: 변경 단위마다 ruff F,I,UP,B clean. SIM117·E501은 pre-existing만(HEAD==now 대조로 순증 0). 프론트 tsc exit 0.
- **단위(hermetic)**: P2 신규 18 + follow-up 회귀 + 기존 dispatcher/service 회귀(briefing/nba 15, email/compliance 8, house_view suite 12) green. (1건 transient PG drop은 단독 2× green 재확인 = 회귀 아님.)
- **라이브 스모크**: Tier-1 ALL_PASS + faithfulness round-trip / P2-7·8 ALL_PASS / dashboard 주입+복원 + 실 leftover 픽스처 제외(None) + genuine ACTIVATED positive-assert / house-view review 200.
- **적대적 리뷰**: Tier-1 3-렌즈(`wf_00c78765`) 21 findings 전건 종결.
- **브라우저 증거**: 3 surface(HouseViewDetail / NbaPage / Dashboard) amber 데이터품질고지(+faithfulness 배지) 렌더 스크린샷 + DOM 단정.

## 5. 방법론 (lessons)
1. **동일 엔티티 다중 read/transition 경로 → SQL 컬럼 + 직렬화 헬퍼 정합 필수.** house_view는 ai_outputs row가 없어 faithfulness를 전용 컬럼(V081)에 영속·정적 notice는 API 직렬화 시 부착. 1차 구현이 GET/generate/LIST만 덮어 4 엔드포인트·4 SQL 우회가 잔존 → 적대적 리뷰가 표면화.
2. **고객대면 텍스트(script/RAG answer)엔 disclosure를 본문이 아닌 별도 필드/assessed-text에만** — 본문 오염 금지.
3. **합성 customer-data dispatcher는 holding total 없는 disclosure-only provenance projection이 정확** (build_portfolio_valuation_payload total은 holding 전용, total_assets_krw와 혼동 방지).
4. **baseline은 thin sample을 명시 로깅**해 full baseline 오인 방지(no silent cap).
5. asyncpg `$N::timestamptz`엔 datetime 객체 필요(str→DataError); house_views.version_no 전역 UNIQUE(MAX+1).

## 6. Unverified / 잔여
- **P2-10 N≥50 baseline**: ✅ 실측 충족(§8, 2026-05-31). 잔여 한계 — `ungrounded_figures`는 substring matcher라 카운트가 **floor**(파생/환산 수치의 숫자열이 grounding 부분문자열과 우연히 겹치면 미flag = false-negative ceiling, JSON `ungrounded_figures_caveat`에 명시). portfolio_analysis 27/50 ungrounded는 하한이며 실제 미근거 수치 비율은 그 이상일 수 있음.
- **house_view activate/activate-lifecycle**: ✅ HTTP 개별 스모크 완료(§9-d, 13/13, reversible).
- **P2-9 live output_json**: ✅ live 스모크 완료(§9-c, 7/7). ✅ compliance-check HTTP 응답 notice 노출 gap 종결(§10, commit `ecdedf0`) — 더 이상 영속 output_json 전용 아님.
- **잔존 ACTIVE QA probe 1건**: test_house_view_activation이 commit하는 픽스처 — F2로 readers에서 inert화(무시)되므로 미정리.
- **레거시 `/activate` write-path supersede 비대칭**: ✅ 수렴 완료(§9-b). 잔여 설계 caveat: legacy(global) vs T16 lifecycle(per-tuple)은 상호배타 운영 모드 — 다중 segment live view를 노출하면 legacy global supersede 재검토 필요(현재 reader가 global-single-row라 inert; 적대적 리뷰 MEDIUM 비차단).

## 7. Commit chain (main, 완전 push)
`bc2208d` (Tier-1 + P2-6) → `23e0b44` (P2-4/5) → `4181877` (P2-7/8) → `51529ef` (P2-9) → `3c4feff` (P2-10) → `cc2cec6` (F1 ACTIVE/ACTIVATED) → `2cd39bc` (F2 픽스처 제외) → `bab0345` (본 close-out) → `3044638` (P2-10 N≥50 실측) → `481301b` (후보 (b) 수렴 + (c)(d) 스모크) → `ecdedf0` (compliance-check HTTP 응답 notice 노출, §10)

## 8. P2-10 baseline 실 N≥50 충족 (2026-05-31, post-closure follow-up)
- **원인 규명**: dry_run 픽스처(`_DRY_RUN_*`)는 `_model_input`를 영속하지 않고 **live(Azure) 경로만** 영속(portfolio_analysis.py:307 / nba_script.py:252 / consultation_briefing.py:352). baseline은 `output_json._model_input`가 dict인 행만 채점하므로 dry_run 출력은 전부 `skipped_no_model_input` → 실 baseline은 실 생성이 유일 경로(dry_run으로는 불가).
- **생성**: `wave_g_nonrag_generate_traces.py`로 디스패처당 55회 live Azure(gpt-5.5) 생성(3×55 = 165 generation, briefing은 dual-LLM이라 ~220 LLM 콜, **0 fail**). FK(`ai_outputs.job_id`→`ai_jobs.id`) 때문에 ai_jobs 행 선삽입(RUNNING)+트랜잭션+SUCCEEDED 마킹(워커 lifecycle 준용). 합성-only 자원(customers 23·nba_actions 53·consultations 1230 cycle), PII는 디스패처가 코드+UUID ref로 차단. 풀 사전워밍 + Patroni transient backoff([[pg-patroni-transient-drop]]) — 단일 timeout/`DatabaseUnavailableError`에 재시도.
- **결과**(`--n 50`; `audit-out/stage-3/llm/nonrag-faithfulness-baseline.json`, gitignored): portfolio_analysis scored50/passed23/ungrounded27 · consultation_briefing 50/48/2 · nba_script 50/50/0 · **전부 skipped0 · meets_target_n true**.
- **실 신호**: portfolio_analysis 27/50(54%)가 ungrounded-figure flag — 실 gpt-5.5가 파생합('100%')·환산('37.5억') 등 grounding에 없는 수치를 빈번 생성. nba_script(qualitative talking-points)는 0/50, briefing 2/50. all-green이 아닌 실측 baseline.
- **적대적 3-lens 검증**(`wf_978ad63d`, GO / 0-refuted): (1) genuineness 0.97 — 150행 전부 gpt-5.5·`_model_input` dict·0 dry-run·양(+)의 token 회계·fresh(23:21-23:38Z), 과거 sweep에도 dry-run 0이라 cherry-pick 불가. (2) accounting 0.9 — 독립 recount가 JSON 정확 재현 + flagged 3건 true-positive(100%/20.5억/37.5억/80% = 파생·환산, grounding 부재) + 게이트는 오히려 lenient(과소flag, false-positive 생성 불가). (3) honesty — `--n 105` 스트레스로 skipped 카운트·thin-sample 경고 정상 동작 입증, portfolio↔nba asymmetry는 실 콘텐츠 차이(정량 prose vs 정성 prose).
- **잔여 한계**(§6): `ungrounded_figures` substring matcher → 카운트는 floor(JSON `ungrounded_figures_caveat` 명시). baseline은 LATEST 50행 윈도우 기준(과거 `_model_input` 부재 행은 윈도우 밖).

## 9. 후보 follow-up (b)/(c)/(d) (2026-05-31, post-closure — 사용자 "후보군 모두 진행")

### 9-b. 레거시 /activate → ACTIVATED 수렴 (코드 변경)
- `SUPERSEDE_ACTIVE_HOUSE_VIEWS_SQL` WHERE `status_code = 'ACTIVE'` → `IN ('ACTIVE','ACTIVATED')` (repositories/house_views.py). 단일 caller `activate_house_view`(legacy ADMIN-only `POST /house-views/{id}/activate`). legacy는 단일 전역 ACTIVE 단언(idx_house_views_one_active)이므로 기존 'ACTIVATED' 잔존이 reader(`IN ('ACTIVE','ACTIVATED')`)에 2 live row로 노출되던 비대칭 해소 — lifecycle `ARCHIVE_ACTIVE_TUPLE`(양방향 정리)과 directional-completeness 일치.
- 검증: 단위 회귀 `test_legacy_activate_supersedes_activated`(DB-rollback, 3 passed) + live (d) 스모크가 legacy activate의 ACTIVATED→SUPERSEDED 실측 + 19 house_view 테스트 회귀0(1 transient PG drop 단독 2× green) + ruff F,I,UP,B,SIM clean·E501-neutral + 적대적 리뷰 GO/0-blocking. backend 재기동(`run_backend.sh`).
- 설계 caveat(적대적 리뷰 MEDIUM, 비차단): legacy(global supersede) vs T16 lifecycle(per-tuple ACTIVATED)는 상호배타 운영 모드. 현재 readers(get_active/dashboard)가 global-single-row(LIMIT 1)라 다중 segment live view 미노출 → inert. 향후 per-tuple live view를 노출하면 legacy global supersede 재검토 필요.

### 9-c. P2-9 live output_json 스모크 (7/7 PASS)
- compliance_check: live `POST /consultations/{id}/compliance-check`(PB1, Azure 1콜) → 영속 `ai_outputs.output_json.data_quality_notice` 실측. **관찰(당시)**: HTTP 응답은 `{passed,issues,recommendation}`만 — notice는 영속 output_json 전용(P2-9 Tier-3 관찰성 scope상 by-design; 응답 노출은 별개 gap). → **종결**: 이 별개 gap은 §10(commit `ecdedf0`)에서 HTTP 응답에 notice를 무조건 투영하도록 닫음.
- email_draft: 동기 엔드포인트 없음 → 워커 디스패처 `run_email_draft` 직접 실행(dual-LLM, Azure 2콜) tx 내 → 영속 output_json.data_quality_notice 실측 → rollback(email_drafts/ai_outputs 무변이).

### 9-d. house_view activate HTTP 개별 스모크 (13/13 PASS, reversible)
- activate-lifecycle(REVIEWED 4490ef76→ACTIVATED): 응답 status ACTIVATED + data_quality_notice + faithfulness(주입값) + raw faithfulness_json 미이중노출 + audit `house_view_activated`. (4490ef76는 faithfulness_json NULL이라 대표 dict 임시 주입 후 복원.)
- legacy activate(fresh DRAFT→ACTIVE): 응답 status ACTIVE + data_quality_notice 정당 부재(ai_generated_at NULL gate) + audit `house_view_activate`; + (b) live 증명(legacy가 직전 ACTIVATED 4490ef76→SUPERSEDED).
- reversible: snapshot→faithfulness 주입→활성화→전부 복원(4490ef76→REVIEWED/faith NULL, 061776be→ACTIVE, 스모크 DRAFT→SUPERSEDED). @idempotent POST는 Idempotency-Key(UUID) 헤더 필수(누락 409). audit_logs 행은 append-only로 잔존(증거).
- Azure 비용: (d)=0(DB 전이만), (c)=~3콜(compliance 1 + email_draft 2). 합산 ~$0.005(레포 metering rate).

## 10. compliance-check HTTP 응답 notice 노출 (2026-05-31, commit `ecdedf0`)
§9-c에서 관찰한 "별개 gap"(compliance-check 동기 HTTP 응답이 `{passed,issues,recommendation}`만 주고 `data_quality_notice`는 영속 `ai_outputs.output_json` 전용) 종결. P2 silent-synthetic 제거 원칙(노출면 전반 데이터품질 신호 일관성) 완성.
- **설계 = 항상-존재(Option B)**: 성공 경로 반환 dict는 이미 최상위 `data_quality_notice`를 보유(`services/compliance_check.py:184`). fail-closed 경로 `_fail_closed()`(:77)에 동일 키 추가 → run_compliance_check의 **모든 return이 키를 담음**. 라우터 `consultations.py`가 `result["data_quality_notice"]`를 **무조건 투영**(bracket access 안전). 거부 대안 A(조건부 `.get()` 투영)는 fail-closed 시 `notice: null` nullable 계약이라 기각.
- **영속 불변**: fail-closed 영속 `_output_payload`는 canonical `ai_unavailable_payload` shape 유지 — notice 미주입(테스트 `assert 'data_quality_notice' not in payload`로 lock). notice는 HTTP-계약 top-level 키 전용.
- **선례 정합**: `api/routers/simulations.py:48-55` `_attach_sim_provenance`(four-gate 동일 도메인)의 라우터-레벨 무조건-부착과 동일 패턴.
- **단일 호출처**: `consultations.py:345`(동명 `quarterly_report.py:68`은 별개 함수). 프론트 직접 fetch 없음(서버측 4-gate 통제면).
- **검증**: ruff F,I,UP,B,SIM,E501 clean(소스 HEAD==now delta 0) / `pytest tests/test_service_compliance_check.py` 5 passed(신규 성공 경로 monkeypatch 테스트 + fail-closed positive assert: top-level 존재 + `_output_payload` 부재) / live HTTP 스모크 5/5(실 Azure 성공 `passed=False` 응답에 notice 실림, backend 재기동 PID 2508025) / `test_backend_api_contracts.py` 19 passed / 3-lens 적대적 리뷰 `wf_89868923` **GO**(0-refuted, 0-blocker).
- **잔여 nit(미차단)**: HTTP-레벨 pytest 부재(라우터 투영은 live 스모크 e2e + 서비스 테스트 전-경로 키 보장으로 transitive lock) / 신규 테스트 DB outage 시 error(파일 기존 컨벤션).
