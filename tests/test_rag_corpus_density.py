"""AC12 — RAG corpus density tests for seed_40_manual_rag.sql.

Verifies that the seeded manual RAG corpus meets minimum quality requirements:
  - 5 documents with body text 400-600 chars each
  - All chunks are unique (no duplicate chunk_text)
  - All chunks contain [교육용] governance marker

Tests parse the SQL file directly (no DB required) to keep CI fast and
independent of database connectivity.

Ref: AC12 (5 docs 400-600자 + chunk uniqueness + [교육용])
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SQL_FILE = PROJECT_ROOT / "db" / "fixtures" / "seed_40_manual_rag.sql"

GOVERNANCE_MARKER = "[교육용]"
DOC_MIN_LEN = 400
DOC_MAX_LEN = 600
EXPECTED_DOC_COUNT = 5


# ---------------------------------------------------------------------------
# Helpers — parse SQL without executing it
# ---------------------------------------------------------------------------

def _load_sql() -> str:
    assert SQL_FILE.exists(), f"SQL fixture not found: {SQL_FILE}"
    return SQL_FILE.read_text(encoding="utf-8")


def _extract_document_bodies(sql: str) -> list[str]:
    """Extract raw_text values from the seed_40_manual_rag_documents CTE.

    The documents CTE contains lines like:
        (N, 'seed-xxx', '[교육용] title', 'urn:...', 'hash', 'body text here'),
    We find the INSERT INTO documents block and extract the last quoted string
    per values row (the raw_content / raw_text column).
    """
    # Find the manual_doc_seed CTE inside the documents INSERT block
    # Pattern: last single-quoted string on each VALUES row in the documents block
    # We look for the block between "seed_40_manual_rag_documents" and the next sql_id comment
    docs_block_match = re.search(
        r"/\* sql_id: seed_40_manual_rag_documents \*/(.*?)/\* sql_id:",
        sql,
        re.DOTALL,
    )
    assert docs_block_match, "seed_40_manual_rag_documents block not found in SQL file"
    docs_block = docs_block_match.group(1)

    # Each VALUES row ends with a long quoted string (the raw_text / body).
    # Match: ('...body text here'),  — last quoted field before closing paren + comma/paren
    # We use a greedy match for the last quoted value in each VALUES tuple.
    bodies: list[str] = []
    # Match full VALUES tuples: ( ... , 'last field' )
    tuple_pattern = re.compile(
        r"\(\s*\d+\s*,\s*'[^']+'\s*,\s*'[^']+'\s*,\s*'[^']+'\s*,\s*'[^']+'\s*,\s*'([^']+)'\s*\)",
        re.DOTALL,
    )
    for m in tuple_pattern.finditer(docs_block):
        bodies.append(m.group(1))
    return bodies


def _extract_chunk_texts(sql: str) -> list[str]:
    """Extract all chunk_text literal values from the seed_40_manual_rag_chunks block."""
    chunks_block_match = re.search(
        r"/\* sql_id: seed_40_manual_rag_chunks \*/(.*?)/\* sql_id:",
        sql,
        re.DOTALL,
    )
    assert chunks_block_match, "seed_40_manual_rag_chunks block not found in SQL file"
    chunks_block = chunks_block_match.group(1)

    # Match VALUES tuples: (doc_no, chunk_no, 'chunk_text')
    chunk_pattern = re.compile(
        r"\(\s*\d+\s*,\s*\d+\s*,\s*'([^']+)'\s*\)",
        re.DOTALL,
    )
    return [m.group(1) for m in chunk_pattern.finditer(chunks_block)]


# ---------------------------------------------------------------------------
# Tests: document body length (AC12: 400-600자)
# ---------------------------------------------------------------------------

def test_sql_file_exists():
    assert SQL_FILE.exists(), f"SQL fixture not found: {SQL_FILE}"


def test_exactly_five_documents():
    """seed_40_manual_rag_documents block must define exactly 5 document bodies."""
    sql = _load_sql()
    bodies = _extract_document_bodies(sql)
    assert len(bodies) == EXPECTED_DOC_COUNT, (
        f"Expected {EXPECTED_DOC_COUNT} document bodies, found {len(bodies)}"
    )


@pytest.mark.parametrize("doc_idx", range(EXPECTED_DOC_COUNT))
def test_document_body_length_400_to_600(doc_idx: int):
    """Each document body must be 400-600 characters long."""
    sql = _load_sql()
    bodies = _extract_document_bodies(sql)
    body = bodies[doc_idx]
    length = len(body)
    assert DOC_MIN_LEN <= length <= DOC_MAX_LEN, (
        f"Doc {doc_idx + 1} body length {length} outside [{DOC_MIN_LEN}, {DOC_MAX_LEN}]: "
        f"{body[:80]!r}..."
    )


# ---------------------------------------------------------------------------
# Tests: chunk uniqueness (AC12: SELECT COUNT(DISTINCT chunk_text) == COUNT(*))
# ---------------------------------------------------------------------------

def test_all_chunk_texts_are_unique():
    """All chunk_text values in the chunks block must be distinct (no duplicates)."""
    sql = _load_sql()
    chunks = _extract_chunk_texts(sql)
    assert len(chunks) > 0, "No chunk_text values found in seed_40_manual_rag_chunks"
    unique_chunks = set(chunks)
    assert len(unique_chunks) == len(chunks), (
        f"Duplicate chunk_text found: {len(chunks)} total, {len(unique_chunks)} unique. "
        f"Duplicates: {[c for c in chunks if chunks.count(c) > 1][:3]!r}"
    )


def test_chunk_count_at_least_30():
    """Must have at least 30 chunks (5 docs × 6 chunks minimum)."""
    sql = _load_sql()
    chunks = _extract_chunk_texts(sql)
    assert len(chunks) >= 30, (
        f"Expected at least 30 chunks, found {len(chunks)}"
    )


# ---------------------------------------------------------------------------
# Tests: governance marker (AC12: [교육용] in all chunks)
# ---------------------------------------------------------------------------

def test_all_chunks_contain_governance_marker():
    """Every chunk_text must contain the [교육용] governance marker."""
    sql = _load_sql()
    chunks = _extract_chunk_texts(sql)
    assert chunks, "No chunks found in SQL file"
    missing = [c[:60] for c in chunks if GOVERNANCE_MARKER not in c]
    assert not missing, (
        f"{len(missing)} chunks missing {GOVERNANCE_MARKER!r}: {missing[:3]!r}"
    )


def test_governance_marker_count_in_sql_at_least_5():
    """[교육용] marker must appear at least 5 times in the SQL file (one per doc body)."""
    sql = _load_sql()
    count = sql.count(GOVERNANCE_MARKER)
    assert count >= 5, (
        f"Expected ≥5 occurrences of {GOVERNANCE_MARKER!r} in SQL, found {count}"
    )


def test_all_document_bodies_contain_governance_marker():
    """Each document body must contain the [교육용] marker."""
    sql = _load_sql()
    bodies = _extract_document_bodies(sql)
    missing = [i + 1 for i, b in enumerate(bodies) if GOVERNANCE_MARKER not in b]
    assert not missing, (
        f"Document(s) {missing} missing {GOVERNANCE_MARKER!r} governance marker"
    )
