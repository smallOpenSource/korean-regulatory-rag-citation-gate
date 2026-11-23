"""SMTP-backed email delivery helpers with fail-closed safety gates."""

from __future__ import annotations

import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

from apps.api.harness.core.config import EmailConfig
from apps.api.harness.core.logging import redact_secret_text

RESIDENT_REGISTRATION_RE = re.compile(r"\b\d{6}-\d{7}\b")
ACCOUNT_LIKE_RE = re.compile(r"\b\d{2,6}[- ]?\d{2,6}[- ]?\d{2,8}\b")
SECRET_WORD_RE = re.compile(
    r"\b(password|passwd|secret|bearer\s+[a-z0-9._~+/=-]+|api[_ -]?key|smtp[_ -]?password)\b",
    re.IGNORECASE,
)


class EmailContentRejectedError(ValueError):
    """Raised when draft content violates the outbound email safety contract."""


class EmailDeliveryBlockedError(RuntimeError):
    """Raised when real SMTP delivery cannot safely run."""


@dataclass(frozen=True)
class EmailDeliveryResult:
    """Sanitized SMTP delivery metadata safe for audit detail JSON."""

    provider_code: str
    recipient_configured: bool
    smtp_host_configured: bool
    message_id_present: bool

    def as_audit_detail(self) -> dict[str, Any]:
        return {
            "provider_code": self.provider_code,
            "recipient_configured": self.recipient_configured,
            "smtp_host_configured": self.smtp_host_configured,
            "message_id_present": self.message_id_present,
        }


def validate_display_safe_email_content(subject: str, body: str) -> None:
    """Reject high-risk identifiers and secret fragments before persistence/send."""

    content = f"{subject}\n{body}"
    if RESIDENT_REGISTRATION_RE.search(content):
        raise EmailContentRejectedError("email content contains resident-registration-like number")
    if ACCOUNT_LIKE_RE.search(content):
        raise EmailContentRejectedError("email content contains account-number-like sequence")
    if SECRET_WORD_RE.search(content):
        raise EmailContentRejectedError("email content contains secret-like text")


def _require_smtp_config(config: EmailConfig) -> None:
    if not config.send_enabled:
        raise EmailDeliveryBlockedError("HARNESS_EMAIL_SEND_ENABLED is not true")
    missing = [
        name
        for name, value in {
            "SMTP_HOST": config.smtp_host,
            "SMTP_USER": config.smtp_user,
            "SMTP_PASSWORD": config.smtp_password,
            "SMTP_SENDER_EMAIL": config.sender_email,
            "TEST_RECIPIENT_EMAIL": config.test_recipient_email,
        }.items()
        if not value
    ]
    if missing:
        raise EmailDeliveryBlockedError("missing SMTP configuration: " + ", ".join(missing))


def send_email_draft(
    config: EmailConfig,
    *,
    subject: str,
    body: str,
) -> EmailDeliveryResult:
    """Send one approved draft through configured SMTP; never simulate success."""

    validate_display_safe_email_content(subject, body)
    _require_smtp_config(config)
    sender_email = str(config.sender_email)
    sender_name = config.sender_name or "Harness"
    recipient = str(config.test_recipient_email)

    message = EmailMessage()
    message["From"] = formataddr((sender_name, sender_email))
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(
            str(config.smtp_host),
            int(config.smtp_port),
            timeout=float(config.timeout_seconds),
        ) as smtp:
            smtp.starttls()
            smtp.login(str(config.smtp_user), str(config.smtp_password))
            smtp.send_message(message)
    except Exception as exc:  # noqa: BLE001 - boundary must redact provider errors
        raise EmailDeliveryBlockedError(redact_secret_text(str(exc))) from exc

    return EmailDeliveryResult(
        provider_code="SMTP",
        recipient_configured=True,
        smtp_host_configured=True,
        message_id_present=bool(message.get("Message-ID")),
    )
