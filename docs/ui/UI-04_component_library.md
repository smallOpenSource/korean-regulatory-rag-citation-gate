# UI-04 Component Library

## Base: shadcn/ui + Tailwind CSS v4

## Core Components
- **StatusBadge**: 상태 코드 → 한국어 색상 뱃지. 준비/활성/승인/완료/신선/검증 통과는 녹색,
  차단/실패/미확인은 빨간색, 주의/건너뜀/오래됨/검증 전/합성 데이터는 주황색.
- **PriorityBadge**: 우선순위 코드 → 긴급/높음/보통/낮음 한국어 색상 뱃지
- **AIGeneratedBadge**: "AI 생성 · {generated_at} · {model}" 표시 (필수, 생략 불가)
- **SyntheticNoticeBanner**: `synthetic_customer_notice`를 Customer 360/Dashboard에 노출해
  고객·포트폴리오 데이터가 합성임을 명시한다.
- **MarketEvidenceFacts**: 출처, 기준시각(`source_as_of`), 신선도, 품질 상태를 작은 fact 카드로
  표시한다. 출처가 없으면 "출처 미확인", 기준시각(`source_as_of`)이 없으면 "미확인"으로 표시한다.
- **ProviderModePanel**: Batch Monitor에서 profile, strict_external, required_provider_codes,
  problem_count를 보여주며 local/SKIPPED/FAILED 상태를 green success로 표시하지 않는다.
- **CustomerCard**: 고객 기본 정보 + 위험등급 + 자산 요약
- **PortfolioDonut**: 자산배분 도넛 차트 (Recharts)
- **후속조치카드**: 업무 유형 + 우선순위 + 기한 + 스크립트 요약
- **ConsultationTimeline**: 상담 이력 타임라인
- **ComplianceChecklist**: suitability_checked + explanation_checked 체크박스
- **HouseViewPanel**: 하우스뷰 요약 + asset_views 테이블
- **RAGCitations**: 인용 번호 클릭 시 원문 표시 패널

## Global Layout
- 좌측 사이드바: 네비게이션 메뉴 (고객 목록, 후속 조치 관리함, 하우스뷰, 배치 모니터, 감사로그)
- 상단 헤더: 로고, 사용자명, 로그아웃
- 메인 영역: 단일 스크롤 컨텐츠
- 우측 패널: RAG Q&A 패널 (토글)

## Responsive
- PC 우선 (1280px+), 태블릿 (768px) 지원.
- 모바일은 MVP 범위 외.
