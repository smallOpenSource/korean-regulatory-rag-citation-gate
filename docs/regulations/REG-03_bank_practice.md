# REG-03 한국 은행권 PB/WM 시스템 Best Practice

## 1. 메타데이터
- 작성일: 2026-05-17 (KST)
- Research Lane: L3 외부 리서치 (general-purpose 에이전트)
- Working path: `<repo-root>`
- 적용 범위: WMAH(Wealth Management AI Harness) PoC. 인터넷망 합성 데이터 5 roles(PB/WM/BRANCH_MANAGER/ADMIN/AUDIT_VIEWER) 직원용 시뮬레이션. 본 문서는 직원용 UX/기능 best practice 매핑이며, 고객 채널(모바일·웹뱅킹) best practice는 별도 lane.
- 본 문서의 한계: 국내 시중은행/증권사 PB 서비스는 일반 공개 마케팅 페이지·언론 보도 수준 정보만 사용. 내부 시스템 화면·기능 세부는 영업비밀이므로 글로벌 벤더(Salesforce Financial Services Cloud) 공개 문서와 컨설팅 보고서(McKinsey/BCG 등)의 일반론으로 갭을 메움.
- Companion docs: REG-01(법 영향 매트릭스), REG-02(감독규정), REG-04(AI 거버넌스), REG-05(인터넷망 보안). BIZ-02/UI-01/PRD-04는 읽기 전용 참조.
- Reflect rule: 본 문서 후보 항목 중 PoC scope 합치 항목은 BACKLOG T240~T259로 후보 등록(우선순위·승인은 메인 lane에서).

## 2. 국내 은행권 PB/WM 사례 (공개 자료 일반화, 특정 회사를 식별하지 않도록 유형별로 묶음)

| 유형 | 운영 주체 | 타깃 자산 구간 | 핵심 서비스 라인업 | 직원/시스템 시사점 |
|---|---|---|---|---|
| 은행 PB(다단 등급) | 은행 | 수억 원 이상(일반), 수십억 원 이상(최상위) | 자산관리, 세무, 부동산, 법률 등 전문가 네트워크 통합 | 다영역 전문가 네트워크 호출이 상담 화면에서 한번에 연결되는 워크스페이스 필요 |
| 금융그룹 협업 PB | 같은 그룹의 은행과 증권 | 수억 원 이상 | 은행과 증권 협업 데스크, 글로벌 자산배분 | 이중 라이선스 직원 동시 화면, 회사간 정보교류 차단(Chinese Wall) 표시 필요 |
| 은행 PB(가문 자산 자문) | 은행 | 수억 원 이상 | 가업승계, 상속과 증여 자문 | 가족 관계도(세대간 자산이전) Customer 360 뷰 |
| 은행 PB(본부 지원형) | 은행 | 수억 원 이상 | 영업점 PB 와 본부 전문 조직의 협업 | 본부 전문 조직 백업(이중 상담) 워크플로 |
| 증권 PB(자산배분형) | 증권사 | 수억 원 이상 | 글로벌 자산배분, 연금, 절세상품 | 모델포트폴리오 추천 + 사후관리(rebalancing alert) |
| 증권 PB(종합 자문형) | 증권사 | 수억 원 이상 | 자산관리, 세무, 부동산, 신탁 | 자산관리 보고서 정기 발송 + 컴플라이언스 검토 |

(주: 자산 구간은 특정 회사를 가리키지 않도록 범위로만 적음. PoC 는 합성 페르소나용 참고치로만 사용.)

## 3. UX/기능 Best Practice — Harness 차이 분석

| 영역 | 글로벌/국내 Best Practice | Harness 현재 상태 | 보강 후보 |
|---|---|---|---|
| Customer 360 | 단일 페이지에 보유자산·거래이력·가족관계·세무·이벤트·상담노트·동의·KYC 일괄 표시(Salesforce FSC Person Account + Householding) | 합성 고객 프로필·보유자산·이벤트 모듈 분산. 가족관계/세대간 자산이전 뷰 미정의 | 고객 상세 화면에 Household 탭, 세무이벤트 타임라인, 동의/적합성 평가 만료 배지 |
| 상담 워크스페이스 | 좌측 360, 중앙 상담노트·녹취·요약, 우측 추천·체크리스트·문서 패널 3-pane. 통화 중 실시간 transcript + AI summarization (Glia, NICE, Salesforce Einstein for Service) | 상담 시뮬레이션은 텍스트 기반, 화면 3-pane 명세 부분적. AI 요약 generated_at+model 표기 필수 | 3-pane 표준화 + 상담 종료 시 "권리고지·자료보관·만료갱신" 4-gate 체크 패널 |
| NBA Inbox(Next Best Action) | 이벤트·시그널(만기/배당/시장/생애주기) 기반 액션 카드, 우선순위·예상가치·SLA 표기. 카드는 "근거(why)" 자료 링크 필수(BCG Wealth Wave) | 이벤트→권유 시뮬 일부 구현, 우선순위·근거링크·SLA 미흡 | NBA 카드에 priority/score/why-link/SLA timer, 처리 결과 audit 로깅 |
| 사후관리(Servicing) | 정기 리뷰주기(분기/반기) + 포트폴리오 드리프트 알람 + 자동 리밸런싱 제안 + 고객 보고서 발송 (증권 PB 공개 사례, McKinsey "Future of Wealth") | 사후관리 트리거(분기 통지) 명세 일부, 리포트 자동생성·드리프트 알람 미구현 | 분기 통지 큐, 포트폴리오 드리프트 임계치 시뮬, 리포트 AI 초안+컴플라이언스 게이트 |
| 컴플라이언스 체크리스트 | 적합성·설명의무·녹취·자료보관·광고심의·이해상충·Chinese Wall·KYC/CDD/EDD 항목별 4-eyes 승인 (Deloitte "Digital WM Compliance") | 4-gate(적합성/설명/부당권유/광고) 시뮬 부분 구현. 4-eyes 승인 흐름 정의 부재 | 게이트별 1차/2차 승인자 분리, BRANCH_MANAGER 승인 이벤트 모의, 위반 시 차단+audit |
| KYC/CDD/EDD | 신규 개설·자산변경·고위험거래 트리거 자동, 위험등급 재평가·EDD 사유 기록 (FATF/감독규정) | 합성 KYC 데이터 보유, 재평가 트리거 명세 미흡 | 트리거 룰(자산 변동률·해외송금·정치적노출인) + EDD 사유서 화면 |
| 이해상충 관리 | 직원·고객 거래 사전신고, Chinese Wall 부서간 정보열람 차단, 임직원 자기매매 모니터링 | 5 roles 분리 RBAC 있음, 이해상충 UI 미정의 | 이해상충 사전신고 화면 + audit, Chinese Wall 표시 배너 |
| AI 보조도구 투명성 | AI 생성물 generated_at·model·confidence·source 4-tuple 표기, 인용·할루시 경고 (금융위 생성형AI 지원방안 2025) | 생성물 표기 원칙 채택, UI 일관성 부분 적용 | 모든 AI 카드 공통 메타데이터 컴포넌트 + "AI 보조" 워터마크 |
| 감사 추적 | 모든 권유·동의·승인·문서 발송 이벤트 immutable audit, 10년 보관, 분쟁조정 시 즉시 추출 (금소법 §28) | audit_logs 스키마 정의, 10년 retention 명세 일부 | 감사 뷰어 화면(필터·내보내기) + 분쟁조정 케이스 데모 |
| 모델 거버넌스 | 모델 카드, 라이프사이클, 사전·사후 모니터링, 휴먼인더루프 (EU AI Act, 인공지능기본법 2026-01) | REG-04에 별도 lane, Harness UI 미연계 | 모델 카드 페이지 + 모델 성능 대시보드(시뮬) |

## 4. PoC Harness 보강 후보 (구체적 화면/기능)

1. **Customer 360 / Household 탭**: 본인 + 배우자 + 자녀 + 부모 합성 계정의 자산·이벤트 통합 뷰. 세대간 자산이전(상속·증여) 시뮬 카드.
2. **상담 워크스페이스 3-pane 표준화**: 좌(360)·중앙(노트+AI요약)·우(추천+체크리스트+문서). AI 요약 카드에 generated_at·model 표기.
3. **상담 종료 4-gate 패널**: 적합성·설명의무·부당권유·광고 항목별 체크와 BRANCH_MANAGER 승인 트리거.
4. **NBA Inbox**: 우선순위·예상가치·SLA timer·근거 링크 4요소를 갖춘 카드 리스트, 처리 결과 audit 자동 로깅.
5. **분기 사후관리 큐**: 합성 페르소나별 분기 통지 due-date, 드리프트 임계치 위반 알람, AI 리포트 초안 발송 게이트.
6. **포트폴리오 드리프트 알람 위젯**: 목표 자산배분 대비 ±N% 초과 시 PB 대시보드 상단 배지.
7. **리포트 자동초안 + 컴플라이언스 게이트**: AI가 분기 리포트 초안 생성 → 컴플라이언스 룰(손실보전/단정문구) 자동검토 → 인간 승인 → 발송.
8. **광고심의 게이트**: 이메일/문자 AI 초안에 "광고 성격" 분류 → 정적 룰 + AI compliance_check 이중검토 → audit MARKETING_REVIEW.
9. **이해상충 사전신고 폼**: 직원 거래 사전등록 화면 + Chinese Wall 위반 시 차단 배너.
10. **KYC/EDD 트리거 룰북**: 자산 변동률·해외송금·PEP 룰 → 재평가 task 자동 생성 → 사유서 화면.
11. **권리고지 박스**: 상담 종료 화면에 청약철회·위법계약해지·자료요구권 4종 권리고지 + 발급 audit.
12. **분쟁조정 데모 케이스**: 합성 분쟁 1건을 ADMIN/AUDIT_VIEWER가 자료요구권 응답시한 타이머와 함께 재생.
13. **감사 뷰어 화면**: 필터(role/event/period), 인쇄용 내보내기(시뮬), 위·변조 방지 해시 표시.
14. **AI 모델 카드 페이지**: 모델 목적·학습데이터(합성)·성능·한계·휴먼인더루프 지점 표기.
15. **Autopilot 자율 시연 시나리오**: 신규 고객 온보딩 → 적합성 평가 → 추천 → 상담 → 발송 → 사후관리까지 단일 시나리오를 ADMIN role이 1-click 재생.

## 5. BACKLOG Task 후보 (T240~T259)

| ID | 제목 | 영향 컴포넌트 | 우선순위 후보 |
|---|---|---|---|
| T240 | Customer 360 화면에 Household 탭(가족관계·세대간 자산이전) 추가 | A/C | P2 |
| T241 | 상담 워크스페이스 3-pane 표준화 + AI 요약 카드 메타데이터(generated_at/model) 강제 | A/B | P1 |
| T242 | 상담 종료 4-gate 패널(적합성·설명·부당권유·광고) + BRANCH_MANAGER 승인 시뮬 | A/E | P1 |
| T243 | NBA Inbox 카드(priority/score/why-link/SLA timer) 구현 + audit 자동 로깅 | A/E | P1 |
| T244 | 분기 사후관리 큐 + 합성 페르소나별 due-date | A/D | P2 |
| T245 | 포트폴리오 드리프트 임계치 알람 위젯 | A/C | P2 |
| T246 | AI 분기 리포트 초안 생성 + 컴플라이언스 자동검토 + 인간 승인 게이트 | B/E | P2 |
| T247 | 광고심의 게이트(정적 룰 + AI compliance_check) + audit MARKETING_REVIEW 코드 | B/E | P1 |
| T248 | 이해상충 사전신고 폼 + Chinese Wall 위반 차단 배너 | A/E | P2 |
| T249 | KYC/EDD 트리거 룰북 + 재평가 task 자동 생성 + 사유서 화면 | A/C/E | P1 |
| T250 | 권리고지 박스(청약철회·위법계약해지·자료요구권) + 발급 audit | A/E | P1 |
| T251 | 분쟁조정 데모 케이스 + 자료요구권 응답시한 타이머 | E | P2 |
| T252 | 감사 뷰어 화면(필터·내보내기·해시 표시) | E | P1 |
| T253 | AI 모델 카드 페이지(목적·데이터·성능·휴먼인더루프) | F | P2 |
| T254 | Autopilot 자율 시연 시나리오(온보딩→사후관리 1-click) | All | P1 |
| T255 | AI 생성물 공통 메타데이터 컴포넌트(generated_at/model/confidence/source) | F/UI | P1 |
| T256 | 합성 페르소나 6종(가족 단위) 데이터 시드 추가 | C | P2 |
| T257 | 분기 통지 발송 시뮬(이메일 초안 + 4-gate 통과 후 발송) | B/D | P2 |
| T258 | 4-eyes 승인 흐름 표준화(상담·발송·고위험거래) | A/E | P1 |
| T259 | 인공지능기본법 2026-01 대응 모델 거버넌스 체크리스트 화면 | F/E | P2 |

(우선순위는 후보값. 메인 lane에서 BIZ-02·UI-01·PRD-04 정합성 검토 후 확정.)

## 6. 인용

- 국내 은행·증권사 PB 서비스 공개 페이지 6곳 (검색일 2026-05-17). 공개본에서는 회사명과 URL 을 A~F 가명으로 대체함
- Salesforce Financial Services Cloud — Wealth Management 공식 문서(Person Account, Householding, Action Plans, Einstein Next Best Action): https://help.salesforce.com/s/articleView?id=sf.fsc_overview.htm (검색일 2026-05-17)
- McKinsey "The future of wealth management in Asia" / BCG "Global Wealth Report" / Deloitte "Digital Wealth Management Compliance" 공개 요약 보고서: https://www.mckinsey.com, https://www.bcg.com, https://www2.deloitte.com (검색일 2026-05-17)

(주: 본 문서는 공개 마케팅·문서·보고서만 인용. 내부 시스템 화면은 영업비밀이므로 일반론으로 추론. 실제 운영망 도입 시 각 사 RFP/벤더 데모로 재검증 필요.)
