# AI-05 Async Endpoint Matrix

## Rule
- 202를 반환하는 AI endpoint는 durable `ai_jobs`를 반드시 생성한다.
- 200을 반환하는 synchronous AI endpoint도 audit_logs와 AI output metadata를 반드시 기록한다.
- 모든 AI 생성 결과는 `ai_outputs`에 generated_at, model_name, agent_id, resource link를 저장한다.

| endpoint | agent_id | sync/async | response | ai_jobs | audit_logs | ai_outputs | future websocket event |
|---|---|---|---|---|---|---|---|
| POST /customers/{customer_id}/portfolio-analysis | portfolio_analysis | async | 202 job_id | yes | yes | yes | ai_job_done after ADR-001; polling remains current |
| POST /consultations/{consultation_id}/briefing | consultation_briefing | async | 202 job_id | yes | yes | yes | ai_job_done after ADR-001; polling remains current |
| POST /consultations/{consultation_id}/compliance-check | compliance_check | sync | 200 passed/issues | no | yes | yes | no |
| POST /house-views/{house_view_id}/generate | house_view_generation | async | 202 job_id | yes | yes | yes | ai_job_done after ADR-001; polling remains current |
| POST /email-drafts | email_draft | sync staff-authored draft | 201 draft_id/status | no | no send audit on draft creation | no AI output for staff-authored draft (`ai_output_id=null`) | no |
| POST /email-drafts/{draft_id}/send | email_draft | sync provider-gated send | 200 SENT or 503 BLOCKED | no | sandbox 발송 성공 시 `email_sent_via_sandbox`; `email_draft_send` 는 real-SMTP 예약(ADR-002 금지) | no new output | no |
| POST /rag/query | rag_qa | sync | 200 answer/citations | no | yes | yes | no |
| NBA batch script generation | nba_script | async internal | ai_jobs-linked batch result | yes | yes | yes | nba_created after ADR-001 |

## Metadata Display
- UI는 ai_outputs.generated_at + ai_outputs.model_name을 사용해 `AI 생성 · {generated_at} · {model}` 배지를 표시한다.
- domain table에 중복 저장된 generated_at/model_name이 있더라도 ai_outputs가 감사/표시 기준 원천이다.
