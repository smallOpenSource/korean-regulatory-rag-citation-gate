"""자본시장법 §54 직무관련정보 — PII masking + leak-warning detection (T200).

Scans outbound text (e.g. Customer 360 → external-domain email drafts) for
Korean PII patterns and produces both (a) a masked version of the text safe
for external transmission and (b) a leak report the caller can use to emit
`info_leak_warning_shown` audit rows and surface a confirmation banner in
the UI before send.

Patterns covered:
  - 주민등록번호 (RRN, 13 digit with hyphen)
  - 외국인등록번호 (ARC, 13 digit, gender-digit 5–8)
  - 휴대폰 / 일반 전화
  - 이메일 (RFC-ish; conservative, no IDN punycode)
  - 카드번호 (16-digit, dashed or contiguous)
  - 계좌번호 (3-2-6 / 3-3-6 / 4-2-7 etc. Korean bank patterns)

The module is dependency-free and deterministic.
"""

from __future__ import annotations

import re

# ─── Pattern catalogue ────────────────────────────────────────────────────────

# Boundary helpers: `\b` does not fire correctly when Korean Hangul is adjacent
# to digits (architect review 2026-05-18). Replace with explicit lookarounds
# that block neighbouring digits but ALLOW Hangul / Latin letters / punctuation.
_NOT_DIGIT_BEFORE = r"(?<!\d)"
_NOT_DIGIT_AFTER = r"(?!\d)"

_PII_PATTERNS: dict[str, tuple[re.Pattern[str], str]] = {
    # category → (regex, mask replacement)
    "rrn":            (re.compile(_NOT_DIGIT_BEFORE + r"\d{6}-?[1-4]\d{6}" + _NOT_DIGIT_AFTER),                 "[REDACTED:RRN]"),
    "arc":            (re.compile(_NOT_DIGIT_BEFORE + r"\d{6}-?[5-8]\d{6}" + _NOT_DIGIT_AFTER),                 "[REDACTED:ARC]"),
    "mobile":         (re.compile(_NOT_DIGIT_BEFORE + r"01[016789]-?\d{3,4}-?\d{4}" + _NOT_DIGIT_AFTER),        "[REDACTED:MOBILE]"),
    "phone":          (re.compile(_NOT_DIGIT_BEFORE + r"0(?!1[016789])\d{1,2}-?\d{3,4}-?\d{4}" + _NOT_DIGIT_AFTER), "[REDACTED:PHONE]"),
    "card":           (re.compile(_NOT_DIGIT_BEFORE + r"\d{4}-?\d{4}-?\d{4}-?\d{4}" + _NOT_DIGIT_AFTER),        "[REDACTED:CARD]"),
    "account":        (re.compile(_NOT_DIGIT_BEFORE + r"\d{3,4}-\d{2,4}-\d{4,7}" + _NOT_DIGIT_AFTER),           "[REDACTED:ACCOUNT]"),
    "email":          (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED:EMAIL]"),
}

# Categories ordered so higher-specificity patterns mask before lower (e.g. RRN
# before generic 13-digit). Python dict preserves insertion order; this order
# is iteration order.

# ─── Public API ───────────────────────────────────────────────────────────────


def detect_pii(text: str) -> dict[str, object]:
    """Locate PII matches in text without modifying it.

    Returns:
        flagged: bool — True if any PII detected
        matches: list[dict] — {category, value, position, length}
        category_counts: dict[str, int]
        audit_action_code: str — "info_leak_warning_shown" if flagged
    """
    if not text:
        return {
            "flagged": False,
            "matches": [],
            "category_counts": {k: 0 for k in _PII_PATTERNS},
            "audit_action_code": "",
        }

    matches: list[dict[str, object]] = []
    counts: dict[str, int] = {k: 0 for k in _PII_PATTERNS}

    for category, (pattern, _mask) in _PII_PATTERNS.items():
        for m in pattern.finditer(text):
            matches.append({
                "category": category,
                "value": m.group(0),
                "position": m.start(),
                "length": len(m.group(0)),
            })
            counts[category] += 1

    flagged = len(matches) > 0
    return {
        "flagged": flagged,
        "matches": matches,
        "category_counts": counts,
        "audit_action_code": "info_leak_warning_shown" if flagged else "",
    }


def mask_pii(text: str) -> dict[str, object]:
    """Return masked copy of text plus the detection report.

    Mask order follows insertion order of `_PII_PATTERNS` so that
    higher-specificity Korean residence numbers do not collide with generic
    digit sequences. Already-masked tokens (`[REDACTED:...]`) are not
    re-scanned.

    Returns:
        masked_text: str
        flagged: bool
        matches: list[dict] (positions reference the ORIGINAL text)
        category_counts: dict[str, int]
        audit_action_code: str
    """
    if not text:
        report = detect_pii(text)
        return {"masked_text": "", **report}

    report = detect_pii(text)
    masked = text
    for pattern, mask in _PII_PATTERNS.values():
        masked = pattern.sub(mask, masked)
    return {"masked_text": masked, **report}


def is_external_domain(recipient_email: str, allowlist: tuple[str, ...] = ()) -> bool:
    """Return True when the recipient email's domain is NOT in the allowlist.

    Used to decide whether T200 masking warning should fire — internal-domain
    sends are pre-approved by REG-01 §5; external sends require the warning.
    """
    if not recipient_email or "@" not in recipient_email:
        return False
    domain = recipient_email.rsplit("@", 1)[1].lower().strip()
    if not domain:
        return False
    return domain not in {d.lower() for d in allowlist}
