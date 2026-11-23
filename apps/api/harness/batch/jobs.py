"""Batch job orchestration with Redis SETNX locks and batch_job_logs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from apps.api.harness.core.logging import redact_secret_text, summarize_db_error
from apps.api.harness.core.redis_client import RedisLock, acquire_lock, release_lock
from apps.api.harness.repositories import batch as batch_repo

PROVIDER_JOB_TYPE_CODES: dict[str, str] = {
    "PROVIDER_BROKER": "BROKER",
    "PROVIDER_DATA_GO_KR": "DATA_GO_KR",
    "PROVIDER_ECOS": "ECOS",
    "PROVIDER_DART": "OPENDART",
    "PROVIDER_KRX": "KRX",
}


@dataclass(frozen=True)
class BatchProviderEvidence:
    """Provider-detail evidence that is persisted separately from job status."""

    provider_code: str
    provider_status_code: str
    target_ref: str
    rows_collected: int = 0
    rows_skipped: int = 0
    rows_failed: int = 0
    reason_message: str | None = None
    provider_detail: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class BatchCounters:
    rows_collected: int = 0
    rows_skipped: int = 0
    rows_failed: int = 0
    provider_evidence: tuple[BatchProviderEvidence, ...] = ()

    def as_dict(self) -> dict[str, int]:
        return {
            "rows_collected": self.rows_collected,
            "rows_skipped": self.rows_skipped,
            "rows_failed": self.rows_failed,
        }


def provider_code_from_job_type(job_type_code: str) -> str | None:
    """Return the provider code for a provider job type, if one is known."""

    return PROVIDER_JOB_TYPE_CODES.get(job_type_code)


def provider_status_from_batch_log(batch_log: Mapping[str, Any]) -> str:
    """Map stable batch-log status into provider-detail taxonomy."""

    status_code = str(batch_log.get("status_code") or "")
    reason = str(batch_log.get("error_message") or "").lower()
    rows_collected = int(batch_log.get("rows_collected") or 0)
    rows_skipped = int(batch_log.get("rows_skipped") or 0)
    if status_code == "DONE":
        return "PROVIDER_DONE" if rows_collected > 0 else "PROVIDER_NO_DATA"
    if status_code == "SKIPPED":
        if "disabled" in reason or "lock already held" in reason:
            return "PROVIDER_SKIPPED_DISABLED"
        return "PROVIDER_SKIPPED_CONFIG"
    if status_code == "FAILED":
        auth_tokens = ("auth", "credential", "api key", "apikey", "auth_key", "401", "403")
        if any(token in reason for token in auth_tokens):
            return "PROVIDER_FAILED_AUTH"
        if any(token in reason for token in ("rate", "limit", "quota", "429")):
            return "PROVIDER_FAILED_RATE_LIMIT"
        if any(token in reason for token in ("network", "timeout", "connection", "dns")):
            return "PROVIDER_FAILED_NETWORK"
        return "PROVIDER_FAILED_SCHEMA"
    if rows_skipped > 0:
        return "PROVIDER_NO_DATA"
    return "PROVIDER_FAILED_SCHEMA"


async def persist_batch_provider_evidence(
    connection: Any,
    *,
    batch_job_log_id: str,
    evidences: tuple[BatchProviderEvidence, ...],
) -> None:
    """Persist provider-detail evidence rows for an existing batch log."""

    for evidence in evidences:
        await batch_repo.insert_batch_provider_evidence(
            connection,
            batch_job_log_id=batch_job_log_id,
            provider_code=evidence.provider_code,
            provider_status_code=evidence.provider_status_code,
            target_ref=evidence.target_ref,
            rows_collected=evidence.rows_collected,
            rows_skipped=evidence.rows_skipped,
            rows_failed=evidence.rows_failed,
            reason_message=redact_secret_text(evidence.reason_message or "")
            if evidence.reason_message
            else None,
            provider_detail=dict(evidence.provider_detail or {}),
        )


async def persist_batch_log_provider_evidence(
    connection: Any,
    *,
    batch_log: Mapping[str, Any],
    target_ref: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Persist aggregate provider-detail evidence derived from one batch log."""

    provider_code = provider_code_from_job_type(str(batch_log.get("job_type_code") or ""))
    if provider_code is None:
        return None
    evidence = BatchProviderEvidence(
        provider_code=provider_code,
        provider_status_code=provider_status_from_batch_log(batch_log),
        target_ref=target_ref or f"{provider_code}:{batch_log.get('job_name')}",
        rows_collected=int(batch_log.get("rows_collected") or 0),
        rows_skipped=int(batch_log.get("rows_skipped") or 0),
        rows_failed=int(batch_log.get("rows_failed") or 0),
        reason_message=str(batch_log.get("error_message") or "") or None,
        provider_detail={
            "job_name": str(batch_log.get("job_name") or ""),
            "job_type_code": str(batch_log.get("job_type_code") or ""),
            "status_code": str(batch_log.get("status_code") or ""),
            **dict(detail or {}),
        },
    )
    return await batch_repo.insert_batch_provider_evidence(
        connection,
        batch_job_log_id=str(batch_log["id"]),
        provider_code=evidence.provider_code,
        provider_status_code=evidence.provider_status_code,
        target_ref=evidence.target_ref,
        rows_collected=evidence.rows_collected,
        rows_skipped=evidence.rows_skipped,
        rows_failed=evidence.rows_failed,
        reason_message=evidence.reason_message,
        provider_detail=dict(evidence.provider_detail or {}),
    )


async def run_locked_batch_job(
    *,
    connection: Any,
    redis_client: Any,
    job_name: str,
    job_type_code: str,
    ttl_seconds: int,
    work: Callable[[], Awaitable[BatchCounters]],
) -> dict[str, Any]:
    """Run a batch job once per Redis lock owner and persist job status."""

    lock_key = f"harness:batch:lock:{job_name}"
    lock: RedisLock | None = acquire_lock(redis_client, key=lock_key, ttl_seconds=ttl_seconds)
    if lock is None:
        return await batch_repo.create_skipped_batch_log(
            connection,
            job_name=job_name,
            job_type_code=job_type_code,
            reason="lock already held",
        )

    log = await batch_repo.create_batch_log(
        connection, job_name=job_name, job_type_code=job_type_code
    )
    try:
        counters = await work()
    except Exception as exc:  # noqa: BLE001 - batch boundary records sanitized failure
        return await batch_repo.mark_batch_failed(
            connection,
            log_id=str(log["id"]),
            rows=BatchCounters(rows_failed=1).as_dict(),
            error_message=redact_secret_text(summarize_db_error(str(exc))),
        )
    finally:
        release_lock(redis_client, lock)

    done = await batch_repo.mark_batch_done(
        connection, log_id=str(log["id"]), rows=counters.as_dict()
    )
    await persist_batch_provider_evidence(
        connection,
        batch_job_log_id=str(done["id"]),
        evidences=counters.provider_evidence,
    )
    return done


async def publish_batch_status(redis_client: Any, payload: dict[str, Any]) -> int:
    """Publish a batch status event for realtime fanout."""

    return int(redis_client.publish("harness:events:batch_status_change", payload_to_json(payload)))


def payload_to_json(payload: dict[str, Any]) -> str:
    """Serialize a small event payload without custom encoders."""

    import json

    return json.dumps(payload, ensure_ascii=False, default=str)
