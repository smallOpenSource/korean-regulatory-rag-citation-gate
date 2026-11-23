"""Prompt injection detection against the INJECTION_PATTERNS.yaml library.

Implements the runtime detection portion of ADR-005 §3.  The pattern file
is loaded on first use and reloaded when its mtime changes — no restart
required after a pattern update.

Usage::

    from apps.api.harness.services.ai.injection_detector import detect_injection

    result = detect_injection(user_text)
    if result.detected:
        # fail-closed: PROMPT_INJECTION_DETECTED
        ...

Returns :class:`InjectionDetectionResult` — always succeeds (never raises);
an empty / missing pattern file is treated as "no match".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

import yaml

_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}
_DEFAULT_PATTERNS_PATH = "prompts/INJECTION_PATTERNS.yaml"


class _PatternEntry(TypedDict, total=False):
    id: str
    category: str
    severity: str
    regex: str
    notes: str


# mtime-keyed cache: path -> (mtime, pattern_list)
_CACHE: dict[str, tuple[float, list[_PatternEntry]]] = {}


# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InjectionDetectionResult:
    """Result of a single injection-detection scan.

    Attributes:
        detected: True when any pattern matched.
        pattern_id: The matched pattern's ``id`` field (e.g. ``"PI-001"``).
        category: One of the six ADR-005 §3 categories.
        severity: ``"high"``, ``"medium"``, or ``"low"``.
        matched_text: First 200 chars of the matched substring.
    """

    detected: bool
    pattern_id: str | None
    category: str | None
    severity: str | None
    matched_text: str | None


# ---------------------------------------------------------------------------
# Pattern loading
# ---------------------------------------------------------------------------


def _coerce_entry(raw: object) -> _PatternEntry | None:
    """Coerce a raw YAML mapping to _PatternEntry; return None if not a dict."""
    if not isinstance(raw, dict):
        return None
    mapping = cast(dict[str, object], raw)
    return _PatternEntry(
        id=str(mapping.get("id", "")),
        category=str(mapping.get("category", "")),
        severity=str(mapping.get("severity", "low")),
        regex=str(mapping.get("regex", "")),
        notes=str(mapping.get("notes", "")),
    )


def _load_patterns(patterns_path: str) -> list[_PatternEntry]:
    """Load patterns from YAML with mtime-based cache reload.

    Returns an empty list if the file is missing or unreadable.
    """
    path = Path(patterns_path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return []

    cached = _CACHE.get(patterns_path)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    try:
        with path.open("r", encoding="utf-8") as fh:
            raw_data = cast(object, yaml.safe_load(fh))
    except Exception:  # noqa: BLE001
        return []

    raw_list: list[object]
    if isinstance(raw_data, dict):
        raw_map = cast(dict[str, object], raw_data)
        patterns_value: object = raw_map.get("patterns")
        raw_list = cast(list[object], patterns_value) if isinstance(patterns_value, list) else []
    else:
        raw_list = []

    patterns: list[_PatternEntry] = [
        entry
        for item in raw_list
        if (entry := _coerce_entry(item)) is not None
    ]
    _CACHE[patterns_path] = (mtime, patterns)
    return patterns


# ---------------------------------------------------------------------------
# Public detection function
# ---------------------------------------------------------------------------


def detect_injection(
    text: str,
    patterns_path: str = _DEFAULT_PATTERNS_PATH,
) -> InjectionDetectionResult:
    """Scan *text* against the injection pattern library.

    Patterns are evaluated in severity order (high → medium → low); the first
    match is returned.  High-severity matches trigger ``ai_injection_detected``
    audit and ``PROMPT_INJECTION_DETECTED`` fail-closed reason; medium-severity
    matches set ``quarantine_flag`` on the originating chunk.

    Args:
        text: The text to scan (user question, retrieved chunk body, or model
            output).
        patterns_path: Path to ``INJECTION_PATTERNS.yaml``; resolved relative
            to the process working directory.

    Returns:
        :class:`InjectionDetectionResult` — ``detected=False`` when no match.
    """
    if not text:
        return _no_match()

    patterns = _load_patterns(patterns_path)
    if not patterns:
        return _no_match()

    # Sort high → medium → low so we return the most severe match first.
    sorted_patterns = sorted(
        patterns,
        key=lambda p: _SEVERITY_ORDER.get(p.get("severity", "low"), 2),
    )

    for entry in sorted_patterns:
        pattern_id = entry.get("id", "")
        category = entry.get("category", "")
        severity = entry.get("severity", "low")
        regex = entry.get("regex", "")
        if not regex:
            continue
        try:
            match = re.search(regex, text)
        except re.error:
            continue
        if match:
            return InjectionDetectionResult(
                detected=True,
                pattern_id=pattern_id or None,
                category=category or None,
                severity=severity or None,
                matched_text=match.group(0)[:200],
            )

    return _no_match()


def _no_match() -> InjectionDetectionResult:
    return InjectionDetectionResult(
        detected=False,
        pattern_id=None,
        category=None,
        severity=None,
        matched_text=None,
    )
