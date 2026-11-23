# BIZ-01 Glossary

## Business Terms
| 용어 | 설명 |
|---|---|
| PB (Private Banker) | 고액자산가 전담 금융 서비스 직원 |
| WM (Wealth Manager) | 종합 자산관리 담당 직원 (PB 상위 개념) |
| HNWI | High Net Worth Individual. 금융자산 10억원 이상 고객 |
| 하우스뷰 | 전사 공통 월별 투자 관점 및 자산배분 권고안 |
| 후속 조치(NBA, Next Best Action) | AI 또는 이벤트 기반 PB 다음 최우선 행동 추천. 화면에서는 "후속 조치"로 표기한다. |
| KI (Knock-In) | ELS/DLS에서 기초자산 가격이 barrier 아래로 떨어지는 사건 |
| ELS | Equity Linked Securities. 주가 연계 파생상품 |
| DLS | Derivative Linked Securities. 기초자산 연계 파생상품 |
| 랩 (Wrap) | 일임형 자산관리 계좌. PB가 재량 운용 |
| 신탁 | 금전·재산을 수탁자에게 이전하여 관리·운용하는 계약 |
| 적합성 원칙 | 고객 위험 성향에 맞는 상품만 권유 (자본시장법 제46조) |
| 설명의무 | 상품 주요 내용·위험·수수료를 고객에게 충분히 설명할 의무 (제47조) |

## 상태 코드(기술 사양)
| 엔티티 | 코드 허용값 | 화면 표시 |
|---|---|
| consultations | DRAFT \| SAVED \| COMPLETED | 초안 \| 저장됨 \| 완료 |
| house_views | DRAFT \| PENDING_REVIEW \| ACTIVE \| SUPERSEDED \| ARCHIVED | 초안 \| 검토 대기 \| 활성 \| 대체됨 \| 보관 |
| nba_actions | PENDING \| IN_PROGRESS \| DONE \| SNOOZED \| DISMISSED | 대기 \| 진행 중 \| 완료 \| 보류 \| 해제 |
| aftercare_events | OPEN \| IN_PROGRESS \| RESOLVED | 진행 필요 \| 진행 중 \| 해결 |
| email_drafts | DRAFT \| APPROVED \| SENT \| CANCELLED | 초안 \| 승인 \| 발송 \| 취소 |
| batch_job_logs | RUNNING \| DONE \| FAILED \| SKIPPED | 실행 중 \| 완료 \| 실패 \| 건너뜀 |

## Code Tables
- priority_code: URGENT(긴급) \| HIGH(높음) \| MEDIUM(보통) \| LOW(낮음)
- role_code: PB \| WM \| BRANCH_MANAGER \| ADMIN \| AUDIT_VIEWER
- segment_code: HNWI_CORE \| HNWI_ULTRA \| EMERGING_HNWI
- channel_code: FACE_TO_FACE \| PHONE \| VIDEO \| WRITTEN
- source_type_code: DART \| REG_PAGE \| RESEARCH \| MANUAL \| WEB_SEARCH
- product_type_code: FUND \| BOND \| ELS_DLS \| WRAP \| TRUST \| DEPOSIT
