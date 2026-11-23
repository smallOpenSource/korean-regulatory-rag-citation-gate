/* sql_id: seed_40_manual_rag_docs */
WITH manual_doc_seed(doc_no, source_url, content_hash, raw_text) AS (
    VALUES
        (1, 'urn:harness:manual:seed:asset-allocation',
         'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
         '[교육용] 자산배분 전략은 고객의 투자목표, 위험감내수준, 투자기간을 기반으로 주식·채권·대체투자 비중을 결정하는 핵심 WM 프로세스다. 전통적인 60/40 포트폴리오(주식 60%, 채권 40%)는 역사적으로 안정적인 성과를 보여왔으나, 저금리 환경에서는 채권 수익률 하락으로 대안 자산 편입 필요성이 높아졌다. PB는 고객 면담 시 목표수익률과 최대손실허용액을 명확히 파악한 후 전략적 자산배분(SAA)과 전술적 자산배분(TAA)을 구분하여 제안한다. SAA는 장기 목표 비중으로 연 1회 리밸런싱을 원칙으로 하며, TAA는 시장 환경 변화에 따라 단기적으로 ±10% 범위 내에서 조정 가능하다. 리밸런싱 실행 전에는 반드시 적합성 확인 및 고객 설명의무를 이행해야 하며, 실행 결과와 변경 사유는 감사로그에 상세히 기록해야 한다.'),
        (2, 'urn:harness:manual:seed:kyc-edd',
         'b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3',
         '[교육용] KYC(고객확인제도)와 EDD(강화된 고객확인)는 자금세탁방지법 및 특정금융정보법에 따라 PB가 의무적으로 수행해야 하는 규제 절차다. 신규 고객 등록 시 실명확인, 직업·소득원천 확인, 거래목적 파악이 필수이며, 고위험 고객(정치적 주요인물·PEP, 고위험 국가 관련 거래)에 대해서는 EDD를 적용한다. EDD 항목에는 자금 출처 확인 서류, 최종수익자 확인, 연간 거래한도 설정이 포함된다. 고객정보는 거래 종료 후 5년간 보존해야 하며, STR(의심거래보고)는 사유 발생 후 3영업일 이내에 금융정보분석원에 보고해야 한다. KYC 재확인은 고위험 등급 고객은 연 1회, 중위험은 2년마다 수행하며, 재확인 거절 또는 미수행 시 거래를 즉시 중단하고 모든 확인 결과와 갱신 이력은 시스템 감사로그에 상세히 기록해야 한다.'),
        (3, 'urn:harness:manual:seed:retirement-planning',
         'c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4',
         '[교육용] 은퇴설계는 고객의 은퇴 후 현금흐름 필요액을 역산하여 현재 시점의 필요 자산규모를 도출하는 재무계획 프로세스다. PB는 국민연금 수령 예상액, 퇴직연금(DB/DC/IRP) 잔액, 개인연금 적립액을 합산하여 은퇴 후 월 생활비와의 GAP을 분석한다. 물가상승률을 연 2~3%로 가정할 때 30년 은퇴 기간을 위한 필요자산은 월 생활비의 약 300~350배 수준이다. 세제혜택 활용을 위해 IRP 연 900만 원, ISA 연 2,000만 원 납입 한도를 최우선으로 채우도록 안내한다. 은퇴 10년 전부터는 포트폴리오 내 주식 비중을 점진적으로 줄이고 채권·연금보험 비중을 높이는 글라이드패스 전략을 적용하며, 적합성 재평가를 연 1회 의무 수행하고, 재평가 결과와 포트폴리오 변경 내역을 감사로그에 상세히 기록해야 한다.'),
        (4, 'urn:harness:manual:seed:esg-investing',
         'd4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5',
         '[교육용] ESG 투자는 환경(Environment)·사회(Social)·지배구조(Governance) 요소를 재무적 분석과 결합하여 장기 지속가능성이 높은 기업에 투자하는 방식이다. 국내 ESG 펀드는 한국거래소 ESG 등급 및 KCGS(한국기업지배구조원) 평가를 기준으로 편입 종목을 선정하며, 탄소중립 목표에 부합하는 기업을 우선 편입한다. PB는 고객에게 ESG 투자의 수익성과 비재무적 리스크 완화 효과를 설명할 의무가 있으며, 그린워싱(greenwashing) 펀드와의 구별 방법도 안내해야 한다. ESG 상품 권유 시 적합성 기준에 ESG 성향 항목을 추가 확인하고, 운용보고서 내 ESG 핵심 지표(탄소배출강도, 이사회 다양성 비율)를 고객이 이해할 수 있도록 설명한다. 분기마다 포트폴리오 ESG 점수 변화를 모니터링하여 사후관리 기록에 남긴다.'),
        (5, 'urn:harness:manual:seed:alternative-investments',
         'e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6',
         '[교육용] 대체투자는 전통 주식·채권 이외의 자산군으로 사모펀드(PE), 부동산 펀드(REITs·블라인드펀드), 인프라 펀드, 헤지펀드, 원자재를 포함한다. 포트폴리오 내 대체투자 편입은 전통자산과의 상관관계가 낮아 분산투자 효과를 높이지만, 유동성 위험·밸류에이션 불투명성·긴 의무보유기간(Lock-up)을 수반한다. 국내 규정상 일반투자자에게 사모펀드를 권유하려면 최소투자금액 1억 원 이상, 전문투자자 요건 충족 또는 위험고지 동의 절차를 거쳐야 한다. PB는 대체투자 상품 설명 시 유동성 제약, 환금 조건, 예상 수익 시나리오(기본·낙관·비관)를 표준화된 설명서에 포함시켜야 하며, 고객 서명 확인 후 감사로그를 남긴다. 부동산 펀드의 경우 공실률·임대수익률·레버리지 비율을 핵심 모니터링 지표로 분기 보고해야 한다.')
)
INSERT INTO raw_documents(
    id, source_type_code, source_url, content_hash, raw_text, is_processed, processed_at
)
SELECT ('aaaaaaaa-aaaa-aaaa-bbbb-' || lpad((4000 + doc_no)::text, 12, '0'))::uuid,
       'MANUAL', source_url, content_hash, raw_text, TRUE, now()
FROM manual_doc_seed
ON CONFLICT (id) DO UPDATE SET
    source_url = EXCLUDED.source_url,
    content_hash = EXCLUDED.content_hash,
    raw_text = EXCLUDED.raw_text,
    is_processed = EXCLUDED.is_processed,
    processed_at = EXCLUDED.processed_at;

/* sql_id: seed_40_manual_rag_documents */
WITH manual_doc_seed(doc_no, source_id, title, source_url, content_hash, raw_text) AS (
    VALUES
        (1, 'seed-asset-allocation', '[교육용] 자산배분 전략 매뉴얼',
         'urn:harness:manual:seed:asset-allocation',
         'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
         '[교육용] 자산배분 전략은 고객의 투자목표, 위험감내수준, 투자기간을 기반으로 주식·채권·대체투자 비중을 결정하는 핵심 WM 프로세스다. 전통적인 60/40 포트폴리오(주식 60%, 채권 40%)는 역사적으로 안정적인 성과를 보여왔으나, 저금리 환경에서는 채권 수익률 하락으로 대안 자산 편입 필요성이 높아졌다. PB는 고객 면담 시 목표수익률과 최대손실허용액을 명확히 파악한 후 전략적 자산배분(SAA)과 전술적 자산배분(TAA)을 구분하여 제안한다. SAA는 장기 목표 비중으로 연 1회 리밸런싱을 원칙으로 하며, TAA는 시장 환경 변화에 따라 단기적으로 ±10% 범위 내에서 조정 가능하다. 리밸런싱 실행 전에는 반드시 적합성 확인 및 고객 설명의무를 이행해야 하며, 실행 결과와 변경 사유는 감사로그에 상세히 기록해야 한다.'),
        (2, 'seed-kyc-edd', '[교육용] KYC/EDD 고객확인절차 매뉴얼',
         'urn:harness:manual:seed:kyc-edd',
         'b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3',
         '[교육용] KYC(고객확인제도)와 EDD(강화된 고객확인)는 자금세탁방지법 및 특정금융정보법에 따라 PB가 의무적으로 수행해야 하는 규제 절차다. 신규 고객 등록 시 실명확인, 직업·소득원천 확인, 거래목적 파악이 필수이며, 고위험 고객(정치적 주요인물·PEP, 고위험 국가 관련 거래)에 대해서는 EDD를 적용한다. EDD 항목에는 자금 출처 확인 서류, 최종수익자 확인, 연간 거래한도 설정이 포함된다. 고객정보는 거래 종료 후 5년간 보존해야 하며, STR(의심거래보고)는 사유 발생 후 3영업일 이내에 금융정보분석원에 보고해야 한다. KYC 재확인은 고위험 등급 고객은 연 1회, 중위험은 2년마다 수행하며, 재확인 거절 또는 미수행 시 거래를 즉시 중단하고 모든 확인 결과와 갱신 이력은 시스템 감사로그에 상세히 기록해야 한다.'),
        (3, 'seed-retirement-planning', '[교육용] 은퇴설계 매뉴얼',
         'urn:harness:manual:seed:retirement-planning',
         'c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4',
         '[교육용] 은퇴설계는 고객의 은퇴 후 현금흐름 필요액을 역산하여 현재 시점의 필요 자산규모를 도출하는 재무계획 프로세스다. PB는 국민연금 수령 예상액, 퇴직연금(DB/DC/IRP) 잔액, 개인연금 적립액을 합산하여 은퇴 후 월 생활비와의 GAP을 분석한다. 물가상승률을 연 2~3%로 가정할 때 30년 은퇴 기간을 위한 필요자산은 월 생활비의 약 300~350배 수준이다. 세제혜택 활용을 위해 IRP 연 900만 원, ISA 연 2,000만 원 납입 한도를 최우선으로 채우도록 안내한다. 은퇴 10년 전부터는 포트폴리오 내 주식 비중을 점진적으로 줄이고 채권·연금보험 비중을 높이는 글라이드패스 전략을 적용하며, 적합성 재평가를 연 1회 의무 수행하고, 재평가 결과와 포트폴리오 변경 내역을 감사로그에 상세히 기록해야 한다.'),
        (4, 'seed-esg-investing', '[교육용] ESG 투자 가이드라인 매뉴얼',
         'urn:harness:manual:seed:esg-investing',
         'd4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5',
         '[교육용] ESG 투자는 환경(Environment)·사회(Social)·지배구조(Governance) 요소를 재무적 분석과 결합하여 장기 지속가능성이 높은 기업에 투자하는 방식이다. 국내 ESG 펀드는 한국거래소 ESG 등급 및 KCGS(한국기업지배구조원) 평가를 기준으로 편입 종목을 선정하며, 탄소중립 목표에 부합하는 기업을 우선 편입한다. PB는 고객에게 ESG 투자의 수익성과 비재무적 리스크 완화 효과를 설명할 의무가 있으며, 그린워싱(greenwashing) 펀드와의 구별 방법도 안내해야 한다. ESG 상품 권유 시 적합성 기준에 ESG 성향 항목을 추가 확인하고, 운용보고서 내 ESG 핵심 지표(탄소배출강도, 이사회 다양성 비율)를 고객이 이해할 수 있도록 설명한다. 분기마다 포트폴리오 ESG 점수 변화를 모니터링하여 사후관리 기록에 남긴다.'),
        (5, 'seed-alternative-investments', '[교육용] 대체투자 매뉴얼',
         'urn:harness:manual:seed:alternative-investments',
         'e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6',
         '[교육용] 대체투자는 전통 주식·채권 이외의 자산군으로 사모펀드(PE), 부동산 펀드(REITs·블라인드펀드), 인프라 펀드, 헤지펀드, 원자재를 포함한다. 포트폴리오 내 대체투자 편입은 전통자산과의 상관관계가 낮아 분산투자 효과를 높이지만, 유동성 위험·밸류에이션 불투명성·긴 의무보유기간(Lock-up)을 수반한다. 국내 규정상 일반투자자에게 사모펀드를 권유하려면 최소투자금액 1억 원 이상, 전문투자자 요건 충족 또는 위험고지 동의 절차를 거쳐야 한다. PB는 대체투자 상품 설명 시 유동성 제약, 환금 조건, 예상 수익 시나리오(기본·낙관·비관)를 표준화된 설명서에 포함시켜야 하며, 고객 서명 확인 후 감사로그를 남긴다. 부동산 펀드의 경우 공실률·임대수익률·레버리지 비율을 핵심 모니터링 지표로 분기 보고해야 한다.')
)
INSERT INTO documents(id, source_type_code, source_id, title, content_hash, raw_content, source_url, published_at)
SELECT ('aaaaaaaa-aaaa-aaaa-aaaa-' || lpad((4000 + doc_no)::text, 12, '0'))::uuid,
       'MANUAL', source_id, title, content_hash, raw_text, source_url, current_date
FROM manual_doc_seed
ON CONFLICT (id) DO UPDATE SET
    title = EXCLUDED.title,
    content_hash = EXCLUDED.content_hash,
    raw_content = EXCLUDED.raw_content,
    source_url = EXCLUDED.source_url,
    published_at = EXCLUDED.published_at;

/* sql_id: seed_40_manual_rag_chunks */
WITH chunk_data(doc_no, chunk_no, chunk_text) AS (
    VALUES
        -- Doc 1: 자산배분 전략 (6 chunks)
        (1, 0, '[교육용] 자산배분 전략의 핵심은 고객의 투자목표, 위험감내수준, 투자기간을 종합적으로 고려하여 주식·채권·대체투자의 최적 비중을 결정하는 것이다.'),
        (1, 1, '[교육용] 전통적인 60/40 포트폴리오(주식 60%, 채권 40%)는 역사적으로 안정적인 장기 성과를 보여왔으나 저금리 환경에서는 채권 수익률 하락으로 대안 자산 편입 필요성이 높아진다.'),
        (1, 2, '[교육용] PB는 고객 면담 시 목표수익률과 최대손실허용액(Maximum Drawdown)을 명확히 파악한 후 전략적 자산배분(SAA)과 전술적 자산배분(TAA)을 구분하여 제안해야 한다.'),
        (1, 3, '[교육용] 전략적 자산배분(SAA)은 장기 목표 비중으로 연 1회 리밸런싱을 원칙으로 하며, 전술적 자산배분(TAA)은 시장 환경 변화에 따라 단기적으로 ±10% 범위 내에서 조정 가능하다.'),
        (1, 4, '[교육용] 리밸런싱 실행 전에는 반드시 적합성 확인 절차를 완료하고 고객에게 설명의무를 이행해야 하며, 해당 사항은 감사 로그로 기록되어야 한다.'),
        (1, 5, '[교육용] 자산배분 리뷰는 고객 생애주기 변화(결혼, 자녀 교육, 은퇴 근접)에 따라 수시로 조정하며, 연 1회 이상 정기 면담을 통해 포트폴리오 적합성을 재평가한다.'),
        -- Doc 2: KYC/EDD 고객확인절차 (6 chunks)
        (2, 0, '[교육용] KYC(고객확인제도)는 자금세탁방지법 및 특정금융정보법에 따라 PB가 신규 고객 등록 시 실명확인, 직업·소득원천 확인, 거래목적 파악을 의무적으로 수행해야 하는 규제 절차다.'),
        (2, 1, '[교육용] EDD(강화된 고객확인)는 정치적 주요인물(PEP), 고위험 국가 관련 거래, 비정상적으로 고액인 거래 등 고위험 고객에게 적용하며 자금 출처 확인 서류와 최종수익자 확인이 필수다.'),
        (2, 2, '[교육용] 고객정보는 거래 종료 후 5년간 보존해야 하며, 의심거래(STR)는 사유 발생 후 3영업일 이내에 금융정보분석원(KoFIU)에 보고해야 한다.'),
        (2, 3, '[교육용] KYC 재확인 주기는 위험등급에 따라 차별화하며, 고위험 고객은 연 1회, 중위험 고객은 2년마다 재확인 절차를 수행하고 갱신 기록을 시스템에 남긴다.'),
        (2, 4, '[교육용] EDD 수행 시 연간 거래한도 설정, 이상거래 모니터링 임계값 설정을 병행하며, 임계값 초과 시 자동으로 준법감시팀에 알림이 발송되도록 설정한다.'),
        (2, 5, '[교육용] KYC/EDD 정보는 접근권한이 부여된 PB와 준법감시팀에 한해 열람 가능하며, 개인정보 열람 및 정정 요청 시 접수일로부터 10영업일 이내에 처리해야 한다.'),
        -- Doc 3: 은퇴설계 (6 chunks)
        (3, 0, '[교육용] 은퇴설계는 고객의 은퇴 후 필요한 월 생활비를 기준으로 역산하여 현재 시점에서 목표 자산규모를 도출하는 재무계획 프로세스로, PB의 핵심 서비스 영역이다.'),
        (3, 1, '[교육용] 은퇴 자산 GAP 분석 시 국민연금 예상 수령액, 퇴직연금(DB·DC·IRP) 잔액, 개인연금 적립액을 합산하고 물가상승률(연 2~3%) 적용 후 은퇴 후 월 생활비와의 부족분을 산출한다.'),
        (3, 2, '[교육용] 물가상승률 2.5% 가정 시 30년 은퇴 기간을 위한 필요 자산은 은퇴 시점 월 생활비의 약 300~350배 수준이며, 이를 현재가치로 환산하여 목표 저축액을 역산한다.'),
        (3, 3, '[교육용] 세제혜택 극대화를 위해 IRP 연 900만 원, ISA 연 2,000만 원 납입 한도를 최우선으로 채우도록 안내하며, 연금저축보험·펀드의 세액공제 한도(연 600만 원)도 활용한다.'),
        (3, 4, '[교육용] 은퇴 10년 전부터 글라이드패스(Glidepath) 전략을 적용하여 주식 비중을 점진적으로 축소하고 채권·연금보험 비중을 높임으로써 시퀀스 리스크(Sequence of Returns Risk)를 완화한다.'),
        (3, 5, '[교육용] 은퇴 설계 포트폴리오는 연 1회 의무 적합성 재평가를 수행하며, 건강 상태 변화·가족 구성원 변화 등 생애 이벤트 발생 시 즉시 재검토 절차를 개시한다.'),
        -- Doc 4: ESG 투자 가이드라인 (6 chunks)
        (4, 0, '[교육용] ESG 투자는 환경(E)·사회(S)·지배구조(G) 요소를 재무 분석에 통합하여 장기 지속가능성이 높은 기업에 투자하는 방식으로, 비재무적 리스크를 체계적으로 관리하는 투자 전략이다.'),
        (4, 1, '[교육용] 국내 ESG 펀드 편입 종목 선정 기준으로 한국거래소 ESG 등급과 KCGS(한국기업지배구조원) 평가를 활용하며, 탄소중립 목표 달성 로드맵 보유 기업에 가점을 부여한다.'),
        (4, 2, '[교육용] PB는 ESG 상품 권유 시 수익성 뿐만 아니라 그린워싱(Greenwashing) 펀드와의 구별 방법을 고객에게 설명해야 하며, EU Taxonomy 기준 부합 여부를 확인 자료로 제시할 수 있다.'),
        (4, 3, '[교육용] ESG 상품 권유 전 적합성 평가 항목에 고객의 ESG 선호도(환경 중시 여부, 사회적 책임 투자 의향)를 추가 확인하고 그 결과를 상담 기록에 반영해야 한다.'),
        (4, 4, '[교육용] 운용보고서에는 포트폴리오 내 탄소배출강도(tCO2e/매출 백만 원), 이사회 여성 비율, 중대 ESG 사건(환경 사고·노동분쟁) 발생 현황 등 핵심 ESG 지표를 필수 공시한다.'),
        (4, 5, '[교육용] ESG 포트폴리오 모니터링은 분기마다 ESG 점수 변화를 추적하며, 편입 종목의 ESG 등급이 2단계 이상 하락 시 사후관리 이벤트를 자동 생성하여 PB에게 알린다.'),
        -- Doc 5: 대체투자 (6 chunks)
        (5, 0, '[교육용] 대체투자 자산군은 사모펀드(PE), 부동산 펀드(REITs·블라인드펀드), 인프라 펀드, 헤지펀드, 원자재로 구성되며 전통자산과의 낮은 상관관계로 포트폴리오 분산 효과를 제공한다.'),
        (5, 1, '[교육용] 대체투자의 주요 리스크는 유동성 위험, 밸류에이션 불투명성, 긴 의무보유기간(Lock-up 3~7년)이며 PB는 이를 고객에게 명확히 설명하고 서면 동의를 받아야 한다.'),
        (5, 2, '[교육용] 국내 규정상 일반투자자에게 사모펀드를 권유하려면 최소투자금액 1억 원 이상 요건을 충족하거나 전문투자자 등록 절차를 완료하고 위험고지 동의서를 수령해야 한다.'),
        (5, 3, '[교육용] 대체투자 상품 설명서에는 유동성 제약 조건, 환금(조기상환) 신청 가능 시기, 기본·낙관·비관 시나리오별 예상 수익률과 손실 한도를 반드시 포함해야 한다.'),
        (5, 4, '[교육용] 부동산 펀드 사후관리 핵심 지표는 공실률, 임대수익률(Cap Rate), 레버리지 비율(LTV)이며, 분기마다 운용사 보고서를 검토하여 이상 징후 발생 시 고객에게 즉시 통보한다.'),
        (5, 5, '[교육용] 대체투자 편입 시 포트폴리오 전체 유동성 비율이 고객이 동의한 최소 유동성 기준(통상 30%)을 하회하지 않도록 자산배분 점검을 사전에 수행하고 감사로그를 기록한다.')
)
INSERT INTO document_chunks(id, document_id, chunk_no, chunk_text, embedding, token_count, is_embedded)
SELECT ('aaaaaaaa-aaaa-aaaa-cccc-' || lpad((4000 + doc_no * 10 + chunk_no)::text, 12, '0'))::uuid,
       ('aaaaaaaa-aaaa-aaaa-aaaa-' || lpad((4000 + doc_no)::text, 12, '0'))::uuid,
       chunk_no,
       chunk_text,
       NULL,
       length(chunk_text),
       FALSE
FROM chunk_data
ON CONFLICT (document_id, chunk_no) DO UPDATE SET
    chunk_text = EXCLUDED.chunk_text,
    embedding = NULL,
    token_count = EXCLUDED.token_count,
    is_embedded = FALSE;

/* sql_id: seed_40_manual_rag_batch_logs */
INSERT INTO batch_job_logs(id, job_name, job_type_code, status_code, started_at, finished_at, rows_collected, rows_skipped, rows_failed, error_message)
VALUES
    ('f0f0f0f0-f0f0-f0f0-f0f0-000000004001', 'seed_full_mvp_operational_baseline', 'SEED', 'DONE', now() - interval '5 minutes', now() - interval '4 minutes', 20, 0, 0, NULL),
    ('f0f0f0f0-f0f0-f0f0-f0f0-000000004002', 'manual_baseline_transform', 'DOCUMENT_TRANSFORM', 'DONE', now() - interval '4 minutes', now() - interval '3 minutes', 5, 0, 0, NULL),
    ('f0f0f0f0-f0f0-f0f0-f0f0-000000004003', 'bge_embedding_refresh', 'EMBEDDING_REFRESH', 'SKIPPED', now() - interval '3 minutes', now() - interval '2 minutes', 0, 1, 0, 'Internal BGE not invoked by seed; run embedding batch with configured service.'),
    ('f0f0f0f0-f0f0-f0f0-f0f0-000000004004', 'broker_market_collector', 'PROVIDER', 'SKIPPED', now() - interval '3 minutes', now() - interval '2 minutes', 0, 1, 0, 'Provider collector requires configured BROKER credentials and real endpoint.'),
    ('f0f0f0f0-f0f0-f0f0-f0f0-000000004005', 'dart_disclosure_collector', 'PROVIDER', 'SKIPPED', now() - interval '3 minutes', now() - interval '2 minutes', 0, 1, 0, 'Provider collector requires configured DART credentials and real endpoint.')
ON CONFLICT (id) DO UPDATE SET
    status_code = EXCLUDED.status_code,
    finished_at = EXCLUDED.finished_at,
    rows_collected = EXCLUDED.rows_collected,
    rows_skipped = EXCLUDED.rows_skipped,
    rows_failed = EXCLUDED.rows_failed,
    error_message = EXCLUDED.error_message;
