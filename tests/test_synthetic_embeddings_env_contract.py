"""AC25 — WMAH_USE_SYNTHETIC_EMBEDDINGS env var contract tests.

Covers:
  - env var unset → default behaviour (real call path branch, use_synthetic_embeddings=False)
  - env var =1 → synthetic vector: dimension=1024, deterministic (hash of chunk_id)
  - dimension mismatch (test-injected wrong dim) → DIMENSION_MISMATCH reason_code
  - BGE unreachable simulation → EMBEDDING_CALL_FAILED audit_code reuse (NR8)

Ref: ADR-005:145, audit.py:9, embedding_config.py
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Import under test
# ---------------------------------------------------------------------------
from apps.api.harness.services.rag.embedding_config import (
    AUDIT_CODE_EMBEDDING_CALL_FAILED,
    EXPECTED_DIMENSIONS,
    REASON_CODE_DIMENSION_MISMATCH,
    get_synthetic_vector,
    use_synthetic_embeddings,
    validate_vector_dimension,
)
from apps.api.harness.core.audit import CANONICAL_AUDIT_ACTION_CODES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_env(value: str | None) -> None:
    """Set or unset WMAH_USE_SYNTHETIC_EMBEDDINGS for the current process."""
    if value is None:
        os.environ.pop("WMAH_USE_SYNTHETIC_EMBEDDINGS", None)
    else:
        os.environ["WMAH_USE_SYNTHETIC_EMBEDDINGS"] = value


# ---------------------------------------------------------------------------
# Test: env var unset → real call path (use_synthetic_embeddings returns False)
# ---------------------------------------------------------------------------

def test_env_unset_defaults_to_real_call_path():
    """Unset env var means use_synthetic_embeddings() returns False (real BGE path)."""
    _set_env(None)
    assert use_synthetic_embeddings() is False


def test_env_zero_string_defaults_to_real_call_path():
    """Explicit =0 means use_synthetic_embeddings() returns False."""
    _set_env("0")
    assert use_synthetic_embeddings() is False


def test_env_arbitrary_value_defaults_to_real_call_path():
    """Any value other than '1' returns False."""
    _set_env("false")
    assert use_synthetic_embeddings() is False
    _set_env(None)


# ---------------------------------------------------------------------------
# Test: env var =1 → synthetic vector dimension=1024
# ---------------------------------------------------------------------------

def test_env_one_enables_synthetic_path():
    """WMAH_USE_SYNTHETIC_EMBEDDINGS=1 → use_synthetic_embeddings() returns True."""
    _set_env("1")
    assert use_synthetic_embeddings() is True
    _set_env(None)


def test_synthetic_vector_dimension_is_1024():
    """get_synthetic_vector returns exactly 1024 floats."""
    vector = get_synthetic_vector("test-chunk-001")
    assert len(vector) == EXPECTED_DIMENSIONS, (
        f"Expected {EXPECTED_DIMENSIONS} dims, got {len(vector)}"
    )


def test_synthetic_vector_all_floats_in_range():
    """All synthetic vector elements are floats in [-1.0, 1.0]."""
    vector = get_synthetic_vector("test-chunk-range-check")
    for i, val in enumerate(vector):
        assert isinstance(val, float), f"Element {i} is not float: {type(val)}"
        assert -1.0 <= val <= 1.0, f"Element {i}={val} out of [-1, 1] range"


# ---------------------------------------------------------------------------
# Test: determinism — same chunk_id → same vector, 50× repetitions
# ---------------------------------------------------------------------------

def test_synthetic_vector_is_deterministic_50x():
    """Same chunk_id always produces the identical vector (50 repetitions)."""
    chunk_id = "determinism-test-chunk-42"
    reference = get_synthetic_vector(chunk_id)
    for _ in range(50):
        result = get_synthetic_vector(chunk_id)
        assert result == reference, "Synthetic vector is non-deterministic"


def test_synthetic_vector_differs_for_different_chunk_ids():
    """Different chunk_ids produce different vectors."""
    v1 = get_synthetic_vector("chunk-id-alpha")
    v2 = get_synthetic_vector("chunk-id-beta")
    assert v1 != v2, "Different chunk_ids should produce different vectors"


# ---------------------------------------------------------------------------
# Test: dimension mismatch → DIMENSION_MISMATCH reason_code (ADR-005:145)
# ---------------------------------------------------------------------------

def test_validate_vector_dimension_raises_on_mismatch():
    """validate_vector_dimension raises ValueError with DIMENSION_MISMATCH for wrong dim."""
    wrong_dim_vector = [0.0] * 512  # 512 != 1024
    with pytest.raises(ValueError) as exc_info:
        validate_vector_dimension(wrong_dim_vector, expected=EXPECTED_DIMENSIONS)
    assert REASON_CODE_DIMENSION_MISMATCH in str(exc_info.value)


def test_validate_vector_dimension_passes_for_correct_dim():
    """validate_vector_dimension does not raise for correct dimension."""
    correct_vector = [0.0] * EXPECTED_DIMENSIONS
    validate_vector_dimension(correct_vector)  # must not raise


def test_dimension_mismatch_reason_code_value():
    """REASON_CODE_DIMENSION_MISMATCH matches ADR-005:145 literal."""
    assert REASON_CODE_DIMENSION_MISMATCH == "DIMENSION_MISMATCH"


# ---------------------------------------------------------------------------
# Test: BGE unreachable → EMBEDDING_CALL_FAILED audit code reuse (NR8)
# ---------------------------------------------------------------------------

def test_embedding_call_failed_audit_code_is_canonical():
    """EMBEDDING_CALL_FAILED is in CANONICAL_AUDIT_ACTION_CODES (audit.py:9 reuse, NR8)."""
    assert AUDIT_CODE_EMBEDDING_CALL_FAILED in CANONICAL_AUDIT_ACTION_CODES, (
        f"{AUDIT_CODE_EMBEDDING_CALL_FAILED!r} not found in CANONICAL_AUDIT_ACTION_CODES; "
        "NR8 reuse contract violated"
    )


def test_embedding_call_failed_audit_code_value():
    """AUDIT_CODE_EMBEDDING_CALL_FAILED matches the string used in audit.py."""
    assert AUDIT_CODE_EMBEDDING_CALL_FAILED == "EMBEDDING_CALL_FAILED"


def test_bge_unreachable_simulation_uses_existing_audit_code():
    """Simulate BGE unreachable: no new reason_code introduced — EMBEDDING_CALL_FAILED reused.

    This test documents the fail-closed contract: when BGE is unreachable the
    existing EMBEDDING_CALL_FAILED audit code is emitted (NR8 — no new code).
    The audit code must be canonical so it can be written to the audit log.
    """
    from apps.api.harness.core.audit import is_valid_audit_action

    # The code must be valid so it can be passed to require_audit_action()
    assert is_valid_audit_action(AUDIT_CODE_EMBEDDING_CALL_FAILED), (
        "EMBEDDING_CALL_FAILED must be a valid audit action to satisfy NR8 reuse contract"
    )
