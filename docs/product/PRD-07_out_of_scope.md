# PRD-07 Scope Boundaries

## PoC 포함 범위 (규제 샌드박스/합성 데이터 전제)
- 고객 직접 사용처럼 보이는 동의/확인 흐름은 별도 고객 포털이 아니라 **직원 화면 내 고객 기능 시뮬레이션**으로 구현한다.
- 주문 흐름은 실제 주문 전송이 아니라 **주문 시뮬레이션**으로 구현한다.
- AI의 상품·포트폴리오 제안은 직원 의사결정 보조이며, 확정 권유/집행 전 4-gate를 반드시 통과해야 한다.
- 4-gate: suitability pass + explanation check + simulated customer consent + employee final approval.
- 모든 위반/차단/승인 이벤트는 audit_logs에 기록한다.

## 운영/프로덕션 제외
- 실제 고객용 B2C 포털 공개.
- 실제 주문 자동 실행 또는 고객 계좌에 대한 주문 전송.
- AI 단독의 투자 권유 확정 또는 직원 승인 없는 고객 전달.
- 실제 고객 개인정보/계좌/주문 데이터 사용.
- 무제한 멀티테넌트 SaaS 운영.

## MVP 이후 검토 가능
- PDF report generation.
- Multi-language UI.
- 다기관 SaaS 운영 모델.

## Architecture 금지
- ORM (JPA/Hibernate/MyBatis Mapper/SQLAlchemy ORM 등).
- Flyway / Liquibase / Alembic.
- enum class를 상태값으로 사용.
- 실제 고객 데이터 테스트 환경 사용.
- mock/test double/local simulator 기반 외부 연동 검증.
- 하드코딩된 모델명·API키·URL·timeout·스케줄.
