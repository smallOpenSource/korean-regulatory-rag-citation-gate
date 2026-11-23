"""Wave-Audit-Defect-Fix v5 Item 1' — single-SoT ACCESS_RULES contract.

Tri-source agreement gate: `apps/web/src/lib/access.ts` is the runtime
source-of-truth. This test ensures the `tests/audit-e2e/all-pages-by-role.spec.ts`
inline ACCESS_RULES table stays a mechanical subset of the runtime table
(modulo the documented BRANCH_MANAGER exclusion from the audit lane and
the 5 routeKeys without a corresponding PAGES entry).

If this test fails, the e2e spec has drifted away from the runtime gate
— e2e tests will be measuring the wrong thing. Fix by aligning the spec
table with the runtime instead of patching individual page failures.

This is the [[absence-vs-presence-verification]] pattern applied to RBAC:
the spec is allowed to be a SUBSET of the runtime, but every cell must
agree on allowed-role membership (filtered by the BM exclusion).
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACCESS_TS = PROJECT_ROOT / "apps" / "web" / "src" / "lib" / "access.ts"
SPEC_TS = PROJECT_ROOT / "tests" / "audit-e2e" / "all-pages-by-role.spec.ts"


# routeKeys that exist in runtime ACCESS_RULES but are intentionally not in
# the audit-e2e PAGES set (no page file under apps/web/src/pages/ for them).
# Documented in spec comment line 86 + per-routeKey Wave-Audit-Defect-Fix
# markers in access.ts.
SPEC_EXCLUDED_ROUTEKEYS: set[str] = {
    "conflictOfInterest",  # Wave-Audit-Defect-Fix C3 — no page in this audit lane
    "consents",            # Wave-Audit-Defect-Fix C1 — no page in this audit lane
    "kycEdd",              # Wave-Audit-Defect-Fix C2 — no page in this audit lane
    "marketingReview",     # Wave-Audit-Defect-Fix C4 — no page in this audit lane
    "dataGovernance",      # Wave-Audit-Defect-Fix C5 — no page in this audit lane
}

# Roles excluded from the audit-e2e lane (test scope decision; per spec
# comment line 86). BM gets its own audit lane in the observability cycle.
# COMPLIANCE_OFFICER is a runtime role (access.ts + core/rbac.py) that the
# Playwright all-pages-by-role spec does not iterate (it covers PB/WM/ADMIN/
# AUDIT_VIEWER), so it is excluded from the spec-subset comparison the same way
# BRANCH_MANAGER is — its server-side access is verified by the backend RBAC tests.
SPEC_EXCLUDED_ROLES: set[str] = {"BRANCH_MANAGER", "COMPLIANCE_OFFICER"}


def _parse_access_rules(source: str) -> dict[str, set[str]]:
    """Extract the {routeKey: {role1, role2, ...}} mapping from a TS source.

    The grammar matched is `routeKey: ["ROLE1", "ROLE2", ...]` which is what
    both access.ts and the spec emit verbatim. Comment lines starting with
    `//` are ignored.
    """
    rules: dict[str, set[str]] = {}
    # Strip block + line comments to keep the parse simple.
    cleaned = re.sub(r"//[^\n]*", "", source)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.S)
    for match in re.finditer(
        r"(\w+):\s*\[\s*((?:\"[A-Z_]+\"\s*,?\s*)+)\]", cleaned
    ):
        key = match.group(1)
        roles = set(re.findall(r"\"([A-Z_]+)\"", match.group(2)))
        # Heuristic: routeKey-style identifiers are lowerCamelCase; skip
        # other matches like type aliases / interface keys.
        if key[0].islower():
            rules[key] = roles
    return rules


def test_access_rules_export_exists() -> None:
    """Runtime ACCESS_RULES must be exported so cross-source contract tests
    can parse the canonical mapping."""
    source = ACCESS_TS.read_text(encoding="utf-8")
    assert "export const ACCESS_RULES" in source, (
        "apps/web/src/lib/access.ts must `export const ACCESS_RULES` so "
        "downstream tests can parse the canonical table; the in-file "
        "helpers (canAccessRoute / routeRoles) are not sufficient because "
        "the contract test wants the raw mapping."
    )


def test_spec_access_rules_is_subset_of_runtime() -> None:
    """Every routeKey present in the e2e spec must (a) exist in the runtime
    table, and (b) have the same allowed-role list modulo the documented
    BRANCH_MANAGER exclusion."""
    runtime = _parse_access_rules(ACCESS_TS.read_text(encoding="utf-8"))
    spec = _parse_access_rules(SPEC_TS.read_text(encoding="utf-8"))

    # Pre-flight: both tables must parse to something meaningful.
    assert len(runtime) >= 25, (
        f"runtime ACCESS_RULES parsed only {len(runtime)} keys; expected "
        f">=25. Parser drift?"
    )
    assert len(spec) >= 18, (
        f"spec ACCESS_RULES parsed only {len(spec)} keys; expected >=18. "
        f"Parser drift?"
    )

    drifted: list[str] = []
    for route_key, spec_roles in spec.items():
        if route_key not in runtime:
            drifted.append(
                f"  - spec.{route_key} exists but runtime ACCESS_RULES has "
                f"no such key"
            )
            continue
        runtime_roles = runtime[route_key] - SPEC_EXCLUDED_ROLES
        if spec_roles != runtime_roles:
            drifted.append(
                f"  - {route_key}: spec={sorted(spec_roles)} "
                f"runtime(minus BM)={sorted(runtime_roles)}"
            )

    assert not drifted, (
        "ACCESS_RULES dual-SoT drift detected (spec drifted from runtime):\n"
        + "\n".join(drifted)
        + "\n\nFix: align tests/audit-e2e/all-pages-by-role.spec.ts ACCESS_RULES "
        "with apps/web/src/lib/access.ts (filtered to remove BRANCH_MANAGER) "
        "instead of patching individual page failures."
    )


def test_spec_excluded_routekeys_have_no_pages() -> None:
    """The 5 routeKeys excluded from the spec must genuinely have no PAGES
    entry in the spec (otherwise the exclusion would silently hide a test
    that should exist)."""
    spec_source = SPEC_TS.read_text(encoding="utf-8")
    for excluded_key in SPEC_EXCLUDED_ROUTEKEYS:
        # PAGES entries look like `routeKey: "conflictOfInterest"`
        pattern = rf'routeKey:\s*"{excluded_key}"'
        match = re.search(pattern, spec_source)
        assert match is None, (
            f"{excluded_key} is in SPEC_EXCLUDED_ROUTEKEYS but the spec has a "
            f"PAGES entry referencing it. Either remove the exclusion or "
            f"remove the PAGES entry."
        )


def test_runtime_routekeys_either_in_spec_or_excluded() -> None:
    """Every runtime ACCESS_RULES key must either be in the spec OR in the
    documented SPEC_EXCLUDED_ROUTEKEYS allowlist. Catches the case where a
    new runtime route is added but the spec is silently left behind."""
    runtime = _parse_access_rules(ACCESS_TS.read_text(encoding="utf-8"))
    spec = _parse_access_rules(SPEC_TS.read_text(encoding="utf-8"))

    unaccounted: list[str] = []
    for route_key in runtime:
        if route_key in spec:
            continue
        if route_key in SPEC_EXCLUDED_ROUTEKEYS:
            continue
        unaccounted.append(route_key)

    assert not unaccounted, (
        f"runtime ACCESS_RULES has routeKeys not in spec and not in the "
        f"documented exclusion list: {unaccounted}\n"
        f"Add them to spec ACCESS_RULES + PAGES, or to SPEC_EXCLUDED_ROUTEKEYS "
        f"with a Wave-* marker."
    )
