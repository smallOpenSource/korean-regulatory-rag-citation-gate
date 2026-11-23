# FE-01 Page Inventory

Wave 4 authoritative page inventory for the WMAH PoC frontend.  
Updated: 2026-05-17 (Wave 4 close-out).  
Source of truth: `apps/web/src/App.tsx`, `apps/web/src/lib/access.ts`, `apps/web/src/lib/types.ts`.

---

## Page Inventory

| 화면 | 경로 (SPA) | RouteKey | 허용 역할 | Wave | 설명 |
|---|---|---|---|---|---|
| 로그인 | `/login` | *(public)* | public | W1 | JWT 발급, 메모리 세션 전용 |
| 대시보드 | `/dashboard` | `dashboard` | ALL (5) | W1 | 긴급 후속 조치, 오늘 일정, 최신 하우스뷰 요약, 국내 시장 기준시각/신선도/품질 상태 |
| 고객 목록 | `/customers` | `customers` | PB, WM, BRANCH_MANAGER, ADMIN | W1 | 담당 고객 목록 + 검색, 합성 고객 고지 |
| 고객 360 | `/customers/:customerId` | `customer360` | PB, WM, BRANCH_MANAGER, ADMIN | W1/W4 | 고객 전체 현황, 포트폴리오 평가 출처/품질, Household 탭(W4), AI 브리핑 패널 |
| 상담 워크스페이스 | `/consultations/:consultationId` | `consultation` | PB, WM | W1/W4 | 3-pane 레이아웃(W4): 좌(Customer 360 요약) · 중앙(AI 브리핑+체크리스트) · 우(4-gate 패널+감사 추적), 시뮬레이션 워터마크 |
| 후속 조치 관리함 | `/nba` | `nba` | PB, WM | W1/W4 | 우선순위 NBA 카드(priority/score/why-link/SLA 타이머), WS 실시간 업데이트, 사후관리 큐 위젯(W4) |
| 하우스뷰 목록 | `/house-views` | `houseViews` | ALL (5) | W1 | 전체 하우스뷰 이력 (DRAFT/ACTIVE/SUPERSEDED) |
| 하우스뷰 상세 | `/house-views/:houseViewId` | `houseViews` | ALL (5) | W1/W4 | 상세 내용, 버전 이력 사이드바(W4), AI 메타데이터(generated_at/model/confidence/source)(W4) |
| 운영자 활성화 | `/house-views/:houseViewId/activate` | `houseViewActivation` | ADMIN | W1 | 하우스뷰 DRAFT → ACTIVE 전환, audit log |
| RAG Q&A | `/rag` | `rag` | PB, WM, BRANCH_MANAGER, ADMIN | W1/W4 | 채팅 인터페이스(W4), 프롬프트 인젝션 fail-closed, 인용 링크, fail-closed 사유 코드 |
| 배치 모니터링 | `/batch` | `batch` | ADMIN | W1 | 배치 작업 상태, 공급자 엄격/로컬 모드, 국내 시장 검증 하위 점검, top200 커버리지 |
| 감사 로그 조회 | `/audit` | `audit` | ADMIN, AUDIT_VIEWER | W1/W4 | 감사 로그 필터(action_code/actor_id/기간), CSV 내보내기(W4), 해시 무결성 표시(W4) |
| 검역 대시보드 | `/quarantine` | `quarantine` | ADMIN | W4 | document_chunks quarantine_flag=true 목록, quarantine_pattern_code/score, ADMIN 해제 버튼 |
| 분쟁조정 케이스 | `/disputes` | `disputes` | ADMIN, AUDIT_VIEWER | W4 | 합성 분쟁조정 케이스 목록, 30일 타이머 카운트다운, OPEN→RESPONDED→RESOLVED 파이프라인 |
| 권리고지 | `/rights-notice` | `rightsNotice` | PB, WM | W4 | 상담 완료 후 트리거. 4종 권리(청약철회 7d/9d, 위법계약해지 1y/5y, 자료요구 30d, 분쟁조정 30d) |
| AI 모델 카드 | `/ai-model-cards` | `aiModelCards` | ALL (5), read-only | W4 | 7개 AI 에이전트 모델 카드(목적·학습데이터·성능·리스크·휴먼인더루프), react-markdown 렌더링 |
| AI 정책 | `/ai-policy` | `aiPolicy` | PB, WM, BRANCH_MANAGER, ADMIN | W4 | 조직 AI 사용 정책(직원 교육용), AI-04 Wave 3 Hardening + ADR-005 dual-LLM + LLM07/LLM10 요약 |
| 인공지능기본법 | `/ai-basic-act` | `aiBasicAct` | ALL (5) | W4 | 2026-01 시행 인공지능기본법 대응 체크리스트, AI-06 NIST AI 600-1 매핑 × 7 controls |
| AI 운영현황 | `/ai-admin` | `aiAdmin` | ADMIN | W4 | AI 사용량/실패율/오용 신호/토큰 소비 대시보드, WS `ai_metrics_tick` 30초 폴링(W4) |
| 403 금지 | `/403` | *(public)* | public | W1 | 권한 없는 접근 시 표시 |

---

## Access Rules Summary

| RouteKey | PB | WM | BRANCH_MANAGER | ADMIN | AUDIT_VIEWER |
|---|:---:|:---:|:---:|:---:|:---:|
| dashboard | ✅ | ✅ | ✅ | ✅ | ✅ |
| customers / customer360 | ✅ | ✅ | ✅ | ✅ | ❌ |
| consultation | ✅ | ✅ | ❌ | ❌ | ❌ |
| nba | ✅ | ✅ | ❌ | ❌ | ❌ |
| houseViews | ✅ | ✅ | ✅ | ✅ | ✅ |
| houseViewActivation | ❌ | ❌ | ❌ | ✅ | ❌ |
| rag | ✅ | ✅ | ✅ | ✅ | ❌ |
| batch | ❌ | ❌ | ❌ | ✅ | ❌ |
| audit | ❌ | ❌ | ❌ | ✅ | ✅ |
| quarantine (W4) | ❌ | ❌ | ❌ | ✅ | ❌ |
| disputes (W4) | ❌ | ❌ | ❌ | ✅ | ✅ |
| rightsNotice (W4) | ✅ | ✅ | ❌ | ❌ | ❌ |
| aiModelCards (W4) | ✅ | ✅ | ✅ | ✅ | ✅ |
| aiPolicy (W4) | ✅ | ✅ | ✅ | ✅ | ❌ |
| aiBasicAct (W4) | ✅ | ✅ | ✅ | ✅ | ✅ |
| aiAdmin (W4) | ❌ | ❌ | ❌ | ✅ | ❌ |

---

## Notes

- `RouteKey` values must match `apps/web/src/lib/types.ts` and `apps/web/src/lib/access.ts`.
- Wave 4 routes with `(W4)` are added by workers tango/uniform/victor/victor in tasks #9–#12.
- `AUDIT_VIEWER` is read-only across all pages; all mutation actions are disabled in the UI.
- `BRANCH_MANAGER` sees branch-scoped customers only (타 지점 고객 404).
- `PB`/`WM` see only their assigned customers (`assigned_pb_id = me`).
- WS push channels per ADR-001: `consultation.update` (PB/WM), `nba.card` (PB/WM/branch), `audit.tail` (ADMIN/AUDIT_VIEWER).
