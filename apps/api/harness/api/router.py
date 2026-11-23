"""Top-level API router."""

from __future__ import annotations


def build_api_router():
    """Build and return the versionless Harness API router."""

    from fastapi import APIRouter

    from .routers import (
        ai,
        audit,
        auth,
        batch,
        conflict_of_interest,
        consents,
        consultation_gates,
        consultations,
        customers,
        dashboard,
        data_governance,
        disputes,
        email,
        house_views,
        kyc_edd,
        marketing_review,
        nba,
        realtime,
        rights_notice,
        simulations,
        websocket,
    )

    router = APIRouter()
    router.include_router(auth.router)
    router.include_router(ai.router)
    router.include_router(customers.router)
    router.include_router(dashboard.router)
    router.include_router(consultations.router)
    router.include_router(consultation_gates.router)
    router.include_router(consents.router)
    router.include_router(email.router)
    router.include_router(house_views.router)
    router.include_router(nba.router)
    router.include_router(kyc_edd.router)
    router.include_router(conflict_of_interest.router)
    router.include_router(marketing_review.router)
    router.include_router(rights_notice.router)
    router.include_router(disputes.router)
    router.include_router(simulations.router)
    router.include_router(realtime.router)
    router.include_router(websocket.router)
    router.include_router(batch.router)
    router.include_router(audit.router)
    router.include_router(data_governance.router)
    return router
