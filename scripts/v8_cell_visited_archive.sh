#!/usr/bin/env bash
# v8_cell_visited_archive.sh
# nightly cron candidate — v8_cell_visited rows 90d 이전 분을 audit_logs_v8_archive 에 복제
#
# 설계 원칙 (PRD §5.5 observability):
#   - audit_logs row 는 절대 DELETE 하지 않는다 (V008+V019 append-only 보장)
#   - 90d 이전 v8_cell_visited row 를 audit_logs_v8_archive 에 INSERT (복제)
#   - 중복 방지: archive 테이블의 id 와 충돌 시 ON CONFLICT DO NOTHING
#   - application query 시 최신 90d 는 audit_logs, 이전 분은 archive 우선
#
# 사용법:
#   DATABASE_URL=postgresql://... bash v8_cell_visited_archive.sh
#   또는 crontab: 0 3 * * * DATABASE_URL=... /path/to/v8_cell_visited_archive.sh
#
# 환경변수:
#   DATABASE_URL  — PostgreSQL 접속 URL (필수)
#   RETENTION_DAYS — 보존 기간(일), 기본값 90
#   DRY_RUN       — "true" 이면 실행하지 않고 대상 row 수만 출력

set -euo pipefail

LOG_TAG="v8_cell_visited_archive"

# ─── 환경 변수 검증 ──────────────────────────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "[${LOG_TAG}] ERROR: DATABASE_URL is not set" >&2
    exit 1
fi

RETENTION_DAYS="${RETENTION_DAYS:-90}"
DRY_RUN="${DRY_RUN:-false}"

echo "[${LOG_TAG}] starting — retention_days=${RETENTION_DAYS}, dry_run=${DRY_RUN}"

# ─── DRY RUN: 대상 row 수 출력 ──────────────────────────────────────────────
if [[ "${DRY_RUN}" == "true" ]]; then
    COUNT_SQL="
SELECT count(*) AS pending_archive_rows
FROM audit_logs
WHERE action_code = 'v8_cell_visited'
  AND created_at < NOW() - INTERVAL '${RETENTION_DAYS} days'
  AND id NOT IN (SELECT id FROM audit_logs_v8_archive);
"
    echo "[${LOG_TAG}] DRY_RUN — pending rows:"
    psql "${DATABASE_URL}" -c "${COUNT_SQL}"
    echo "[${LOG_TAG}] DRY_RUN complete — no rows archived"
    exit 0
fi

# ─── ARCHIVE INSERT (audit_logs row 는 절대 삭제 안 함) ─────────────────────
ARCHIVE_SQL="
INSERT INTO audit_logs_v8_archive (
    id,
    actor_id,
    action_code,
    resource_type,
    resource_id,
    ip_address,
    user_agent,
    detail_json,
    created_at,
    archived_at
)
SELECT
    id,
    actor_id,
    action_code,
    resource_type,
    resource_id,
    ip_address,
    user_agent,
    detail_json,
    created_at,
    NOW() AS archived_at
FROM audit_logs
WHERE action_code = 'v8_cell_visited'
  AND created_at < NOW() - INTERVAL '${RETENTION_DAYS} days'
ON CONFLICT (id) DO NOTHING;
"

echo "[${LOG_TAG}] archiving v8_cell_visited rows older than ${RETENTION_DAYS} days..."
RESULT=$(psql "${DATABASE_URL}" -c "${ARCHIVE_SQL}" 2>&1)
echo "[${LOG_TAG}] psql result: ${RESULT}"

# ─── 검증: audit_logs row 수 변화 없음 확인 ─────────────────────────────────
VERIFY_SQL="
SELECT
    (SELECT count(*) FROM audit_logs WHERE action_code = 'v8_cell_visited') AS audit_logs_count,
    (SELECT count(*) FROM audit_logs_v8_archive WHERE action_code = 'v8_cell_visited') AS archive_count;
"
echo "[${LOG_TAG}] verification counts:"
psql "${DATABASE_URL}" -c "${VERIFY_SQL}"

echo "[${LOG_TAG}] done — audit_logs rows preserved (append-only, never deleted)"
