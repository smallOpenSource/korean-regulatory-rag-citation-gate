#!/bin/bash
# scripts/run_gitleaks_scan.sh
# REG-05 T289 — static secret scan via gitleaks.
# Exit codes match ADR-007 validator convention:
#   0 = pass (no findings)
#   2 = fail (findings detected — sanitized report written)
#   3 = config error (gitleaks binary unavailable, config missing)
# Usage:
#   scripts/run_gitleaks_scan.sh           # scan working tree
#   scripts/run_gitleaks_scan.sh --git     # scan git history (deeper, slower)
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

REPORT_DIR="${PROJECT_ROOT}/.omx/reports/verification"
mkdir -p "${REPORT_DIR}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT_JSON="${REPORT_DIR}/gitleaks-${TS}.json"

# Config must exist
CONFIG="${PROJECT_ROOT}/.gitleaks.toml"
if [[ ! -f "${CONFIG}" ]]; then
    echo "[gitleaks] config error: ${CONFIG} not found" >&2
    exit 3
fi

# Binary must be on PATH (ADR-003 pre-approved; binary install, not pip/npm)
if ! command -v gitleaks >/dev/null 2>&1; then
    echo "[gitleaks] config error: gitleaks binary not on PATH" >&2
    echo "[gitleaks] install: https://github.com/gitleaks/gitleaks/releases" >&2
    exit 3
fi

MODE="detect"
SOURCE_FLAGS=("--no-git")
if [[ "${1:-}" == "--git" ]]; then
    # Scan committed history too
    SOURCE_FLAGS=()
fi

echo "[gitleaks] running ${MODE} (config=${CONFIG}, report=${REPORT_JSON})"
set +e
gitleaks "${MODE}" \
    --config "${CONFIG}" \
    --source "${PROJECT_ROOT}" \
    "${SOURCE_FLAGS[@]}" \
    --no-banner \
    --redact \
    --report-format json \
    --report-path "${REPORT_JSON}" \
    --exit-code 2
RC=$?
set -e

case "${RC}" in
    0)
        echo "[gitleaks] PASS — no secrets detected; report ${REPORT_JSON}"
        exit 0
        ;;
    2)
        echo "[gitleaks] FAIL — findings written to ${REPORT_JSON}" >&2
        echo "[gitleaks] count: $(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "${REPORT_JSON}" 2>/dev/null || echo unknown)" >&2
        exit 2
        ;;
    *)
        echo "[gitleaks] config error: gitleaks exited with ${RC}" >&2
        exit 3
        ;;
esac
