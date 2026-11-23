# DEV-01 Development Conventions

## Python
- Python 3.11.5 (/opt/conda/envs/wm_env/bin/python)
- 패키지 관리: pip + requirements.txt (conda 환경)
- 스타일: Black + Ruff (line-length=120)
- 타입 힌팅: 함수 인자 및 반환값에 필수
- SQL: 항상 `/* sql_id: short_readable_id */` 주석 포함

## File Size
- 300줄 권장, 500줄 절대 상한.
- 역할 분리: router.py / service.py / repository.py / schema.py

## Function Rules
- chain 깊이 3단계 이내.
- side effect 있는 함수와 없는 함수 분리.
- DB 접근 함수는 repository.py 전용.

## Frontend
- React 18 + TypeScript + Vite
- 상태관리: Zustand (localStorage 사용 금지)
- 서버 상태: TanStack Query
- 스타일: Tailwind CSS v4
- 컴포넌트: shadcn/ui 기반
- 라우터: React Router v6 (protected routes)

## SQL Conventions
- SELECT 절에 * 금지.
- 파라미터 바인딩: $1, $2 (asyncpg 스타일).
- 트랜잭션: 여러 INSERT/UPDATE는 반드시 트랜잭션으로 묶음.

## Git Conventions
- 브랜치: feature/{task-id}-{short-description}
- 커밋: [{task-id}] {action}: {description}
- PR: 코드 + 관련 docs 변경사항 포함

## Implemented Code Foundation
- Backend Python package root: `apps/api/harness`.
- Core helpers live under `apps/api/harness/core` for config, raw-SQL validation, DB pool helpers, Redis locks, RBAC, audit codes, logging redaction, and JWT/password primitives.
- Run backend/static foundation tests with `/opt/conda/envs/wm_env/bin/python -m pytest`.
- Run modified-file lint with `/opt/conda/envs/wm_env/bin/python -m ruff check apps/api/harness/core apps/api/harness/main.py db tests/test_config_security.py tests/test_sql_contracts.py`.
- Do not log raw `.env` values; use `AppConfig.safe_dict()` for diagnostics.
