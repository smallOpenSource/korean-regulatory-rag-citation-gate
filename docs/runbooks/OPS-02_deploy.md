# OPS-02 Deploy

## Checklist (순서 준수)
1. 환경변수 확인 (CFG-01 목록 전체).
2. `git pull` → 최신 코드.
3. `pip install -r requirements.txt`.
4. `python db/migrator.py` (DB migration).
5. `systemctl restart harness-api`.
6. `scripts/run_batch_scheduler.py --plan-only`로 scheduler/provider governance를 확인한 뒤 `systemctl restart harness-scheduler`.
7. `cd apps/web && npm ci && npm run build` → Nginx 재로드.
8. /health 엔드포인트 200 응답 확인.
9. 배치 monitor 화면에서 scheduler 정상 동작 확인; serviceable top-200 job은 official KRX governance가 완전하지 않으면 `BLOCKED`가 정상이다.
10. `scripts/verify_total_product_readiness.py --verification-gate-report <gate.md> --serviceable-result-json .omx/specs/autoresearch-service-readiness-top200-30d/result.json --result-json .omx/reports/verification/total-product-readiness-result.json`를 실행해 total-product readiness를 확인한다. 이 단계는 Playwright/E2E, required-provider batch, serviceable top-200, hostile false-green controls 중 하나라도 빠지면 실패해야 한다.

## Rollback
- 코드: `git revert` + 재배포.
- DB: 롤백 migration SQL 작성 후 실행 (Alembic 없음).
- 데이터 백업: 배포 전 pg_dump 필수.

## Operations Status Evidence
- 배포 후 상태 증거는 OPS-04 순서를 따른다: `scripts/status.sh --deep --no-fail`, `/health`, `/batch/status`, `/data/readiness`, 그리고 관련 `.omx/reports/` 경로.
- WebSocket push 알림은 `backlog/not-current-contract`이므로 배포 성공 또는 배치 실패 알림의 필수 증거로 사용하지 않는다.
- 실패 로그와 리포트에는 provider key, bearer token, SMTP credential, database password를 출력하지 않는다.
