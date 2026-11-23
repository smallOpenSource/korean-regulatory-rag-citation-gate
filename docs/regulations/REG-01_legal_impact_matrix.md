# REG-01 Legal Impact Matrix (자본시장법 · 금융소비자보호법 · 신용정보법)

## 1. 메타데이터
- 작성일: 2026-05-17
- 작성자: L1 외부 리서치 lane (general-purpose 에이전트)
- 적용 범위: WMAH(Wealth Management AI Harness) PoC. 인터넷망에서 합성 고객 데이터만 사용하는 직원용 시뮬레이션 환경(5 roles: PB / WM / BRANCH_MANAGER / ADMIN / AUDIT_VIEWER).
- 본 매트릭스의 한계: 본 문서는 법령 본문과 공식 해석을 PoC harness 구현 의사결정에 매핑한 참고자료이며 법적 자문이 아니다. 실제 운영망 도입 전에는 별도 법률검토가 필요하다.
- 핵심 출처: 국가법령정보센터(law.go.kr), 금융위원회(fsc.go.kr), 금융감독원(fss.or.kr), 한국금융투자협회(kofia.or.kr), 법제처(moleg.go.kr).
- 중요 변경 이력 인식: 2021-03-25 금융소비자보호법 시행과 동시에 자본시장법 §46(적합성 원칙)·§46-2(적정성 원칙)·§47(설명의무)·§49(부당권유 금지)·§57(투자광고) 등은 금융소비자보호법으로 통합·이관되었다. 본 문서는 사용자가 지시한 자본시장법 조항 번호를 "이관 후 현행 근거 조항"으로 재매핑한다.

## 2. 법률별 핵심 조항 표

### 2.1 자본시장과 금융투자업에 관한 법률 ("자본시장법", 현행)
| 법률 | 조항 | 핵심 의무 | 위반 시 제재 |
|---|---|---|---|
| 자본시장법 | §37 신의성실의무 등 | 금융투자업자는 신의에 따라 성실하게 직무 수행, 이해상충 방지 | 금융위 행정처분, 손해배상 |
| 자본시장법 | §44 이해상충 방지 | 이해상충 파악·평가·관리, 관리 곤란 시 거래 회피 | 시정명령·과태료 |
| 자본시장법 | §45 정보교류 차단 (Chinese Wall) | 고유재산/투자자재산, 부서간 정보교류 차단 | 행정처분 |
| 자본시장법 | §54 직무관련 정보 이용 금지 | 직무상 알게 된 미공개 정보를 자기·제3자 이익을 위해 이용 금지 | 자본시장법 §445 형사처벌(3년이하 징역/1억 이하 벌금) |
| 자본시장법 | §55 손실보전·이익보장 약정 금지 | 손실 전부·일부 보전 약정 금지, 이익 보장 약정 금지 | §445 형사처벌, 행정처분 |
| 자본시장법 | §64 손해배상책임 | 법령·약관·집합투자규약·투자설명서 위반 시 손해배상 | 민사 손해배상 |
| 자본시장법 | §178 부정거래 금지 | 부정한 수단·계획·기교, 거짓 표시 금지 | §443 형사처벌(1년 이상 유기/이득 3~5배 벌금) |
| (구) §46 적합성 / §47 설명의무 / §49 부당권유 / §57 광고 | 2021-03-25 삭제·이관 → 금융소비자보호법으로 일원화 | — | — |

### 2.2 금융소비자 보호에 관한 법률 ("금소법", 2021-03-25 시행, 2024-2025 감독규정 개정 반영)
| 법률 | 조항 | 핵심 의무 | 위반 시 제재 |
|---|---|---|---|
| 금소법 | §17 적합성 원칙 | 일반/전문 금소비자 확인 → 정보 파악 → 부적합 상품 권유 금지 | 최대 3천만원 과태료 |
| 금소법 | §18 적정성 원칙 | 비권유 거래도 정보 파악 후 부적정 사실 고지·확인 서명 | 최대 3천만원 과태료 |
| 금소법 | §19 설명의무 | 중요사항 설명 + 이해 확인(서명·녹취 등) + 거짓·왜곡 금지 | 관련 수입의 50% 이하 징벌적 과징금 + 1억 이하 과태료 + 입증책임전환부 손해배상 |
| 금소법 | §20 불공정영업행위 금지 | 우월적 지위 남용, 끼워팔기, 부당한 담보·보증 요구 등 금지 | 50% 과징금 + 1억 과태료 |
| 금소법 | §21 부당권유 금지 | 단정적 판단, 불확실한 사항을 확실하다 단정, 거짓·중요사항 누락, 불초청 권유 등 금지 | 50% 과징금 + 1억 과태료 |
| 금소법 | §22 광고규제 | 광고 시 명확·공정 전달, 필수기재사항·금지표현 준수, 협회 사전심의 | 50% 과징금 + 1억 과태료 |
| 금소법 | §23 계약서류 제공의무 | 계약체결 시 계약서·약관·설명서 지체 없이 제공 | 최대 1천만원 과태료 |
| 금소법 | §28 자료유지·열람 | 10년(또는 종류별 5~10년) 자료 유지, 소비자 열람청구 응대 | 과태료, 분쟁조정 불리 |
| 금소법 | §32 손해배상 / 입증책임 | §19 위반 시 판매업자가 고의·과실 없음 입증 못하면 배상 책임 | 민사 손해배상 |
| 금소법 | §46 청약철회권 | 보장성 15일, 투자성·자문 7일(고난도 9일), 대출성 14일 내 철회. 위약금·손해배상 청구 금지 | 위반 시 1천만원 과태료, 환급 의무 |
| 금소법 | §47 위법계약해지권 | §17·§18·§19·§20·§21 위반 시 안 날 1년·계약일 5년 내 해지 청구 | 수수료·위약금 없이 해지, 분쟁조정 |
| 금소법 | §57 과징금 | 위반 관련 수입의 50% 이하 징벌적 과징금 | (제재 자체) |
| 금소법 | §69 과태료 | §17~§22 위반 등에 1억/3천만/1천만 차등 과태료 | (제재 자체) |

### 2.3 신용정보의 이용 및 보호에 관한 법률 ("신용정보법", 현행 + 2024-2025 마이데이터 2.0 반영)
| 법률 | 조항 | 핵심 의무 | 위반 시 제재 |
|---|---|---|---|
| 신용정보법 | §15 수집·이용의 원칙 | 목적 명확·필요최소·합법수단 | 행정처분 |
| 신용정보법 | §32 제공·활용 동의 | 개인신용정보 제3자 제공 시 사전 개별 동의, 동의서 별도 구분·고지사항 명시 | 5년 이하 징역 / 5천만원 이하 벌금 |
| 신용정보법 | §33 이용 제한 | 상거래관계 유지 판단 목적 외 이용 금지(또는 별도 동의), 민감정보 별도 동의 | 행정처분 + 과징금 |
| 신용정보법 | §34 개인식별정보 처리 | 주민번호·여권번호 등 식별정보 처리 시 개별 동의 또는 법령근거 | 5년 이하 / 5천만원 이하 |
| 신용정보법 | §35 신용정보 이용·제공 사실 통지 | 통지 요청 시 최근 3년 이용·제공 내역 통지 | 과태료 |
| 신용정보법 | §36 상거래 거절 근거 신용정보 고지 | 거절 시 근거 정보·제공처 고지 | 과태료 |
| 신용정보법 | §37 동의철회·연락중지청구 | 마케팅 목적 제공동의 철회, 영업목적 연락중지 요구 즉시 반영 | 과태료 |
| 신용정보법 | §38 열람·정정청구 | 본인정보 열람·정정 청구, 다툼 중에는 제3자 제공 시 사실 고지 | 과태료 |
| 신용정보법 | §38-2 / §38-3 | 신용조회 사실 통지, 개인신용정보 삭제요구 | 과태료 |
| 신용정보법 | §39 무료 열람권 | 연 1회 이상 무료 열람 | 과태료 |
| 신용정보법 | §40 신용정보회사등의 금지사항 | 광고·마케팅 목적의 부당 이용, 거짓 수집·제공, 직무 외 이용 금지 | 행정처분 + 형사 |
| 신용정보법 | §40-2 가명정보 처리 | 통계·연구·공익 목적 한정, 재식별 금지, 적정성 평가 | 5년 이하/5천만 이하, 전체 매출 3% 이하 과징금 |
| 신용정보법 | §20-2 보존·파기 | 상거래 종료 후 5년 내 파기·분리보관, 가명정보 보유기간 연장 시 적정성 평가 | 행정처분 + 과태료 |
| 신용정보법 | §43 손해배상 / §43-2 법정손해배상 | 위반 시 손해배상, 법정손해배상(피해 입증 곤란 시) | 민사 책임 |

## 3. PoC Harness 영향 매트릭스
컴포넌트 약칭: **A** Customer 360 / **B** 4-Gate Recommendation·Order Simulation / **C** AI 생성물 표시·이메일 / **D** Audit log / **E** 신용정보/동의/약관 화면 (현재 일부 미구현)

| 조항 | A | B | C | D | E | 기존 docs/business 캡처 여부 | 추가 구현 후보 |
|---|---|---|---|---|---|---|---|
| 자본시장법 §54 직무관련정보 | O |   | O | O |   | BIZ-06 (이해충돌 한 줄만) | A 화면에 "직무관련 정보 외부유출 금지" 경고, C 이메일 발송 시 외부 도메인 확인 게이트, D `info_leak_warning_shown` |
| 자본시장법 §55 손실보전 금지 |   | B | C | O |   | 미캡처 | C AI 응답 후처리에서 "원금보장/손실보전" 금지표현 차단, B order simulation 메모란 금지표현 검출 |
| 자본시장법 §64 손해배상 |   | B |   | O |   | 부분(설명의무 체크) | D 손배 입증용 게이트 통과 evidence를 audit detail에 포함 |
| 금소법 §17 적합성 | A | B |   | O |   | BIZ-06 §46, BIZ-09 gate#1 | 서버 측 위험등급 재계산 강화(이미 BIZ-09 명시), 일반/전문 소비자 구분 필드 |
| 금소법 §18 적정성 | A | B |   | O |   | 미캡처(권유 없는 거래) | "부적정" 시 confirmation 모달 + audit `appropriateness_warning_acknowledged` |
| 금소법 §19 설명의무 |   | B | C | O |   | BIZ-06 §47, BIZ-09 gate#2 | C 설명서 PDF/요약 미리보기, gate#2 detail에 설명 항목 체크리스트 JSON, 녹취 placeholder(시뮬레이션) |
| 금소법 §20 불공정영업 |   | B | C | O |   | 미캡처 | C 추천 reasoning에 끼워팔기·강요 키워드 lint, audit `unfair_practice_flagged` |
| 금소법 §21 부당권유 |   | B | C | O |   | 미캡처 | C 금지표현 가드(단정적/확실/원금보장/특혜), 불초청 권유 차단 |
| 금소법 §22 광고규제 |   |   | C |   | E | 미캡처 | C 이메일/안내문 발송 전 "광고 여부" 분류 + 필수기재 lint, 협회 심의 placeholder |
| 금소법 §23 계약서류 제공 |   | B | C | O | E | 미캡처 | B approve 시 합성 계약서/약관 PDF 자동 생성·발송(시뮬레이션), D `contract_docs_delivered` |
| 금소법 §28 자료유지/열람 |   |   |   | O | E | 부분(audit_logs 5년) | retention policy 명시(10년), AUDIT_VIEWER 열람 UI |
| 금소법 §32 손해배상 입증책임 |   | B |   | O |   | 부분 | gate 통과 evidence(타임스탬프·체크박스 ID·사용자 ID) 불변 보관, hash chain placeholder |
| 금소법 §46 청약철회권 |   | B |   | O | E | 미캡처 | B 승인 후 "철회 가능 기간 안내 배너", E 철회 신청 시뮬레이션 화면, audit `withdrawal_simulated` |
| 금소법 §47 위법계약해지권 |   | B |   | O | E | 미캡처 | E 위법계약해지권 행사 시뮬레이션 화면, audit `illegal_contract_termination_simulated` |
| 금소법 §57 과징금 / §69 과태료 |   |   | C | O |   | 미캡처 | C UI 표기 "위반 시 최대 50% 과징금" 경고문, BLOCKED 사유에 위반 조항 코드 첨부 |
| 신용정보법 §32 제공동의 | A |   |   | O | E | 미캡처(합성 동의만) | E 합성 동의서 화면(필수/선택 구분, 보유기간, 제공처), audit `synthetic_consent_*` 코드 세분화 |
| 신용정보법 §33 이용 제한 | A |   | C | O |   | 미캡처 | A/C 화면에 "이 정보는 합성 데이터" 워터마크, 마케팅 목적 별도 동의 확인 |
| 신용정보법 §34 개인식별정보 | A |   |   | O | E | 부분(합성 데이터) | 주민번호 placeholder 마스킹(***-1******) 강제, 시드 합성 ID 사용 명문화 |
| 신용정보법 §35 이용·제공 통지 | A |   |   | O | E | 미캡처 | A "정보 이용·제공 내역" 탭, audit `info_usage_disclosure_requested` |
| 신용정보법 §37 동의철회 | A |   |   | O | E | 미캡처 | E 동의철회·연락중지 시뮬레이션 버튼, audit `marketing_consent_withdrawn` |
| 신용정보법 §38 열람·정정 | A |   |   | O | E | 미캡처 | E 본인정보 열람·정정 시뮬레이션, audit `info_access_request` / `info_correction_request` |
| 신용정보법 §40 금지사항 |   |   | C | O |   | 미캡처 | C 이메일 발송 시 마케팅/비마케팅 분류 + 동의 매핑 검사 |
| 신용정보법 §40-2 가명정보 |   |   | C | O |   | 미캡처 | C house view·NBA 학습데이터를 가명정보로 표기, 재식별 금지 문구 |
| 신용정보법 §20-2 파기 | A |   |   | O | E | 미캡처 | E "합성 고객 만기·해지 5년 시뮬레이션", 백그라운드 batch placeholder |
| 신용정보법 §43 손해배상 |   |   |   | O |   | 미캡처 | audit 무결성 보장(append-only, hash) 설계 명시 |

## 4. 추가 구현 후보 상세

### 4.1 audit action_code 후보 (OBS-02에 신규 등록 제안)
- 적합성/적정성: `suitability_recalculated_server`, `appropriateness_warning_acknowledged`, `client_type_classified` (일반/전문)
- 설명의무: `explanation_checklist_completed`, `explanation_doc_previewed`, `explanation_recording_started` (placeholder)
- 부당권유/불공정: `prohibited_phrase_blocked`, `unsolicited_recommendation_blocked`, `unfair_practice_flagged`
- 광고: `marketing_content_classified`, `marketing_required_field_lint_failed`
- 계약/철회: `contract_docs_delivered`, `withdrawal_simulated`, `illegal_contract_termination_simulated`
- 신용정보: `synthetic_consent_required_collected`, `synthetic_consent_optional_collected`, `synthetic_consent_withdrawn`, `marketing_contact_stop_requested`, `info_access_request`, `info_correction_request`, `info_usage_disclosure_requested`, `credit_info_purge_simulated`
- AI/감사 무결성: `ai_output_disclaimer_rendered`, `ai_output_phrase_lint_blocked`, `audit_chain_hash_recorded`

### 4.2 UI 안내문 후보
- AI 생성물 푸터: "AI 생성 · {generated_at} · {model} · 시뮬레이션 / 실제 주문 아님"
- 부당권유 가드: "원금보장·확실한 수익 등 단정적 표현은 자본시장법 §55, 금소법 §21에 의해 금지되며 자동 차단됩니다."
- 적합성 경고: "고객 위험등급({customer_grade}) < 권유 상품 위험등급({product_grade}) — 4-gate 차단(자본시장법/금소법 §17 적합성 원칙)."
- 청약철회 배너: "투자성 상품은 계약체결일로부터 7일(고난도 9일) 이내 청약철회가 가능합니다. (금소법 §46)"
- 위법계약해지 안내: "판매원칙(§17~§21) 위반 사실을 안 날부터 1년·계약일부터 5년 이내 해지 청구 가능. (금소법 §47)"
- 신용정보 동의: "본 PoC는 합성 데이터를 사용합니다. 신용정보법 §32·§33 동의 흐름은 시뮬레이션입니다."
- AUDIT_VIEWER 안내: "본 화면은 금소법 §28 자료유지·열람 의무 시뮬레이션이며 합성 데이터입니다."

### 4.3 차단 게이트 후보 (서버 측 강제)
- G-A 부당권유 금지표현 검출: AI 추천/이메일 초안에 정규식·키워드 사전 적용 → 검출 시 status_code=BLOCKED, audit `prohibited_phrase_blocked`
- G-B 광고 분류 게이트: 발송 콘텐츠가 마케팅이면 필수기재(이자율·수수료·위험·연락처) lint 통과 필요
- G-C 적정성 추가 게이트(권유 없는 거래 시): 정보 미파악 / 부적정 시 confirmation 요구
- G-D 계약서류 게이트: 추천/주문 시뮬레이션 APPROVED → 합성 계약서 PDF 생성 & 첨부 확인
- G-E 신용정보 동의 매핑 게이트: AI 처리 단계마다 사용한 항목이 동의 범위에 포함되는지 서버 재검증
- G-F 데이터 분류 게이트: 외부 도메인 발송 시 식별정보(이름/주민/계좌 등) 마스킹 필수
- G-G 가명정보 재식별 가드: house view·NBA 학습 데이터 결합 시 재식별 위험 평가 placeholder

### 4.4 약관/공시 화면 후보 (현재 미구현 컴포넌트 E)
- E1 합성 동의서 화면: 필수/선택 동의, 보유기간, 제공처, 마케팅 동의 분리 (신용정보법 §32)
- E2 동의·열람·정정·철회 시뮬레이션 화면 (신용정보법 §37·§38)
- E3 청약철회·위법계약해지권 시뮬레이션 화면 (금소법 §46·§47)
- E4 자료유지 열람 화면 (AUDIT_VIEWER 전용, 금소법 §28)
- E5 분쟁조정 신청 시뮬레이션 화면 (금소법 §33~§43)
- E6 약관·설명서 PDF 미리보기 (금소법 §19·§23)
- E7 광고 사전심의 placeholder 화면 (금소법 §22)

## 5. BACKLOG task 후보 (T200~T219)
- [ ] T200 자본시장법 §54 직무관련정보 — Customer 360에 외부 도메인 이메일 발송 시 식별정보 마스킹 경고 + audit `info_leak_warning_shown`
- [ ] T201 자본시장법 §55 손실보전 금지 — AI 추천/이메일 후처리 prohibited_phrase 사전 도입, BLOCKED 처리 + audit `prohibited_phrase_blocked`
- [ ] T202 금소법 §17 적합성 — 일반/전문 금융소비자 구분 필드 추가, gate#1 detail에 분류 결과 저장
- [ ] T203 금소법 §18 적정성 — 권유 없는 거래용 추가 게이트(부적정 confirmation), audit `appropriateness_warning_acknowledged`
- [ ] T204 금소법 §19 설명의무 — 설명항목 체크리스트 JSON 스키마화, 설명서 PDF 미리보기 컴포넌트
- [ ] T205 금소법 §20 불공정영업 — 추천 reasoning lint(끼워팔기·강요 키워드) + audit `unfair_practice_flagged`
- [ ] T206 금소법 §21 부당권유 — 단정적 판단·원금보장 금지표현 가드(클라이언트+서버 이중)
- [ ] T207 금소법 §22 광고규제 — 이메일/안내문 발송 전 마케팅 분류 + 필수기재 lint
- [ ] T208 금소법 §23 계약서류 제공 — 추천/주문 시뮬레이션 APPROVED 시 합성 계약서 PDF 자동 생성·전달(시뮬레이션)
- [ ] T209 금소법 §28 자료유지·열람 — AUDIT_VIEWER 전용 자료열람 화면(E4), retention 정책 문서화
- [ ] T210 금소법 §32 손해배상 입증책임 — gate evidence(타임스탬프·체크박스·사용자ID) append-only 저장, hash chain placeholder
- [ ] T211 금소법 §46 청약철회권 — 승인 직후 철회 안내 배너 + E3 철회 시뮬레이션 화면 + audit `withdrawal_simulated`
- [ ] T212 금소법 §47 위법계약해지권 — E3 위법계약해지 시뮬레이션 + 분쟁조정 placeholder
- [ ] T213 금소법 §57/§69 제재 — BLOCKED 사유 JSON에 위반 조항 코드(violation_clause_code) 필드 추가
- [ ] T214 신용정보법 §32 제공동의 — E1 합성 동의서 화면(필수/선택 분리, 보유기간, 제공처)
- [ ] T215 신용정보법 §33/§34 이용·식별정보 — 주민번호 등 마스킹 표준 + 합성 ID 정책 명문화
- [ ] T216 신용정보법 §35/§38 열람·통지 — Customer 360에 "정보 이용·제공 내역" 탭 + 정정청구 시뮬레이션
- [ ] T217 신용정보법 §37 동의철회 — E2 동의철회·연락중지 시뮬레이션, audit `marketing_consent_withdrawn`
- [ ] T218 신용정보법 §40-2 가명정보 — house view·NBA 학습데이터 메타에 "가명/재식별금지" 라벨, 재식별 위험 placeholder
- [ ] T219 신용정보법 §20-2 파기 — 합성 고객 만기·해지 5년 파기 batch placeholder, audit `credit_info_purge_simulated`

## 6. 인용 (공식 출처 · 검색일 2026-05-17)
- 국가법령정보센터, 「자본시장과 금융투자업에 관한 법률」 — https://www.law.go.kr/lsInfoP.do?lsiSeq=105908
- 국가법령정보센터, 「금융소비자 보호에 관한 법률」 — https://www.law.go.kr/lsInfoP.do?lsiSeq=218047
- 국가법령정보센터, 「신용정보의 이용 및 보호에 관한 법률」 — https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=140586
- 국가법령정보센터, 「신용정보의 이용 및 보호에 관한 법률 시행령」 — https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=220813
- 국가법령정보센터, 「금융소비자 보호에 관한 감독규정」 — https://www.law.go.kr/행정규칙/금융소비자%20보호에%20관한%20감독규정
- 금융위원회, 「금융소비자보호법 시행령 및 감독규정 개정안 입법예고」 — https://www.fsc.go.kr/no010101/85339
- 금융위원회, 「마이데이터 2.0 시행을 위한 제도적 기반 마련」 보도자료 — https://fsc.go.kr/no010101/83150
- 찾기쉬운 생활법령정보(법제처), 「금융상품 6대 판매원칙」 — https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1771&ccfNo=1&cciNo=1&cnpClsNo=2
- 찾기쉬운 생활법령정보(법제처), 「계약의 청약철회권」 — https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1771&ccfNo=1&cciNo=2&cnpClsNo=1
- 찾기쉬운 생활법령정보(법제처), 「위법계약의 해지권」 — https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1771&ccfNo=1&cciNo=2&cnpClsNo=2
- 찾기쉬운 생활법령정보(법제처), 「금융분쟁조정위원회의 분쟁조정」 — https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1771&ccfNo=4&cciNo=1&cnpClsNo=1
- 찾기쉬운 생활법령정보(법제처), 「신용정보주체의 동의 획득」 — https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1702&ccfNo=3&cciNo=1&cnpClsNo=2
- 법제처, 「신용정보의 이용 및 보호에 관한 법률 해설」 — https://www.moleg.go.kr/mpbleg/mpblegInfo.mo?mid=a10402020000&mpb_leg_pst_seq=129391
- 한국금융투자협회 법규정보시스템, 「금융투자회사 개인(신용)정보보호 가이드라인」 — https://law.kofia.or.kr/service/law/lawFullScreenContent.do?seq=313&historySeq=1071
- 한국금융투자협회, 「분쟁조정제도 안내」 — https://www.kofia.or.kr/wpge/m_76/sub040101.do
- 한국금융소비자보호재단, 「금융소비자보호법 안내」 — http://www.kfcpf.or.kr/front/protect/protection_law.do
