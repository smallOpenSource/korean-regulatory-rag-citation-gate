# BIZ-03 House View

## Purpose
전사 공통 투자 관점을 정의하고 고객 상담에 **일관되게** 적용한다.
AI가 시장 데이터를 기반으로 초안을 생성하고 ADMIN이 검토·활성화한다.

## Lifecycle
```
DRAFT → PENDING_REVIEW → ACTIVE → SUPERSEDED → ARCHIVED
```
- DRAFT: 생성 직후. ADMIN이 편집 가능.
- PENDING_REVIEW: 검토 요청 상태. 변경 제한.
- ACTIVE: 전사 적용 중. 동시에 1개만 허용.
- SUPERSEDED: 신규 ACTIVE 생성 시 자동 전환.
- ARCHIVED: 영구 보존. 삭제 불가.

## Content Structure (house_views 테이블)
- summary: 시장 총평 (300자 이내)
- asset_views_json: [{asset_class, stance(overweight|neutral|underweight), rationale}]
- model_portfolios_json: [{profile, allocation[{asset_class, weight_pct}]}]
- risks_json: [string]

## Consultation 연계
- 상담 생성 시 현재 ACTIVE house_view_id를 기본 연결.
- 승인 전 house view는 상담 기본값으로 사용 금지.
- 적용 이력은 house_view_applications 테이블에 기록.
