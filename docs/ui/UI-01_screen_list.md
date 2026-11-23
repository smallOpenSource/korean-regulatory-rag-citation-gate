# UI-01 Screen List

Updated: 2026-05-17 (Wave 4).

| 화면 | 경로 | 허용 역할 | Wave | 설명 |
|---|---|---|---|---|
| 로그인 | /login | public | W1 | JWT 발급, 메모리 세션 전용 |
| 대시보드 | /dashboard | ALL | W1 | 긴급 후속 조치, 오늘 일정, 최신 하우스뷰 요약, 국내 시장 기준시각(source_as_of)/신선도/품질 상태 |
| 고객 목록 | /customers | PB, WM, BRANCH_MANAGER, ADMIN | W1 | 담당 고객 목록 + 검색, 합성 고객 고지 |
| 고객 360 | /customers/:id | PB, WM, BRANCH_MANAGER, ADMIN | W1/W4 | 고객 전체 현황, 합성 고객 고지, 포트폴리오 평가 출처/품질 상태, Household 탭(W4) |
| 상담 워크스페이스 | /consultations/:id | PB, WM | W1/W4 | 3-pane(W4): 좌(360 요약)·중앙(AI 브리핑+체크리스트)·우(4-gate 패널+감사 추적) |
| 후속 조치 관리함 | /nba | PB, WM | W1/W4 | 후속 조치 카드(점수/why-link/SLA 타이머)(W4), WS 실시간 업데이트 |
| 하우스뷰 목록 | /house-views | ALL | W1 | 전체 하우스뷰 이력 |
| 하우스뷰 상세 | /house-views/:id | ALL | W1/W4 | 상세 내용, 버전 이력 사이드바(W4), AI 메타데이터 4-tuple(W4) |
| 운영자 활성화 | /house-views/:id/activate | ADMIN | W1 | 하우스뷰 활성화 |
| RAG Q&A | /rag | PB, WM, BRANCH_MANAGER, ADMIN | W1/W4 | 채팅 인터페이스(W4), 프롬프트 인젝션 fail-closed, 인용 링크 |
| 배치 모니터링 | /batch | ADMIN | W1 | 배치 작업 상태, 공급자 엄격/로컬 모드, 국내 시장 검증 하위 점검 |
| 감사 로그 | /audit | ADMIN, AUDIT_VIEWER | W1/W4 | 감사로그 조회, 필터·CSV 내보내기·해시 표시(W4) |
| 검역 대시보드 | /quarantine | ADMIN | **W4** | document_chunks quarantine 목록, pattern_code/score, 해제 버튼 |
| 분쟁조정 케이스 | /disputes | ADMIN, AUDIT_VIEWER | **W4** | 합성 분쟁조정 케이스, 30일 타이머, OPEN→RESPONDED→RESOLVED |
| 권리고지 | /rights-notice | PB, WM | **W4** | 상담 완료 후 4종 권리고지(청약철회·위법계약해지·자료요구·분쟁조정) |
| AI 모델 카드 | /ai-model-cards | ALL (read-only) | **W4** | 7개 AI 에이전트 모델 카드 |
| AI 정책 | /ai-policy | PB, WM, BRANCH_MANAGER, ADMIN | **W4** | 조직 AI 사용 정책(직원 교육용) |
| 인공지능기본법 | /ai-basic-act | ALL | **W4** | 2026-01 시행 인공지능기본법 대응 거버넌스 체크리스트 |
| AI 운영현황 | /ai-admin | ADMIN | **W4** | AI 사용량/실패율/오용 신호/토큰 소비 대시보드 |
| 403 금지 | /403 | public | W1 | 권한 없는 접근 화면 |

## Wave 4 Component Additions

| 컴포넌트 | 파일 | 설명 |
|---|---|---|
| `<AIMetadataFooter>` | `components/AIMetadataFooter.tsx` | AI 생성 메타데이터 4-tuple 공통 푸터 (generated_at/model/confidence/source) |
| `<HouseholdTab>` | `components/HouseholdTab.tsx` | Customer 360 Household 탭 (가족관계·세대간 자산이전) |
| `<PoCAutoApprovalBadge>` | `components/PoCAutoApprovalBadge.tsx` | PoC AUTO APPROVAL MODE 황색 배너 (ADR-004) |
| `<SyntheticWatermark>` | `components/SyntheticWatermark.tsx` | 합성 데이터 대각선 워터마크 |
| 4-gate 패널 | `pages/ConsultationPage.tsx` (우측 pane) | 적합성·설명의무·부당권유·광고심의 게이트 상태 |
| 후속 조치 카드 리스트 | `pages/NbaPage.tsx` | 우선순위 배지 + SLA 타이머 + why-link + 처리 버튼 |
| 검역 대시보드 | `pages/QuarantineDashboard.tsx` | quarantine_flag document_chunks 관리 |
| 감사 뷰어 | `pages/AuditViewer.tsx` | 필터·내보내기·해시 표시 |
| 권리고지 페이지 | `pages/RightsNotice.tsx` | 4종 권리고지 |
| 분쟁조정 케이스 | `pages/DisputeCase.tsx` | 30일 타이머 분쟁조정 파이프라인 |
| AI 모델 카드 | `pages/AIModelCards.tsx` | 7개 에이전트 모델 카드 |
| AI 정책 | `pages/AIPolicy.tsx` | 조직 AI 정책 |
| 인공지능기본법 | `pages/KoreanAIBasicActPage.tsx` | 거버넌스 체크리스트 |
| AI 운영현황 | `pages/AIAdminDashboard.tsx` | AI 사용량/실패율/오용 신호/토큰 소비 |

## Access Control Rules
- 역할 미충족 라우트 접근 → 403 페이지 표시.
- BRANCH_MANAGER: 소속 지점 고객만 조회 가능 (타 지점 고객 404).
- PB/WM: 배정된 고객(assigned_pb_id = me)만 접근 가능.
- AUDIT_VIEWER: 읽기 전용, 모든 변경 액션 비활성화.
