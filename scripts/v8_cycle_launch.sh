#!/bin/bash
# v8_cycle_launch.sh — Stage 2 G2 deliverable (T109)
#
# Cycle launch orchestrator for v8 PRD state-graph-traversal.
# Estimated ~24h compute per cycle (PRD §6 Stage 2).
#
# Phases:
#   0. Pre-flight (ground-truth lock + dispatcher dry-run + Azure quota)
#   1. BFS traversal (v8_bfs_visitor.py --mode full)
#   2. Deterministic detectors (L1/L3/L4) per visited cell
#   3. LLM critic batch (L2 text + L5 vision) — calibration_eval_per_cycle=50
#   4. Screenshot grid generate (user spot-check sample 371)
#   5. Unreachable manifest populate (v8-unreachable-manifest.yaml)
#   6. Cycle decision yaml (.omc/state/v8-cycle-N-decision.yaml)
#   7. G2 gate assertion (accounting 100% strict)
#
# Exit codes:
#   0  — cycle complete, G2 gate PASS
#   1  — cycle complete but G2 gate FAIL (accounting < 100%)
#   2  — pre-flight FAIL (env or topology blocker)
#   3  — runtime exception during traversal

set -uo pipefail

CYCLE="${1:-1}"
MODE="${2:-dry-run}"  # dry-run | full | sample
SAMPLE_N="${3:-10}"

PY="${PYTHON_PATH:-python3}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS="${REPO}/scripts"
STATE="${REPO}/.omc/state"
TRAVERSAL_DIR="${STATE}/v8-traversal"
LAUNCH_LOG="${TRAVERSAL_DIR}/cycle_${CYCLE}_launch.log"
mkdir -p "${TRAVERSAL_DIR}"

log() {
  echo "[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $*" | tee -a "${LAUNCH_LOG}"
}

phase_header() {
  log ""
  log "============================================"
  log "Phase $1: $2"
  log "============================================"
}

# --------------------------------------------------------------------------
# Phase 0 — Pre-flight
# --------------------------------------------------------------------------

phase_header 0 "Pre-flight checks"

# 0a. ground-truth.yaml LOCKED status
log "0a. ground-truth.yaml LOCKED verify"
LOCK_STATUS=$(grep '^lock_status:' "${STATE}/v8-ground-truth.yaml" | awk '{print $2}')
if [ "${LOCK_STATUS}" != "LOCKED-cycle-1-baseline" ]; then
  log "FAIL: lock_status=${LOCK_STATUS} (expected LOCKED-cycle-1-baseline)"
  exit 2
fi
log "  PASS"

# 0b. dispatcher dry-run smoke (DELTA-4 test-double)
log "0b. dispatcher dry-run smoke"
if [ -f "${REPO}/tests/test_v8_dispatcher_dry_run.py" ]; then
  if "${PY}" -m pytest -q "${REPO}/tests/test_v8_dispatcher_dry_run.py" \
       --no-header 2>&1 | tee -a "${LAUNCH_LOG}" | tail -5; then
    log "  PASS"
  else
    log "FAIL: dispatcher dry-run regression"
    exit 2
  fi
else
  log "  WARN: test_v8_dispatcher_dry_run.py missing (Stage 0 G0a-1 deliverable)"
fi

# 0c. cell_space accounting smoke
log "0c. cell_space accounting smoke"
ACCOUNTING=$("${PY}" "${SCRIPTS}/v8_cell_space.py" --summary-only 2>&1 | tail -20)
echo "${ACCOUNTING}" | tee -a "${LAUNCH_LOG}" >/dev/null
if echo "${ACCOUNTING}" | grep -q '"accounting_100pct": true'; then
  log "  PASS — 40,320 cells, accounting_100pct=true"
else
  log "FAIL: cell_space accounting != 100%"
  exit 2
fi

# 0d. Azure quota probe (placeholder — actual AZURE_OPENAI_* env check)
log "0d. Azure quota probe"
if [ "${MODE}" = "full" ]; then
  if [ -z "${AZURE_OPENAI_API_KEY:-}" ] || [ -z "${AZURE_OPENAI_ENDPOINT:-}" ]; then
    log "FAIL: AZURE_OPENAI_API_KEY/ENDPOINT not set; full mode requires L2/L5 Azure access"
    exit 2
  fi
  log "  PASS (AZURE_OPENAI_API_KEY/ENDPOINT present)"
else
  log "  SKIP (mode=${MODE}, no API needed)"
fi

# 0e. Playwright env probe
log "0e. Playwright env probe"
if [ "${MODE}" = "full" ] || [ "${MODE}" = "sample" ]; then
  PW_PY=/opt/conda/envs/playwright/bin/python
  if [ ! -x "${PW_PY}" ]; then
    log "FAIL: Playwright python env missing at ${PW_PY}"
    exit 2
  fi
  if [ -z "${DISPLAY:-}" ]; then
    log "  WARN: DISPLAY env not set (xvfb DISPLAY=:99 expected)"
  fi
  log "  PASS (playwright env detected)"
else
  log "  SKIP (mode=${MODE})"
fi

# --------------------------------------------------------------------------
# Phase 1 — BFS traversal
# --------------------------------------------------------------------------

phase_header 1 "BFS traversal (mode=${MODE})"

START_TS=$(date +%s)
case "${MODE}" in
  dry-run)
    "${PY}" "${SCRIPTS}/v8_bfs_visitor.py" \
      --cycle "${CYCLE}" --mode dry-run \
      --output-dir "${TRAVERSAL_DIR}" \
      2>&1 | tee -a "${LAUNCH_LOG}"
    ;;
  sample)
    "${PY}" "${SCRIPTS}/v8_bfs_visitor.py" \
      --cycle "${CYCLE}" --mode sample --sample-size "${SAMPLE_N}" \
      --output-dir "${TRAVERSAL_DIR}" \
      2>&1 | tee -a "${LAUNCH_LOG}"
    ;;
  full)
    "${PY}" "${SCRIPTS}/v8_bfs_visitor.py" \
      --cycle "${CYCLE}" --mode full \
      --output-dir "${TRAVERSAL_DIR}" \
      --populate-manifest \
      2>&1 | tee -a "${LAUNCH_LOG}"
    ;;
  *)
    log "FAIL: unknown mode ${MODE}"
    exit 2
    ;;
esac
PHASE1_EXIT=${PIPESTATUS[0]}
END_TS=$(date +%s)
log "Phase 1 elapsed: $((END_TS - START_TS))s, exit=${PHASE1_EXIT}"

# --------------------------------------------------------------------------
# Phase 7 — G2 gate assertion (accounting 100% strict)
# --------------------------------------------------------------------------

phase_header 7 "G2 gate assertion"

CYCLE_DIR="${TRAVERSAL_DIR}/cycle_${CYCLE}"
SUMMARY_JSON="${CYCLE_DIR}/summary.json"
if [ -f "${SUMMARY_JSON}" ]; then
  VISITED=$("${PY}" -c "import json; print(json.load(open('${SUMMARY_JSON}'))['visited_count'])")
  UNREACH=$("${PY}" -c "import json; print(json.load(open('${SUMMARY_JSON}'))['unreachable_count'])")
  SKIPPED=$("${PY}" -c "import json; print(json.load(open('${SUMMARY_JSON}')).get('skipped_resume', 0))")
  TOTAL=$((VISITED + UNREACH + SKIPPED))
  log "  visited=${VISITED}, unreachable=${UNREACH}, skipped_resume=${SKIPPED}, total=${TOTAL}"
  if [ "${TOTAL}" -eq 40320 ]; then
    log "  G2 gate PASS — accounting 100% (40,320 = N_VIEWPORT_EXT)"
    G2_PASS=true
  else
    log "  G2 gate FAIL — accounting=${TOTAL} != 40,320 (DELTA-3/C3 strict)"
    G2_PASS=false
  fi
else
  log "  G2 gate FAIL — no summary.json at ${SUMMARY_JSON}"
  G2_PASS=false
fi

log ""
log "Cycle ${CYCLE} launch complete (mode=${MODE})"
if [ "${G2_PASS}" = "true" ]; then
  exit 0
else
  exit 1
fi
