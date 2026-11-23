# OPS-01 Server Setup

## Stack
- OS: Rocky Linux 8
- Python: /opt/conda/envs/wm_env/bin/python (3.11.5)
- DB: PostgreSQL 17 + pgvector extension
- Cache: Redis 7
- Reverse Proxy: Nginx
- Process Manager: systemd (or supervisord)

## PostgreSQL Setup
```sql
/* sql_id: setup_create_vector_extension */ CREATE EXTENSION IF NOT EXISTS vector;
/* sql_id: setup_create_harness_database */ CREATE DATABASE harness;
/* sql_id: setup_create_harness_app_user */ CREATE USER harness_app WITH PASSWORD '...';
/* sql_id: setup_grant_harness_database */ GRANT ALL PRIVILEGES ON DATABASE harness TO harness_app;
```

## Migration
```bash
cd <repo-root>
/opt/conda/envs/wm_env/bin/python db/migrator.py
```

## Service Files
- harness-api.service: FastAPI (uvicorn, port 8000)
- harness-scheduler.service: `scripts/run_batch_scheduler.py --run-once` loop or supervisor-managed batch scheduler, using the same Redis-locking runner
- harness-web.service: Nginx serving React build (port 80/443)

## Nginx Config
- /api/ → proxy_pass http://127.0.0.1:8000
- /ws → reserved backend WebSocket proxy target. WebSocket push is `backlog/not-current-contract` until ADR-001 is implemented; current browser/API operations use `/api`, `/health`, `/batch/status`, and `/data/readiness`.
- / → root <repo-root>/apps/web/dist

## Local PoC Lifecycle Scripts
```bash
cd <repo-root>
scripts/start.sh
scripts/status.sh --deep --no-fail
scripts/stop.sh
```

- `scripts/start.sh`: starts FastAPI/Uvicorn and Vite with `.env` loaded without printing
  secret values. It first runs a raw-SQL PostgreSQL preflight using the configured `.env`;
  authentication or connectivity failures stop startup before Uvicorn is launched. API receives
  backend `.env`; web/npm child processes receive only safe shell variables plus `VITE_*` and
  `HARNESS_*`. When `setsid` is available, child processes are launched in a detached session so
  they remain running after the invoking shell exits.
- `CORS_ENABLED=false` is the local default. Browser calls use the same-origin `/api` path through
  the Vite dev proxy or Nginx `/api/` proxy, not cross-origin API calls.
- If production/staging deploys the frontend on a different origin, enable credentialed CORS only
  with exact `CORS_ALLOWED_ORIGINS` values and the intended refresh-cookie attributes
  (`AUTH_REFRESH_COOKIE_SECURE`, `AUTH_REFRESH_COOKIE_SAMESITE`, `AUTH_REFRESH_COOKIE_PATH`).
  Do not use `*` with credentials.
- `scripts/stop.sh`: stops PID-file-managed local PoC processes.
- `scripts/status.sh`: checks PID files and local HTTP endpoints; `--deep` also pings configured
  PostgreSQL and Redis with class-only failure reasons. HTTP endpoints are healthy only on 2xx.
  Use `--no-fail` to capture honest `status=blocked failures=N no_fail=1` evidence without
  converting unavailable local dependencies into a green result. See OPS-04.
- `HARNESS_DRY_RUN=1` or `--dry-run` prints intended lifecycle actions without starting or stopping
  processes.
- `HARNESS_API_HOST`, `HARNESS_API_PORT`, `HARNESS_WEB_HOST`, and `HARNESS_WEB_PORT` override local
  bind addresses and ports.
- `HARNESS_STATUS_TIMEOUT_SECONDS` and `HARNESS_STOP_TIMEOUT_SECONDS` tune status HTTP and graceful
  shutdown waits.
- `HARNESS_AUTO_NPM_INSTALL=1` allows `scripts/start.sh` to run `npm ci` when
  `apps/web/node_modules` is absent; default behavior is to fail closed instead of doing unexpected
  network install work.

## Synthetic PoC Login Accounts
These accounts are synthetic seed data from `db/fixtures/seed_synthetic.sql`.

| Role | Email | Password |
|---|---|---|
| PB | synthetic.pb1@example.invalid | HarnessSynthetic!2026 |
| WM | synthetic.wm1@example.invalid | HarnessSynthetic!2026 |
| ADMIN | synthetic.admin@example.invalid | HarnessSynthetic!2026 |

Before logging in, run migrations and apply the synthetic fixture. If `CREATE EXTENSION vector`
fails with insufficient privilege, a DB administrator must install/enable `vector` and `pgcrypto`
for the configured database, then rerun the migration and seed steps.
