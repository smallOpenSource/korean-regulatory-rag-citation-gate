#!/usr/bin/env bash
# Preflight gate: verify ADR amendment commit pins match current HEAD.
# Exit 0 if all pins match or are 'skip'. Exit 1 on any mismatch.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PINNED_FILE="${PINNED_FILE:-$SCRIPT_DIR/cycle2-adr-pinned.txt}"

# ADR key → relative file path (supports glob prefix matching)
declare -A ADR_FILE_MAP
ADR_FILE_MAP["ADR-003"]="docs/architecture/ADR-003_dependency_change_gate.md"
ADR_FILE_MAP["ADR-005-section-1"]="docs/architecture/ADR-005_dual_llm_quarantine.md"
ADR_FILE_MAP["ADR-005-section-3"]="docs/architecture/ADR-005_dual_llm_quarantine.md"
ADR_FILE_MAP["ADR-005-section-5"]="docs/architecture/ADR-005_dual_llm_quarantine.md"
ADR_FILE_MAP["ADR-007-section-2"]="docs/architecture/ADR-007_validator_contract_specs.md"
ADR_FILE_MAP["ADR-007-section-4"]="docs/architecture/ADR-007_validator_contract_specs.md"
ADR_FILE_MAP["V041"]=""

# Extract the Nth markdown section (from one '## ' heading to the next)
# Usage: extract_section <file> <section_index_1based>
extract_section() {
  local file="$1"
  local idx="$2"
  awk -v idx="$idx" '
    /^## / { sec++; if (sec > idx) exit }
    sec == idx { print }
  ' "$file"
}

# Map section key suffix to 1-based section index within the ADR file
section_index_for_key() {
  local key="$1"
  case "$key" in
    ADR-005-section-1) echo 1 ;;
    ADR-005-section-3) echo 3 ;;
    ADR-005-section-5) echo 5 ;;
    ADR-007-section-2) echo 2 ;;
    ADR-007-section-4) echo 4 ;;
    *)                 echo "" ;;
  esac
}

if [[ ! -f "$PINNED_FILE" ]]; then
  echo "ERROR: pinned file not found: $PINNED_FILE" >&2
  exit 1
fi

FAIL=0

while IFS='=' read -r key value; do
  # Skip blank lines and comment lines
  [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue

  key="${key// /}"
  value="${value// /}"

  if [[ "$value" == "skip" ]]; then
    echo "SKIP  $key"
    continue
  fi

  if [[ -z "$value" ]]; then
    echo "ERROR $key: empty pin value (use 'skip' if not needed)" >&2
    FAIL=1
    continue
  fi

  # Validate pinned hash exists in repo
  if ! git -C "$REPO_ROOT" cat-file -e "${value}^{commit}" 2>/dev/null; then
    echo "FAIL  $key: pinned hash '$value' not found in repository" >&2
    FAIL=1
    continue
  fi

  adr_file="${ADR_FILE_MAP[$key]:-}"

  # V041 or other entries with no associated file: just verify commit exists
  if [[ -z "$adr_file" ]]; then
    # 커밋 존재 여부는 위에서 이미 검증했으므로 추가 비교 없이 통과 처리합니다.
    echo "OK    $key (commit $value exists)"
    continue
  fi

  section_idx="$(section_index_for_key "$key")"

  if [[ -n "$section_idx" ]]; then
    # Section-specific diff: compare the relevant markdown section only
    pinned_section=$(git -C "$REPO_ROOT" show "${value}:${adr_file}" 2>/dev/null \
      | awk -v idx="$section_idx" '/^## / { sec++; if (sec > idx) exit } sec == idx { print }')
    current_section=$(extract_section "$REPO_ROOT/$adr_file" "$section_idx")

    # Whitespace-tolerant comparison via diff -w
    if diff -w <(echo "$pinned_section") <(echo "$current_section") > /dev/null 2>&1; then
      echo "OK    $key (section $section_idx matches pinned $value)"
    else
      echo "FAIL  $key: section $section_idx has changed since pinned commit $value" >&2
      FAIL=1
    fi
  else
    # Full-file diff (whitespace tolerant)
    if git -C "$REPO_ROOT" diff -w "${value}" HEAD -- "$adr_file" | grep -q '^[+-][^+-]' 2>/dev/null; then
      echo "FAIL  $key: $adr_file has changed since pinned commit $value" >&2
      FAIL=1
    else
      echo "OK    $key ($adr_file matches pinned $value)"
    fi
  fi

done < "$PINNED_FILE"

if [[ "$FAIL" -ne 0 ]]; then
  echo ""
  echo "PREFLIGHT FAILED: one or more ADR amendment pins do not match." >&2
  exit 1
fi

echo ""
echo "PREFLIGHT PASSED: all ADR amendment pins verified."
exit 0
