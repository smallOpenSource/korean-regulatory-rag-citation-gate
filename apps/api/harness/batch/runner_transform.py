"""Transform and embed batch pipeline stages."""

from __future__ import annotations

import os
from typing import Any

from apps.api.harness.batch.documents import transform_raw_documents
from apps.api.harness.batch.embedding import refresh_embeddings
from apps.api.harness.core.config import AppConfig
from apps.api.harness.external.bge import BgeClient, BgeClientConfig

from .runner_readiness import create_skipped_stage_log, run_local_stage
from .types import StageResult, env_int, missing_env


def resolve_embedding_batch_size(value: int | None) -> int:
    """Resolve embedding batch size from CLI override or environment."""

    if value is not None:
        return max(value, 1)
    return env_int("BGE_EMBEDDING_BATCH_SIZE", default=32, minimum=1, maximum=256)


async def run_transform_stage(connection: Any, redis_client: Any) -> StageResult:
    """Transform raw documents into RAG documents/chunks."""

    return await run_local_stage(
        connection,
        redis_client,
        stage="transform",
        job_name="raw_document_transform",
        job_type_code="DOCUMENT_TRANSFORM",
        work=lambda: transform_raw_documents(connection=connection),
    )


async def run_embed_stage(
    connection: Any,
    redis_client: Any,
    *,
    config: AppConfig,
    batch_size: int,
) -> StageResult:
    """Refresh embeddings when internal BGE credentials are configured."""

    missing = missing_env(("BGE_EMBEDDING_API_KEY", "BGE_RERANK_API_KEY"))
    if missing:
        return await create_skipped_stage_log(
            connection,
            stage="embed",
            job_name="bge_embedding_refresh",
            job_type_code="EMBEDDING_REFRESH",
            reason=f"Internal BGE credentials not configured: {', '.join(missing)}",
            detail={"configured": False},
        )

    client = BgeClient(
        BgeClientConfig.from_ai_config(
            config.ai,
            embedding_key=os.environ["BGE_EMBEDDING_API_KEY"],
            rerank_key=os.environ["BGE_RERANK_API_KEY"],
        )
    )
    return await run_local_stage(
        connection,
        redis_client,
        stage="embed",
        job_name="bge_embedding_refresh",
        job_type_code="EMBEDDING_REFRESH",
        work=lambda: refresh_embeddings(
            connection=connection,
            bge_client=client,
            batch_size=batch_size,
        ),
        detail={"configured": True, "batch_size": batch_size},
    )
