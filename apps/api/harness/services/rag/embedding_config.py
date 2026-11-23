"""WMAH_USE_SYNTHETIC_EMBEDDINGS env var contract (AC25, ADR-005:145).

Environment variable:
    WMAH_USE_SYNTHETIC_EMBEDDINGS
        Unset or "0": real BGE call path (production default).
        "1":          deterministic synthetic vector path (Cycle 2 fixture-only scope).

Synthetic vector spec:
    - Dimension: 1024 (V007:23 vector(1024), BGE-M3)
    - Algorithm: SHA-256(chunk_id bytes) → seed → uniform [-1.0, 1.0] over 1024 floats
    - Determinism: same chunk_id always produces same vector

Fail-closed contracts:
    - Dimension mismatch → DIMENSION_MISMATCH reason_code (ADR-005:145)
    - BGE service unreachable → EMBEDDING_CALL_FAILED audit_code (audit.py:9, NR8 reuse)
"""

from __future__ import annotations

import hashlib
import os
import struct

# BGE-M3 / pgvector dimension contract (V007:23)
EXPECTED_DIMENSIONS = 1024

# Fail-closed reason codes (ADR-005 §5, line 145)
REASON_CODE_DIMENSION_MISMATCH = "DIMENSION_MISMATCH"

# Audit code reused from audit.py:9 (NR8 — no new reason_code)
AUDIT_CODE_EMBEDDING_CALL_FAILED = "EMBEDDING_CALL_FAILED"


def use_synthetic_embeddings() -> bool:
    """Return True when WMAH_USE_SYNTHETIC_EMBEDDINGS=1 is set.

    Unset or any value other than "1" returns False (real BGE call path).
    """
    return os.environ.get("WMAH_USE_SYNTHETIC_EMBEDDINGS", "0").strip() == "1"


def get_synthetic_vector(chunk_id: str) -> list[float]:
    """Generate a deterministic synthetic embedding vector for ``chunk_id``.

    Uses SHA-256(chunk_id) to seed a deterministic sequence of 1024 floats
    uniformly distributed in [-1.0, 1.0].  Same chunk_id always produces
    the same vector (re-runnable, no random state).

    Args:
        chunk_id: Stable string identifier for the chunk (UUID or text key).

    Returns:
        List of 1024 floats in [-1.0, 1.0].

    Raises:
        ValueError: If the produced vector dimension does not equal
                    EXPECTED_DIMENSIONS (DIMENSION_MISMATCH fail-closed path).
    """
    digest = hashlib.sha256(chunk_id.encode("utf-8")).digest()  # 32 bytes

    # Expand to 1024 floats by hashing successive counter blocks.
    # Each SHA-256 call yields 32 bytes = 8 × uint32 values → 8 floats.
    # 1024 / 8 = 128 rounds.
    floats: list[float] = []
    for counter in range(128):
        block = hashlib.sha256(digest + counter.to_bytes(4, "big")).digest()
        for i in range(0, 32, 4):
            uint_val: int = struct.unpack_from(">I", block, i)[0]
            # Map [0, 2^32) → [-1.0, 1.0]
            floats.append(uint_val / 2_147_483_647.5 - 1.0)

    if len(floats) != EXPECTED_DIMENSIONS:
        raise ValueError(
            f"{REASON_CODE_DIMENSION_MISMATCH}: produced {len(floats)} dims, "
            f"expected {EXPECTED_DIMENSIONS}"
        )
    return floats


def validate_vector_dimension(vector: list[float], *, expected: int = EXPECTED_DIMENSIONS) -> None:
    """Raise ValueError with DIMENSION_MISMATCH reason_code if dimension is wrong.

    Used at retrieval time when a stored or incoming vector dimension does not
    match the pgvector column dimension (ADR-005:145 fail-closed contract).

    Args:
        vector: The embedding vector to validate.
        expected: Expected number of dimensions (default: EXPECTED_DIMENSIONS=1024).

    Raises:
        ValueError: With DIMENSION_MISMATCH reason_code in the message.
    """
    if len(vector) != expected:
        raise ValueError(
            f"{REASON_CODE_DIMENSION_MISMATCH}: vector has {len(vector)} dims, "
            f"expected {expected}"
        )
