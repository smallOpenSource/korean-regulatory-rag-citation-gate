"""Unit tests for the marketing AI-compliance review window (P1-a, 2026-05-30).

The AI compliance check (``_build_ai_prompt``) must review the FULL body so its
window matches the full-text static leading-block lint. The earlier ``body[:200]``
truncation hid structural footer items (수신거부 안내, always at the end) and any
본문 후반부 위반 from the AI, producing verdicts that disagreed with the full-text
lint and read as non-deterministic issue_codes relative to the real email.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apps.api.harness.services.marketing.core import (  # noqa: E402
    _AI_REVIEW_BODY_CAP,
    _build_ai_prompt,
)


def _user_content(subject: str, body: str, number: str) -> str:
    messages = _build_ai_prompt(subject, body, number)
    return next(m["content"] for m in messages if m["role"] == "user")


def test_ai_prompt_includes_body_beyond_200_chars():
    """A violation token past char 200 must reach the AI (window parity with lint)."""
    marker = "원금보장_위반_마커"
    body = ("가" * 400) + marker + ("나" * 100)
    content = _user_content("제목", body, "2026-12345")
    assert marker in content, "body past 200 chars was not shown to the AI"


def test_ai_prompt_includes_trailing_optout_footer():
    """수신거부 안내 (structurally at the end of the email) must be visible to the AI."""
    footer = "수신거부: unsubscribe@example.com"
    body = ("본문 내용 " * 80) + "\n" + footer  # footer is well past char 200
    assert len(body) > 200  # guard: the footer really is past the old window
    content = _user_content("제목", body, "2026-12345")
    assert footer in content, "trailing opt-out footer was not shown to the AI"


def test_ai_prompt_relabels_full_body_not_excerpt():
    """The prompt frames the body as 전문, not the old 첫 단락 excerpt."""
    content = _user_content("제목", "짧은 본문", "2026-12345")
    assert "본문 전문" in content
    assert "본문 첫 단락" not in content


def test_ai_prompt_caps_pathological_body_with_failclosed_note():
    """An over-cap body is truncated AND the AI is told to fail-closed on the tail."""
    tail_marker = "꼬리마커_CUT"
    body = ("엑스" * _AI_REVIEW_BODY_CAP) + tail_marker  # tail sits past the cap
    content = _user_content("제목", body, "2026-12345")
    assert tail_marker not in content, "over-cap tail should be truncated"
    assert "잘렸습니다" in content, "truncation note missing"
    assert "passed=false" in content, "fail-closed instruction missing on truncation"


def test_ai_prompt_no_truncation_note_for_realistic_body():
    """A realistic-length body carries no truncation note (deterministic full review)."""
    body = "정상 광고 본문입니다. " * 50  # well under the cap
    assert len(body) <= _AI_REVIEW_BODY_CAP
    content = _user_content("제목", body, "2026-12345")
    assert "잘렸습니다" not in content


def test_ai_prompt_at_exact_cap_sends_full_body_no_note():
    """len(body) == cap: the whole body is sent and NO truncation note appears
    (the `> cap` guard is strict — exact-cap bodies are not cut)."""
    body = "가" * _AI_REVIEW_BODY_CAP
    assert len(body) == _AI_REVIEW_BODY_CAP
    content = _user_content("제목", body, "2026-12345")
    assert "잘렸습니다" not in content
    assert content.count("가") >= _AI_REVIEW_BODY_CAP  # full body present, nothing cut


def test_ai_prompt_one_char_over_cap_truncates_tail():
    """len(body) == cap + 1: the (cap+1)-th char (a violation marker) is cut and
    the fail-closed truncation note appears (off-by-one boundary)."""
    body = ("가" * _AI_REVIEW_BODY_CAP) + "Ω"
    assert len(body) == _AI_REVIEW_BODY_CAP + 1
    content = _user_content("제목", body, "2026-12345")
    assert "Ω" not in content, "(cap+1)-th char should be truncated from the body"
    assert "잘렸습니다" in content
