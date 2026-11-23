# DB-01 Conceptual Model

## Core Entities
| 엔티티 | 설명 |
|---|---|
| branches | 지점 마스터 |
| employees | PB/WM/관리자 직원 |
| customers | 고액자산가 고객 |
| risk_assessments | 고객 위험 성향 설문 이력 |
| portfolios | 고객별 포트폴리오 |
| portfolio_holdings | 포트폴리오 보유 상품 내역 |
| products | 금융상품 마스터 |
| consultations | 상담 기록 |
| consultation_notes | 상담 중 작성 노트 |
| house_views | 월별 하우스뷰 |
| house_view_applications | 상담에 적용된 하우스뷰 연결 |
| nba_actions | AI 생성 또는 이벤트 기반 다음 최적 액션 |
| aftercare_events | 만기·KI·손실 등 사후관리 이벤트 |
| documents | 수집 문서 메타데이터 |
| document_chunks | RAG용 청크 + 벡터 임베딩 |
| audit_logs | 중요 행위 감사 이력 (append-only) |
| email_drafts | AI 생성 이메일 초안 |

## Batch Entities
| 엔티티 | 설명 |
|---|---|
| batch_job_logs | 배치 실행 이력 |
| raw_documents | 수집 원문 |
| source_licenses | 시장/공시 원천 라이선스 및 사용 가능 상태 |
| securities | 국내(KR) 상장주식 마스터 |
| security_identifiers | 종목코드/ISIN/KRX 단축코드 식별자 |
| product_underlyings | 상품과 국내 상장주식 기초자산 연결 |
| trading_calendar | KOSPI/KOSDAQ/KONEX 거래일 달력 |
| market_data_evidence | 원천 payload/backfill/reconciliation/quality 증거 |
| market_price_bars | 국내 상장주식 일별 OHLCV 시세 |
| corporate_actions | 배당/분할 등 국내 주식 corporate action |
| market_data_quality_checks | 시세 품질 점검 결과 |
| market_prices | 레거시 시세 테이블(쓰기 금지, V012 이후 사용 금지) |
| financial_ratios | 재무비율 (PER/PBR/ROE 등) |
| investor_flows | 펀드 자금 흐름 |
| macro_indicators | 거시경제 지표 |

## Core Relationships
- employee(branch_id) → branches
- customer(assigned_pb_id) → employees, customer(branch_id) → branches
- risk_assessment(customer_id) → customers
- portfolio(customer_id) → customers
- portfolio_holding(portfolio_id) → portfolios, (product_id) → products
- consultation(customer_id) → customers, (employee_id) → employees, (house_view_id) → house_views
- consultation_note(consultation_id) → consultations
- house_view_application(house_view_id) → house_views, (consultation_id) → consultations
- nba_action(customer_id) → customers, (employee_id) → employees
- aftercare_event(customer_id) → customers, (product_id) → products
- document_chunk(document_id) → documents
- email_draft(customer_id) → customers, (employee_id) → employees, (consultation_id) → consultations
