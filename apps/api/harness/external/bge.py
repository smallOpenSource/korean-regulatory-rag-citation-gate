"""Internal BGE embedding and rerank client."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from apps.api.harness.core.config import AiConfig

from .http import ExternalProviderError, request_json

RETRY_STATUS_MARKERS = ("HTTP 429", "HTTP 503")


@dataclass(frozen=True)
class BgeClientConfig:
    embedding_url: str
    embedding_key: str
    embedding_model: str
    dimensions: int
    rerank_url: str
    rerank_key: str
    rerank_model: str
    auth_scheme: str = "Bearer"
    timeout_seconds: float = 30.0
    max_attempts: int = 3
    backoff_base_seconds: float = 0.5

    @classmethod
    def from_ai_config(
        cls,
        ai: AiConfig,
        *,
        embedding_key: str,
        rerank_key: str,
        auth_scheme: str = "Bearer",
        timeout_seconds: float = 30.0,
    ) -> BgeClientConfig:
        return cls(
            embedding_url=ai.bge_embedding_url,
            embedding_key=embedding_key,
            embedding_model=ai.bge_embedding_model,
            dimensions=ai.bge_dimensions,
            rerank_url=ai.bge_rerank_url,
            rerank_key=rerank_key,
            rerank_model=ai.bge_rerank_model,
            auth_scheme=ai.bge_auth_scheme or auth_scheme,
            timeout_seconds=ai.bge_embedding_timeout_seconds or timeout_seconds,
        )


class BgeClient:
    """Client for the internal BGE Bearer API."""

    def __init__(self, config: BgeClientConfig) -> None:
        self.config = config

    def _auth_header(self, key: str) -> str:
        return f"{self.config.auth_scheme or 'Bearer'} {key}"

    def _post_with_retry(self, *, url: str, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return request_json(
                    method="POST",
                    url=url,
                    headers={"Authorization": self._auth_header(key)},
                    payload=payload,
                    timeout_seconds=self.config.timeout_seconds,
                ).payload
            except ExternalProviderError as exc:
                retryable = str(exc).startswith(RETRY_STATUS_MARKERS)
                if attempt >= self.config.max_attempts or not retryable:
                    raise
                time.sleep(self.config.backoff_base_seconds * (2 ** (attempt - 1)))
        raise ExternalProviderError("BGE retry loop exhausted")

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Call BGE embeddings with `texts` and validate dense vectors."""

        if not texts:
            return []
        payload = {"model": self.config.embedding_model, "texts": texts}
        response = self._post_with_retry(
            url=self.config.embedding_url,
            key=self.config.embedding_key,
            payload=payload,
        )
        vectors = extract_dense_embeddings(response)
        validate_embeddings(vectors, expected_count=len(texts), dimensions=self.config.dimensions)
        return vectors

    def rerank(self, *, query: str, documents: list[str], top_n: int) -> list[Any]:
        """Call BGE rerank and validate that returned items map to input documents."""

        if not documents:
            return []
        payload = {
            "model": self.config.rerank_model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        response = self._post_with_retry(
            url=self.config.rerank_url, key=self.config.rerank_key, payload=payload
        )
        items = extract_rerank_items(response)
        validate_rerank_items(items, document_count=len(documents))
        return items


def extract_dense_embeddings(payload: dict[str, Any]) -> list[list[float]]:
    """Extract dense embeddings from supported internal response shapes."""

    for key in ("dense_embeddings", "embeddings", "vectors"):
        value = payload.get(key)
        if isinstance(value, list):
            if not value:
                return []
            if isinstance(value[0], dict) and isinstance(value[0].get("embedding"), list):
                return [item["embedding"] for item in value]
            if isinstance(value[0], list):
                return value
    data = payload.get("data")
    if isinstance(data, list) and data:
        vectors: list[list[float]] = []
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("embedding"), list):
                vectors.append(item["embedding"])
        if vectors:
            return vectors
    raise ExternalProviderError("BGE response missing dense_embeddings")


def validate_embeddings(
    vectors: list[list[float]], *, expected_count: int, dimensions: int
) -> None:
    """Validate embedding count, dimension, and numeric values."""

    if len(vectors) != expected_count:
        raise ExternalProviderError("BGE embedding count mismatch")
    for vector in vectors:
        if len(vector) != dimensions:
            raise ExternalProviderError("BGE embedding dimension mismatch")
        if not all(isinstance(value, (int, float)) for value in vector):
            raise ExternalProviderError("BGE embedding contains non-numeric values")


def extract_rerank_items(payload: dict[str, Any]) -> list[Any]:
    """Extract rerank result list from supported response shapes."""

    for key in ("results", "data", "rankings", "documents"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    raise ExternalProviderError("BGE rerank response missing results")


def validate_rerank_items(items: list[Any], *, document_count: int) -> None:
    """Validate common BGE rerank result shapes without assuming one vendor schema."""

    if not items:
        raise ExternalProviderError("BGE rerank response missing ranked items")
    for position, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        raw_index = item.get("index", item.get("document_index", item.get("rank")))
        if raw_index is None:
            continue
        if not isinstance(raw_index, int):
            raise ExternalProviderError("BGE rerank item index is not an integer")
        index = (
            raw_index - 1
            if raw_index == position + 1 and raw_index >= document_count
            else raw_index
        )
        if index < 0 or index >= document_count:
            raise ExternalProviderError("BGE rerank item index out of range")
        score = item.get("score", item.get("relevance_score", item.get("rerank_score")))
        if score is not None and not isinstance(score, (int, float)):
            raise ExternalProviderError("BGE rerank score is not numeric")
