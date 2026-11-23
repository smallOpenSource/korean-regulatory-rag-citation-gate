"""Azure Content Safety pre/post check — LLM guard (ADR-005 §6, W3-T6).

Toggle: AZURE_CONTENT_SAFETY_ENABLED=true (default OFF for PoC).
Pre-checks user input; post-checks AI output.
On flag: returns blocked=True with reason CONTENT_SAFETY_BLOCKED.
Caller must add CONTENT_SAFETY_BLOCKED to RAG_FAIL_CLOSED_CODES and emit
ai_fail_closed audit row.

Required env when enabled:
  AZURE_CONTENT_SAFETY_ENDPOINT  — e.g. https://xxx.cognitiveservices.azure.com
  AZURE_CONTENT_SAFETY_API_KEY   — subscription key
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from apps.api.harness.core.logging import redact_secret_text

# Severity 0-6: 0=safe, 2=low, 4=medium, 6=high.
# Block threshold: anything >= this severity triggers fail-closed.
_DEFAULT_THRESHOLD = 2
CONTENT_SAFETY_CATEGORIES: tuple[str, ...] = ("Hate", "Violence", "Sexual", "SelfHarm")


@dataclass(frozen=True)
class ContentSafetyResult:
    """Result of one content safety check."""

    blocked: bool
    reason: str | None              # "CONTENT_SAFETY_BLOCKED" when blocked, else None
    categories_flagged: list[str] = field(default_factory=list)
    max_severity: int = 0


def is_content_safety_enabled() -> bool:
    """Return True when AZURE_CONTENT_SAFETY_ENABLED=true."""
    return os.getenv("AZURE_CONTENT_SAFETY_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _block_threshold() -> int:
    try:
        return int(os.getenv("AZURE_CONTENT_SAFETY_THRESHOLD", str(_DEFAULT_THRESHOLD)))
    except ValueError:
        return _DEFAULT_THRESHOLD


def _call_api(text: str) -> dict[str, Any]:
    """POST to Azure Content Safety REST API; return parsed JSON."""
    endpoint = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "").strip().rstrip("/")
    api_key = os.getenv("AZURE_CONTENT_SAFETY_API_KEY", "").strip()

    if not endpoint or not api_key:
        return {"categoriesAnalysis": []}

    api_version = os.getenv("AZURE_CONTENT_SAFETY_API_VERSION", "2024-09-01")
    url = f"{endpoint}/contentsafety/text:analyze?api-version={api_version}"
    body = json.dumps({
        "text": text[:10_000],
        "categories": list(CONTENT_SAFETY_CATEGORIES),
        "outputType": "FourSeverityLevels",
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=body,
        headers={
            "Ocp-Apim-Subscription-Key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = float(os.getenv("AZURE_CONTENT_SAFETY_TIMEOUT_SECONDS", "5.0"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())  # type: ignore[no-any-return]
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"Content Safety API HTTP {exc.code}: {redact_secret_text(str(exc))}"
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"Content Safety API error: {redact_secret_text(str(exc))}"
        ) from exc


def check_content_safety(text: str, *, context: str = "input") -> ContentSafetyResult:
    """Run Azure Content Safety check; fail-open on infrastructure errors.

    Args:
        text: User input or AI output to scan.
        context: "input" | "output" (informational — used in caller audit logs).

    Returns:
        ContentSafetyResult — inspect ``blocked`` before returning to user.
    """
    _ = context  # reserved for future per-context threshold config

    if not is_content_safety_enabled():
        return ContentSafetyResult(blocked=False, reason=None)

    try:
        response = _call_api(text)
    except Exception:  # noqa: BLE001
        # Fail-open: infrastructure issues must not block legitimate requests
        return ContentSafetyResult(blocked=False, reason=None)

    threshold = _block_threshold()
    flagged: list[str] = []
    max_sev = 0

    for item in response.get("categoriesAnalysis", []):
        category = str(item.get("category", ""))
        severity = int(item.get("severity", 0))
        max_sev = max(max_sev, severity)
        if severity >= threshold:
            flagged.append(f"{category}:{severity}")

    blocked = bool(flagged)
    return ContentSafetyResult(
        blocked=blocked,
        reason="CONTENT_SAFETY_BLOCKED" if blocked else None,
        categories_flagged=flagged,
        max_severity=max_sev,
    )
