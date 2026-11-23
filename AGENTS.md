# AGENTS.md

## Purpose
Harness는 PB/WM 직원의 고액자산가 고객 관리 업무를 지원하는 내부형 AI 웹서비스다.
AI는 의사결정 보조만 수행하고 최종 판단 책임은 직원과 소속 금융기관에 있다.

## Must Read Order (first task on any new session)
1. docs/product/PRD-01_product_overview.md
2. docs/product/PRD-04_user_scenarios.md
3. docs/business/BIZ-02_pb_wm_workflow.md
4. docs/business/BIZ-06_compliance.md
5. docs/db/DB-02_logical.md
6. docs/api/API-01_contracts.yaml
7. docs/ai/AI-02_agent_spec.yaml
8. docs/batch/BATCH-01_pipeline_overview.md
9. docs/dev/DEV-01_dev_conventions.md

## Hard Rules
- Project root: 저장소 루트(`<repo-root>`)
- Python: /opt/conda/envs/wm_env/bin/python (3.11.5)
- ORM 금지, Flyway/Alembic 금지.
- SQL은 순수 SQL만 사용.
- SQL 형식: `/* sql_id: short_human_readable_id */ {sql_text}`
- 합성 데이터 외 하드코딩 금지, mocking 금지, enum class 금지.
- 상태값은 DB varchar + CHECK constraint 또는 lookup table 사용.
- 파일 길이 300라인 권장, 500라인 드문 예외.
- function chain 깊이 3단계 이내.
- 고객 개인정보 원문을 로그와 프롬프트에 넣지 않는다.
- 모델명, 키, URL, timeout, 배치 스케줄은 코드 하드코딩 금지 → env 또는 docs 기준.

## Project Structure
```
apps/api/       FastAPI backend
apps/web/       React + Vite frontend
db/migrations/  Versioned SQL (V001__*.sql ...)
db/migrator.py  Custom migration runner
docs/           Business and implementation specs
prompts/        LLM prompt templates
.omx/           Runtime pid/log/report output (gitignored, created on demand)
```

## Doc Sync Rules
- DB 변경 → docs/db/ + migration SQL 동시 갱신.
- API 변경 → docs/api/API-01_contracts.yaml 동시 갱신.
- AI 기능 변경 → docs/ai/* + prompts/* 동시 갱신.
- 배치 변경 → docs/batch/* 동시 갱신.
- 작업 완료 후 PLANS.md, MEMORIES.md, BACKLOG.md 상태 갱신.

## Security Hard Rules
- RBAC 위반 구현 금지.
- 설명의무·적합성 체크 없는 권유 흐름 구현 금지.
- 감사로그 없는 AI 생성 기능 구현 금지.
- AI 생성 내용은 UI에 생성 시각·모델명 표기 필수.
