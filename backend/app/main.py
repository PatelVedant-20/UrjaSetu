"""UrjaSetu backend application entrypoint.

Wires the Phase 0 chain:

    FastAPI -> configuration -> SQLAlchemy session -> PostgreSQL

Business logic does not live here. This module only composes the application
(docs/00_PROJECT_BIBLE.md: API-first backend).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.adapters.forecast import register_default_providers
from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.api.ws import router as ws_router
from app.core.config import get_settings
from app.core.errors import DatabaseUnavailableError, register_exception_handlers
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.db.session import check_database_connection, dispose_engine
from app.services.forecast_registry import available_providers

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown.

    Startup probes PostgreSQL and logs the result but does NOT abort on
    failure. A database that is slow to come up must not put the API into a
    crash-restart loop; `GET /health/ready` is the endpoint that reports the
    dependency as unavailable (docs/00_PROJECT_BIBLE.md: reliability).
    """
    settings = get_settings()
    logger.info(
        "Starting %s v%s (env=%s)", settings.app_name, settings.app_version, settings.app_env
    )

    try:
        latency_ms = check_database_connection()
        logger.info(
            "Database connection verified in %.2f ms (%s)",
            latency_ms,
            settings.safe_database_url(),
        )
    except DatabaseUnavailableError:
        logger.error(
            "Database unreachable at startup (%s). The API will start, but "
            "/health/ready will report not_ready until PostgreSQL is available.",
            settings.safe_database_url(),
        )

    worker = None
    if settings.simulation_worker_enabled and settings.app_env == "development":
        from app.services.workspace_worker import run_worker

        worker = asyncio.create_task(run_worker())
    yield
    if worker:
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker

    dispose_engine()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Application factory.

    A factory rather than a module-level singleton so tests can build an app
    against their own configuration.
    """
    settings = get_settings()
    configure_logging()

    # Bind provider names to implementations as part of wiring the app, so a
    # request can never arrive before the registry is populated. Explicit
    # rather than an import side effect, which keeps startup order visible.
    register_default_providers(replace=True)
    logger.info("Forecast providers registered: %s", ", ".join(available_providers()))

    # OpenAPI/Swagger is exposed outside production only.
    expose_docs = settings.app_env in ("development", "test")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="UrjaSetu — grid-aware local renewable-energy marketplace API.",
        lifespan=lifespan,
        docs_url="/docs" if expose_docs else None,
        redoc_url="/redoc" if expose_docs else None,
        openapi_url="/openapi.json" if expose_docs else None,
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Attach a request id to every request, log line and error envelope.

        An inbound `X-Request-ID` is honoured so a correlation id survives
        across service hops.
        """
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    register_exception_handlers(app)
    attempts: dict[str, list[float]] = {}

    @app.middleware("http")
    async def protect(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Legacy phase endpoints are operator-only; browser writes require a custom header.

        The explicit test-only compatibility switch cannot disable security in development
        or production. New workspace endpoints always enforce their session dependencies.
        """
        legacy_test = settings.app_env == "test" and settings.allow_legacy_test_api
        path = request.url.path
        if not legacy_test and path.startswith("/api/v1"):
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("origin")
                if request.headers.get("X-Requested-With") != "UrjaSetu" or (
                    origin
                    and origin not in settings.cors_allowed_origins
                    and origin.split("://", 1)[-1] != request.headers.get("host")
                ):
                    return JSONResponse(
                        {"detail": "Request origin could not be verified."}, status_code=403
                    )
            if path.startswith("/api/v1/auth/") and request.method == "POST":
                key = request.client.host if request.client else "unknown"
                recent = [t for t in attempts.get(key, []) if time.monotonic() - t < 60]
                if len(recent) >= 20:
                    return JSONResponse(
                        {"detail": "Too many attempts. Try again in a minute."}, status_code=429
                    )
                attempts[key] = recent + [time.monotonic()]
            if (
                not path.startswith(("/api/v1/auth/", "/api/v1/workspace"))
                and path != "/api/v1/meta"
            ):
                if request.method not in ("GET", "HEAD", "OPTIONS"):
                    return JSONResponse(
                        {"detail": "Legacy write retired. Use the connected workspace workflow."},
                        status_code=410,
                    )
                from app.db.session import get_session_factory
                from app.services.auth_service import COOKIE, resolve

                def is_operator() -> bool:
                    with get_session_factory()() as db:
                        actor = resolve(db, request.cookies.get(COOKIE))
                        return bool(actor and actor.role.value in ("operator", "admin"))

                if not await asyncio.to_thread(is_operator):
                    return JSONResponse(
                        {"detail": "Use the authenticated workspace API."}, status_code=403
                    )
        return await call_next(request)

    # Browsers refuse a credentialed request to an origin answered with "*",
    # so the allowed origins are enumerated and credentials are permitted.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    # Health probes and the realtime gateway sit at the root, as
    # docs/05_API_SPEC.md writes them; versioned resources under the v1 prefix.
    app.include_router(health_router)
    app.include_router(ws_router)
    from app.api.workspace_ws import router as workspace_ws

    app.include_router(workspace_ws)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
