"""UrjaSetu backend application entrypoint.

Wires the Phase 0 chain:

    FastAPI -> configuration -> SQLAlchemy session -> PostgreSQL

Business logic does not live here. This module only composes the application
(docs/00_PROJECT_BIBLE.md: API-first backend).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from app.api.v1.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import DatabaseUnavailableError, register_exception_handlers
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.db.session import check_database_connection, dispose_engine

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

    yield

    dispose_engine()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Application factory.

    A factory rather than a module-level singleton so tests can build an app
    against their own configuration.
    """
    settings = get_settings()
    configure_logging()

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

    # Health probes sit at the root; versioned resources under the v1 prefix.
    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
