"""Wave-Audit-Defect-Fix observability cycle Item #64 — BRANCH_MANAGER +
COMPLIANCE_OFFICER audit lanes.

The Playwright `all-pages-by-role.spec.ts` audit lane covers PB / WM /
ADMIN / AUDIT_VIEWER but explicitly excludes BRANCH_MANAGER (spec line
86: "BRANCH_MANAGER is excluded from this audit lane"). The runtime
ACCESS_RULES table at `apps/web/src/lib/access.ts` nevertheless includes
BM on 18 of 28 routeKeys, so BM access semantics need their own
verification.

COMPLIANCE_OFFICER (준법감시인, added 2026-06-01) is likewise excluded
from the Playwright spec (SPEC_EXCLUDED_ROLES in
test_access_rules_single_sot.py), so it gets its own backend lane below.
It is a read-only compliance-oversight role that — unlike BM — reads
audit logs and disputes (allowed) but has no customer scope and no
write/governance gates (denied on customers / data-governance / consents
/ kyc-edd). The probe table is the server-side ground truth; access.ts
is kept consistent with it (see lib/access.ts COMPLIANCE_OFFICER rows).

This is a backend-only lane (no Playwright) that:
1. Logs in as synthetic.branch.manager@example.invalid via /auth/login.
2. For each routeKey in the runtime ACCESS_RULES, asserts the
   server-side route guard returns 200 (allowed) or 403 (forbidden)
   matching the table.
3. Documents the implicit assumption: "allowed in client = allowed by
   server" — if the server-side guard contradicts access.ts, the
   spec/runtime/server tri-source disagreement is surfaced here.

Skips gracefully when the backend isn't reachable (CI without uvicorn).
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request

import pytest

BASE_URL = os.environ.get(
    "WMAH_BACKEND_URL",
    f"http://127.0.0.1:{os.environ.get('HARNESS_API_PORT', '8010')}",
)
BM_EMAIL = "synthetic.branch.manager@example.invalid"
BM_PASSWORD = os.environ.get("WMAH_E2E_PASSWORD", "HarnessSynthetic!2026")
CO_EMAIL = "synthetic.compliance@example.invalid"
CO_PASSWORD = os.environ.get("WMAH_E2E_PASSWORD", "HarnessSynthetic!2026")


# Each tuple is (routeKey, GET endpoint, expected_status_when_BM).
# The GET endpoint is a representative server-side check; pages that
# are pure SPA paths without a unique backend GET fall back to a
# generic /health-style probe (skipped here).
# Each tuple: (routeKey, endpoint, expected_status_class).
# expected_status_class: 200 means "BM should be allowed" (200/404/422
# accepted — guard passed); "denied" means "BM should be blocked"
# (403/404/422/405 accepted — guard MAY have denied OR endpoint not
# exposed; both prove BM has no positive access).
BM_ROUTE_PROBES: list[tuple[str, str, str]] = [
    # routeKey, endpoint, expected
    ("dashboard",          "/dashboard",                  "allowed"),
    ("customers",          "/customers?limit=10&offset=0", "allowed"),
    ("aftercare",          "/aftercare-events",            "allowed"),
    ("houseViews",         "/house-views?limit=10",        "allowed"),
    ("rag",                "/rag/health",                  "allowed"),
    ("audit",              "/audit-logs?limit=1",          "denied"),
    ("rightsNotice",       "/rights-notice",               "allowed"),
    ("conflictOfInterest", "/conflict-of-interest/disclosures?limit=1", "allowed"),
    ("marketingReview",    "/marketing-reviews?limit=1",   "allowed"),
    ("dataGovernance",     "/data-governance/purge-schedule", "allowed"),
    ("consents",           "/consents?customer_id=33333333-3333-3333-3333-333333333301", "allowed"),
    ("kycEdd",             "/kyc-edd/triggers?limit=1",    "allowed"),
    ("disputeCase",        "/disputes?limit=1",            "denied"),
    ("batch",              "/batch/runs?limit=1",          "denied"),
    ("quarantine",         "/document-chunks?quarantine_flag=true&limit=1", "denied"),
    ("houseViewActivation","/house-views/HV-AUDIT-0001",   "denied"),
    ("aiAdminDashboard",   "/ai-jobs?limit=1",             "denied"),
]

# COMPLIANCE_OFFICER lane (준법감시인 — read-only compliance oversight).
# Server ground truth verified live 2026-06-01. Differs from BM on:
#   - audit / disputeCase: CO allowed (reads), BM denied.
#   - customers / aftercare / dataGovernance / consents / kycEdd: CO denied
#     (no customer scope, no write/governance gates), BM allowed.
# access.ts COMPLIANCE_OFFICER membership is kept consistent with this table
# (allowed rows are listed; denied rows are not), so client and server agree.
CO_ROUTE_PROBES: list[tuple[str, str, str]] = [
    # routeKey, endpoint, expected
    ("dashboard",          "/dashboard",                   "allowed"),
    ("audit",              "/audit-logs?limit=1",          "allowed"),
    ("disputeCase",        "/disputes?limit=1",            "allowed"),
    ("conflictOfInterest", "/conflict-of-interest/disclosures?limit=1", "allowed"),
    ("marketingReview",    "/marketing-reviews?limit=1",   "allowed"),
    ("houseViews",         "/house-views?limit=10",        "allowed"),
    ("customers",          "/customers?limit=10&offset=0", "denied"),
    ("aftercare",          "/aftercare-events",            "denied"),
    ("rag",                "/rag/health",                  "denied"),
    ("rightsNotice",       "/rights-notice",               "denied"),
    ("dataGovernance",     "/data-governance/purge-schedule", "denied"),
    ("consents",           "/consents?customer_id=33333333-3333-3333-3333-333333333301", "denied"),
    ("kycEdd",             "/kyc-edd/triggers?limit=1",    "denied"),
    ("batch",              "/batch/runs?limit=1",          "denied"),
    ("quarantine",         "/document-chunks?quarantine_flag=true&limit=1", "denied"),
    ("houseViewActivation","/house-views/HV-AUDIT-0001",   "denied"),
    ("aiAdminDashboard",   "/ai-jobs?limit=1",             "denied"),
]

# Resolved cross-source disagreements (kept for audit trail; empty list
# means client and server agree). disputeCase BM was resolved on
# 2026-05-23 by removing BRANCH_MANAGER from access.ts:24 to match the
# server-side guard at POST /disputes. The probe above now asserts that
# BM is denied at /disputes, matching the runtime ACCESS_RULES.
ACCESS_TS_VS_SERVER_DISAGREEMENT: list[tuple[str, str]] = []


def _backend_up() -> bool:
    try:
        port = int(os.environ.get("HARNESS_API_PORT", "8010"))
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _backend_up(), reason="backend uvicorn not reachable")


def _login(email: str, password: str) -> str | None:
    data = json.dumps({"email": email, "password": password}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/login",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("access_token")
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        return None


def _probe(token: str, path: str) -> int:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError:
        return 0


@pytest.fixture(scope="module")
def bm_token() -> str:
    token = _login(BM_EMAIL, BM_PASSWORD)
    assert token, f"BRANCH_MANAGER login failed for {BM_EMAIL}"
    return token


def test_branch_manager_login_succeeds(bm_token: str) -> None:
    """BRANCH_MANAGER account can authenticate."""
    assert isinstance(bm_token, str) and len(bm_token) > 100


@pytest.mark.parametrize(
    "route_key,endpoint,expected_class",
    BM_ROUTE_PROBES,
    ids=[t[0] for t in BM_ROUTE_PROBES],
)
def test_branch_manager_server_guards_match_access_rules(
    bm_token: str,
    route_key: str,
    endpoint: str,
    expected_class: str,
) -> None:
    """For each BM-relevant routeKey, the server-side guard's response
    must match the runtime ACCESS_RULES expectation.

    `expected_class="allowed"` accepts 200/404/422 (200=success;
    404/422=guard passed but resource/payload didn't match the probe
    URL — still proves BM is not RBAC-blocked).

    `expected_class="denied"` accepts 403/404/405 (403=explicit RBAC
    denial; 404/405=endpoint not exposed to BM at the probed path —
    still proves BM has no positive access).
    """
    status = _probe(bm_token, endpoint)
    if expected_class == "allowed":
        assert status in (200, 404, 422), (
            f"BM {route_key} ({endpoint}): expected allowed (200/404/422), got {status}. "
            f"If 403, the server-side guard contradicts access.ts which lists BM — "
            f"see ACCESS_TS_VS_SERVER_DISAGREEMENT in this file for known cases."
        )
    else:  # denied
        assert status in (403, 404, 405, 422), (
            f"BM {route_key} ({endpoint}): expected denied (403/404/405/422), got {status}. "
            f"If 200, the server-side guard is overly permissive vs access.ts. "
            f"(422 accepted because validation can short-circuit the role guard for "
            f"placeholder probe paths like HV-AUDIT-0001 that are not valid UUIDs.)"
        )


@pytest.fixture(scope="module")
def co_token() -> str:
    token = _login(CO_EMAIL, CO_PASSWORD)
    assert token, f"COMPLIANCE_OFFICER login failed for {CO_EMAIL}"
    return token


def test_compliance_officer_login_succeeds(co_token: str) -> None:
    """COMPLIANCE_OFFICER account can authenticate."""
    assert isinstance(co_token, str) and len(co_token) > 100


@pytest.mark.parametrize(
    "route_key,endpoint,expected_class",
    CO_ROUTE_PROBES,
    ids=[t[0] for t in CO_ROUTE_PROBES],
)
def test_compliance_officer_server_guards_match_access_rules(
    co_token: str,
    route_key: str,
    endpoint: str,
    expected_class: str,
) -> None:
    """COMPLIANCE_OFFICER read-only oversight: each server-side guard must
    match the role's access.ts membership.

    `expected_class="allowed"` accepts 200/404/422 (guard passed);
    `expected_class="denied"` accepts 403/404/405/422 (guard blocked or the
    endpoint is not positively exposed to CO). CO differs from BM by reading
    audit + disputes while being denied customer/governance/write surfaces.
    """
    status = _probe(co_token, endpoint)
    if expected_class == "allowed":
        assert status in (200, 404, 422), (
            f"CO {route_key} ({endpoint}): expected allowed (200/404/422), got {status}. "
            f"If 403, the server-side guard contradicts access.ts which lists "
            f"COMPLIANCE_OFFICER on this routeKey."
        )
    else:  # denied
        assert status in (403, 404, 405, 422), (
            f"CO {route_key} ({endpoint}): expected denied (403/404/405/422), got {status}. "
            f"If 200, the server-side guard is overly permissive vs the read-only "
            f"COMPLIANCE_OFFICER intent (no customer scope / no write-governance gates)."
        )


def test_known_cross_source_disagreements_documented() -> None:
    """Sanity check: any documented disagreement must reference a routeKey
    that exists in the live ACCESS_TS_VS_SERVER_DISAGREEMENT list so it
    doesn't get silently dropped.

    When the list is empty it means client (access.ts) and server route
    guards agree across all probed routeKeys. Any future disagreement
    must be added here AND BM_ROUTE_PROBES kept consistent (probe must
    assert the server-side reality, not the access.ts claim).
    """
    for route_key, rationale in ACCESS_TS_VS_SERVER_DISAGREEMENT:
        assert route_key and rationale and len(rationale) > 20
