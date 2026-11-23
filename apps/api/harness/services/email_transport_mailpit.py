"""Mailpit sandbox SMTP transport — the only permitted send path in PoC.

ADR-002: only `mailpit` transport accepted; any other value fails closed.
Recipient allowlist enforced server-side (synthetic @example.invalid only).
aiosmtplib not installed; uses asyncio.to_thread + stdlib smtplib.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any

from apps.api.harness.core.logging import redact_secret_text

# Synthetic recipient allowlist — server-side enforced (ADR-002 §Synthetic Recipient Allowlist).
SYNTHETIC_RECIPIENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^[^@]+@example\.invalid$", re.IGNORECASE),
    re.compile(r"^syn-[a-z]+-\d{1,4}@example\.invalid$", re.IGNORECASE),
)

# Closed taxonomy of failure reason codes (ADR-002 §State Machine).
FAILURE_TRANSPORT_DISALLOWED = "transport_disallowed"
FAILURE_TRANSPORT_UNREACHABLE = "transport_unreachable"
FAILURE_RECIPIENT_NOT_SYNTHETIC = "recipient_not_synthetic"
FAILURE_INTERNAL_ERROR = "internal_error"


class MailpitTransportError(RuntimeError):
    """Raised when Mailpit delivery fails; carries a safe failure_reason_code."""

    failure_reason_code: str

    def __init__(self, message: str, failure_reason_code: str) -> None:
        super().__init__(message)
        self.failure_reason_code = failure_reason_code


@dataclass(frozen=True)
class MailpitDeliveryResult:
    """Safe delivery metadata recorded in email_drafts and audit_logs."""

    transport_message_id: str  # SHA-256 hash of the SMTP Message-ID
    recipient_hash: str        # SHA-256 hash of the synthetic recipient
    mailpit_host: str
    mailpit_port: int

    def as_audit_detail(self) -> dict[str, object]:
        return {
            "transport": "mailpit",
            "transport_message_id": self.transport_message_id,
            "recipient_hash": self.recipient_hash,
            "mailpit_host": self.mailpit_host,
            "mailpit_port": self.mailpit_port,
        }


def _sha256_truncated(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:length]


def _is_synthetic_recipient(address: str) -> bool:
    """Return True when address matches the server-side synthetic allowlist."""
    return any(pattern.match(address.strip()) for pattern in SYNTHETIC_RECIPIENT_PATTERNS)


def _smtp_send_sync(
    *,
    host: str,
    port: int,
    auth_user: str | None,
    auth_password: str | None,
    from_addr: str,
    from_name: str,
    to_addr: str,
    subject: str,
    body: str,
    timeout: float,
) -> str:
    """Blocking SMTP send to Mailpit; returns the Message-ID string."""
    msg = EmailMessage()
    msg["From"] = formataddr((from_name, from_addr))
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=host)
    msg.set_content(body)

    # Mailpit runs plain SMTP on port 1025 — no STARTTLS, optional auth.
    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        if auth_user and auth_password:
            _ = smtp.login(auth_user, auth_password)
        _ = smtp.send_message(msg)

    message_id = msg["Message-ID"]
    return str(message_id) if message_id else make_msgid()


def _require_mailpit_transport(transport: str) -> None:
    """Fail closed if transport is anything other than 'mailpit'."""
    if transport.strip().lower() != "mailpit":
        raise MailpitTransportError(
            f"transport '{transport}' is not allowed in PoC; only 'mailpit' is accepted",
            FAILURE_TRANSPORT_DISALLOWED,
        )


async def send_via_mailpit(
    *,
    transport: str,
    mailpit_host: str,
    mailpit_port: int,
    mailpit_auth_user: str | None,
    mailpit_auth_password: str | None,
    sender_email: str,
    sender_name: str,
    recipient: str,
    subject: str,
    body: str,
    timeout: float = 10.0,
    sandbox_guardrail_enabled: bool = True,
) -> MailpitDeliveryResult:
    """Send one approved email draft via Mailpit; never simulate success.

    Args:
        sandbox_guardrail_enabled: When True (default) the synthetic-recipient
            allowlist is enforced server-side (``@example.invalid`` only). When
            False the guardrail is bypassed so production-intended recipients
            in ``TEST_RECIPIENT_EMAIL`` (e.g. a real address) can be delivered
            through the Mailpit sandbox. Toggled by follow-up cycle B2 via
            ``EMAIL_SANDBOX_GUARDRAIL_ENABLED`` env flag.

    Raises:
        MailpitTransportError: for any delivery failure with a closed failure_reason_code.
    """
    _require_mailpit_transport(transport)

    if sandbox_guardrail_enabled and not _is_synthetic_recipient(recipient):
        raise MailpitTransportError(
            f"recipient domain is not on the synthetic allowlist",
            FAILURE_RECIPIENT_NOT_SYNTHETIC,
        )

    try:
        message_id = await asyncio.to_thread(
            _smtp_send_sync,
            host=mailpit_host,
            port=mailpit_port,
            auth_user=mailpit_auth_user,
            auth_password=mailpit_auth_password,
            from_addr=sender_email,
            from_name=sender_name,
            to_addr=recipient,
            subject=subject,
            body=body,
            timeout=timeout,
        )
    except MailpitTransportError:
        raise
    except OSError as exc:
        safe = redact_secret_text(str(exc))
        raise MailpitTransportError(
            f"Mailpit unreachable: {safe}",
            FAILURE_TRANSPORT_UNREACHABLE,
        ) from exc
    except Exception as exc:  # noqa: BLE001 - boundary must redact provider errors
        safe = redact_secret_text(str(exc))
        raise MailpitTransportError(
            f"SMTP error: {safe}",
            FAILURE_INTERNAL_ERROR,
        ) from exc

    return MailpitDeliveryResult(
        transport_message_id=_sha256_truncated(message_id, 32),
        recipient_hash=_sha256_truncated(recipient, 16),
        mailpit_host=mailpit_host,
        mailpit_port=mailpit_port,
    )
