"""Identity comparison helper — UUID coercion-safe same_actor predicate.

The wmah PoC mixes ``str`` and ``uuid.UUID`` representations of actor ids on
either side of the asyncpg boundary: ``actor.employee_id`` is plain ``str``
(parsed from the JWT subject), while asyncpg returns identifier columns as
``uuid.UUID``. A naive ``actor_id == other_id`` comparison therefore returns
``False`` even when both sides represent the same employee, which is what
silently broke the v3 B5 same-actor audit emit before the inline ``str()``
fix at ``routers/consultations.py:108``.

This helper centralizes the coercion + None-handling so future emit sites
(svc-viability-v4 I1 kyc_edd, I2 house_views, I3 disputes, I4 consultations
preventive) cannot regress.
"""

from __future__ import annotations

import uuid


def same_actor(
    actor_id: str | uuid.UUID | None,
    other_id: str | uuid.UUID | None,
) -> bool:
    """Return True iff both identifiers compare equal after ``str`` coercion.

    Either operand being ``None`` returns ``False`` — there is no actor to
    compare against. This is the intentional sentinel that suppresses the
    same-actor audit emit on the very first ``previous_actor_id IS NULL``
    invocation (per ADR-017).
    """

    if actor_id is None or other_id is None:
        return False
    return str(actor_id) == str(other_id)
