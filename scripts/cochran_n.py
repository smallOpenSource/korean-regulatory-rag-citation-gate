#!/usr/bin/env python3
"""v8 Cochran n derivation (DELTA-N2 audit-table self-verify gate).

PRD §3.7.1 + DELTA-N2: bit-compare output against audit table §1
(ralplan-wmah-state-graph-traversal-v8-derivation-audit.md L29 n_user_sample row).

Expected output (iter 3):
  n_inf=385, n_fpc=371, user_burden_min=2226, user_burden_hr=37.1,
  cycle_total=1113, adversarial_split=186, random_split=185
"""
import json
import math
import sys

z = 1.96   # 95% CI two-tailed
p = 0.5    # max variance
e = 0.05   # 5% margin
N = 10080  # N_REACHABLE per audit table §1 (21 × 5 × 8 × 12)

n_inf = math.ceil(z * z * p * (1 - p) / (e * e))           # ceil(384.16) = 385
n_fpc = math.ceil(n_inf / (1 + (n_inf - 1) / N))           # ceil(370.87) = 371

user_burden_min = n_fpc * 2 * 3                            # 371 × 2 × 3 = 2226
user_burden_hr = user_burden_min / 60                      # 37.1
cycle_total = n_fpc * 3                                    # 1113
adversarial_split = math.ceil(n_fpc / 2)                   # 186
random_split = n_fpc - adversarial_split                   # 185

# DELTA-N2 self-verify gate: bit-compare computed values against the audit-table §1
# expected set; any drift => exit 1. (Previously a comment-only no-op: it printed the
# values but never asserted them, so a formula/constant drift would pass silently.)
_EXPECTED = {
    "n_inf": 385,
    "n_fpc": 371,
    "user_burden_min": 2226,
    "cycle_total": 1113,
    "adversarial_split": 186,
    "random_split": 185,
}
_computed = {
    "n_inf": n_inf,
    "n_fpc": n_fpc,
    "user_burden_min": user_burden_min,
    "cycle_total": cycle_total,
    "adversarial_split": adversarial_split,
    "random_split": random_split,
}
_drift = {k: (_computed[k], exp) for k, exp in _EXPECTED.items() if _computed[k] != exp}
if _drift:
    print(f"FAIL: cochran_n drift vs audit table §1 (computed, expected): {_drift}", file=sys.stderr)
    sys.exit(1)

out = {
    "z": z, "p": p, "e": e, "N": N,
    "n_inf": n_inf, "n_fpc": n_fpc,
    "user_burden_min": user_burden_min,
    "user_burden_hr": user_burden_hr,
    "cycle_total": cycle_total,
    "adversarial_split": adversarial_split,
    "random_split": random_split,
}
print(json.dumps(out, indent=2))
