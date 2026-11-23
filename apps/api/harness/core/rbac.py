"""Role and row-level authorization helpers."""

from __future__ import annotations

from dataclasses import dataclass

ROLE_CODES: tuple[str, ...] = (
    "PB",
    "WM",
    "BRANCH_MANAGER",
    "ADMIN",
    "AUDIT_VIEWER",
    "COMPLIANCE_OFFICER",
)


@dataclass(frozen=True)
class ActorContext:
    """Authenticated employee context used for row-level filtering."""

    employee_id: str
    role_code: str
    branch_id: str | None = None

    def __post_init__(self) -> None:
        if self.role_code not in ROLE_CODES:
            raise ValueError(f"Unknown role_code: {self.role_code}")


def can_read_audit_logs(actor: ActorContext) -> bool:
    """ADMIN, AUDIT_VIEWER, and COMPLIANCE_OFFICER can read audit logs (read-only oversight)."""

    return actor.role_code in {"ADMIN", "AUDIT_VIEWER", "COMPLIANCE_OFFICER"}


def can_access_customer(actor: ActorContext, customer: dict[str, str | None]) -> bool:
    """Apply documented row-level access rules to an in-memory customer row."""

    if actor.role_code == "ADMIN":
        return True
    if actor.role_code == "AUDIT_VIEWER":
        return False
    if actor.role_code == "PB":
        return customer.get("assigned_pb_id") == actor.employee_id
    if actor.role_code in {"WM", "BRANCH_MANAGER"}:
        return bool(actor.branch_id) and customer.get("branch_id") == actor.branch_id
    return False


def customer_scope_predicate(
    actor: ActorContext, *, alias: str = "c"
) -> tuple[str, tuple[str, ...]]:
    """Return a raw-SQL predicate and positional params for customer scoping.

    The returned fragment is not a standalone statement, so it intentionally does
    not contain a ``sql_id``. Repository functions must wrap it in statements
    that do start with a ``sql_id`` comment.
    """

    if actor.role_code == "ADMIN":
        return "TRUE", ()
    if actor.role_code == "AUDIT_VIEWER":
        return "FALSE", ()
    if actor.role_code == "PB":
        return f"{alias}.assigned_pb_id = $1", (actor.employee_id,)
    if actor.role_code in {"WM", "BRANCH_MANAGER"}:
        if not actor.branch_id:
            return "FALSE", ()
        return f"{alias}.branch_id = $1", (actor.branch_id,)
    return "FALSE", ()
