"""LLM07 system-prompt leakage redactor — OWASP LLM Top 10 (ADR-005 §6, W3-T6).

Scans model output for system-prompt-like phrases and masks them before
the text is returned to the user or persisted.

On leakage: caller must emit LLM07_LEAKAGE_REDACTED audit + ai_fail_closed
and use fail_closed_reason_code=PROMPT_INJECTION_DETECTED.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Leakage patterns ──────────────────────────────────────────────────────────

_LEAKAGE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ROLE_DISCLOSURE",       re.compile(r"(?i)\bYour\s+role\s+is\b")),
    ("AI_SELF_ID",            re.compile(r"(?i)\bYou\s+are\s+an\s+AI\b")),
    ("SYSTEM_HEADER",         re.compile(r"(?i)\bSystem\s*:")),
    ("TRAINING_DISCLOSURE",   re.compile(r"(?i)\bI\s+was\s+trained\s+by\b")),
    ("INSTRUCTION_ECHO",      re.compile(r"(?i)\bMy\s+instructions?\s+(are|is|say)\b")),
    ("AS_INSTRUCTED",         re.compile(r"(?i)\bAs\s+instructed\b")),
    ("ASSISTANT_HEADER",      re.compile(r"(?i)\bAs\s+an\s+AI\s+assistant\b")),
    ("IGNORE_PRIOR",          re.compile(r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions?")),
    ("SPOTLIGHT_MARKER_ECHO", re.compile(r"</?(USER_DATA|RETRIEVED_CONTEXT|SYSTEM)\b")),
    ("PRIVILEGED_LANE_ECHO",  re.compile(r"(?i)\b(privileged|quarantined|orchestrator)\s+(lane|llm|model)\b")),
]

_MASK = "[REDACTED:LLM07]"
_JACCARD_THRESHOLD = 0.6


@dataclass(frozen=True)
class RedactionResult:
    """Output of one LLM07 redaction pass."""

    leakage_detected: bool
    redacted_text: str
    patterns_matched: list[str] = field(default_factory=list)


def redact_llm_output(text: str, *, system_prompt: str | None = None) -> RedactionResult:
    """Scan *text* for system-prompt leakage and redact matches in-place.

    Always returns; never raises. An empty text passes through unchanged.

    Args:
        text: Raw model output to scan.
        system_prompt: Optional registered system prompt for Jaccard overlap
            detection (≥0.6 triggers full-text masking with JACCARD_SYSTEM_OVERLAP).

    Returns:
        RedactionResult — inspect leakage_detected before using redacted_text.
    """
    if not text:
        return RedactionResult(leakage_detected=False, redacted_text=text)

    patterns_matched: list[str] = []
    redacted = text

    for name, pattern in _LEAKAGE_PATTERNS:
        if pattern.search(redacted):
            patterns_matched.append(name)
            redacted = pattern.sub(_MASK, redacted)

    # Jaccard overlap check against registered system prompt
    if system_prompt and not patterns_matched:
        if _jaccard(text, system_prompt) >= _JACCARD_THRESHOLD:
            patterns_matched.append("JACCARD_SYSTEM_OVERLAP")
            redacted = _MASK

    leakage = bool(patterns_matched)
    return RedactionResult(
        leakage_detected=leakage,
        redacted_text=redacted if leakage else text,
        patterns_matched=patterns_matched,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"[가-힣]+|[a-zA-Z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
