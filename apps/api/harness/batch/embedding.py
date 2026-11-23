"""Embedding refresh helpers for document_chunks."""

from __future__ import annotations

from typing import Any

from apps.api.harness.core.db import execute, fetch_all
from apps.api.harness.external.bge import BgeClient

LIST_UNEMBEDDED_CHUNKS_SQL = """
/* sql_id: list_unembedded_chunks */
SELECT id, chunk_text
FROM document_chunks
WHERE is_embedded IS FALSE
ORDER BY created_at
LIMIT $1;
"""

UPDATE_CHUNK_EMBEDDING_SQL = """
/* sql_id: update_chunk_embedding */
UPDATE document_chunks
SET embedding = $2::vector, is_embedded = TRUE
WHERE id = $1::uuid;
"""


def vector_literal(vector: list[float]) -> str:
    """Convert a numeric vector to pgvector text literal."""

    return "[" + ",".join(str(float(value)) for value in vector) + "]"


async def refresh_embeddings(
    *, connection: Any, bge_client: BgeClient, batch_size: int
) -> dict[str, int]:
    """Embed unembedded chunks using internal BGE and update pgvector columns."""

    rows = await fetch_all(connection, LIST_UNEMBEDDED_CHUNKS_SQL, batch_size)
    if not rows:
        return {"rows_collected": 0, "rows_skipped": 0, "rows_failed": 0}
    texts = [str(row["chunk_text"]) for row in rows]
    vectors = bge_client.embed_texts(texts)
    for row, vector in zip(rows, vectors, strict=True):
        await execute(
            connection, UPDATE_CHUNK_EMBEDDING_SQL, str(row["id"]), vector_literal(vector)
        )
    return {"rows_collected": len(rows), "rows_skipped": 0, "rows_failed": 0}
