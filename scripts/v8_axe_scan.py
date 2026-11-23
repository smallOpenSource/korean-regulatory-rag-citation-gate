#!/usr/bin/env python3
"""
v8 axe-core accessibility scan (DELTA-5 mechanically derived).

Navigates 25 routes across pre-auth and 5 roles, injects axe-core,
and dumps accessibility + interactive role data per route×role.

Output: .omc/state/v8-axe-scan.json
"""
# Python: /opt/conda/envs/playwright/bin/python
# Browsers: /opt/playwright-browsers
# Display: DISPLAY=:99

import json
import os
import sys
import time
from pathlib import Path

# ── Env setup ──────────────────────────────────────────────────────────────────
os.environ.setdefault("DISPLAY", ":99")
os.environ.setdefault(
    "PLAYWRIGHT_BROWSERS_PATH", "/opt/playwright-browsers"
)

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("ERROR: playwright not available in this Python env", file=sys.stderr)
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────────
_WEB_PORT = os.environ.get("HARNESS_WEB_PORT", "8000")
BASE_URL = os.environ.get("WMAH_BASE_URL", f"http://localhost:{_WEB_PORT}")
OUTPUT_PATH = (Path(__file__).resolve().parents[1] / ".omc/state/v8-axe-scan.json")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# Roles with sample login credentials (env or defaults for dev)
ROLES = {
    "PB":              {"email": os.environ.get("PB_EMAIL", "pb@test.local"),             "password": os.environ.get("PB_PASSWORD", "test1234")},
    "WM":              {"email": os.environ.get("WM_EMAIL", "wm@test.local"),              "password": os.environ.get("WM_PASSWORD", "test1234")},
    "BRANCH_MANAGER":  {"email": os.environ.get("BM_EMAIL", "bm@test.local"),              "password": os.environ.get("BM_PASSWORD", "test1234")},
    "ADMIN":           {"email": os.environ.get("ADMIN_EMAIL", "admin@test.local"),        "password": os.environ.get("ADMIN_PASSWORD", "test1234")},
    "AUDIT_VIEWER":    {"email": os.environ.get("AV_EMAIL", "auditviewer@test.local"),     "password": os.environ.get("AV_PASSWORD", "test1234")},
}

# All routes from App.tsx:46-75
# Pre-auth routes (no login required)
PRE_AUTH_ROUTES = ["/login", "/403"]

# Protected routes (one sample per route; parametric routes use a placeholder id)
PROTECTED_ROUTES = [
    "/dashboard",
    "/customers",
    "/customers/1",
    "/consultations/1",
    "/nba",
    "/aftercare",
    "/email-drafts",
    "/house-views",
    "/house-views/1",
    "/house-views/1/activate",
    "/rag",
    "/batch",
    "/audit",
    "/quarantine",
    "/audit-viewer",
    "/rights-notice",
    "/dispute-cases",
    "/ai-model-cards",
    "/ai-policy",
    "/korean-ai-act",
    "/ai-admin-dashboard",
    "/autopilot-demo",
]

# Fetch axe-core CDN script (or inline a minimal shim for offline env)
AXE_CDN = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.9.1/axe.min.js"

AXE_SHIM = """
// Minimal axe-core shim for offline environments
window.axe = window.axe || {
  run: function() {
    return Promise.resolve({
      violations: [],
      passes: [],
      incomplete: [],
      inapplicable: [],
      _shim: true
    });
  }
};
"""

def inject_axe(page) -> bool:
    """Try to inject axe-core. Returns True if real axe loaded, False if shim."""
    try:
        # Try network-available axe-core first
        page.add_script_tag(url=AXE_CDN)
        loaded = page.evaluate("typeof window.axe !== 'undefined'")
        if loaded:
            return True
    except Exception:
        pass
    # Fallback: inject shim so axe.run() always resolves
    page.add_script_tag(content=AXE_SHIM)
    return False


def run_axe(page) -> dict:
    """Run axe.run() and return results as dict."""
    try:
        result = page.evaluate("""
            () => axe.run(document, {
                runOnly: ['wcag2a', 'wcag2aa', 'best-practice'],
                resultTypes: ['violations', 'passes', 'incomplete']
            }).then(r => ({
                violations: r.violations.map(v => ({
                    id: v.id,
                    impact: v.impact,
                    description: v.description,
                    nodes: v.nodes.length
                })),
                passes_count: r.passes.length,
                incomplete_count: r.incomplete.length,
                _shim: r._shim || false
            }))
        """)
        return result
    except Exception as exc:
        return {"error": str(exc), "violations": [], "passes_count": 0, "incomplete_count": 0}


def get_interactive_roles(page) -> list:
    """Extract interactive elements and their ARIA roles."""
    try:
        return page.evaluate("""
            () => {
                const sel = 'button, a[href], input, select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="radio"], [tabindex], [role="dialog"], [aria-modal], [role="tab"], [role="menuitem"], [role="switch"]';
                return Array.from(document.querySelectorAll(sel)).slice(0, 100).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    role: el.getAttribute('role') || null,
                    aria_label: el.getAttribute('aria-label') || null,
                    aria_modal: el.getAttribute('aria-modal') || null,
                    tabindex: el.getAttribute('tabindex') || null,
                    type: el.getAttribute('type') || null,
                    text: (el.textContent || '').trim().slice(0, 60)
                }));
            }
        """)
    except Exception:
        return []


def login(page, creds: dict) -> bool:
    """Attempt login. Returns True on success."""
    try:
        page.goto(f"{BASE_URL}/login", timeout=15_000)
        page.fill('input[type="email"]', creds["email"], timeout=5_000)
        page.fill('input[type="password"]', creds["password"], timeout=5_000)
        page.click('button[type="submit"]', timeout=5_000)
        # Wait for redirect away from /login
        page.wait_for_url(lambda url: "/login" not in url, timeout=10_000)
        return True
    except Exception as exc:
        return False


def scan_route(page, route: str, role_name: str) -> dict:
    """Navigate to route and scan with axe + interactive role extraction."""
    url = f"{BASE_URL}{route}"
    result = {
        "route": route,
        "role": role_name,
        "url": url,
        "status": "ok",
        "axe": {},
        "interactive_elements": [],
        "error": None,
    }
    try:
        page.goto(url, timeout=15_000, wait_until="networkidle")
        axe_injected = inject_axe(page)
        result["axe_real"] = axe_injected
        result["axe"] = run_axe(page)
        result["interactive_elements"] = get_interactive_roles(page)
    except PWTimeout:
        result["status"] = "timeout"
        result["error"] = "page load timeout"
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    return result


def main():
    results = {}
    scan_errors = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            executable_path=str(
                next(
                    (p for pattern in [
                        "chromium-*/chrome-linux64/chrome",
                        "chromium-*/chrome-linux/chrome",
                    ] for p in sorted(Path("/opt/playwright-browsers").glob(pattern), reverse=True)),
                    Path("/opt/playwright-browsers/chromium/chrome")
                )
            ),
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )

        # ── Pre-auth routes (no login) ──────────────────────────────────────────
        context = browser.new_context()
        page = context.new_page()
        for route in PRE_AUTH_ROUTES:
            key = f"pre_auth::{route}"
            print(f"[pre_auth] {route}", flush=True)
            results[key] = scan_route(page, route, "pre_auth")
        page.close()
        context.close()

        # ── Protected routes × 5 roles ──────────────────────────────────────────
        for role_name, creds in ROLES.items():
            context = browser.new_context()
            page = context.new_page()

            logged_in = login(page, creds)
            if not logged_in:
                scan_errors.append(f"Login failed for role {role_name}")
                print(f"[WARN] Login failed for {role_name} — skipping role", flush=True)
                page.close()
                context.close()
                continue

            print(f"[{role_name}] logged in", flush=True)

            # Sample one route per role (spec: "5 roles 각 1 sample")
            # Full scan: all protected routes
            for route in PROTECTED_ROUTES:
                key = f"{role_name}::{route}"
                print(f"  [{role_name}] {route}", flush=True)
                results[key] = scan_route(page, route, role_name)
                time.sleep(0.3)  # polite crawl delay

            page.close()
            context.close()

        browser.close()

    output = {
        "scan_meta": {
            "base_url": BASE_URL,
            "pre_auth_routes": PRE_AUTH_ROUTES,
            "protected_routes": PROTECTED_ROUTES,
            "roles": list(ROLES.keys()),
            "total_cells": len(results),
            "scan_errors": scan_errors,
            "axe_cdn": AXE_CDN,
        },
        "results": results,
    }

    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nDone. {len(results)} cells scanned → {OUTPUT_PATH}", flush=True)
    if scan_errors:
        print(f"Errors: {scan_errors}", flush=True)


if __name__ == "__main__":
    main()
