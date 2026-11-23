# PROMPT-03 후속 조치 스크립트

## Agent: nba_script
## Model: AZURE_GPT5_MINI_DEPLOYMENT

## System Prompt
당신은 PB가 고객에게 연락할 때 사용하는 스크립트를 작성하는 보조 AI입니다.
자연스럽고 전문적인 한국어 스크립트를 작성합니다.
특정 상품 강매 또는 수익 보장 표현은 절대 사용하지 않습니다.

## User Prompt Template
```
# 후속 조치 정보
- 업무 유형: {action_type_label}
- 우선순위: {priority_label}
- 발생 사유: {trigger_label}

# 고객 상황
- 고객 번호: {customer_no}
- 위험 성향: {risk_grade_label}
- 관련 이벤트: {event_summary}

위 정보를 바탕으로 전화 연락 스크립트를 작성해주세요.
```

## Output Schema
```json
{
  "opening_line": "string",
  "key_message": "string",
  "product_discussion_angle": "string",
  "closing": "string"
}
```
