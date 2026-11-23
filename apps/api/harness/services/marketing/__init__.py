"""Marketing services namespace.

Re-exports the pre-existing marketing/`core.py` surface (formerly
`marketing.py` before T236 introduced the sub-package). New submodules:

  - kofia_verification (T236) — KOFIA digital-solicitation identity + chat
"""

# Re-export everything from core to preserve backward-compatible imports
# such as `from apps.api.harness.services.marketing import check_pii_outbound`.
from apps.api.harness.services.marketing.core import *  # noqa: F401,F403
from apps.api.harness.services.marketing.core import (  # explicit re-exports
    AiComplianceResult,
    CLASSIFICATION_MARKETING,
    CLASSIFICATION_OPERATIONAL,
    MarketingGateResult,
    MarketingLintResult,
    ai_compliance_check,
    check_pii_outbound,
    classify_email_static,
    lint_marketing_leading_block,
    run_marketing_gate,
)
