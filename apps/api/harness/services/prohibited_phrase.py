"""Prohibited-phrase post-processing guard (T201, REG-01 §5 자본시장법 §55).

자본시장법 §55 (손실보전 금지) requires that AI recommendations and outbound emails
must be scanned for phrases that promise loss compensation or guaranteed returns.
This module provides a *post-processing* guard that complements the existing
unfair_solicitation rule engine (which fires at consultation time):

    unfair_solicitation.check()   → consultation BLOCK at recommendation time
    prohibited_phrase.scan_text() → post-generation BLOCK on any AI output or email

Both share regex sources but emit distinct audit codes so investigators can tell
which gate fired. Pure module, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# REG-01 §5 자본시장법 §55 — 손실보전 금지 phrase registry. Each entry pairs a
# regex with a phrase_id used in audit detail_json. Names match the regulatory
# vocabulary so reviewers can map findings back to the statute clause.
PROHIBITED_PHRASES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("loss_compensation", re.compile(r"손실\s*보전|손실을?\s*보전|손실.*보장|손실.*책임", re.IGNORECASE)),
    ("profit_guarantee", re.compile(r"이익\s*보장|수익\s*보장|원금\s*보장|반드시\s*수익|확정\s*수익", re.IGNORECASE)),
    ("definitive_safe", re.compile(r"100\s*%\s*안전|절대\s*안전|위험\s*없[음다]", re.IGNORECASE)),
    ("definitive_return", re.compile(r"무조건\s*수익|확실히?\s*돈을?\s*법", re.IGNORECASE)),
)


@dataclass(frozen=True, slots=True)
class ProhibitedPhraseHit:
    phrase_id: str
    matched_span: str  # Already redacted to ≤80 chars to avoid leaking surrounding PII
    rule: str = "PROHIBITED_PHRASE_BLOCKED"


def scan_text(text: str | None) -> list[ProhibitedPhraseHit]:
    """Return all prohibited-phrase hits in *text* (empty list = passes).

    Callers BLOCK the surrounding action when the list is non-empty and write an
    audit row with action_code ``prohibited_phrase_blocked`` and detail_json
    ``{"phrase_ids": [...], "samples": [...]}``.  Samples are pre-truncated to 80
    characters so the audit row cannot leak full email/customer content.
    """
    if not text:
        return []
    hits: list[ProhibitedPhraseHit] = []
    seen: set[str] = set()
    for phrase_id, pattern in PROHIBITED_PHRASES:
        match = pattern.search(text)
        if match is None or phrase_id in seen:
            continue
        sample = match.group(0).strip()[:80]
        hits.append(ProhibitedPhraseHit(phrase_id=phrase_id, matched_span=sample))
        seen.add(phrase_id)
    return hits


def audit_detail_from_hits(hits: list[ProhibitedPhraseHit]) -> dict[str, list[str]]:
    """Pack hits into the canonical audit detail_json shape."""
    return {
        "phrase_ids": [h.phrase_id for h in hits],
        "samples": [h.matched_span for h in hits],
    }
