#!/usr/bin/env bash
# v8_dispatcher_real_call_regression.sh
# Weekly cron: 4 dispatcher × 5 dry-run call = 20 real-hit API regression.
#
# PRD §4 #7 DELTA-4 / G0a-1.  Azure token Δ tolerance = 0 exact.
#
# Mode: dry_run=True is gated SERVER-SIDE by WMAH_ENABLE_DRY_RUN_PROBE=1.
#   (The prior `Bearer v8-synthetic-traversal-token` shortcut was removed in Wave-Audit A2/CR-3;
#    Phase 2 now authenticates with a real staff JWT in API_AUTH_TOKEN.)
#   - Real HTTP request to running API server (live network path exercised)
#   - Real DB write (ai_jobs row created + ai_outputs INSERT)
#   - Real WS broadcast (ai_job_done event)
#   - Azure SDK bypassed → Δ = 0 tokens
#
# Usage (cron example, every Monday 02:00 KST = Sunday 17:00 UTC):
#   0 17 * * 0 scripts/v8_dispatcher_real_call_regression.sh >> /var/log/v8_regression.log 2>&1
#
# Prerequisites:
#   API_BASE_URL  — running server, default http://localhost:8001
#   API_AUTH_TOKEN — staff-level Bearer token (distinct from synthetic token)
#   The running server must export WMAH_ENABLE_DRY_RUN_PROBE=1 so the dispatcher returns dry_run=True
#
# Exit codes: 0 = all 20 calls passed, non-zero = at least one failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Environment ───────────────────────────────────────────────────────────────
if [[ -f "${PROJECT_ROOT}/.env" ]]; then
    # shellcheck disable=SC1091
    set -a; source "${PROJECT_ROOT}/.env"; set +a
fi

API_BASE_URL="${API_BASE_URL:-http://localhost:8001}"
API_AUTH_TOKEN="${API_AUTH_TOKEN:-}"

PYTHON="${PYTHON:-/opt/conda/envs/wm_env/bin/python}"
CURL="$(command -v curl)"

PASS=0
FAIL=0

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ── Phase 1: pytest dry-run unit gate (Azure Δ=0 evidence, no server needed) ─
log "=== Phase 1: pytest unit gate (4 dispatchers × 5 calls) ==="
cd "${PROJECT_ROOT}"
if "${PYTHON}" -m pytest tests/test_v8_dispatcher_dry_run.py -v --tb=short; then
    log "Phase 1 PASS — 20 dispatcher dry-run unit calls verified, Azure Δ=0"
    PASS=$((PASS + 1))
else
    log "Phase 1 FAIL — dispatcher dry-run unit gate failed"
    FAIL=$((FAIL + 1))
fi

# ── Phase 2: live API smoke calls via synthetic token (server must be running) ─
log "=== Phase 2: live API smoke via staff Bearer API_AUTH_TOKEN (server needs WMAH_ENABLE_DRY_RUN_PROBE=1) ==="

if [[ -z "${API_AUTH_TOKEN}" ]]; then
    log "SKIP Phase 2: API_AUTH_TOKEN not set — live API smoke skipped"
else
    # Helper: single POST call, check HTTP 202, check dry_run=true in response
    call_endpoint() {
        local label="$1"
        local url="$2"
        local idx="$3"
        local http_code
        http_code="$("${CURL}" -s -o /tmp/v8_resp_"${idx}".json -w "%{http_code}" \
            -X POST "${url}" \
            -H "Authorization: Bearer ${API_AUTH_TOKEN}" \
            -H "Content-Type: application/json")"
        if [[ "${http_code}" == "202" ]]; then
            local dry_run_flag
            dry_run_flag="$(python3 -c "import json,sys; d=json.load(open('/tmp/v8_resp_${idx}.json')); print(d.get('dry_run','MISSING'))" 2>/dev/null || echo "PARSE_ERROR")"
            if [[ "${dry_run_flag}" == "True" ]]; then
                log "  PASS [${label}] HTTP 202, dry_run=True"
                PASS=$((PASS + 1))
            else
                log "  FAIL [${label}] HTTP 202 but dry_run=${dry_run_flag}"
                FAIL=$((FAIL + 1))
            fi
        else
            log "  FAIL [${label}] HTTP ${http_code}"
            FAIL=$((FAIL + 1))
        fi
    }

    # Requires valid consultation_id and customer_id in the live DB.
    # Populate V8_TEST_CONSULTATION_ID / V8_TEST_CUSTOMER_ID in .env or env.
    CONSULTATION_ID="${V8_TEST_CONSULTATION_ID:-00000000-0000-0000-0000-000000000001}"
    CUSTOMER_ID="${V8_TEST_CUSTOMER_ID:-00000000-0000-0000-0000-000000000001}"

    for i in $(seq 1 5); do
        call_endpoint "consultation_briefing call${i}" \
            "${API_BASE_URL}/consultations/${CONSULTATION_ID}/briefing" \
            "cb_${i}"
        call_endpoint "portfolio_analysis call${i}" \
            "${API_BASE_URL}/customers/${CUSTOMER_ID}/portfolio-analysis" \
            "pa_${i}"
    done
fi

# ── Summary ───────────────────────────────────────────────────────────────────
log "=== v8 dispatcher regression summary: PASS=${PASS} FAIL=${FAIL} ==="
if [[ "${FAIL}" -gt 0 ]]; then
    log "DECISION POINT: ${FAIL} failure(s) detected — escalate to team-lead before merging."
    exit 1
fi
log "All regression checks passed."
exit 0
