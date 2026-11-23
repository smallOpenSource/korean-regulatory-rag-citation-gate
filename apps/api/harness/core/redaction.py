"""Python logging filter for PII and secret redaction (REG-05 T288).

Mask format: ``***REDACTED***`` — no length information is leaked.

Sensitive keys masked (exact match or glob pattern):
    Authorization, Cookie, Set-Cookie, access_token, refresh_token,
    harness_refresh_token, password, passwd, client_secret, smtp_pass,
    azure_api_key, broker_app_secret, *_api_key, *_secret, *_token

Apply globally by calling ``configure_logging_redaction()`` once at app startup.
"""

from __future__ import annotations

import logging
import re
from typing import Any

_REDACTED = "***REDACTED***"

# Keys whose *values* must always be masked (exact name, case-insensitive)
_EXACT_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "authorization",
        "cookie",
        "set-cookie",
        "access_token",
        "refresh_token",
        "harness_refresh_token",
        "password",
        "passwd",
        "client_secret",
        "smtp_pass",
        "azure_api_key",
        "broker_app_secret",
    }
)

# Suffix patterns that mark a key as sensitive regardless of prefix
_SENSITIVE_SUFFIXES: tuple[str, ...] = ("_api_key", "_secret", "_token")

# Regex for Bearer tokens and query-param secrets in free-form strings
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=\-]+")
_PARAM_RE = re.compile(
    r"(?i)([?&](?:api_key|auth_key|service_key|token)=)[^&\s]+"
)


def _is_sensitive_key(key: str) -> bool:
    lower = key.lower()
    if lower in _EXACT_SENSITIVE_KEYS:
        return True
    return any(lower.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES)


def _redact_string(value: str) -> str:
    """Remove Bearer tokens and query-param secrets from free-form text."""
    value = _BEARER_RE.sub(lambda m: f"{m.group(1)}{_REDACTED}", value)
    value = _PARAM_RE.sub(lambda m: f"{m.group(1)}{_REDACTED}", value)
    return value


def _redact_value(key: str, value: Any) -> Any:
    if _is_sensitive_key(key):
        return _REDACTED
    if isinstance(value, str):
        return _redact_string(value)
    return value


class SecretRedactionFilter(logging.Filter):
    """Mask secrets and PII in all log records passing through this filter.

    Applies to ``record.msg`` (free-form text) and ``record.args`` (key→value
    dicts or positional tuples used in %-style formatting).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_string(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: _redact_value(k, v) for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _redact_string(a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True


def configure_logging_redaction() -> None:
    """Install ``SecretRedactionFilter`` on the root logger (idempotent).

    Call once at application startup before any request is processed.
    The filter propagates to all child loggers automatically.
    """
    root = logging.getLogger()
    if any(isinstance(f, SecretRedactionFilter) for f in root.filters):
        return  # already installed
    root.addFilter(SecretRedactionFilter())
