"""
tests/test_console_error_classifier.py

Unit tests for classify_console_error() in scripts/audit_v1_ui_matrix.py.

T4-2 acceptance binary:
- classify_console_error function defined + importable
- 403 → design_intent_role_gated
- 422 → script_bug
- 5xx / network error → production_bug
- T2-2 fresh baseline 5 console_errors ALL → design_intent_role_gated
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Import the target function from scripts/ (not a package, use spec loader)
# ---------------------------------------------------------------------------
_SCRIPT_PATH = pathlib.Path(__file__).parent.parent / "scripts" / "audit_v1_ui_matrix.py"


def _load_classifier():
    spec = importlib.util.spec_from_file_location("audit_v1_ui_matrix", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Suppress playwright ImportError during module load (it is guarded inside main_async)
    sys.modules.setdefault("playwright", type(sys)("playwright"))
    sys.modules.setdefault("playwright.async_api", type(sys)("playwright.async_api"))
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


@pytest.fixture(scope="module")
def classifier_mod():
    return _load_classifier()


@pytest.fixture(scope="module")
def classify(classifier_mod):  # type: ignore[no-untyped-def]
    return classifier_mod.classify_console_error


# ---------------------------------------------------------------------------
# Bucket: design_intent_role_gated (HTTP 403)
# ---------------------------------------------------------------------------

class TestDesignIntentRoleGated:
    def test_403_standard_browser_text(self, classify):
        """Standard Chrome console error for 403 → design_intent_role_gated."""
        text = "Failed to load resource: the server responded with a status of 403 (Forbidden)"
        assert classify(text) == "design_intent_role_gated"

    def test_403_short_pattern(self, classify):
        assert classify("GET https://api/v1/resource 403") == "design_intent_role_gated"

    def test_403_path_in_url(self, classify):
        assert classify("https://host/403 not accessible") == "design_intent_role_gated"

    # T2-2 actual failing cells — all must be design_intent_role_gated
    @pytest.mark.parametrize("role,route", [
        ("PB1",         "dataGovernance"),
        ("WM1",         "dataGovernance"),
        ("AUDIT_VIEWER","dataGovernance"),
        ("AUDIT_VIEWER","conflictOfInterest"),
        ("AUDIT_VIEWER","kycEdd"),
    ])
    def test_t2_2_actual_cells(self, classify, role, route):
        """T2-2 fresh baseline: all 5 console_errors must be design_intent_role_gated."""
        text = "Failed to load resource: the server responded with a status of 403 (Forbidden)"
        result = classify(text)
        assert result == "design_intent_role_gated", (
            f"[{role}] {route}: expected design_intent_role_gated, got {result!r}"
        )


# ---------------------------------------------------------------------------
# Bucket: script_bug (HTTP 422)
# ---------------------------------------------------------------------------

class TestScriptBug:
    def test_422_browser_text(self, classify):
        text = "Failed to load resource: the server responded with a status of 422 (Unprocessable Entity)"
        assert classify(text) == "script_bug"

    def test_422_short(self, classify):
        assert classify("POST /api/v1/something 422") == "script_bug"


# ---------------------------------------------------------------------------
# Bucket: production_bug (5xx / network)
# ---------------------------------------------------------------------------

class TestProductionBug:
    def test_500(self, classify):
        text = "Failed to load resource: the server responded with a status of 500 (Internal Server Error)"
        assert classify(text) == "production_bug"

    def test_502(self, classify):
        assert classify("502 Bad Gateway") == "production_bug"

    def test_503(self, classify):
        assert classify("503 Service Unavailable") == "production_bug"

    def test_net_err(self, classify):
        assert classify("net::ERR_CONNECTION_REFUSED https://host/api") == "production_bug"

    def test_failed_to_fetch(self, classify):
        assert classify("Failed to fetch https://host/api/endpoint") == "production_bug"

    def test_unknown_text_defaults_to_production_bug(self, classify):
        """Unrecognised errors default to production_bug (conservative)."""
        assert classify("Something completely unexpected happened") == "production_bug"


# ---------------------------------------------------------------------------
# Bucket aggregation: console_error_buckets in T2-2 summary
# ---------------------------------------------------------------------------

class TestT22SummaryBuckets:
    """Verify that T2-2 fresh summary.json contains correct bucket counts.

    This test reads the live artifact produced by T2-2. If the file is absent
    (CI without prior run) the test is skipped rather than hard-failed.
    """

    SUMMARY_PATH = (
        pathlib.Path(__file__).parent.parent
        / "audit-out"
        / "service-viability-v1"
        / "axis-1-t2-2-fresh"
        / "summary.json"
    )

    @pytest.fixture(autouse=True)
    def _require_summary(self):
        if not self.SUMMARY_PATH.exists():
            pytest.skip(f"T2-2 summary not found at {self.SUMMARY_PATH}")

    def _load(self):
        import json
        with open(self.SUMMARY_PATH, encoding="utf-8") as f:
            return json.load(f)

    def test_summary_has_console_error_buckets_key(self):
        d = self._load()
        assert "console_error_buckets" in d, "summary.json missing console_error_buckets"

    def test_script_bug_count_is_zero(self):
        """T2-2 had no 422 errors — script_bug must be 0."""
        d = self._load()
        buckets = d["console_error_buckets"]
        assert buckets.get("script_bug", -1) == 0, (
            f"Expected script_bug=0, got {buckets.get('script_bug')}"
        )

    def test_production_bug_count_is_zero(self):
        """T2-2 had no 5xx / network errors — production_bug must be 0."""
        d = self._load()
        buckets = d["console_error_buckets"]
        assert buckets.get("production_bug", -1) == 0, (
            f"Expected production_bug=0, got {buckets.get('production_bug')}"
        )

    def test_design_intent_count_matches_total_console_errors(self):
        """All T2-2 console_errors (5) must be design_intent_role_gated."""
        d = self._load()
        buckets = d.get("console_error_buckets", {})
        total_errors = d.get("fail_category_counts", {}).get("console_error", 0)
        assert buckets.get("design_intent_role_gated", 0) == total_errors, (
            f"design_intent_role_gated={buckets.get('design_intent_role_gated')} "
            f"!= total console_error cells={total_errors}"
        )
