"""금소법 §20 불공정영업 금지 — recommendation reasoning lint (T205).

Detects keywords associated with unfair sales practices in AI-generated
recommendation reasoning text:

  - **bundling** (끼워팔기): tying multiple products to one decision
  - **coercion** (강요): pressuring with mandatory framing or threats
  - **aggressive** (공격적): urgency, fear, scarcity manipulation tactics

A non-empty flag returns `flagged=True` and the per-keyword positions; the
caller is expected to (a) emit an `unfair_practice_flagged` audit row and
(b) block or downgrade the AI output per REG-01 §5 enforcement policy.

This module is dependency-free and deterministic. Keyword lists are
intentionally explicit (not regex over generic stems) so audit reviewers
can read exactly which strings trigger the flag.
"""

from __future__ import annotations

# Keyword catalogues per §20 enforcement guidance (FSC + KOFIA precedents).
# Each tuple = (substring to match, severity weight 1-3).
BUNDLING_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("끼워팔기", 3),
    ("함께 가입", 2),
    ("동시 가입", 2),
    ("같이 가입", 2),
    ("패키지 가입", 2),
    ("동시에 가입", 2),
    ("묶음 상품", 2),
    ("세트 가입", 2),
)

COERCION_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("반드시 가입", 3),
    ("무조건 가입", 3),
    ("의무 가입", 3),
    ("필수 가입", 3),
    ("안 사면 손해", 3),
    ("안 하면 손해", 3),
    ("위약금", 2),
    ("거절 시", 2),
    ("거절하시면", 2),
    ("불이익", 2),
)

AGGRESSIVE_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("빨리 결정", 2),
    ("마지막 기회", 2),
    ("한정 수량", 2),
    ("지금 안 하면", 2),
    ("후회하실", 2),
    ("손해 보실", 2),
    ("늦으면", 2),
    ("오늘만", 2),
)

CATEGORY_MAP: dict[str, tuple[tuple[str, int], ...]] = {
    "bundling": BUNDLING_KEYWORDS,
    "coercion": COERCION_KEYWORDS,
    "aggressive": AGGRESSIVE_KEYWORDS,
}


def lint_reasoning(text: str) -> dict[str, object]:
    """Scan AI reasoning text for unfair-sales-practice keywords.

    Returns:
        flagged: bool — True if any keyword present
        violations: list[dict] — each {keyword, category, position, severity}
        category_counts: dict[str, int] — hits per category
        severity_total: int — sum of severity weights (0 if clean)
        audit_action_code: str — "unfair_practice_flagged" if flagged else ""
    """
    if not text:
        return {
            "flagged": False,
            "violations": [],
            "category_counts": {k: 0 for k in CATEGORY_MAP},
            "severity_total": 0,
            "audit_action_code": "",
        }

    violations: list[dict[str, object]] = []
    category_counts: dict[str, int] = {k: 0 for k in CATEGORY_MAP}
    severity_total = 0

    for category, keyword_list in CATEGORY_MAP.items():
        for keyword, severity in keyword_list:
            start = 0
            while True:
                pos = text.find(keyword, start)
                if pos == -1:
                    break
                violations.append({
                    "keyword": keyword,
                    "category": category,
                    "position": pos,
                    "severity": severity,
                })
                category_counts[category] += 1
                severity_total += severity
                start = pos + len(keyword)

    flagged = len(violations) > 0
    return {
        "flagged": flagged,
        "violations": violations,
        "category_counts": category_counts,
        "severity_total": severity_total,
        "audit_action_code": "unfair_practice_flagged" if flagged else "",
    }


def is_clean(text: str) -> bool:
    """Convenience helper — True if text has no unfair-practice keywords."""
    return not lint_reasoning(text)["flagged"]
