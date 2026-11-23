"""Authentication primitives without external JWT/password dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Any

JWT_ALG = "HS256"
JWT_TYPE = "JWT"
PASSWORD_ALG = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 210_000
SALT_BYTES = 16

# RFC 8725 — JWT BCP controls
JWT_ALG_ALLOWLIST: frozenset[str] = frozenset({"HS256", "RS256", "ES256"})
JWT_ISSUER = "harness-poc"
JWT_AUDIENCE = "harness-web"
CLOCK_SKEW_SECONDS = 60


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _json_dumps(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def create_access_token(
    *,
    subject: str,
    secret: str,
    expires_in_seconds: int,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a compact HMAC-SHA256 JWT access token (RFC 8725 compliant).

    Standard BCP claims added automatically: iss, aud, nbf (now - clock_skew), jti (UUID4).
    Callers may override jti by including it in extra_claims.
    """
    if not secret:
        raise ValueError("JWT secret is required")
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": subject,
        "iat": now,
        "nbf": now - CLOCK_SKEW_SECONDS,
        "exp": now + expires_in_seconds,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    header = {"alg": JWT_ALG, "typ": JWT_TYPE}
    signing_input = b".".join(
        (
            _b64url_encode(_json_dumps(header)).encode(),
            _b64url_encode(_json_dumps(payload)).encode(),
        )
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{signing_input.decode()}.{_b64url_encode(signature)}"


def decode_token(token: str, *, secret: str, verify_exp: bool = True) -> dict[str, Any]:
    """Validate and decode a HMAC-SHA256 JWT (RFC 8725 alg-allowlist enforced).

    Clock skew: exp is accepted up to CLOCK_SKEW_SECONDS past declared expiry;
    nbf is accepted up to CLOCK_SKEW_SECONDS before declared not-before time.
    """
    if not secret:
        raise ValueError("JWT secret is required")
    try:
        encoded_header, encoded_payload, encoded_signature = token.split(".")
    except ValueError as exc:
        raise ValueError("Malformed token") from exc

    header = json.loads(_b64url_decode(encoded_header))
    alg = header.get("alg", "")
    if alg not in JWT_ALG_ALLOWLIST:
        # Explicitly reject alg=none, alg=HS512, and any other non-allowlisted algorithm
        raise ValueError(f"Rejected token algorithm: {alg!r}")
    if alg != JWT_ALG:
        # Allowlisted but not implemented (RS256/ES256 require asymmetric keys)
        raise ValueError(f"Unsupported token algorithm: {alg!r}")

    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual = _b64url_decode(encoded_signature)
    if not hmac.compare_digest(expected, actual):
        raise ValueError("Invalid token signature")

    payload = json.loads(_b64url_decode(encoded_payload))

    # RFC 8725 §3.1/§3.7/§3.10 — validate iss, aud, jti presence (T282)
    issuer = payload.get("iss")
    if issuer != JWT_ISSUER:
        raise ValueError(f"Rejected token issuer: {issuer!r}")
    audience = payload.get("aud")
    if audience != JWT_AUDIENCE:
        raise ValueError(f"Rejected token audience: {audience!r}")
    if not payload.get("jti"):
        raise ValueError("Token missing jti claim")

    now = int(time.time())
    if verify_exp and payload.get("exp", 0) + CLOCK_SKEW_SECONDS < now:
        raise ValueError("Token expired")
    if "nbf" in payload and payload["nbf"] - CLOCK_SKEW_SECONDS > now:
        raise ValueError("Token not yet valid")
    return payload


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256."""

    if not password:
        raise ValueError("Password is required")
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{PASSWORD_ALG}${PBKDF2_ITERATIONS}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a PBKDF2 password hash."""

    try:
        algorithm, iterations_text, salt_text, digest_text = password_hash.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False
    if algorithm != PASSWORD_ALG:
        return False
    salt = _b64url_decode(salt_text)
    expected = _b64url_decode(digest_text)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(expected, actual)
