"""Authentication business-logic helpers (REG-05 T281 password policy)."""

from __future__ import annotations

_MIN_PASSWORD_LENGTH = 12


def validate_password_policy(password: str) -> list[str]:
    """Return a list of policy violations. Empty list means the password is compliant.

    Policy (ASVS V2.1 / REG-05 T281):
    - Minimum length: 12 characters
    - No complexity requirements enforced (length-only rule per ASVS V2.1.1)
    """
    violations: list[str] = []
    if len(password) < _MIN_PASSWORD_LENGTH:
        violations.append(
            f"Password must be at least {_MIN_PASSWORD_LENGTH} characters long"
        )
    return violations
