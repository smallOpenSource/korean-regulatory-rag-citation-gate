# REG-02 Supervisor Rules — 금융위/금융감독원 감독규정·시행세칙·해설서 PoC Harness 영향

## 1. 메타데이터
- Research Lane: L2 (외부 리서치 P1 lane)
- Working path: `<repo-root>`
- Generated: 2026-05-17 (Asia/Seoul)
- Researcher: general-purpose agent (a9c6c89353340ebd9)
- Source-of-truth scope (deep-interview Round 2 + Round 8): 자본시장법 §46/§47 + 금융소비자보호법 + 신용정보법 + 금감원/금융위 규정·시행세칙·해설
- Companion lane: REG-01 (법 조항별 영향 매트릭스, L1) — 본 문서는 그 하위 감독규정·해설·자율규제 layer
- Reflect rule (Round 8): 발견된 영향 사항은 BACKLOG/ralplan/구현에 전수 반영
- 검색일: 2026-05-17 (KST)
- 검색 채널: fsc.go.kr, law.go.kr, easylaw.go.kr, eiec.kdi.re.kr, law.kofia.or.kr, kimchang.com 보도자료/해설

## 2. 규정/시행세칙 표

| 규정명 | 발령기관 | 핵심 내용 | 2024–2026 개정사항 |
|---|---|---|---|
| 금융투자업규정 | 금융위 (고시) | 적합성·설명의무 운영 세칙, 위험등급 분류, 투자권유 기록보존, 외화증권 매매 절차 | 2024-50호(2024-11-12 시행): 투자일임·신탁계약 투자성향 분석주기 연 4회→연 1회로 완화, 분기 통지 의무 신설; 외화예탁금 별도예치 확대 |
| 금융투자업규정 시행세칙 | 금감원 | 위험등급 산정, 적합성·설명의무 화면·기록 세부, 표준양식 | 2024–2025 누적 개정 (적합성평가 6개 필수확인 정보 명확화, 핵심설명서 상단 위험 우선 기재) |
| 금융소비자 보호에 관한 감독규정 | 금융위 (고시) | 6대 판매행위 규제 세부 기준(적합성·적정성·설명의무·불공정영업·부당권유·광고규제), 청약철회권·위법계약해지권·자료요구권 절차 | 2025-07-15~2025-08-25 규정변경예고(고난도 금투상품 불완전판매 예방 종합대책 후속); 핵심설명서 최상단에 부적합 소비자유형·손실가능성·손실사례 우선기재 의무화; 부당권유 신설(특정 답변 유도, 대면→비대면 권유, 회사 대리가입) |
| 신용정보업감독규정 | 금융위 (고시) | 동의 양식, 처리방침, 정보주체 권리행사, 마이데이터 안전성 | 2025-2호(2025-02-05 의결): 만 14세+ 청소년 마이데이터 단독 이용; 1차 목록+2차 상세 2단계 전송요구→일원화; 정보 수집·이용·제공 동의 일괄; 마이데이터 제3자 제공 시 침해사고대응기관 전송시스템 의무; 대면점포 마이데이터 허용 + 내부관리규정 |
| 금융투자상품 투자권유 시행세칙 | 금감원 | 투자권유 절차, 적합성 확인, 위험등급-투자성향 매칭 | 고난도상품 위험등급 2등급 이상 부여 권고 유지 |
| 금융분야 AI 가이드라인 (통합 개정안) | 금융위 | AI 7대 원칙(거버넌스/합법성/보조수단성/신뢰성/금융안정성/신의성실/보안성), 학습데이터 정확성·안전성, 투명성·공정성, 소비자 권리 | 2026-1분기 시행 예정(현재 개정 진행); 인공지능기본법(2025-01 제정, 2026-01 시행) 하위법규 반영; 비금융회사(핀테크), 내부업무 지원도 적용 권고 |
| 금융권 생성형 AI 활용 지원방안 | 금융위 | 생성형 AI 인용/할루시네이션/프롬프트 인젝션/감사 권고 | 2025년 발표(보도자료 83594), 통합 가이드라인 흡수 예정 |
| 투자성 상품 위험등급 산정 가이드라인 | 금융위 | 1~6등급 체계, 시장위험+신용위험 기반, 환율위험 1–2등급 가산, 유동성위험 별도 기재, 고난도상품 2등급 이상 | 2023-01 시행, 2024–2025 운영 안정화 |
| 금융상품 설명의무 합리적 이행 가이드라인 + 온라인 설명의무 가이드라인 | 금융위/협회 | 일반인 기준 평이 작성, 그림/그래프 활용, 자체 설명서 작성기준, 온라인 화면 설명 기준 | 협회 중심 상시보완 체계 운영 |
| KOFIA 표준투자권유준칙 | 한국금융투자협회 (자율규제) | 적합성 확인서 양식, 투자권유 절차, 디지털·로보어드바이저 권유 |  2024–2025 누적 개정; 비대면 권유 시 본인확인·녹취·보관 강화 |
| KOFIA 금융투자회사 영업·업무규정 시행세칙 | 한국금융투자협회 | 광고심의(협회 사전심의), 컴플라이언스 매뉴얼 | 2025-05-30, 2025-06-20 등 연내 다회 개정 |

## 3. PoC Harness 영향 매트릭스

| 규정/가이드 | 영향 컴포넌트 | 구현 권장 사항 |
|---|---|---|
| 금융투자업규정 §적합성 (2024-50호) | A(consultation, recommendation_simulation), E(audit) | 적합성 평가에 6개 필수확인 정보(투자목적·재산상황·투자경험·연령·손실감내·투자기간) 모두 캡처. 투자성향 평가 주기 표시(연 1회), 변경 회신 통지 모의 |
| 금소법 감독규정 §설명의무 (2025 개정) | A(설명의무 체크), B(설명서 AI 초안 생성) | 핵심설명서 상단 박스에 ① 부적합 소비자 유형, ② 손실가능성/손실사례 우선 표시. AI 생성 설명문에도 동일 leading-block 강제 |
| 금소법 감독규정 §부당권유 (2025 신설) | A(권유 UI), E(audit) | "특정 답변 유도", "대면→비대면 전환", "회사 대리가입" 패턴 차단/경고 + audit_logs.action_code=`UNFAIR_SOLICITATION_BLOCKED` |
| 금소법 §광고규제 (제22조) + KOFIA 광고심의 세칙 | B(email_draft, AI 마케팅 카피), E(audit) | 광고 성격 문구는 발송 전 "광고심의 게이트" 검토. PoC에서는 정적 룰(손실보전/이익보장/단정문구) + AI compliance_check 이중 검토 + audit `MARKETING_REVIEW_PASS/BLOCK` |
| 금소법 청약철회·위법계약해지·자료요구권 | A(consultation 종료 UI), E(audit) | 상담 완료 화면에 권리고지 박스 + 권리행사 시뮬레이션 워크플로(데모용). audit `RIGHT_NOTICE_DISPLAYED` |
| 금소법 분쟁조정 (금감원 30일) | E(compliance 화면), D(operations) | 합성 분쟁조정 케이스 1건을 데모 모드에 포함; 자료요구권 응답시한(7일/30일) 데모용 타이머 표시 |
| 신용정보업감독규정 (2025-2호) | E(고객 동의, 처리방침), C(데이터) | 합성 고객 신용정보는 일괄 동의 시뮬, 처리방침 페이지 표기. 동의 보관 row + 만 14세+ 단독 이용 시나리오는 PoC scope 밖(non-goal 선언) |
| 마이데이터 2.0 (2025) | C, E | PoC에서는 마이데이터 사업자 역할 비채택 — non-goal 명시. 대신 "Out-of-scope" 배너 + 향후 확장 메모만 |
| 위험등급 산정 가이드라인 | C(product master), A(권유) | 상품 risk_grade_code를 1~6 체계로 정렬. 시장+신용위험 메타필드 + (있다면) 환율위험·유동성위험·고난도 플래그. 4-gate 적합성 체크 서버 재계산 시 상품 등급 > 고객 등급이면 BLOCKED |
| 설명의무 합리적 이행·온라인 가이드 | A, B | 화면형 설명서: 일반인 가독성, 그림/그래프 옵션, 페이지 분량 추적. AI 생성 설명문 평가 항목(가독성·완결성·위험노출)을 결정성 골든 테스트에 포함 |
| KOFIA 표준투자권유준칙 | A(권유), E(audit) | 디지털 채널 권유 시 본인확인+녹취/녹화 메타필드(텍스트 chat log) 저장. 합성 동의 시뮬에도 동일 메타 보관 |
| 금융분야 AI 가이드라인 7대원칙 (2026-1Q 시행 예정) | B(7 agents), E(audit), D(observability) | 거버넌스: AI Job/AI Output 테이블 + admin AI 운영현황 화면. 합법성: 프롬프트 템플릿 검토 통과 기록. 보조수단성: AI 결과는 "초안/검토용" 라벨 + 직원 최종 승인 게이트. 신뢰성: 인용 정합성·결정성 골든 스냅샷. 금융안정성: rate limit·fail-closed. 신의성실: 소비자 권리/오인 방지 leading-block. 보안성: prompt-injection 검역 + 모델/데이터 분리 |
| 생성형 AI 활용 지원방안 | B | 인용·할루시네이션·prompt-injection 검역은 이미 Round 3 제약과 일치. AI 출력 generated_at+model 표기 유지 |

## 4. 운영 세칙 적용 권장

### 4.1 적합성 확인서 화면 요구사항 (Consultation UI)
- 6개 필수확인 정보 필드를 모두 입력 강제 (투자목적, 재산상황, 투자경험, 연령, 손실감내수준, 투자기간).
- "특정 답변 유도 금지" 패턴: 객관식 옵션 순서를 무작위화하고, 임직원이 미리 답을 채워둘 수 없도록 클라이언트 readonly + 서버 재검증.
- 결과 화면에 고객 위험등급(1~6) + 회신 변경 통지(연 1회) 안내 박스.
- audit_logs.action_code: `SUITABILITY_CONFIRMED`, `SUITABILITY_FAILED`, `SUITABILITY_UPDATE_NOTICE_SHOWN`.

### 4.2 설명의무 체크리스트 화면 요구사항
- 핵심설명서 최상단 leading-block: (1) "이 상품에 부적합한 소비자 유형", (2) "주요 손실 가능성과 과거 손실 사례".
- 체크리스트 항목 단위로 직원 확인 클릭 → gate_detail_json에 timestamp + 체크 ID 기록.
- AI 생성 설명문도 동일한 leading-block 구조를 출력하도록 prompt 템플릿에 강제.
- audit_logs.action_code: `EXPLANATION_CONFIRMED`, `EXPLANATION_BLOCK_MISSING_LEADING`.

### 4.3 부당권유 차단 패턴 (Server gate)
- 차단 룰 (정규식/룰 엔진):
  - "확실", "원금보장", "손실 없음", "100% 수익" 등 단정 표현 → BLOCK.
  - 적합성 평가 후 고객 위험등급보다 높은 상품을 권유 시 BLOCK (서버 재계산).
  - 대면 상담 완료 후 짧은 시간 안에 비대면 계약 시도 → WARN + audit.
- 모든 BLOCK은 audit_logs.detail_json에 사유 코드(`UNFAIR_DEFINITIVE`, `UNFAIR_RISK_OVER`, `UNFAIR_OFFLINE_TO_ONLINE`).

### 4.4 광고문 검토 게이트 (Email/마케팅 카피)
- 발송 후보 텍스트 → (a) compliance_check AI 에이전트 검토, (b) 정적 룰 검증, (c) "광고심의 통과" 라벨 부여 시에만 발송 가능.
- 손실보전·이익보장 오인 표현, 비교광고 표현, 단정 표현 차단.
- audit_logs.action_code: `MARKETING_REVIEW_PASS`, `MARKETING_REVIEW_BLOCK`.

### 4.5 권리고지·분쟁조정 데모 워크플로
- 상담 완료 시 "청약철회권·위법계약해지권·자료요구권·분쟁조정" 안내 배너 자동 표시 → 클릭 시 데모 페이지.
- 데모 모드(PoC_AUTO_APPROVAL)는 합성 분쟁조정 case 1건 자동 생성 후 30일 타이머 시뮬.

### 4.6 AI 7대 원칙 매핑 (BIZ-06 보강)
- 거버넌스 → AI Job/AI Output 테이블 + admin 화면.
- 합법성 → prompt 템플릿 검토 + 법령 leading-block.
- 보조수단성 → "초안/검토용" 배지 + employee_final_approval 게이트.
- 신뢰성 → 인용·결정성·confidence 표기.
- 금융안정성 → fail-closed + rate limit.
- 신의성실 → 부적합 유형/손실 우선 표기.
- 보안성 → prompt-injection 검역 + 모델·데이터 분리.

## 5. BACKLOG Task 후보 (T220~T239)

| ID | 영역 | Task | 출처 규정 |
|---|---|---|---|
| T220 | A/E | 적합성 확인서 6개 필수확인 정보 강제 + 옵션 무작위화 | 금소법 감독규정 2025 개정 |
| T221 | A/E | 적합성 확인서 변경 연 1회 통지 시뮬 + audit_logs | 금융투자업규정 2024-50호 |
| T222 | A/B | 핵심설명서 leading-block(부적합 유형/손실 우선 표시) UI + AI prompt 템플릿 적용 | 금소법 감독규정 2025 |
| T223 | A/E | 부당권유 룰 엔진(단정·위험초과·대면후비대면) + BLOCK audit | 금소법 감독규정 부당권유 신설 |
| T224 | B/E | compliance_check AI + 정적 룰 광고심의 게이트 | 금소법 §22 + KOFIA 광고심의 |
| T225 | A/D | 상담 완료 권리고지 배너 (청약철회·해지·자료요구·분쟁조정) | 금소법 권리 4종 |
| T226 | D/E | 분쟁조정 30일 타이머 데모 케이스 1건 자동 생성 | 금소법 §36 + 금감원 절차 |
| T227 | C | 상품 risk_grade_code 1~6 마이그레이션 + 시장/신용/환율/유동성/고난도 메타필드 | 위험등급 산정 가이드라인 |
| T228 | A | 서버 4-gate에서 상품 위험등급 > 고객 위험등급이면 BLOCKED 재계산 강제 | 금융투자업규정 §적합성 |
| T229 | E | 신용정보 일괄 동의 시뮬 + 처리방침 페이지 + 동의 row 보관 | 신용정보업감독규정 2025-2호 |
| T230 | E | 만 14세+ 단독 이용 / 마이데이터 2.0 non-goal 배너 + 메모 | 신용정보업감독규정 2025-2호 |
| T231 | B | 7 AI 에이전트별 "초안/검토용" 배지 + employee_final_approval 게이트 | 금융분야 AI 가이드라인 보조수단성 |
| T232 | B | AI prompt-injection 검역 quarantine 테이블 + 룰 셋 (RAG ingestion 단계) | AI 가이드라인 보안성 + 생성형 AI 지원방안 |
| T233 | B/D | AI 인용 정합성·결정성 골든 스냅샷 테스트(7 agents 전체) | AI 가이드라인 신뢰성 |
| T234 | D | admin AI 운영현황 화면(거버넌스: 사용량/실패율/오용 신호) | AI 가이드라인 거버넌스 |
| T235 | A/B | 설명서 가독성·분량 평가 KPI + AI 출력 평가 게이트 | 설명의무 합리적 이행 가이드라인 |
| T236 | A | KOFIA 디지털 권유 본인확인+chat log/녹취 메타 저장 | 표준투자권유준칙 |
| T237 | E | audit_logs.action_code 신규: UNFAIR_*, MARKETING_REVIEW_*, RIGHT_NOTICE_DISPLAYED 등 → OBS-02 갱신 | BIZ-06 + 본 문서 |
| T238 | B | AI fail-closed + rate limit 정책 (금융안정성 원칙) | AI 가이드라인 금융안정성 |
| T239 | E | 권유/시뮬 기록 보존 5년 정책 + 기록 export 데모 | 자본시장법 + 금소법 + 감독규정 공통 |

## 6. 인용 (검색일 2026-05-17 KST)
1. 금융위원회 보도자료(2025-02-27) — 고난도 금융투자상품 불완전판매 예방 종합대책: https://www.fsc.go.kr/no010101/84921
2. 금융위원회 보도자료(2025-12-22) — 금융분야 AI 가이드라인 개정방향: https://www.fsc.go.kr/no010101/85908
3. 금융위원회 보도자료 — 투자성 상품 위험등급 산정 가이드라인: https://www.fsc.go.kr/no010101/79327
4. 금융위원회 보도자료 — 금융상품 설명의무 합리적 이행 가이드라인: https://www.fsc.go.kr/po010101/76239 / 첨부 PDF https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=76243&fileTy=ATTACH&fileNo=2
5. 금융위원회 보도자료 — 온라인 설명의무 가이드라인: https://www.fsc.go.kr/no010101/78276
6. 금융위원회 보도자료 — 금융권 생성형 AI 활용 지원방안: https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=83594&fileTy=ATTACH&fileNo=7
7. 금융위 보도자료 — 마이데이터 2.0 서비스 개시: https://www.fsc.go.kr/no010101/84780
8. 금융위 보도자료 — 신용정보업감독규정 일부개정고시안 의결(2025-02-05): https://eiec.kdi.re.kr/policy/materialView.do?num=263002
9. 국가법령정보센터 — 금융투자업규정 (행정규칙): https://www.law.go.kr/admRulLsInfoP.do?admRulSeq=2100000249422
10. 국가법령정보센터 — 금융투자업규정 시행세칙: https://www.law.go.kr/행정규칙/금융투자업규정시행세칙
11. 국가법령정보센터 — 금융소비자 보호에 관한 감독규정: https://www.law.go.kr/LSW/admRulInfoP.do?admRulSeq=2100000226154
12. 국가법령정보센터 — 신용정보업감독규정: https://www.law.go.kr/행정규칙/신용정보업감독규정
13. 국가법령정보센터 — 금융소비자 보호에 관한 법률: https://www.law.go.kr/LSW/lsInfoP.do?lsId=013704
14. 찾기쉬운 생활법령정보 — 금융상품 6대 판매원칙: https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1771&ccfNo=1&cciNo=1&cnpClsNo=2
15. 찾기쉬운 생활법령정보 — 청약철회권: https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1771&ccfNo=1&cciNo=2&cnpClsNo=1
16. 찾기쉬운 생활법령정보 — 금감원 분쟁조정: https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=572&ccfNo=6&cciNo=2&cnpClsNo=1
17. KOFIA 법규정보시스템 — 표준투자권유준칙: https://law.kofia.or.kr/service/law/lawFullScreenContent.do?seq=149&historySeq=1572
18. KOFIA 법규정보시스템 — 금융투자회사 영업·업무규정 시행세칙: https://law.kofia.or.kr/service/law/lawFullScreen.do?seq=137&historySeq=1613
19. KOFIA 법규정보시스템 — 컴플라이언스 매뉴얼 III: https://law.kofia.or.kr/service/law/lawFullScreenContent.do?seq=262&historySeq=1154
20. Kim & Chang — 금융분야 AI 가이드라인 개정안 공개 해설: https://www.kimchang.com/ko/insights/detail.kc?sch_section=4&idx=33825
21. KDI 경제정보센터 — 신용정보업감독규정 일부개정고시안 의결(2025-02-05): https://eiec.kdi.re.kr/policy/materialView.do?num=263002

## 7. Phase 1b 인터뷰 보강 시사점 (요약)
- ambiguity 잔존 영역 추가 결정 필요 항목:
  - (a) PoC에서 6개 필수확인 정보 모두 사용 vs 최소 4개로 축소 채택?
  - (b) 광고심의 게이트는 정적 룰 + AI 이중 vs AI 단일?
  - (c) 분쟁조정/권리고지 데모는 자동 실행 vs admin 토글로 별도?
  - (d) 마이데이터 2.0/만14세+ 단독은 명시적 non-goal 배너 vs 완전 미언급?
- 위 4문항은 Phase 1b 짧은 인터뷰 후보로 spec-pending에 추가 권장.
