"""KOFIA 디지털 권유 본인확인 + chat log/녹취 메타 저장 (T236).

Records the metadata schema and verification-step structure required by
the 금융투자협회 (KOFIA) digital-solicitation compliance guideline. The
actual identity verification (Korean ID document scan, biometric prompt)
and recording capture (chat transport, audio capture) live in upstream
clients; this module enforces the canonical metadata shape stored in
audit_logs / consultation_artifacts so downstream review and KOFIA
sample-audit produces a complete trail.

Verification step methods covered:
  - id_document     — 신분증 사본 + OCR
  - mobile_otp      — 본인 명의 휴대전화 OTP
  - bank_account    — 본인 명의 계좌 1원 인증
  - facial_match    — selfie ↔ ID photo biometric match
  - signature       — 전자서명 (PKI)

Conversation channel kinds:
  - chat            — text chat log (turns + timestamps)
  - voice           — recorded audio (transcript + sha256)
  - video           — recorded video (transcript + sha256)
"""

from __future__ import annotations

from datetime import UTC, datetime

VERIFICATION_METHODS: frozenset[str] = frozenset({
    "id_document",
    "mobile_otp",
    "bank_account",
    "facial_match",
    "signature",
})

CHANNEL_KINDS: frozenset[str] = frozenset({"chat", "voice", "video"})


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_verification_step(
    method: str,
    *,
    employee_id: str,
    customer_id: str,
    succeeded: bool,
    evidence_ref: str = "",
    failure_reason: str = "",
    captured_at: str | None = None,
) -> dict[str, object]:
    """Construct one KOFIA identity-verification step record.

    `evidence_ref` is an opaque pointer (file path, document_chunks.id,
    audit row id, etc.) the verifier writes for later audit retrieval.
    `failure_reason` should be a short closed-set code (e.g.
    `OCR_LOW_CONFIDENCE`, `OTP_TIMEOUT`) rather than free text — caller's
    responsibility to constrain.
    """
    if method not in VERIFICATION_METHODS:
        raise ValueError(f"unknown verification method: {method!r}")
    if not employee_id or not customer_id:
        raise ValueError("employee_id and customer_id are required")
    return {
        "method": method,
        "employee_id": employee_id,
        "customer_id": customer_id,
        "succeeded": bool(succeeded),
        "evidence_ref": evidence_ref,
        "failure_reason": failure_reason if not succeeded else "",
        "captured_at": captured_at or _utc_now_iso(),
        "audit_action_code": (
            "kofia_identity_verified" if succeeded else "kofia_identity_verification_failed"
        ),
    }


def build_chat_log_meta(
    *,
    consultation_id: str,
    channel_kind: str,
    transport: str,
    turn_count: int,
    transcript_sha256: str,
    duration_seconds: int = 0,
    recorded_at: str | None = None,
) -> dict[str, object]:
    """Construct KOFIA chat/recording metadata for one consultation channel.

    `transport` is e.g. `internal_chat`, `mailpit_sandbox`, `voip_sandbox`.
    `transcript_sha256` MUST be hex-encoded SHA-256 of the canonical
    transcript text the chat/voice client persists (idempotent hash for
    later integrity verification).
    """
    if channel_kind not in CHANNEL_KINDS:
        raise ValueError(f"unknown channel_kind: {channel_kind!r}")
    if not consultation_id:
        raise ValueError("consultation_id is required")
    if not transport:
        raise ValueError("transport is required")
    if turn_count < 0:
        raise ValueError("turn_count must be >= 0")
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be >= 0")
    if len(transcript_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in transcript_sha256.lower()
    ):
        raise ValueError("transcript_sha256 must be 64-char lowercase hex")
    return {
        "consultation_id": consultation_id,
        "channel_kind": channel_kind,
        "transport": transport,
        "turn_count": int(turn_count),
        "duration_seconds": int(duration_seconds),
        "transcript_sha256": transcript_sha256.lower(),
        "recorded_at": recorded_at or _utc_now_iso(),
        "audit_action_code": "kofia_chat_log_recorded",
    }


def compose_kofia_record(
    verifications: list[dict[str, object]],
    chat_logs: list[dict[str, object]],
) -> dict[str, object]:
    """Combine verification steps + chat logs into a single KOFIA record.

    Returns:
        verifications: list (passed-through, order preserved)
        chat_logs: list (passed-through)
        verifications_passed: int
        verifications_failed: int
        chat_log_count: int
        compliant: bool — True iff ≥1 successful verification + ≥1 chat log
    """
    if not isinstance(verifications, list) or not isinstance(chat_logs, list):
        raise TypeError("verifications and chat_logs must be lists")

    passed = sum(1 for v in verifications if v.get("succeeded") is True)
    failed = sum(1 for v in verifications if v.get("succeeded") is False)
    chat_log_count = len(chat_logs)
    compliant = passed >= 1 and chat_log_count >= 1

    return {
        "verifications": verifications,
        "chat_logs": chat_logs,
        "verifications_passed": passed,
        "verifications_failed": failed,
        "chat_log_count": chat_log_count,
        "compliant": compliant,
        "audit_action_code": "kofia_record_composed",
    }
