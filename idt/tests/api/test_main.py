"""Tests for main application setup."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


class TestAppCreation:
    """Test FastAPI app creation."""

    def test_create_app_returns_fastapi_instance(self):
        """Test create_app returns FastAPI instance."""
        from src.api.main import create_app

        app = create_app()
        assert app is not None
        assert hasattr(app, "routes")

    def test_app_includes_document_upload_router(self):
        """Test app includes document upload router."""
        from src.api.main import create_app

        app = create_app()
        routes = [route.path for route in app.routes]

        assert "/api/v1/documents/upload" in routes or any(
            "/api/v1/documents" in str(route) for route in app.routes
        )


class TestDependencyConfiguration:
    """Test dependency configuration."""

    def test_dependency_override_is_set(self):
        """Test document processor dependency override is configured."""
        from src.api.main import create_app
        from src.api.routes.document_upload import get_document_processor

        app = create_app()

        # Check that dependency override is set
        assert get_document_processor in app.dependency_overrides

    def test_create_processor_function_exists(self):
        """Test create_processor function exists and is async."""
        from src.api.main import create_processor
        import asyncio

        assert asyncio.iscoroutinefunction(create_processor)


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_endpoint_returns_ok(self):
        """Test health endpoint returns ok status."""
        from src.api.main import create_app

        app = create_app()
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
