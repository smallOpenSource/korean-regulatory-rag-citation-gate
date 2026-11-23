#!/usr/bin/env bash
# Aggregate acceptance evidence for status, API tests, web checks, E2E, and batch.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/common.sh
source "$SCRIPT_DIR/common.sh"
HARNESS_ROOT="${HARNESS_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PYTHON_BIN="${PYTHON_PATH:-/opt/conda/envs/wm_env/bin/python}"
REPORT_DIR="$HARNESS_ROOT/.omx/reports/verification"
CONTINUE_ON_FAILURE=0
RUN_E2E=1
RUN_BATCH=1
BATCH_AS_OF_DATE="${HARNESS_BATCH_AS_OF_DATE:-$(date -u +%Y-%m-%d)}"
BATCH_LOOKBACK_DAYS="${HARNESS_BATCH_LOOKBACK_DAYS:-30}"
BATCH_PROVIDER_STRICTNESS="${HARNESS_PROVIDER_STRICTNESS:-required}"

usage() {
  cat <<USAGE
Usage: scripts/run_verification_gate.sh [--report-dir DIR] [--skip-e2e] [--skip-batch] [--continue-on-failure]

Runs the reproducible verification-doc gate:
  - scripts/status.sh --deep --no-fail
  - ruff + pytest
  - web typecheck/lint/unit/build
  - Playwright E2E unless --skip-e2e is supplied
  - scripts/run_batch_pipeline.sh --profile full-mvp --all-stages --lookback-days 30
    with non-blocking all-provider diagnostics and required-provider acceptance unless --skip-batch is supplied

Each command output is appended to a timestamped Markdown report under .omx/reports/verification.
After the gate, run scripts/verify_total_product_readiness.py with the generated report and
serviceable result JSON to reject missing E2E/batch evidence or misleading false-green output.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --report-dir)
      REPORT_DIR="$2"
      shift
      ;;
    --skip-e2e) RUN_E2E=0 ;;
    --skip-batch) RUN_BATCH=0 ;;
    --continue-on-failure) CONTINUE_ON_FAILURE=1 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/gate-$(date -u +%Y%m%dT%H%M%SZ).md"
FAILURES=0

run_step() {
  local name="$1"
  shift
  {
    printf '\n## %s\n\n' "$name"
    printf '```console\n'
    printf '$'
    printf ' %q' "$@"
    printf '\n'
  } >> "$REPORT_FILE"

  set +e
  "$@" >> "$REPORT_FILE" 2>&1
  local status=$?
  set -e

  {
    printf '\n(exit %s)\n' "$status"
    printf '```\n'
  } >> "$REPORT_FILE"

  if [[ "$status" -ne 0 ]]; then
    FAILURES=$((FAILURES + 1))
    if [[ "$CONTINUE_ON_FAILURE" -ne 1 ]]; then
      echo "verification_step=$name result=failed report=$REPORT_FILE" >&2
      exit "$status"
    fi
  fi
}

run_nonblocking_step() {
  local name="$1"
  shift
  {
    printf '\n## %s\n\n' "$name"
    printf '```console\n'
    printf '$'
    printf ' %q' "$@"
    printf '\n'
  } >> "$REPORT_FILE"

  set +e
  "$@" >> "$REPORT_FILE" 2>&1
  local status=$?
  set -e

  {
    printf '\n(exit %s; non-blocking diagnostic)\n' "$status"
    printf '```\n'
  } >> "$REPORT_FILE"
}

cd "$HARNESS_ROOT"
load_dotenv "$HARNESS_ROOT/.env"
PYTHON_BIN="$(python_bin)"

if [[ "$RUN_E2E" -eq 1 ]]; then
  # Non-production fixture credentials: keep Playwright from reporting green with skipped
  # login/role/reload coverage when the caller has not supplied explicit E2E variables.
  : "${E2E_SYNTHETIC_PASSWORD:=HarnessSynthetic!2026}"
  : "${E2E_EMPLOYEE_EMAIL:=synthetic.pb1@example.invalid}"
  : "${E2E_EMPLOYEE_PASSWORD:=$E2E_SYNTHETIC_PASSWORD}"
  export E2E_SYNTHETIC_PASSWORD E2E_EMPLOYEE_EMAIL E2E_EMPLOYEE_PASSWORD
fi

{
  printf '# Verification Gate Evidence\n\n'
  printf -- '- started_at_utc: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf -- '- harness_root: %s\n' "$HARNESS_ROOT"
  printf -- '- python: %s\n' "$PYTHON_BIN"
} > "$REPORT_FILE"

run_step "Runtime status" ./scripts/status.sh --deep --no-fail
run_step "Ruff" "$PYTHON_BIN" -m ruff check apps/api db tests
run_step "Pytest" "$PYTHON_BIN" -m pytest -q
run_step "Web typecheck" bash -lc "cd apps/web && npm run typecheck"
run_step "Web lint" bash -lc "cd apps/web && npm run lint"
run_step "Web unit tests" bash -lc "cd apps/web && npm run test -- --run"
run_step "Web build" bash -lc "cd apps/web && npm run build"

if [[ "$RUN_E2E" -eq 1 ]]; then
  run_step "Playwright E2E" bash -lc "cd apps/web && PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers npm run e2e"
fi

if [[ "$RUN_BATCH" -eq 1 ]]; then
  BATCH_DIAGNOSTIC_REPORT="$REPORT_DIR/batch-all-$(date -u +%Y%m%dT%H%M%SZ).json"
  run_nonblocking_step "Batch pipeline all-provider diagnostic" ./scripts/run_batch_pipeline.sh \
    --profile full-mvp \
    --all-stages \
    --lookback-days "$BATCH_LOOKBACK_DAYS" \
    --as-of-date "$BATCH_AS_OF_DATE" \
    --provider-strictness all \
    --embedding-batch-size "${BGE_BATCH_SIZE:-16}" \
    --report "$BATCH_DIAGNOSTIC_REPORT"

  BATCH_REPORT="$REPORT_DIR/batch-required-$(date -u +%Y%m%dT%H%M%SZ).json"
  run_step "Batch pipeline required-provider acceptance" ./scripts/run_batch_pipeline.sh \
    --profile full-mvp \
    --all-stages \
    --lookback-days "$BATCH_LOOKBACK_DAYS" \
    --as-of-date "$BATCH_AS_OF_DATE" \
    --provider-strictness "$BATCH_PROVIDER_STRICTNESS" \
    --embedding-batch-size "${BGE_BATCH_SIZE:-16}" \
    --report "$BATCH_REPORT"
fi

{
  printf '\n## Summary\n\n'
  printf -- '- finished_at_utc: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf -- '- failures: %s\n' "$FAILURES"
} >> "$REPORT_FILE"

echo "verification_gate_report=$REPORT_FILE failures=$FAILURES"
exit "$FAILURES"
