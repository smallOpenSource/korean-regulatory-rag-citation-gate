"""P0 AI-output-quality: shared data-quality disclosure + faithfulness gate.

A regulated WM/PB harness must not let an AI output present synthetic /
unverified data as established fact, and must be able to verify that a generated
output is grounded in the data the model was actually given. These helpers are
called by the single/dual-LLM dispatchers (portfolio_analysis,
consultation_briefing, nba_script) to:

1. Carry a mandatory data-quality / synthetic-data disclosure (``data_quality_*``
   notices are stamped by the callers; ``has_disclosure`` verifies presence).
2. Stamp a deterministic faithfulness assessment (``assess_faithfulness``) that
   checks the output text against the PII-safe ``model_input`` the generator
   captured — flagging missing disclosure and ungrounded financial figures.

The gate is deterministic on purpose: it runs on every generation with no extra
Azure call. An LLM-judge faithfulness mode can be layered on later (the
``model_input`` capture is the grounding it would need).
"""

from __future__ import annotations

import json
import re
from typing import Any

# A synthetic/unverified data-quality disclosure phrase for agents whose inputs
# are PoC synthetic customer data but which do not carry a per-holding valuation
# provenance (portfolio_analysis builds its own from the Customer-360 basis).
SYNTHETIC_ADVISORY_NOTICE = (
    "[데이터 품질 고지] 본 AI 산출물은 의사결정 보조용이며, PoC 환경의 합성·미검증 "
    "고객/포트폴리오 데이터를 기반으로 합니다. 실제 시장·고객 사실로 확정해 사용하지 마십시오."
)

# Tokens that count as a data-quality / synthetic / unverified disclosure.
_DISCLOSURE_TOKENS: tuple[str, ...] = (
    "SYNTHETIC_HOLDING_VALUE",
    "합성 시드",
    "합성·미검증",
    "합성 데이터",
    "데이터 품질",
    "UNVERIFIED",
    "미검증",
    "실제 시장 평가액",
    "확정해 사용",
)

# Financial figures worth grounding: percentages and KRW amounts with a unit.
# Bare integers (counts like "리스크 3개") are intentionally NOT checked — only
# figures that assert a quantitative financial fact.
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_AMOUNT_RE = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(억|조|만원|원|KRW)")


def has_disclosure(text: str) -> bool:
    """True when the text carries a recognised data-quality disclosure phrase."""
    t = text or ""
    return any(tok in t for tok in _DISCLOSURE_TOKENS)


def _grounding_blob(model_input: dict[str, Any] | None) -> str:
    if not model_input:
        return ""
    return json.dumps(model_input, ensure_ascii=False, default=str)


def ungrounded_figures(output_text: str, model_input: dict[str, Any] | None) -> list[str]:
    """Percentages / KRW amounts in the output whose digits are absent from the grounding.

    Advisory + intentionally lenient (substring match): a figure is flagged ONLY
    when its digit string does not appear anywhere in the serialized grounding.
    This is an observability signal, NOT a proof of grounding, and it has a known
    false-negative ceiling: a fabricated figure whose digits coincidentally occur
    as a substring of some grounding value (e.g. "12%" while 1.123 or 4512 sits in
    the blob) will NOT be flagged. It reliably catches only figures whose digits
    are wholly absent from the inputs (a clearly invented "+3.2%" when no such
    digits exist). Callers / reviewers must NOT read an empty result as a guarantee
    that every figure is grounded — pair it with the require_disclosure check.
    """
    blob = _grounding_blob(model_input)
    flagged: list[str] = []
    for match in _PCT_RE.finditer(output_text or ""):
        if match.group(1) not in blob:
            flagged.append(match.group(0))
    for match in _AMOUNT_RE.finditer(output_text or ""):
        raw = match.group(1)
        if raw not in blob and raw.replace(",", "") not in blob:
            flagged.append(match.group(0))
    deduped: list[str] = []
    for item in flagged:
        if item not in deduped:
            deduped.append(item)
    return deduped[:20]


def assess_faithfulness(
    *,
    output_text: str,
    model_input: dict[str, Any] | None,
    require_disclosure: bool = True,
) -> dict[str, Any]:
    """Deterministic faithfulness gate result stamped onto an AI output.

    Returns ``{method, has_disclosure, ungrounded_figures, flags, passed}``.
    ``passed`` is False when the data-quality disclosure is missing from the
    output text or an ungrounded financial figure is present. The caller stamps
    this onto ``output_json['faithfulness']`` so QA / reviewers can see it; the
    mandatory disclosure itself is also carried in a separate
    ``data_quality_notice`` field, so this gate is observability + flagging, not
    the only line of defence.
    """
    disclosure_present = has_disclosure(output_text)
    figures = ungrounded_figures(output_text, model_input)
    flags: list[str] = []
    if require_disclosure and not disclosure_present:
        flags.append("MISSING_DATA_QUALITY_DISCLOSURE")
    if figures:
        flags.append("UNGROUNDED_FIGURES")
    return {
        "method": "deterministic_v1",
        "has_disclosure": disclosure_present,
        "ungrounded_figures": figures,
        "flags": flags,
        "passed": not flags,
    }
