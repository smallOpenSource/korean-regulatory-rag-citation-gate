#!/usr/bin/env python
"""audit_v1_ui_matrix.py — Service Viability Audit v1 / Axis 1

Captures 112 UI snapshots (27 protected routes × 4 roles + 1 wildcard × 4 roles)
per plan `.omc/plans/ralplan-wmah-service-viability-audit-v1.2.md` §3.1.

For every (role, route) cell we record:
  - PNG screenshot (full page)
  - DOM serialized HTML
  - console log (level=error+warning)
  - network log (status / url / response timing)
  - 5-layer extracted text (body text + aria-label + title + placeholder + alt)
  - PASS/FAIL per binary criteria (§3.1 Per-snapshot check):
      * english i18n key body hit count
      * microsecond literal body hit count
      * raw placeholder body hit count (— / N/A / 대기 중 / loading / 0%)
      * console error count
      * HTTP 5xx network count
      * 403 self-landing (if role has access per ACCESS_RULES)

BFS auth race mitigation v2 (per [[bfs-auth-race-window]] + Q4 wait map):
  - login → wait_for_url('**/dashboard')
  - per-route goto → networkidle → wait_for_timeout(700)
  - waits for `window.__wmahAuth?.getAccessToken()` to return truthy (auth
    restored from refresh cookie) up to AUTH_TOKEN_POLL_MS — covers the
    post-reload SPA bootstrap race where ProtectedRoute renders before
    restoreSession() completes, redirecting to /login.
  - waits for the per-route anchor selector from
    `scripts/audit_v1_wait_map.json` (h1/h2/main text-based locator)
    up to ANCHOR_POLL_MS — confirms the page actually rendered, not just
    that the URL changed.
  - login_redirect retry 1x via page.reload() if "직원 로그인" body
  - waits for `window.__wmahPageReady === true` flag (App.tsx:53-57) up to 3000ms

Output layout:
  audit-out/service-viability-v1/axis-1/baseline/
    {role}__{route_slug}.png
    {role}__{route_slug}.dom.html
    {role}__{route_slug}.console.json
    {role}__{route_slug}.network.json
  audit-out/service-viability-v1/axis-1/summary.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import re
import sys
import time
from typing import Any, Literal

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_WEB_PORT = os.environ.get("HARNESS_WEB_PORT", "8000")
DEFAULT_BASE_URL = os.environ.get("AUDIT_V1_BASE_URL", f"http://127.0.0.1:{_WEB_PORT}")
OUTPUT_BASE = REPO_ROOT / "audit-out" / "service-viability-v1" / "axis-1"

# ---------------------------------------------------------------------------
# Q4 wait map — per-route anchor selectors (BFS auth race mitigation v2)
# ---------------------------------------------------------------------------

def _load_wait_map() -> tuple[dict[str, str], dict[str, Any]]:
    path = REPO_ROOT / "scripts" / "audit_v1_wait_map.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        routes = dict(doc.get("routes", {}))
        schema = dict(doc.get("_schema", {}))
        return routes, schema
    except Exception:
        return {}, {}


_ROUTE_ANCHORS, _ANCHOR_SCHEMA = _load_wait_map()
_FALLBACK_ANCHOR: str = str(_ANCHOR_SCHEMA.get("fallback_selector", "main"))
_AUTH_TOKEN_POLL_MS: int = int(_ANCHOR_SCHEMA.get("auth_token_poll_ms", 6000))
_ANCHOR_POLL_MS: int = int(_ANCHOR_SCHEMA.get("anchor_poll_ms", 6000))

# ---------------------------------------------------------------------------
# Roles + creds (per worker brief: ADMIN canonical password = HarnessSynthetic!2026)
# ---------------------------------------------------------------------------

ROLE_CREDS: dict[str, dict[str, str]] = {
    "PB1": {"email": "synthetic.pb1@example.invalid", "password": "HarnessSynthetic!2026", "role_code": "PB"},
    "WM1": {"email": "synthetic.wm1@example.invalid", "password": "HarnessSynthetic!2026", "role_code": "WM"},
    "ADMIN": {"email": "synthetic.admin@example.invalid", "password": "HarnessSynthetic!2026", "role_code": "ADMIN"},
    "AUDIT_VIEWER": {"email": "synthetic.audit@example.invalid", "password": "HarnessSynthetic!2026", "role_code": "AUDIT_VIEWER"},
}

# ---------------------------------------------------------------------------
# ACCESS_RULES (mirror of apps/web/src/lib/access.ts — single SoT per
# [[access-rules-single-sot]]; runtime client behavior is the authority,
# we just mirror to predict per-role accessibility for landed_on_403 check).
# ---------------------------------------------------------------------------

ACCESS_RULES: dict[str, list[str]] = {
    "dashboard": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "customers": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
    "customer360": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
    "consultation": ["PB", "WM"],
    "nba": ["PB", "WM"],
    "aftercare": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
    "emailDrafts": ["PB", "WM"],
    "houseViews": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "houseViewActivation": ["ADMIN"],
    "rag": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
    "batch": ["ADMIN"],
    "audit": ["ADMIN", "AUDIT_VIEWER"],
    "quarantine": ["ADMIN"],
    "auditViewer": ["ADMIN", "AUDIT_VIEWER"],
    "rightsNotice": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
    "disputeCase": ["PB", "WM", "ADMIN", "AUDIT_VIEWER"],
    "conflictOfInterest": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "marketingReview": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "dataGovernance": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "consents": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "kycEdd": ["WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "aiModelCards": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "aiPolicy": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "koreanAIAct": ["PB", "WM", "BRANCH_MANAGER", "ADMIN", "AUDIT_VIEWER"],
    "aiAdminDashboard": ["ADMIN"],
    "autopilotDemo": ["PB", "WM", "BRANCH_MANAGER", "ADMIN"],
}

# ---------------------------------------------------------------------------
# Route inventory (App.tsx:67-101 SoT direct)
# ---------------------------------------------------------------------------

# (route_pattern, routeKey, slug)
ROUTES: list[tuple[str, str, str]] = [
    ("/dashboard",                          "dashboard",          "dashboard"),
    ("/customers",                          "customers",          "customers"),
    ("/customers/:customerId",              "customer360",        "customer-360"),
    ("/consultations/:consultationId",      "consultation",       "consultation"),
    ("/nba",                                "nba",                "nba"),
    ("/aftercare",                          "aftercare",          "aftercare"),
    ("/email-drafts",                       "emailDrafts",        "email-drafts"),
    ("/house-views",                        "houseViews",         "house-views"),
    ("/house-views/:houseViewId",           "houseViews",         "house-view-detail"),
    ("/house-views/:houseViewId/activate",  "houseViewActivation","house-view-activate"),
    ("/rag",                                "rag",                "rag"),
    ("/batch",                              "batch",              "batch"),
    ("/audit",                              "audit",              "audit"),
    ("/quarantine",                         "quarantine",         "quarantine"),
    ("/audit-viewer",                       "auditViewer",        "audit-viewer"),
    ("/rights-notice",                      "rightsNotice",       "rights-notice"),
    ("/dispute-cases",                      "disputeCase",        "dispute-cases"),
    ("/conflict-of-interest",               "conflictOfInterest", "conflict-of-interest"),
    ("/marketing-review",                   "marketingReview",    "marketing-review"),
    ("/data-governance",                    "dataGovernance",     "data-governance"),
    ("/consents",                           "consents",           "consents"),
    ("/kyc-edd",                            "kycEdd",             "kyc-edd"),
    ("/ai-model-cards",                     "aiModelCards",       "ai-model-cards"),
    ("/ai-policy",                          "aiPolicy",           "ai-policy"),
    ("/korean-ai-act",                      "koreanAIAct",        "korean-ai-act"),
    ("/ai-admin-dashboard",                 "aiAdminDashboard",   "ai-admin-dashboard"),
    ("/autopilot-demo",                     "autopilotDemo",      "autopilot-demo"),
]

# Wildcard catch (App.tsx:101 → Navigate to /dashboard).  Protected (dashboard).
WILDCARD_PATH = "/typo-svc-via-audit-v1"
WILDCARD_SLUG = "wildcard-fallback"

# Test IDs (synthetic fixture; mirror of .omc/state/v8-fixture-ids.json).
# customerId MUST be a UUID (not customer_no like SYN-CUST-NNN) — the FastAPI
# route GET /customers/{customer_id} declares ``customer_id: UUID`` (see
# apps/api/harness/api/routers/customers.py:58-84) so any non-UUID value
# triggers HTTP 422 in the Customer-360 panel for all roles. Follow-up
# cycle Wave2-B4: SYN-CUST-001 → 33333333-3333-3333-3333-333333333301
# (deterministic V042 mapping; psql verified 2026-05-24).
TEST_IDS: dict[str, str] = {
    "customerId": "33333333-3333-3333-3333-333333333301",
    "consultationId": "d26f1b9b-03b2-469d-86f5-3f14606f9cc8",
    "houseViewId": "a0000052-0000-0000-0000-000000000001",
}


def concretize(path: str) -> str:
    out = path
    for k, v in TEST_IDS.items():
        out = out.replace(f":{k}", v)
    return out


# ---------------------------------------------------------------------------
# Detector regexes (per plan §3.1 Per-snapshot check)
# ---------------------------------------------------------------------------

# English i18n key pattern (lowercase dot-namespaced; conservative).
# Avoid extension/hostnames by requiring no protocol and ≤4 segments of [a-z]+
# starting with a known i18n prefix or pattern.
I18N_KEY_RE = re.compile(
    r"\b(?:nba|dashboard|consultation|consultations|customer|customers|"
    r"email|emails|emailDrafts|aftercare|house|houseViews|rights|dispute|"
    r"conflict|marketing|consent|consents|kyc|audit|ai|batch|quarantine|"
    r"rag|autopilot|common|nav|sidebar|menu|button|form|error|success)"
    r"(?:\.[a-z][a-zA-Z0-9_]+){1,3}\b"
)
MICROSEC_RE = re.compile(r"\b\d+\s*(?:μs|microseconds?)\b", re.IGNORECASE)
RAW_PLACEHOLDER_PATTERNS = [
    ("dash_em", re.compile(r"(?:^|[\s>])—(?:[\s<]|$)")),
    ("zero_percent", re.compile(r"(?<![\d.])0\s*%")),
    ("waiting_kr", re.compile(r"대기\s*중")),
    ("loading_en", re.compile(r"\bloading\b", re.IGNORECASE)),
    ("na_token", re.compile(r"\bN\s*/\s*A\b")),
]

# Known-good whitelist: routes that legitimately render "—" / "0%" / "대기 중"
# as design-intent prose (em-dash title separators, audit-row labels,
# aria-labels, compound-percent metrics) — NOT as empty-state placeholders.
# Single SoT lives at apps/web/src/lib/empty-state-whitelist.ts; this loader
# reads the JSON mirror produced in the same commit. Follow-up cycle
# Wave2-Q1 svc-follow-up-v1 — 19/19 baseline false-positive cells covered
# by 8 slugs (see .omc/handoffs/svc-follow-up-v1__wave2-q1-placeholder-classification.md).
def _load_empty_state_whitelist() -> set[str]:
    path = REPO_ROOT / "apps" / "web" / "src" / "lib" / "empty-state-whitelist.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        slugs = doc.get("slugs", [])
        return {str(s) for s in slugs if isinstance(s, str)}
    except Exception:
        # Fail-open: missing whitelist file degrades to strict detector
        # behavior (current cycle), preserving baseline auditability.
        return set()


EMPTY_STATE_WHITELIST_ROUTE_SLUGS: set[str] = _load_empty_state_whitelist()


# ---------------------------------------------------------------------------
# Capture worker
# ---------------------------------------------------------------------------

async def login(page: Any, base_url: str, role: str) -> bool:
    cred = ROLE_CREDS[role]
    await page.goto(base_url + "/login", wait_until="networkidle", timeout=30000)
    await page.fill('input[type="email"]', cred["email"])
    await page.fill('input[type="password"]', cred["password"])
    await page.click('button[type="submit"]')
    try:
        await page.wait_for_url("**/dashboard", timeout=20000)
    except Exception:
        # Some roles may land on a different default; tolerate
        await page.wait_for_timeout(2000)
    return True


async def wait_page_ready(page: Any, max_ms: int = 3000) -> None:
    """Wait for App.tsx:53-57 `window.__wmahPageReady === true` (best-effort)."""
    try:
        await page.wait_for_function(
            "() => (window.__wmahPageReady === true) || document.readyState === 'complete'",
            timeout=max_ms,
        )
    except Exception:
        pass


async def wait_auth_restored(page: Any, max_ms: int = 6000) -> bool:
    """Wait for `window.__wmahAuth?.getAccessToken()` truthy (Q4 v2).

    auth.ts:55-58 exposes a DEV-only helper that returns the current
    accessToken from the zustand store; once the refresh-cookie exchange
    completes (success), this flips truthy and ProtectedRoute can render
    the requested route instead of bouncing to /login.

    Returns True if auth token observed, False if the poll timed out
    (we still continue — some routes are unguarded or the call may have
    been pre-resolved by an earlier capture).
    """

    try:
        await page.wait_for_function(
            "() => {"
            "const a = window.__wmahAuth;"
            "return a && typeof a.getAccessToken === 'function' && !!a.getAccessToken();"
            "}",
            timeout=max_ms,
        )
        return True
    except Exception:
        return False


async def wait_route_anchor(page: Any, slug: str, max_ms: int) -> str:
    """Wait for per-route anchor element from wait_map.json (Q4).

    Returns the matched selector string ('' if neither anchor nor fallback
    was visible within ``max_ms``). Failure path:
      1. anchor selector → if times out, try fallback `<main>` selector
      2. if both time out, return '' so caller can record a soft warning
         without aborting the cell capture.
    """

    anchor = _ROUTE_ANCHORS.get(slug)
    candidates: list[str] = []
    if anchor:
        candidates.append(anchor)
    if _FALLBACK_ANCHOR and _FALLBACK_ANCHOR not in candidates:
        candidates.append(_FALLBACK_ANCHOR)
    for selector in candidates:
        try:
            await page.wait_for_selector(selector, state="visible", timeout=max_ms)
            return selector
        except Exception:
            continue
    return ""


def extract_layered_text(dom_text: str, aria_labels: list[str], titles: list[str],
                         placeholders: list[str], alts: list[str]) -> str:
    parts = [dom_text or ""]
    parts.extend(aria_labels or [])
    parts.extend(titles or [])
    parts.extend(placeholders or [])
    parts.extend(alts or [])
    return "\n".join(parts)


def scan_text(text: str) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = {"i18n_key": [], "microsec": [], "placeholder": []}
    findings["i18n_key"] = list({m.group(0) for m in I18N_KEY_RE.finditer(text)})[:50]
    findings["microsec"] = list({m.group(0) for m in MICROSEC_RE.finditer(text)})[:50]
    for name, regex in RAW_PLACEHOLDER_PATTERNS:
        hits = list({m.group(0).strip() for m in regex.finditer(text)})
        for h in hits[:10]:
            findings["placeholder"].append(f"{name}:{h}")
    return findings


_ConsoleErrorBucket = Literal["script_bug", "production_bug", "design_intent_role_gated"]

# Regex patterns matched against browser console error text (case-insensitive).
# Ordered: most-specific first so earlier rules win.
_BUCKET_REGEX_PATTERNS: list[tuple[re.Pattern[str], _ConsoleErrorBucket]] = [
    # 403 Forbidden → role-gated background API, page itself is accessible
    (re.compile(r"status of 403\b", re.IGNORECASE), "design_intent_role_gated"),
    # 422 Unprocessable Entity → audit script sent invalid input
    (re.compile(r"status of 422\b", re.IGNORECASE), "script_bug"),
    (re.compile(r"\b422\b", re.IGNORECASE), "script_bug"),
    # 5xx → production-side failure
    (re.compile(r"status of 5\d{2}\b", re.IGNORECASE), "production_bug"),
    (re.compile(r"\b5\d{2}\b"), "production_bug"),
    # Network errors → production_bug (service unreachable)
    (re.compile(r"net::ERR_", re.IGNORECASE), "production_bug"),
    (re.compile(r"Failed to fetch", re.IGNORECASE), "production_bug"),
]


def classify_console_error(text: str) -> _ConsoleErrorBucket:
    """Classify a browser console error message into one of three buckets.

    Buckets:
    - ``script_bug``               HTTP 422 emitted because the audit script
                                   sent invalid input to the backend.
    - ``production_bug``           HTTP 5xx, network failure, or undefined
                                   endpoint — indicates a real backend defect.
    - ``design_intent_role_gated`` HTTP 403 on a background API sub-resource
                                   that the current role is not permitted to
                                   access; the page itself is reachable and
                                   this console noise is expected by design.
    """
    for pattern, bucket in _BUCKET_REGEX_PATTERNS:
        if pattern.search(text):
            return bucket
    # Unrecognised error — treat conservatively as production_bug
    return "production_bug"


async def capture_one(page: Any, base_url: str, role: str, route_pattern: str,
                       routeKey: str, slug: str, out_dir: pathlib.Path) -> dict[str, Any]:
    """Visit one (role, route) cell and emit 4 artifacts + result row."""
    t0 = time.time()
    role_code = ROLE_CREDS[role]["role_code"]
    has_access = role_code in ACCESS_RULES.get(routeKey, [])
    is_wildcard = route_pattern.startswith("/typo-")
    target_url = base_url + concretize(route_pattern)

    console_msgs: list[dict[str, Any]] = []
    network_responses: list[dict[str, Any]] = []
    page_errors: list[str] = []

    def _on_console(msg: Any) -> None:
        try:
            if msg.type in ("error", "warning"):
                console_msgs.append({"type": msg.type, "text": msg.text[:500]})
        except Exception:
            pass

    def _on_response(resp: Any) -> None:
        try:
            status = resp.status
            url = resp.url
            if status >= 400:
                network_responses.append({"status": status, "url": url[:300]})
        except Exception:
            pass

    def _on_page_error(err: Any) -> None:
        try:
            page_errors.append(str(err)[:500])
        except Exception:
            pass

    page.on("console", _on_console)
    page.on("response", _on_response)
    page.on("pageerror", _on_page_error)

    final_url = ""
    visible_text = ""
    aria_labels: list[str] = []
    titles: list[str] = []
    placeholders: list[str] = []
    alts: list[str] = []
    dom_html_path = out_dir / f"{role}__{slug}.dom.html"
    png_path = out_dir / f"{role}__{slug}.png"
    console_path = out_dir / f"{role}__{slug}.console.json"
    network_path = out_dir / f"{role}__{slug}.network.json"
    capture_errors: list[str] = []

    auth_token_observed = False
    anchor_matched = ""
    try:
        await page.goto(target_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(700)
        # Q4 v2: wait for auth token before anything else so ProtectedRoute
        # does not race to /login. Best-effort; skip-tolerant for unguarded
        # pages (/login itself never hits this code path).
        auth_token_observed = await wait_auth_restored(page, max_ms=_AUTH_TOKEN_POLL_MS)
        await wait_page_ready(page, max_ms=3000)
        # Q4 v2: wait for per-route anchor (h1/h2 text or main fallback).
        anchor_matched = await wait_route_anchor(page, slug, max_ms=_ANCHOR_POLL_MS)
        try:
            visible_text = await page.locator("body").text_content(timeout=5000) or ""
        except Exception as e:
            capture_errors.append(f"body_text_content: {e!s:.150}")
        # login_redirect retry 1x (executes even when anchor matched if body
        # text still smells like the login page — covers the case where the
        # h1 fallback `main` selector matched but content is still login).
        if "직원 로그인" in visible_text[:300] and "보호된" in visible_text[:300]:
            try:
                await page.reload(wait_until="networkidle", timeout=15000)
                await page.wait_for_timeout(1000)
                # Second-chance auth wait + anchor wait after reload
                auth_token_observed = (
                    await wait_auth_restored(page, max_ms=_AUTH_TOKEN_POLL_MS)
                    or auth_token_observed
                )
                await wait_page_ready(page, max_ms=3000)
                anchor_matched = (
                    await wait_route_anchor(page, slug, max_ms=_ANCHOR_POLL_MS)
                    or anchor_matched
                )
                visible_text = await page.locator("body").text_content(timeout=5000) or ""
            except Exception as e:
                capture_errors.append(f"login_retry: {e!s:.150}")
        final_url = page.url
        # 5-layer extraction
        try:
            aria_labels = await page.evaluate(
                "() => Array.from(document.querySelectorAll('[aria-label]')).map(e => e.getAttribute('aria-label') || '')"
            )
        except Exception:
            aria_labels = []
        try:
            titles = await page.evaluate(
                "() => Array.from(document.querySelectorAll('[title]')).map(e => e.getAttribute('title') || '')"
            )
        except Exception:
            titles = []
        try:
            placeholders = await page.evaluate(
                "() => Array.from(document.querySelectorAll('[placeholder]')).map(e => e.getAttribute('placeholder') || '')"
            )
        except Exception:
            placeholders = []
        try:
            alts = await page.evaluate(
                "() => Array.from(document.querySelectorAll('[alt]')).map(e => e.getAttribute('alt') || '')"
            )
        except Exception:
            alts = []
        try:
            await page.screenshot(path=str(png_path), full_page=True)
        except Exception as e:
            capture_errors.append(f"screenshot: {e!s:.150}")
        try:
            html_content = await page.content()
            dom_html_path.write_text(html_content, encoding="utf-8")
        except Exception as e:
            capture_errors.append(f"dom_dump: {e!s:.150}")
    except Exception as e:
        capture_errors.append(f"navigate: {e!s:.150}")

    # Detach listeners
    try:
        page.remove_listener("console", _on_console)
        page.remove_listener("response", _on_response)
        page.remove_listener("pageerror", _on_page_error)
    except Exception:
        pass

    console_path.write_text(
        json.dumps({"messages": console_msgs, "page_errors": page_errors, "capture_errors": capture_errors},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    network_path.write_text(
        json.dumps({"non_2xx": network_responses}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Detection
    layered = extract_layered_text(visible_text[:20000], aria_labels[:200],
                                    titles[:200], placeholders[:200], alts[:200])
    findings = scan_text(layered)

    # Filter placeholders if whitelisted
    if slug in EMPTY_STATE_WHITELIST_ROUTE_SLUGS:
        findings["placeholder"] = []

    http_5xx = [r for r in network_responses if r["status"] >= 500]
    console_error_msgs = [m for m in console_msgs if m["type"] == "error"]
    console_errors_n = len(console_error_msgs)
    console_error_buckets: dict[str, int] = {
        "script_bug": 0,
        "production_bug": 0,
        "design_intent_role_gated": 0,
    }
    for m in console_error_msgs:
        bucket = classify_console_error(m.get("text", ""))
        console_error_buckets[bucket] += 1
    landed_on_403 = final_url.endswith("/403") or "/403" in final_url
    landed_on_login = final_url.endswith("/login") or "/login" in final_url

    # PASS criteria (binary): role has access path
    fail_reasons: list[str] = []
    if has_access and not is_wildcard:
        if landed_on_403:
            fail_reasons.append("landed_on_403_despite_access")
        if landed_on_login:
            fail_reasons.append("landed_on_login_despite_access")
    if is_wildcard:
        # wildcard must redirect to /dashboard
        if not (final_url.endswith("/dashboard") or "/dashboard" in final_url):
            fail_reasons.append("wildcard_not_redirected_to_dashboard")
    if findings["i18n_key"]:
        fail_reasons.append(f"i18n_key:{len(findings['i18n_key'])}")
    if findings["microsec"]:
        fail_reasons.append(f"microsec:{len(findings['microsec'])}")
    if findings["placeholder"] and has_access and not landed_on_403 and not landed_on_login:
        fail_reasons.append(f"placeholder:{len(findings['placeholder'])}")
    if console_errors_n > 0:
        fail_reasons.append(f"console_error:{console_errors_n}")
    if http_5xx:
        fail_reasons.append(f"http_5xx:{len(http_5xx)}")
    if capture_errors:
        fail_reasons.append(f"capture_errors:{len(capture_errors)}")

    result = {
        "role": role,
        "role_code": role_code,
        "route_pattern": route_pattern,
        "routeKey": routeKey,
        "slug": slug,
        "is_wildcard": is_wildcard,
        "has_access": has_access,
        "target_url": target_url,
        "final_url": final_url,
        "landed_on_403": landed_on_403,
        "landed_on_login": landed_on_login,
        "console_error_count": console_errors_n,
        "console_error_buckets": console_error_buckets,
        "console_warning_count": sum(1 for m in console_msgs if m["type"] == "warning"),
        "http_5xx_count": len(http_5xx),
        "non_2xx_count": len(network_responses),
        "findings": findings,
        "fail_reasons": fail_reasons,
        "pass": not fail_reasons,
        "elapsed_ms": int((time.time() - t0) * 1000),
        # Q4 evidence (BFS auth race wait map — bfs-auth-race-window)
        "auth_token_observed": auth_token_observed,
        "anchor_matched": anchor_matched,
        "anchor_expected": _ROUTE_ANCHORS.get(slug, ""),
        "artifacts": {
            "png": str(png_path.relative_to(REPO_ROOT)),
            "dom_html": str(dom_html_path.relative_to(REPO_ROOT)),
            "console": str(console_path.relative_to(REPO_ROOT)),
            "network": str(network_path.relative_to(REPO_ROOT)),
        },
    }
    return result


async def run_role(pw: Any, base_url: str, role: str, snapshots_dir: pathlib.Path) -> list[dict[str, Any]]:
    """Login as role per cell, capture 28 cells under per-cell + per-session caps.

    svc-viability-v3 A4 + C9 (ADR-015) — per-cell fresh ``browser.new_context()``
    + ``new_page()`` + ``login()`` defeats long-session JWT expiry that crashed
    the prior single-session run (0/112 PASS at ~50min). Two-layer cap
    (per-cell 600s + per-session 1800s) bounds runtime under upstream hangs.
    """
    PER_CELL_CAP_S = 600.0
    PER_SESSION_CAP_S = 1800.0

    results: list[dict[str, Any]] = []
    browser = await pw.chromium.launch(headless=True)
    cells: list[tuple[str, str, str, bool]] = [
        (rp, rk, sl, False) for (rp, rk, sl) in ROUTES
    ]
    cells.append((WILDCARD_PATH, "dashboard", WILDCARD_SLUG, True))
    role_start = time.monotonic()

    def _cap_record(
        route_pattern: str, routeKey: str, slug: str, is_wildcard: bool,
        reason: str, elapsed_ms: int,
    ) -> dict[str, Any]:
        target = base_url + (WILDCARD_PATH if is_wildcard else concretize(route_pattern))
        return {
            "role": role, "role_code": ROLE_CREDS[role]["role_code"],
            "route_pattern": route_pattern, "routeKey": routeKey,
            "slug": slug, "is_wildcard": is_wildcard, "has_access": False,
            "target_url": target,
            "final_url": "", "landed_on_403": False, "landed_on_login": False,
            "console_error_count": 0, "console_warning_count": 0,
            "http_5xx_count": 0, "non_2xx_count": 0,
            "findings": {"i18n_key": [], "microsec": [], "placeholder": []},
            "fail_reasons": [reason],
            "pass": False, "elapsed_ms": elapsed_ms,
            "cap_exceeded": True,
            "artifacts": {},
        }

    try:
        for route_pattern, routeKey, slug, is_wildcard in cells:
            print(f"[{role}] capturing {slug}", flush=True)
            cell_t0 = time.monotonic()
            if cell_t0 - role_start > PER_SESSION_CAP_S:
                results.append(_cap_record(
                    route_pattern, routeKey, slug, is_wildcard,
                    "per_session_cap_exceeded", 0,
                ))
                continue
            context = await browser.new_context(viewport={"width": 1440, "height": 900})
            page = await context.new_page()
            try:
                try:
                    await login(page, base_url, role)
                except Exception as e:
                    print(f"[{role}/{slug}] login error: {e}", flush=True)
                try:
                    rec = await asyncio.wait_for(
                        capture_one(page, base_url, role, route_pattern, routeKey, slug, snapshots_dir),
                        timeout=PER_CELL_CAP_S,
                    )
                except asyncio.TimeoutError:
                    rec = _cap_record(
                        route_pattern, routeKey, slug, is_wildcard,
                        "per_cell_cap_exceeded",
                        int((time.monotonic() - cell_t0) * 1000),
                    )
                except Exception as e:
                    target = base_url + (WILDCARD_PATH if is_wildcard else concretize(route_pattern))
                    rec = {
                        "role": role, "role_code": ROLE_CREDS[role]["role_code"],
                        "route_pattern": route_pattern, "routeKey": routeKey,
                        "slug": slug, "is_wildcard": is_wildcard, "has_access": False,
                        "target_url": target,
                        "final_url": "", "landed_on_403": False, "landed_on_login": False,
                        "console_error_count": 0, "console_warning_count": 0,
                        "http_5xx_count": 0, "non_2xx_count": 0,
                        "findings": {"i18n_key": [], "microsec": [], "placeholder": []},
                        "fail_reasons": [f"top_level_exc:{type(e).__name__}:{e!s:.100}"],
                        "pass": False, "elapsed_ms": int((time.monotonic() - cell_t0) * 1000),
                        "artifacts": {},
                    }
            finally:
                await context.close()
            results.append(rec)
    finally:
        await browser.close()
    return results


async def main_async(base_url: str, output_dir: pathlib.Path) -> int:
    snapshots_dir = output_dir / "baseline"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.async_api import async_playwright  # type: ignore[import-not-found]
    except ImportError as e:
        print(f"FATAL: playwright not installed in {sys.executable} — {e}", flush=True)
        return 2
    all_results: list[dict[str, Any]] = []
    t0 = time.time()
    async with async_playwright() as pw:
        for role in ROLE_CREDS:
            print(f"=== role {role} ===", flush=True)
            results = await run_role(pw, base_url, role, snapshots_dir)
            all_results.extend(results)
    elapsed = int(time.time() - t0)

    # Summary
    pass_count = sum(1 for r in all_results if r["pass"])
    fail_count = len(all_results) - pass_count
    per_category: dict[str, int] = {
        "i18n_key": 0, "microsec": 0, "placeholder": 0,
        "console_error": 0, "http_5xx": 0,
        "landed_on_403_with_access": 0, "landed_on_login_with_access": 0,
        "wildcard_misroute": 0, "capture_error_or_exc": 0,
    }
    for r in all_results:
        for reason in r["fail_reasons"]:
            if reason.startswith("i18n_key"):
                per_category["i18n_key"] += 1
            elif reason.startswith("microsec"):
                per_category["microsec"] += 1
            elif reason.startswith("placeholder"):
                per_category["placeholder"] += 1
            elif reason.startswith("console_error"):
                per_category["console_error"] += 1
            elif reason.startswith("http_5xx"):
                per_category["http_5xx"] += 1
            elif reason == "landed_on_403_despite_access":
                per_category["landed_on_403_with_access"] += 1
            elif reason == "landed_on_login_despite_access":
                per_category["landed_on_login_with_access"] += 1
            elif reason == "wildcard_not_redirected_to_dashboard":
                per_category["wildcard_misroute"] += 1
            elif reason.startswith("capture_errors") or reason.startswith("top_level_exc"):
                per_category["capture_error_or_exc"] += 1

    # Aggregate console_error_buckets across all cells
    agg_ce_buckets: dict[str, int] = {
        "script_bug": 0,
        "production_bug": 0,
        "design_intent_role_gated": 0,
    }
    for r in all_results:
        for bucket_key, count in r.get("console_error_buckets", {}).items():
            if bucket_key in agg_ce_buckets:
                agg_ce_buckets[bucket_key] += count

    summary = {
        "cycle": "service-viability-v1",
        "axis": "axis-1",
        "phase": "baseline",
        "base_url": base_url,
        "total_snapshots": len(all_results),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "elapsed_seconds": elapsed,
        "fail_category_counts": per_category,
        "console_error_buckets": agg_ce_buckets,
        "roles": list(ROLE_CREDS.keys()),
        "routes_protected": len(ROUTES),
        "routes_wildcard": 1,
        "snapshot_results": all_results,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DONE total={len(all_results)} pass={pass_count} fail={fail_count} elapsed={elapsed}s", flush=True)
    print(f"summary: {summary_path}", flush=True)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Axis 1 UI snapshot 112 capture")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--output-dir", default=str(OUTPUT_BASE))
    args = p.parse_args()
    return asyncio.run(main_async(args.base_url, pathlib.Path(args.output_dir)))


if __name__ == "__main__":
    sys.exit(main())
