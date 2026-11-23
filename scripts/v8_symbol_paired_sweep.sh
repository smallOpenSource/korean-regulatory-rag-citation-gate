#!/bin/bash
# v8_symbol_paired_sweep.sh — DELTA-M1 audit (Task #24)
#
# PRD principle L341: "본문은 symbol 참조로만 표기, 숫자 hard-code 금지".
# 각 target numeric occurrence가 PRD body line에서 ±2 lines 내에 symbol token
# (n_user_sample, N_REACHABLE 등) 또는 deprecation log strike-through에 있는지 verify.
#
# Output: .omc/state/v8-symbol-sweep-report.txt
#
# Exit codes:
#   0 — all targets symbol-paired or deprecation-logged (PASS)
#   1 — violations found (documented in report, PRD M1 partial fail)
#   2 — environment / file missing (PRE-FLIGHT FAIL)

set -uo pipefail

PRD=".omc/plans/ralplan-wmah-state-graph-traversal-v8.md"
AUDIT=".omc/plans/ralplan-wmah-state-graph-traversal-v8-derivation-audit.md"
REPORT=".omc/state/v8-symbol-sweep-report.txt"

if [ ! -f "${PRD}" ]; then
  echo "ERROR: PRD missing at ${PRD}" >&2
  exit 2
fi
if [ ! -f "${AUDIT}" ]; then
  echo "ERROR: audit missing at ${AUDIT}" >&2
  exit 2
fi

# Targets that MUST be paired with a symbol token within ±2 lines.
declare -a TARGETS=("371" "2226" "37.1" "186" "185" "10080")
# Symbol tokens permitted as adjacent pairing.
SYMBOL_TOKENS='n_user_sample|n_inf|n_fpc|N_REACHABLE|N_THEORETICAL|N_VIEWPORT_EXT|user_burden_min|user_burden_hr|adversarial_split|random_split|cycle_total|INTERACTION_CLASSES'
# Deprecation log markers — numerics inside these lines are exempt.
DEPRECATION_PATTERN='strike-through|iter [12] (value|stale|deprecated)|deprecation|history annotation|iter 1 \(was|이전 값'

# Allowlist — evidence-paired numerics that need not be tokenized.
declare -a ALLOWLIST=("21" "5" "5902" "4" "100" "1113")

mkdir -p "$(dirname "${REPORT}")"
{
  echo "=== v8 symbol-paired sweep report ==="
  echo "Generated: $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  echo "PRD: ${PRD}"
  echo "Audit: ${AUDIT}"
  echo "Allowlist: ${ALLOWLIST[*]}"
  echo
} > "${REPORT}"

violations=0
total_checked=0

check_target() {
  local target="$1"
  local file="$2"
  local label="$3"

  # 소수점 타겟(예: 37.1)의 '.'은 ERE 와일드카드이므로 리터럴로 이스케이프합니다.
  local esc="${target//./\\.}"
  # All line numbers where target appears as a whole-word numeric.
  # `\b` not always supported with grep -E on all locales; use perl-style instead.
  local lines
  lines=$(grep -nE "(^|[^0-9.])${esc}([^0-9]|$)" "${file}" | cut -d: -f1)
  local count
  count=$(echo "${lines}" | grep -c . || true)
  echo "--- ${label}: target=${target} occurrences=${count} ---" >> "${REPORT}"

  if [ -z "${lines}" ]; then
    return 0
  fi

  while read -r ln; do
    [ -z "${ln}" ] && continue
    total_checked=$((total_checked + 1))
    # Examine ±2 lines around the hit for either a symbol token or deprecation marker.
    local context
    context=$(sed -n "$((ln - 2)),$((ln + 2))p" "${file}")
    if echo "${context}" | grep -qE "${SYMBOL_TOKENS}"; then
      echo "  line ${ln}: PAIRED (symbol token within ±2)" >> "${REPORT}"
    elif echo "${context}" | grep -qE "${DEPRECATION_PATTERN}"; then
      echo "  line ${ln}: DEPRECATION-EXEMPT" >> "${REPORT}"
    else
      echo "  line ${ln}: VIOLATION — no adjacent symbol or deprecation marker" >> "${REPORT}"
      echo "    context:" >> "${REPORT}"
      echo "${context}" | sed 's/^/      | /' >> "${REPORT}"
      violations=$((violations + 1))
    fi
  done <<< "${lines}"
}

for target in "${TARGETS[@]}"; do
  check_target "${target}" "${PRD}" "PRD body"
done

# Audit table itself uses raw numbers in derivation rows — those are SoT, not
# violations. We still report counts for transparency.
{
  echo
  echo "--- audit table raw numeric occurrences (FYI, exempt) ---"
} >> "${REPORT}"
for target in "${TARGETS[@]}"; do
  # 소수점 타겟의 '.'은 ERE 와일드카드이므로 리터럴로 이스케이프합니다.
  esc="${target//./\\.}"
  audit_count=$(grep -cE "(^|[^0-9.])${esc}([^0-9]|$)" "${AUDIT}" || true)
  echo "  audit ${target}: ${audit_count}" >> "${REPORT}"
done

{
  echo
  echo "=== summary ==="
  echo "PRD lines checked: ${total_checked}"
  echo "violations: ${violations}"
} >> "${REPORT}"

if [ "${violations}" -eq 0 ]; then
  echo "  verdict: PASS" >> "${REPORT}"
  exit 0
else
  echo "  verdict: VIOLATIONS — see report" >> "${REPORT}"
  exit 1
fi
