#!/usr/bin/env bash
# Verify QA harnesses do not treat hostile command output as success.

set -euo pipefail

FAILURES=0

record_failure() {
  local name="$1"
  local detail="$2"
  FAILURES=$((FAILURES + 1))
  printf 'hostile_check=%s result=failed detail=%s\n' "$name" "$detail"
}

record_pass() {
  local name="$1"
  local detail="$2"
  printf 'hostile_check=%s result=passed detail=%s\n' "$name" "$detail"
}

check_misleading_success() {
  local output
  local status
  set +e
  output="$({ printf 'SUCCESS but wrong\n'; exit 7; } 2>&1)"
  status=$?
  set -e
  if [[ "$status" -ne 0 && "$output" == *SUCCESS* ]]; then
    record_pass "misleading_success" "nonzero_status_${status}_preserved"
  else
    record_failure "misleading_success" "status_${status}_output_${output}"
  fi
}

check_timeout() {
  local status
  set +e
  timeout 1 bash -c 'sleep 5' >/dev/null 2>&1
  status=$?
  set -e
  if [[ "$status" -eq 124 ]]; then
    record_pass "timeout" "timeout_status_124_preserved"
  else
    record_failure "timeout" "status_${status}"
  fi
}

check_corrupted_state_parse() {
  local tmp_file
  local status
  tmp_file="$(mktemp)"
  printf '{not-valid-json' > "$tmp_file"
  set +e
  python - "$tmp_file" <<'PY' >/dev/null 2>&1
import json
import sys
from pathlib import Path

json.loads(Path(sys.argv[1]).read_text())
PY
  status=$?
  set -e
  rm -f "$tmp_file"
  if [[ "$status" -ne 0 ]]; then
    record_pass "corrupted_state_parse" "json_parse_failure_preserved"
  else
    record_failure "corrupted_state_parse" "parse_unexpectedly_succeeded"
  fi
}

check_misleading_success
check_timeout
check_corrupted_state_parse

if [[ "$FAILURES" -ne 0 ]]; then
  printf 'hostile_checks=failed failures=%s\n' "$FAILURES"
  exit 1
fi
printf 'hostile_checks=passed failures=0\n'
