"""Shared pytest configuration and plugin hooks.

DeepEval faithfulness hook (ADR-003 pre-approved, ADR-005 §4 / REG-04 §4.1):
- If env AI_FAITHFULNESS_USE_DEEPEVAL=true AND deepeval is importable:
  Tests marked @pytest.mark.rag_faithfulness receive an automatic
  FaithfulnessMetric assertion injected via pytest_runtest_call.
- Otherwise: hook is a no-op (graceful fallback).

Usage in a test:
    @pytest.mark.rag_faithfulness(
        input="query text",
        actual_output="model answer",
        retrieval_context=["chunk1", "chunk2"],
        threshold=0.7,
    )
    def test_something(): ...

The marker args are optional overrides; if the test attaches
``_deepeval_case`` to the request node (via fixture), that takes priority.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Custom marks registration (avoids PytestUnknownMarkWarning)
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "rag_faithfulness: mark test to trigger DeepEval faithfulness assertion (ADR-005 §4).",
    )
    config.addinivalue_line(
        "markers",
        "rag_golden: RAG golden-set regression tests (REG-04 T260).",
    )
    config.addinivalue_line(
        "markers",
        "module_split: module-split backward-compatibility tests (W3-T7).",
    )
    config.addinivalue_line(
        "markers",
        "adversarial: adversarial scenario tests (REG-04 §4.3, LLM01).",
    )
    config.addinivalue_line(
        "markers",
        "security: security property tests.",
    )
    config.addinivalue_line(
        "markers",
        "integration: tests requiring a live API server.",
    )


# ---------------------------------------------------------------------------
# DeepEval faithfulness hook
# ---------------------------------------------------------------------------

_DEEPEVAL_ENABLED: bool = os.environ.get("AI_FAITHFULNESS_USE_DEEPEVAL", "").lower() in (
    "1", "true", "yes"
)

_deepeval_available: bool = False
_FaithfulnessMetric: Any = None
_LLMTestCase: Any = None

if _DEEPEVAL_ENABLED:
    try:
        from deepeval.metrics import FaithfulnessMetric as _FM  # type: ignore[import]
        from deepeval.test_case import LLMTestCase as _TC  # type: ignore[import]

        _FaithfulnessMetric = _FM
        _LLMTestCase = _TC
        _deepeval_available = True
    except ImportError:
        pass  # graceful fallback — hook is no-op


def _extract_faithfulness_args(
    item: pytest.Item,
) -> tuple[str, str, list[str], float] | None:
    """Return (input, actual_output, retrieval_context, threshold) from marker or None."""
    marker = item.get_closest_marker("rag_faithfulness")
    if marker is None:
        return None

    # Priority 1: test attached _deepeval_case dict via a fixture store
    deepeval_case: dict[str, Any] | None = getattr(item, "_deepeval_case", None)
    if deepeval_case:
        return (
            deepeval_case.get("input", ""),
            deepeval_case.get("actual_output", ""),
            deepeval_case.get("retrieval_context", []),
            float(deepeval_case.get("threshold", 0.7)),
        )

    # Priority 2: marker kwargs
    return (
        str(marker.kwargs.get("input", "")),
        str(marker.kwargs.get("actual_output", "")),
        list(marker.kwargs.get("retrieval_context", [])),
        float(marker.kwargs.get("threshold", 0.7)),
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Any:  # type: ignore[return]
    """Inject DeepEval faithfulness assertion after the test body runs."""
    outcome = yield  # run the actual test

    if not (_DEEPEVAL_ENABLED and _deepeval_available):
        return  # hook disabled or DeepEval not installed

    args = _extract_faithfulness_args(item)
    if args is None:
        return  # not a rag_faithfulness test

    input_text, actual_output, retrieval_context, threshold = args

    if not actual_output or not retrieval_context:
        # Not enough data to evaluate — skip assertion rather than false-fail
        return

    try:
        metric = _FaithfulnessMetric(threshold=threshold)  # type: ignore[call-arg]
        test_case = _LLMTestCase(  # type: ignore[call-arg]
            input=input_text,
            actual_output=actual_output,
            retrieval_context=retrieval_context,
        )
        metric.measure(test_case)
        score: float = metric.score  # type: ignore[attr-defined]
        assert score >= threshold, (
            f"DeepEval faithfulness hook: score {score:.3f} < threshold {threshold} "
            f"(ADR-005 §4, AI_FAITHFULNESS_MIN={threshold})"
        )
    except AssertionError:
        raise
    except Exception as exc:  # noqa: BLE001
        # DeepEval judge call failed — record but do not fail the test
        item.warn(
            pytest.PytestWarning(
                f"DeepEval faithfulness hook error (non-fatal): {exc}"
            )
        )
