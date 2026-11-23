#!/usr/bin/env bash
# scripts/run_determinism_check.sh
#
# Per memory rule [[test-determinism-against-random-input]] + v6 plan §6 Memory rule
# `test-determinism-against-random-input` gate. Repeats a pytest selector N times
# (default 50) and reports PASS_COUNT/FAIL_COUNT. Exits 0 only if PASS_COUNT == N.
#
# Why: random/HMAC/base64-encoded inputs (e.g. token tamper, signature collision
# windows) can hide flakiness behind a single passing run. Multi-run loop surfaces
# the worst tail of the encoding distribution.
#
# Usage:
#   scripts/run_determinism_check.sh                                    # default selector + 50 iter
#   scripts/run_determinism_check.sh -n 100                             # custom iter count
#   scripts/run_determinism_check.sh -- tests/test_config_security.py   # custom pytest target
#   scripts/run_determinism_check.sh -n 200 -- tests/test_x.py::test_y  # combine
#
# Exit codes:
#   0  PASS_COUNT == N            (deterministic green)
#   1  PASS_COUNT <  N            (flaky / failing — investigate)
#   2  usage error
set -euo pipefail

# 리포지토리 루트에 고정해야 pytest selector가 어느 CWD에서도 동일하게 해석됩니다.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.." || exit 1

# 인터프리터를 wm_env로 고정합니다 (시스템 python은 wmah 의존성 미설치).
PYTHON_BIN="${PYTHON_PATH:-/opt/conda/envs/wm_env/bin/python}"

ITER=50
SELECTOR=(
  "tests/test_config_security.py::test_token_decode_rejects_tampering"
)

while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--iter)
      ITER="${2:?missing iter count}"
      shift 2
      ;;
    --)
      shift
      SELECTOR=("$@")
      break
      ;;
    -h|--help)
      sed -n '1,30p' "$0"
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if ! [[ "$ITER" =~ ^[0-9]+$ ]] || (( ITER < 1 )); then
  echo "iter must be positive integer (got: $ITER)" >&2
  exit 2
fi

PASS_COUNT=0
FAIL_COUNT=0
FAILED_RUNS=()

echo "[determinism] target: ${SELECTOR[*]}"
echo "[determinism] iterations: ${ITER}"

for ((i=1; i<=ITER; i++)); do
  if "$PYTHON_BIN" -m pytest -q --no-header --disable-warnings -x "${SELECTOR[@]}" > /tmp/determinism-run-$$.log 2>&1; then
    PASS_COUNT=$((PASS_COUNT+1))
  else
    FAIL_COUNT=$((FAIL_COUNT+1))
    FAILED_RUNS+=("$i")
  fi
done

rm -f /tmp/determinism-run-$$.log

echo "[determinism] PASS_COUNT=${PASS_COUNT}/${ITER}"
echo "[determinism] FAIL_COUNT=${FAIL_COUNT}/${ITER}"

if (( PASS_COUNT == ITER )); then
  echo "[determinism] OK — deterministic green across ${ITER} runs"
  exit 0
fi

echo "[determinism] FAIL — non-deterministic. failed runs: ${FAILED_RUNS[*]:-none}"
echo "[determinism] hint: rerun with -x and inspect signature/encoding edge cases"
exit 1
