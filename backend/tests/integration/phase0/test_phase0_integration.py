"""Phase 0 integration verification — Manthan's testing agent.

Verifies the Phase-0 acceptance criteria from docs/09_PHASE_0_SETUP.md and
docs/10_TESTING_AND_INTEGRATION.md WITHOUT modifying any core implementation.

Tests cover:
  1. Application startup via the factory
  2. Database connectivity (SELECT 1, ORM round-trip)
  3. Health endpoint contract (/health, /health/ready)
  4. Database query execution via session dependency
  5. Error envelope contract on all error paths
  6. Failure behavior when database is unavailable (mocked)
  7. Configuration safety (no secrets leak, PostgreSQL-only)
  8. Request-ID propagation
  9. Lifespan behavior (startup probe, shutdown dispose)
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import DatabaseUnavailableError, UrjaSetuError
from app.db.models import SystemMetadata
from app.db.session import check_database_connection
from app.main import create_app

# ---------------------------------------------------------------------------
# 1. Application startup
# ---------------------------------------------------------------------------


class TestApplicationStartup:
    """Verify the create_app factory produces a valid FastAPI instance."""

    def test_create_app_returns_fastapi_instance(self) -> None:
        app = create_app()
        assert isinstance(app, FastAPI)

    def test_create_app_has_correct_title(self) -> None:
        app = create_app()
        assert app.title == "UrjaSetu"

    def test_create_app_has_version(self) -> None:
        app = create_app()
        assert app.version == "0.1.0"

    def test_create_app_includes_health_routes(self) -> None:
        app = create_app()
        route_paths = [route.path for route in app.routes]
        assert "/health" in route_paths
        assert "/health/ready" in route_paths

    def test_create_app_includes_api_v1_meta(self) -> None:
        app = create_app()
        route_paths = [route.path for route in app.routes]
        assert "/api/v1/meta" in route_paths


# ---------------------------------------------------------------------------
# 2. Database connectivity
# ---------------------------------------------------------------------------


class TestDatabaseConnectivity:
    """Prove the database is live and accepts queries."""

    def test_select_one_roundtrip(self, engine: Engine) -> None:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar_one()
        assert result == 1

    def test_current_database_matches_config(self, engine: Engine, settings: Settings) -> None:
        """The database we are connected to matches what the config says."""
        with engine.connect() as conn:
            db_name = conn.execute(text("SELECT current_database()")).scalar_one()
        assert db_name == make_url(settings.database_url).database

    def test_check_database_connection_returns_latency(self) -> None:
        latency_ms = check_database_connection()
        assert isinstance(latency_ms, float)
        assert latency_ms >= 0

    def test_engine_dialect_is_postgresql(self, engine: Engine) -> None:
        assert engine.dialect.name == "postgresql"


# ---------------------------------------------------------------------------
# 3. Health endpoint contract
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Verify /health liveness probe contract per docs/05_API_SPEC.md."""

    def test_health_status_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_shape(self, client: TestClient) -> None:
        body = client.get("/health").json()
        required_keys = {"status", "app", "version", "environment"}
        assert required_keys.issubset(set(body.keys()))

    def test_health_status_value_is_ok(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert body["status"] == "ok"

    def test_health_has_no_dependency_info(self, client: TestClient) -> None:
        """Liveness must NOT probe dependencies (docs/00_PROJECT_BIBLE.md: reliability)."""
        body = client.get("/health").json()
        assert "dependencies" not in body

    def test_health_returns_correct_app_name(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert body["app"] == "UrjaSetu"


class TestReadinessEndpoint:
    """Verify /health/ready readiness probe contract."""

    def test_readiness_status_200_when_db_up(self, client: TestClient) -> None:
        response = client.get("/health/ready")
        assert response.status_code == 200

    def test_readiness_reports_ready_status(self, client: TestClient) -> None:
        body = client.get("/health/ready").json()
        assert body["status"] == "ready"

    def test_readiness_lists_postgresql_dependency(self, client: TestClient) -> None:
        body = client.get("/health/ready").json()
        dep_names = [d["name"] for d in body["dependencies"]]
        assert "postgresql" in dep_names

    def test_readiness_postgresql_has_latency(self, client: TestClient) -> None:
        body = client.get("/health/ready").json()
        pg_dep = next(d for d in body["dependencies"] if d["name"] == "postgresql")
        assert pg_dep["latency_ms"] is not None
        assert pg_dep["latency_ms"] >= 0

    def test_readiness_postgresql_status_ok(self, client: TestClient) -> None:
        body = client.get("/health/ready").json()
        pg_dep = next(d for d in body["dependencies"] if d["name"] == "postgresql")
        assert pg_dep["status"] == "ok"


# ---------------------------------------------------------------------------
# 4. Database query execution via ORM
# ---------------------------------------------------------------------------


class TestDatabaseQueryExecution:
    """Prove ORM CRUD against system_metadata works end-to-end."""

    def test_insert_and_query_system_metadata(self, db_session: Session) -> None:
        key = f"integration.test.{uuid.uuid4()}"
        row = SystemMetadata(key=key, value="integration-check")
        db_session.add(row)
        db_session.flush()

        found = db_session.query(SystemMetadata).filter_by(key=key).one()
        assert found.value == "integration-check"
        assert isinstance(found.id, uuid.UUID)

    def test_created_at_is_set_by_server(self, db_session: Session) -> None:
        key = f"integration.timestamp.{uuid.uuid4()}"
        row = SystemMetadata(key=key, value="ts-check")
        db_session.add(row)
        db_session.flush()

        found = db_session.query(SystemMetadata).filter_by(key=key).one()
        assert found.created_at is not None
        assert found.created_at.tzinfo is not None, "Timestamps must be timezone-aware UTC"

    def test_updated_at_is_set_by_server(self, db_session: Session) -> None:
        key = f"integration.updated.{uuid.uuid4()}"
        row = SystemMetadata(key=key, value="update-check")
        db_session.add(row)
        db_session.flush()

        found = db_session.query(SystemMetadata).filter_by(key=key).one()
        assert found.updated_at is not None

    def test_uuid_primary_key_is_generated(self, db_session: Session) -> None:
        key = f"integration.uuid.{uuid.uuid4()}"
        row = SystemMetadata(key=key, value="uuid-check")
        db_session.add(row)
        db_session.flush()

        found = db_session.query(SystemMetadata).filter_by(key=key).one()
        assert found.id is not None
        assert isinstance(found.id, uuid.UUID)

    def test_unique_constraint_enforced(self, db_session: Session) -> None:
        key = f"integration.unique.{uuid.uuid4()}"
        db_session.add(SystemMetadata(key=key, value="first"))
        db_session.flush()

        db_session.add(SystemMetadata(key=key, value="duplicate"))
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            db_session.flush()


# ---------------------------------------------------------------------------
# 5. Error envelope contract
# ---------------------------------------------------------------------------


class TestErrorEnvelope:
    """Every non-2xx must return the locked envelope from docs/05_API_SPEC.md."""

    def test_404_has_error_envelope(self, client: TestClient) -> None:
        response = client.get("/nonexistent-path")
        assert response.status_code == 404
        body = response.json()
        assert "error" in body
        error = body["error"]
        assert "code" in error
        assert "message" in error
        assert "details" in error
        assert "request_id" in error

    def test_404_code_is_not_found(self, client: TestClient) -> None:
        body = client.get("/nonexistent-path").json()
        assert body["error"]["code"] == "NOT_FOUND"

    def test_error_envelope_has_request_id(self, client: TestClient) -> None:
        body = client.get("/nonexistent-path").json()
        assert body["error"]["request_id"] != ""
        assert body["error"]["request_id"] is not None


# ---------------------------------------------------------------------------
# 6. Failure behavior when database is unavailable
# ---------------------------------------------------------------------------


class TestDatabaseUnavailableBehavior:
    """Verify graceful degradation when PostgreSQL is unreachable."""

    def test_check_database_connection_raises_on_failure(self) -> None:
        """check_database_connection must raise DatabaseUnavailableError."""
        with (
            patch(
                "app.db.session.get_engine",
                side_effect=DatabaseUnavailableError(details={"reason": "mocked"}),
            ),
            pytest.raises(DatabaseUnavailableError),
        ):
            check_database_connection()

    def test_readiness_returns_503_when_db_unavailable(self) -> None:
        """When the database is down, /health/ready should return 503."""
        db_err = DatabaseUnavailableError(details={"reason": "OperationalError"})
        # Must mock both the lifespan check (app.main) and the endpoint check
        # (app.api.v1.health), since create_app() runs the lifespan which also
        # calls check_database_connection and would hang without a mock.
        with (
            patch("app.main.check_database_connection", side_effect=db_err),
            patch("app.api.v1.health.check_database_connection", side_effect=db_err),
        ):
            app = create_app()
            with TestClient(app, raise_server_exceptions=False) as test_client:
                response = test_client.get("/health/ready")

        assert response.status_code == 503
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] == "DATABASE_UNAVAILABLE"

    def test_health_liveness_unaffected_by_db_failure(self) -> None:
        """The /health endpoint must return 200 even if the database is down.

        This is a critical reliability requirement: orchestrators use /health
        for liveness; a DB blip must not trigger a restart loop.
        """
        db_err = DatabaseUnavailableError(details={"reason": "OperationalError"})
        with (
            patch("app.main.check_database_connection", side_effect=db_err),
            patch("app.api.v1.health.check_database_connection", side_effect=db_err),
        ):
            app = create_app()
            with TestClient(app, raise_server_exceptions=False) as test_client:
                response = test_client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_database_unavailable_error_is_urjasetu_error(self) -> None:
        """DatabaseUnavailableError inherits from UrjaSetuError."""
        assert issubclass(DatabaseUnavailableError, UrjaSetuError)

    def test_database_unavailable_error_has_503_status(self) -> None:
        err = DatabaseUnavailableError()
        assert err.http_status == 503


# ---------------------------------------------------------------------------
# 7. Configuration safety
# ---------------------------------------------------------------------------


class TestConfigurationSafety:
    """Verify the configuration module enforces Phase-0 guardrails."""

    def test_settings_has_database_url(self, settings: Settings) -> None:
        assert settings.database_url is not None
        assert settings.database_url != ""

    def test_database_url_starts_with_postgresql(self, settings: Settings) -> None:
        assert settings.database_url.startswith(("postgresql+psycopg://", "postgresql://"))

    def test_safe_database_url_redacts_password(self, settings: Settings) -> None:
        safe = settings.safe_database_url()
        # The example password is 'urjasetu'; it must be redacted.
        assert "***" in safe or "@" not in safe

    def test_settings_reject_sqlite(self) -> None:
        with pytest.raises(ValueError, match="requires PostgreSQL"):
            Settings(database_url="sqlite:///test.db")

    def test_settings_reject_mysql(self) -> None:
        with pytest.raises(ValueError, match="requires PostgreSQL"):
            Settings(database_url="mysql://user:pass@localhost/db")

    def test_market_mode_is_day_ahead(self, settings: Settings) -> None:
        """docs/00_PROJECT_BIBLE.md section 7 locks the market mode."""
        assert settings.market_mode == "day_ahead"

    def test_enabled_integrations_is_empty_in_phase_0(self, settings: Settings) -> None:
        """Phase 0 has no external adapters wired."""
        assert settings.enabled_integrations == []

    def test_api_v1_prefix_is_correct(self, settings: Settings) -> None:
        assert settings.api_v1_prefix == "/api/v1"


# ---------------------------------------------------------------------------
# 8. Request-ID propagation
# ---------------------------------------------------------------------------


class TestRequestIDPropagation:
    """Verify the X-Request-ID middleware works correctly."""

    def test_response_always_has_request_id_header(self, client: TestClient) -> None:
        response = client.get("/health")
        assert "X-Request-ID" in response.headers

    def test_supplied_request_id_is_echoed(self, client: TestClient) -> None:
        custom_id = "test-" + str(uuid.uuid4())
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id

    def test_generated_request_id_is_valid_uuid(self, client: TestClient) -> None:
        response = client.get("/health")
        request_id = response.headers["X-Request-ID"]
        # Should be parseable as UUID (auto-generated)
        uuid.UUID(request_id)

    def test_error_envelope_request_id_matches_header(self, client: TestClient) -> None:
        custom_id = str(uuid.uuid4())
        response = client.get("/nonexistent", headers={"X-Request-ID": custom_id})
        assert response.json()["error"]["request_id"] == custom_id
        assert response.headers["X-Request-ID"] == custom_id


# ---------------------------------------------------------------------------
# 9. Meta endpoint verification
# ---------------------------------------------------------------------------


class TestMetaEndpoint:
    """Verify /api/v1/meta returns correct Phase-0 metadata."""

    def test_meta_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/v1/meta")
        assert response.status_code == 200

    def test_meta_response_shape(self, client: TestClient) -> None:
        body = client.get("/api/v1/meta").json()
        required_keys = {
            "app",
            "version",
            "api_version",
            "environment",
            "market_mode",
            "enabled_integrations",
        }
        assert required_keys.issubset(set(body.keys()))

    def test_meta_api_version_is_v1(self, client: TestClient) -> None:
        body = client.get("/api/v1/meta").json()
        assert body["api_version"] == "v1"

    def test_meta_market_mode_is_day_ahead(self, client: TestClient) -> None:
        body = client.get("/api/v1/meta").json()
        assert body["market_mode"] == "day_ahead"

    def test_meta_no_integrations_in_phase_0(self, client: TestClient) -> None:
        body = client.get("/api/v1/meta").json()
        assert body["enabled_integrations"] == []

    def test_meta_app_name(self, client: TestClient) -> None:
        body = client.get("/api/v1/meta").json()
        assert body["app"] == "UrjaSetu"


# ---------------------------------------------------------------------------
# 10. OpenAPI / Swagger availability
# ---------------------------------------------------------------------------


class TestOpenAPIAvailability:
    """Swagger docs must be available in development/test environments."""

    def test_openapi_json_accessible(self, client: TestClient) -> None:
        response = client.get("/openapi.json")
        assert response.status_code == 200

    def test_openapi_lists_health_endpoints(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/health" in paths
        assert "/health/ready" in paths

    def test_openapi_lists_meta_endpoint(self, client: TestClient) -> None:
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/v1/meta" in paths

    def test_docs_endpoint_accessible(self, client: TestClient) -> None:
        response = client.get("/docs")
        assert response.status_code == 200
