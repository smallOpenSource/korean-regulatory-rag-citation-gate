"""Marketing classification, 광고심의 leading-block lint, PII outbound gate.

REG-02 T224 / REG-03 T247 / ADR-002 §Marketing Classification.
Static rule first; AI compliance_check (Azure GPT5/mini) as second gate.
AI fails closed → BLOCK.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from apps.api.harness.core.logging import redact_secret_text

logger = logging.getLogger(__name__)

# svc-viability-v4 I7 (ADR-019.1) — singleton state for ai_compliance_mock_used
# audit emit. Module-level dict so a single uvicorn worker process emits the
# row exactly once across the process lifetime regardless of how many marketing
# drafts the operator submits. AI_COMPLIANCE_MODE env (live|mock_pass|mock_fail)
# is checked inside ai_compliance_check(); main.py startup safety prevents
# non-live modes from being used in production (app_env == "production").
_MOCK_EMIT_STATE: dict[str, Any] = {"emitted": False, "mode_first_seen_at": None}

# ---------------------------------------------------------------------------
# PII outbound regex (ADR-002 §Audit Redaction Filter / task spec)
# ---------------------------------------------------------------------------

# 주민등록번호 — 6-digit birth prefix + separator + generation digit 1-4 + 6 digits
RRN_RE = re.compile(r"\b\d{6}-[1-4]\d{6}\b")

# 신용카드번호 — 4×4 digit blocks (common Korean / international format)
CARD_4X4_RE = re.compile(r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b")
# Compact 13–19 digit sequences that look like card numbers
CARD_COMPACT_RE = re.compile(r"\b\d{13,19}\b")

# 계좌번호 — Korean bank account numbers are typically 10–14 digits
ACCOUNT_RE = re.compile(r"\b\d{3}[\s\-]\d{6,8}[\s\-]\d{2,3}\b")

PII_CHECKS: list[tuple[re.Pattern[str], str]] = [
    (RRN_RE, "rrn"),
    (CARD_4X4_RE, "card_number"),
    (ACCOUNT_RE, "bank_account"),
]


def check_pii_outbound(subject: str, body: str) -> list[str]:
    """Return a list of PII category names found; empty list means clear.

    Checks 주민번호, 카드번호, 계좌번호 patterns across subject + body.
    """
    content = f"{subject}\n{body}"
    hits: list[str] = []
    for pattern, category in PII_CHECKS:
        if pattern.search(content):
            hits.append(category)
    return hits


# ---------------------------------------------------------------------------
# Marketing classification — static rules
# ---------------------------------------------------------------------------

# Keywords that indicate a marketing / promotional intent
_MARKETING_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"[이상품][\s]*(소개|추천|안내|홍보)", re.IGNORECASE),
    re.compile(r"(이벤트|프로모션|혜택|할인|특별|한정)", re.IGNORECASE),
    re.compile(r"(신상품|신규|출시|런칭|캠페인)", re.IGNORECASE),
    re.compile(r"(투자|펀드|ETF|ELS|DLS)[\s]*(소개|안내|추천|홍보)", re.IGNORECASE),
    re.compile(r"광고", re.IGNORECASE),
]

CLASSIFICATION_MARKETING = "MARKETING"
CLASSIFICATION_OPERATIONAL = "OPERATIONAL"


def classify_email_static(subject: str, body: str) -> str:
    """Return MARKETING or OPERATIONAL based on keyword heuristics.

    This is the first classification gate; the AI compliance check is the second.
    """
    content = f"{subject}\n{body}"
    if any(pattern.search(content) for pattern in _MARKETING_PATTERNS):
        return CLASSIFICATION_MARKETING
    return CLASSIFICATION_OPERATIONAL


# ---------------------------------------------------------------------------
# 광고심의 leading-block lint (static rule)
# ---------------------------------------------------------------------------

# 수신거부 안내 patterns (무료/즉시 처리 안내 required per REG-03)
_OPT_OUT_RE = re.compile(r"수신\s*거부", re.IGNORECASE)

# Leading block pattern: 광고심의 사전심의필 <number>
_LEADING_BLOCK_SUBJECT_RE = re.compile(r"광고심의\s*사전심의필\s*\S+")
_LEADING_BLOCK_BODY_RE = re.compile(r"^광고심의\s*사전심의필\s*\S+", re.MULTILINE)


@dataclass(frozen=True)
class MarketingLintResult:
    passed: bool
    issue_codes: list[str]
    description: str


def lint_marketing_leading_block(
    subject: str,
    body: str,
    pre_review_number: str,
) -> MarketingLintResult:
    """Static lint for 광고심의 사전심의필 leading block (REG-03 T247).

    Checks:
    1. Subject contains `광고심의 사전심의필 {pre_review_number}`.
    2. Body FIRST non-empty line contains `광고심의 사전심의필 {pre_review_number}`.
    3. Body contains 수신거부 안내.
    """
    issues: list[str] = []

    # Build the expected literal token for this draft
    expected_token = f"광고심의 사전심의필 {pre_review_number}"

    if expected_token not in subject:
        issues.append("MISSING_LEADING_BLOCK_SUBJECT")

    # Check first non-empty body line
    first_line = next(
        (line.strip() for line in body.splitlines() if line.strip()),
        "",
    )
    if expected_token not in first_line:
        issues.append("MISSING_LEADING_BLOCK_BODY")

    if not _OPT_OUT_RE.search(body):
        issues.append("MISSING_OPT_OUT")

    if issues:
        return MarketingLintResult(
            passed=False,
            issue_codes=issues,
            description=f"광고심의 leading-block 정적 검사 실패: {', '.join(issues)}",
        )
    return MarketingLintResult(
        passed=True,
        issue_codes=[],
        description="광고심의 leading-block 정적 검사 통과",
    )


# ---------------------------------------------------------------------------
# AI compliance_check — Azure GPT5/mini cascade (fail-closed)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AiComplianceResult:
    passed: bool
    issue_codes: list[str]
    summary: str
    ai_called: bool  # False if AI skipped / degraded


# P1-a: the AI compliance check must review the FULL body so its window matches
# the full-text static leading-block lint. email_drafts.body is unbounded TEXT
# (V008); this defensive cap protects the Azure input budget against pathological
# inputs while never truncating a realistic marketing email (incl. its footer).
# Unit = Python str code points (not bytes/tokens): 8000 Korean chars ≈ 24 KB
# UTF-8 / ~8–12k tokens, comfortably within the Azure deployment input limit
# (max_completion_tokens=2000 is the separate OUTPUT budget).
_AI_REVIEW_BODY_CAP = 8000


def _build_ai_prompt(subject: str, body: str, pre_review_number: str) -> list[dict[str, str]]:
    """Build the PROMPT-08 messages for the Azure OpenAI chat endpoint.

    The AI reviews the FULL body (defensively capped), aligning its review window
    with the full-text static lint. The earlier ``body[:200]`` excerpt left the
    AI unable to see structural footer items its own checklist asks about
    (수신거부 안내 — always at the end — and any 본문 후반부 위반), so the AI verdict
    disagreed with the full-text static lint and read as non-deterministic
    issue_codes relative to the real email.
    """
    system_prompt = (
        "당신은 금융 광고심의 전문 AI입니다.\n"
        "금소법 §22(광고규제), KOFIA 광고심의 세칙에 따라 이메일 광고문 초안을 검토합니다.\n"
        "부적합 표현 하나라도 발견 시 passed=false. 불확실한 경우 passed=false (fail-closed).\n"
        "응답은 JSON만 출력합니다: {\"passed\": bool, \"issue_codes\": [str], \"summary\": str}"
    )
    body_for_review = body[:_AI_REVIEW_BODY_CAP]
    truncation_note = (
        f"\n(주의: 본문이 {_AI_REVIEW_BODY_CAP}자를 초과해 잘렸습니다. 잘린 부분은 "
        "미검토이므로 불확실 시 passed=false 처리하십시오.)"
        if len(body) > _AI_REVIEW_BODY_CAP
        else ""
    )
    user_prompt = (
        f"# 광고 이메일 초안 검토\n\n"
        f"## 제목\n{subject}\n\n"
        f"## 본문 전문\n{body_for_review}{truncation_note}\n\n"
        f"## 사전심의필번호\n{pre_review_number}\n\n"
        "검토 항목:\n"
        f"1. '광고심의 사전심의필 {pre_review_number}' 선행 블록이 제목과 본문 첫 줄에 모두 있는가?\n"
        "2. 손실가능성/위험등급 기재 여부.\n"
        "3. 원금보장·이익보장·단정적 수익 표현 여부.\n"
        "4. 수신거부 안내 포함 여부.\n"
        "5. 기타 금소법·KOFIA 위반 사항.\n"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _call_azure_openai_sync(
    endpoint: str,
    api_key: str,
    deployment: str,
    messages: list[dict[str, str]],
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Synchronous Azure OpenAI chat call; caller wraps in asyncio.to_thread.

    Uses ``AZURE_OPENAI_API_VERSION`` from env (.env single SoT) and the
    gpt-5.5 reasoning-model contract:
    - ``max_completion_tokens`` instead of ``max_tokens``
    - no ``temperature`` (gpt-5.5 only accepts default 1)

    Same fix applied to ``services/house_view.py`` in 9a6e0ae;
    ``services/marketing/core.py`` was missed and surfaced as F8 AI_ERROR.
    """

    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview").strip() or "2025-04-01-preview"
    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    # gpt-5.5 reasoning model consumes hidden tokens before visible output.
    # 300 token budget left content empty (Expecting value char 0); house_view
    # uses 2000 for the same model class. response_format constrains output
    # to valid JSON so the downstream json.loads() in ai_compliance_check is
    # safe across content variation.
    payload = json.dumps(
        {
            "messages": messages,
            "max_completion_tokens": 2000,
            "response_format": {"type": "json_object"},
        },
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


async def _emit_mock_singleton(mode: str, pid: int, started_at: str) -> None:
    """Insert one ai_compliance_mock_used audit_logs row per process startup.

    svc-viability-v4 I7 (ADR-019.1). Resolves ``DATABASE_URL`` from the env,
    opens a dedicated asyncpg connection (the services layer doesn't carry a
    request-scoped pool handle), and INSERTs the singleton emit row. Any
    failure is logged with WARNING and swallowed — the WARNING log itself is
    a redundant ops signal so missing DB connectivity does not silently mask
    the mode usage.
    """

    database_url = os.getenv("DATABASE_URL", "").strip()
    if database_url.startswith("postgresql+asyncpg://"):
        database_url = "postgresql://" + database_url[len("postgresql+asyncpg://"):]
    if not database_url:
        logger.warning(
            "ai_compliance_mock_used singleton emit skipped: DATABASE_URL unset "
            "(mode=%s pid=%d)",
            mode, pid,
        )
        return

    try:
        import asyncpg
    except ImportError:
        logger.warning("ai_compliance_mock_used emit skipped: asyncpg not importable")
        return

    detail = {
        "mode": mode,
        "pid": pid,
        "started_at": started_at,
        "mode_first_seen_at": started_at,
    }
    try:
        conn = await asyncpg.connect(database_url)
        try:
            await conn.execute(
                "/* sql_id: ai_compliance_mock_singleton_emit */ "
                "INSERT INTO audit_logs(action_code, resource_type, detail_json) "
                "VALUES ($1, $2, $3::jsonb)",
                "ai_compliance_mock_used",
                "ai_compliance_mode_toggle",
                json.dumps(detail),
            )
        finally:
            await conn.close()
    except Exception as exc:  # noqa: BLE001 - emit best-effort, WARNING is canonical
        logger.warning(
            "ai_compliance_mock_used singleton emit failed: %s",
            redact_secret_text(str(exc))[:200],
        )


async def ai_compliance_check(
    subject: str,
    body: str,
    pre_review_number: str,
) -> AiComplianceResult:
    """Run PROMPT-08 AI compliance check; fail-closed on any error.

    Returns AiComplianceResult with passed=False if AI is unavailable.

    svc-viability-v4 I7 (ADR-019.1) — the ``AI_COMPLIANCE_MODE`` env var
    (live|mock_pass|mock_fail) bypasses the Azure call in non-production
    PoC environments. ``main.py`` startup raises if a non-live mode is set
    with ``app_env == "production"``, so this branch can never be reached in
    a production process. The first non-live invocation per process emits a
    singleton ``ai_compliance_mock_used`` audit row + WARNING log.
    """

    mode = os.getenv("AI_COMPLIANCE_MODE", "live").strip() or "live"

    if mode != "live":
        global _MOCK_EMIT_STATE
        if not _MOCK_EMIT_STATE["emitted"]:
            iso = datetime.now(timezone.utc).isoformat()
            _MOCK_EMIT_STATE["mode_first_seen_at"] = iso
            _MOCK_EMIT_STATE["emitted"] = True
            await _emit_mock_singleton(mode=mode, pid=os.getpid(), started_at=iso)
            logger.warning(
                "ai_compliance_mock_used singleton emit: mode=%s pid=%d started_at=%s",
                mode, os.getpid(), iso,
            )
        if mode == "mock_pass":
            return AiComplianceResult(
                passed=True,
                issue_codes=[],
                summary="MOCK_PASS — AI_COMPLIANCE_MODE=mock_pass (PoC bypass, see ADR-019.1)",
                ai_called=False,
            )
        if mode == "mock_fail":
            return AiComplianceResult(
                passed=False,
                issue_codes=["MOCK_FAIL"],
                summary="MOCK_FAIL — AI_COMPLIANCE_MODE=mock_fail (PoC bypass, see ADR-019.1)",
                ai_called=False,
            )
        raise ValueError(
            f"Unknown AI_COMPLIANCE_MODE={mode!r}; allowed: live|mock_pass|mock_fail"
        )

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "").strip()

    if not (endpoint and api_key and deployment):
        # AI not configured → fail closed per ADR-002
        return AiComplianceResult(
            passed=False,
            issue_codes=["AI_UNAVAILABLE"],
            summary="AI compliance_check 설정 미완료 — fail-closed (BLOCK)",
            ai_called=False,
        )

    messages = _build_ai_prompt(subject, body, pre_review_number)

    try:
        raw = await asyncio.to_thread(
            _call_azure_openai_sync,
            endpoint,
            api_key,
            deployment,
            messages,
        )
        content = raw["choices"][0]["message"]["content"].strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = re.sub(r"^```[a-z]*\n?", "", content)
            content = re.sub(r"\n?```$", "", content)
        parsed: dict[str, Any] = json.loads(content)
        passed = bool(parsed.get("passed", False))
        issue_codes = list(parsed.get("issue_codes", []))
        summary = str(parsed.get("summary", ""))
        return AiComplianceResult(
            passed=passed,
            issue_codes=issue_codes,
            summary=summary,
            ai_called=True,
        )
    except Exception as exc:  # noqa: BLE001 - fail closed boundary
        safe = redact_secret_text(str(exc))
        return AiComplianceResult(
            passed=False,
            issue_codes=["AI_ERROR"],
            summary=f"AI compliance_check 오류 — fail-closed: {safe[:80]}",
            ai_called=True,
        )


# ---------------------------------------------------------------------------
# Combined marketing gate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketingGateResult:
    classification: str              # MARKETING | OPERATIONAL
    static_rule_pass: bool
    ai_compliance_pass: bool | None  # None when not applicable (OPERATIONAL)
    ai_reasoning_redacted: str | None
    decision: str                    # MARKETING_REVIEW_PASS | MARKETING_REVIEW_BLOCK
    lint_result: MarketingLintResult | None
    issue_codes: list[str]


async def run_marketing_gate(
    subject: str,
    body: str,
    marketing_classified: bool,
    pre_review_number: str | None,
) -> MarketingGateResult:
    """Run the full marketing review gate for a draft about to be submitted/sent.

    For OPERATIONAL drafts: pass immediately.
    For MARKETING drafts: static lint → AI cascade → BLOCK if either fails.
    """
    classification = (
        CLASSIFICATION_MARKETING
        if marketing_classified
        else classify_email_static(subject, body)
    )

    if classification == CLASSIFICATION_OPERATIONAL:
        return MarketingGateResult(
            classification=CLASSIFICATION_OPERATIONAL,
            static_rule_pass=True,
            ai_compliance_pass=None,
            ai_reasoning_redacted=None,
            decision="MARKETING_REVIEW_PASS",
            lint_result=None,
            issue_codes=[],
        )

    # MARKETING path — leading-block lint required
    number = (pre_review_number or "").strip()
    if not number:
        return MarketingGateResult(
            classification=CLASSIFICATION_MARKETING,
            static_rule_pass=False,
            ai_compliance_pass=None,
            ai_reasoning_redacted=None,
            decision="MARKETING_REVIEW_BLOCK",
            lint_result=None,
            issue_codes=["MISSING_PRE_REVIEW_NUMBER"],
        )

    lint = lint_marketing_leading_block(subject, body, number)
    if not lint.passed:
        return MarketingGateResult(
            classification=CLASSIFICATION_MARKETING,
            static_rule_pass=False,
            ai_compliance_pass=None,
            ai_reasoning_redacted=None,
            decision="MARKETING_REVIEW_BLOCK",
            lint_result=lint,
            issue_codes=lint.issue_codes,
        )

    # Static rule passed → AI cascade
    ai_result = await ai_compliance_check(subject, body, number)
    ai_pass = ai_result.passed
    decision = "MARKETING_REVIEW_PASS" if ai_pass else "MARKETING_REVIEW_BLOCK"

    return MarketingGateResult(
        classification=CLASSIFICATION_MARKETING,
        static_rule_pass=True,
        ai_compliance_pass=ai_pass,
        ai_reasoning_redacted=ai_result.summary[:500] if ai_result.summary else None,
        decision=decision,
        lint_result=lint,
        issue_codes=ai_result.issue_codes if not ai_pass else [],
    )
