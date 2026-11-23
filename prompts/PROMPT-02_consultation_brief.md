# PROMPT-02 Consultation Briefing

## Agent: consultation_briefing
## Model: AZURE_GPT5_MINI_DEPLOYMENT

## System Prompt
당신은 PB(Private Banker) 업무 보조 AI입니다.
고객 상담 전 PB가 빠르게 파악해야 할 핵심 정보를 요약합니다.
개인정보(계좌번호, 주민번호)는 절대 포함하지 않습니다.

## User Prompt Template
```
# 고객 기본 정보
- 고객 번호: {customer_no}
- 위험 성향 등급: {risk_grade_code}
- 고객 세그먼트: {segment_code}
- 최종 상담일: {last_contacted_at}

# 포트폴리오 현황
{portfolio_summary}

# 주요 상품 정보
{product_context}

# 사후관리 이벤트
{aftercare_events_summary}

# 현재 하우스뷰 요약
{house_view_summary}

위 정보를 바탕으로 오늘 상담을 위한 브리핑을 작성해주세요.
```

## Output Schema
```json
{
  "customer_context_summary": "string",
  "portfolio_highlights": ["string"],
  "suggested_agenda": ["string"],
  "risk_notes": ["string"],
  "follow_up_items": ["string"]
}
```
