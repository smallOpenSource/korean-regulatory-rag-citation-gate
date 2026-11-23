"""FastAPI application factory for Harness."""

from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from typing import Any

from .api.router import build_api_router
from .api.routers import realtime
from .core.config import default_env_path, load_config
from .core.db import create_pool
from .core.logging import redact_secret_text
from .core.middleware import register_security_middleware
from .core.redis_client import create_async_redis_client, create_redis_client
from .services.ai_jobs_worker import worker_loop as ai_jobs_worker_loop


def create_app():
    """Create the API app with DB-backed routes and safe diagnostics."""

    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:  # pragma: no cover - startup dependency check covers this
        raise RuntimeError("fastapi is required to create the Harness API app") from exc

    startup_config = load_config(default_env_path())

    # svc-viability-v4 I7 (ADR-019.1) — production safety check.
    # AI_COMPLIANCE_MODE must be "live" (or unset, which defaults to "live")
    # in production. A non-live mode here would let the marketing 4-eye gate
    # be exercised without a real Azure call, which is unacceptable for the
    # regulatory contract once the PoC is promoted. Raise loudly at startup
    # so a misconfigured deploy fails immediately instead of silently
    # bypassing the compliance gate.
    _ai_mode = os.getenv("AI_COMPLIANCE_MODE", "live").strip() or "live"
    if _ai_mode != "live" and startup_config.runtime.app_env == "production":
        raise RuntimeError(
            f"AI_COMPLIANCE_MODE must be 'live' in production "
            f"(app_env={startup_config.runtime.app_env!r}, got mode={_ai_mode!r}). "
            f"See ADR-019.1 §Production safety."
        )

    @asynccontextmanager
    async def lifespan(app: Any):
        config = startup_config
        pool = await create_pool(config.database)
        redis_client = None
        realtime_stop = asyncio.Event()
        realtime_task: asyncio.Task[None] | None = None
        ai_jobs_stop = asyncio.Event()
        ai_jobs_task: asyncio.Task[None] | None = None
        app.state.config = config
        app.state.pool = pool
        async_redis_client = None
        try:
            try:
                redis_client = create_redis_client(config.redis)
                app.state.redis_client = redis_client
                async_redis_client = create_async_redis_client(config.redis)
                app.state.async_redis_client = async_redis_client
                realtime_task = asyncio.create_task(
                    realtime.redis_fanout_loop(
                        redis_client=redis_client,
                        pool=pool,
                        stop_event=realtime_stop,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - API can still serve polling when Redis is down
                app.state.redis_client = None
                app.state.async_redis_client = None
                app.state.realtime_startup_error = redact_secret_text(str(exc))
            # In-process AI job worker (UltraQA cycle 17 S35) — shares
            # RealtimeConnectionManager singleton so ai_job_done broadcasts
            # reach the same WebSocket subscribers the API process serves.
            ai_jobs_task = asyncio.create_task(
                ai_jobs_worker_loop(
                    pool,
                    manager=realtime.manager,
                    stop_event=ai_jobs_stop,
                )
            )
            yield
        finally:
            realtime_stop.set()
            ai_jobs_stop.set()
            if realtime_task is not None:
                realtime_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await realtime_task
            if ai_jobs_task is not None:
                ai_jobs_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await ai_jobs_task
            if redis_client is not None:
                with contextlib.suppress(Exception):
                    redis_client.close()
            if async_redis_client is not None:
                with contextlib.suppress(Exception):
                    await async_redis_client.aclose()
            await pool.close()

    app = FastAPI(title="Harness Internal API", version="0.1.0", lifespan=lifespan)
    if startup_config.cors.enabled and startup_config.cors.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(startup_config.cors.allowed_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Accept", "Authorization", "Content-Type"],
        )
    app.include_router(build_api_router())

    # T284/T286/T288/T294 — security middleware + exception handlers
    # Called after CORSMiddleware so SecurityHeadersMiddleware wraps outermost.
    register_security_middleware(app, startup_config)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "harness-api"}

    @app.get("/health/config")
    async def config_health() -> dict[str, object]:
        config = getattr(app.state, "config", None) or load_config(default_env_path())
        return {"status": "ok", "config": config.safe_dict()}

    return app


app = create_app()
