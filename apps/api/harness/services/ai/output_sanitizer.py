"""Output sanitization utility (T278, REG-04 §6).

Applied to every quarantined-LLM response before customer-facing delivery. Complements
``llm_redactor`` (system-prompt leakage) and ``content_safety`` (Azure Content Safety
toggle) by handling three additional defenses:

1. HTML strip — removes any HTML tags the LLM may have echoed back, preventing
   stored-XSS via AI output.
2. Link allowlist — only permits hyperlinks whose host appears in the configured
   allowlist (typically synthetic example.invalid + the bank's own domains).
3. Instruction-echo suppression — strips obvious "ignore previous instructions"
   style fragments the LLM may have parroted from a successful injection that
   slipped past the upstream injection_detector.

The function is pure and side-effect free. Returns a :class:`SanitizeResult` whose
`removed` flag tells callers whether to mark the surrounding ai_outputs row with
``LLM07_LEAKAGE_REDACTED`` or ``OUTPUT_SANITIZED`` in detail_json.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser


_DEFAULT_LINK_ALLOWLIST: frozenset[str] = frozenset({
    "example.invalid",
    "harness.local",
    "harness-internal.example.invalid",
})

_INSTRUCTION_ECHO_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(ignore|disregard|forget)\b[^.]{0,80}(previous|prior|above)\b[^.]{0,40}instructions?"),
    re.compile(r"(?i)\bsystem\s*prompt\b[^.]{0,40}(reveal|disclose|show|share)"),
    re.compile(r"(?i)<\s*USER_DATA\s*>"),
    re.compile(r"(?i)<\s*RETRIEVED_CONTEXT\b"),
)

_URL_PATTERN: re.Pattern[str] = re.compile(r"https?://([^\s/]+)([^\s]*)")


@dataclass(frozen=True, slots=True)
class SanitizeResult:
    text: str
    html_stripped: bool
    links_removed: int
    instruction_echoes_removed: int

    @property
    def removed(self) -> bool:
        return self.html_stripped or self.links_removed > 0 or self.instruction_echoes_removed > 0


class _HTMLStripper(HTMLParser):
    """Collect text content while discarding tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self.saw_tag: bool = False

    def handle_starttag(self, tag: str, attrs):  # noqa: ANN001
        self.saw_tag = True

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def sanitize_llm_output(
    text: str | None,
    *,
    link_allowlist: frozenset[str] | None = None,
) -> SanitizeResult:
    """Run the three sanitization passes and return :class:`SanitizeResult`."""
    if not text:
        return SanitizeResult(text="", html_stripped=False, links_removed=0, instruction_echoes_removed=0)
    allow = link_allowlist if link_allowlist is not None else _DEFAULT_LINK_ALLOWLIST

    # 1) HTML strip
    stripper = _HTMLStripper()
    stripper.feed(text)
    stripped = stripper.text()
    html_stripped = stripper.saw_tag

    # 2) Link allowlist — replace disallowed URLs with [link removed]
    links_removed = 0

    def _replace_link(match: re.Match[str]) -> str:
        nonlocal links_removed
        host = match.group(1).lower()
        if any(host == d or host.endswith("." + d) for d in allow):
            return match.group(0)
        links_removed += 1
        return "[link removed]"

    after_links = _URL_PATTERN.sub(_replace_link, stripped)

    # 3) Instruction-echo suppression
    instruction_echoes_removed = 0
    after_echoes = after_links
    for pattern in _INSTRUCTION_ECHO_PATTERNS:
        after_echoes, n = pattern.subn("[instruction redacted]", after_echoes)
        instruction_echoes_removed += n

    return SanitizeResult(
        text=after_echoes,
        html_stripped=html_stripped,
        links_removed=links_removed,
        instruction_echoes_removed=instruction_echoes_removed,
    )
