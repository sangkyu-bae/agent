"""Tests for RequestLoggingMiddleware."""

import json
import logging
import pytest
from io import StringIO
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.infrastructure.logging.middleware import RequestLoggingMiddleware
from src.infrastructure.logging import StructuredLogger
from src.infrastructure.logging.formatters import StructuredFormatter


class TestRequestLoggingMiddleware:
    """RequestLoggingMiddleware 테스트."""

    @pytest.fixture
    def log_stream(self):
        """로그 출력 캡처 fixture."""
        return StringIO()

    @pytest.fixture
    def logger(self, log_stream):
        """테스트용 로거 fixture."""
        logger = StructuredLogger(name="test_request_middleware", level=logging.DEBUG)
        logger._logger.handlers.clear()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(StructuredFormatter())
        logger._logger.addHandler(handler)
        return logger

    @pytest.fixture
    def app(self, logger):
        """테스트용 FastAPI 앱 fixture."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        @app.post("/submit")
        async def submit_endpoint():
            return {"submitted": True}

        return app

    @pytest.fixture
    def client(self, app):
        """테스트 클라이언트 fixture."""
        return TestClient(app)

    def test_request_id_is_generated(self, client, log_stream):
        """request_id가 생성된다."""
        response = client.get("/test")
        assert response.status_code == 200

        logs = log_stream.getvalue().strip().split("\n")
        assert len(logs) >= 1
        parsed = json.loads(logs[0])
        assert "request_id" in parsed

    def test_request_id_in_response_header(self, client):
        """응답 헤더에 X-Request-ID가 포함된다."""
        response = client.get("/test")
        assert "X-Request-ID" in response.headers

    def test_request_log_includes_method(self, client, log_stream):
        """요청 로그에 method가 포함된다."""
        client.get("/test")
        logs = log_stream.getvalue().strip().split("\n")
        parsed = json.loads(logs[0])
        assert parsed["method"] == "GET"

    def test_request_log_includes_endpoint(self, client, log_stream):
        """요청 로그에 endpoint가 포함된다."""
        client.get("/test")
        logs = log_stream.getvalue().strip().split("\n")
        parsed = json.loads(logs[0])
        assert parsed["endpoint"] == "/test"

    def test_request_log_includes_query_params(self, client, log_stream):
        """요청 로그에 query_params가 포함된다."""
        client.get("/test?foo=bar&baz=123")
        logs = log_stream.getvalue().strip().split("\n")
        parsed = json.loads(logs[0])
        assert "query_params" in parsed
        assert parsed["query_params"]["foo"] == "bar"
        assert parsed["query_params"]["baz"] == "123"

    def test_response_log_includes_status_code(self, client, log_stream):
        """응답 로그에 status_code가 포함된다."""
        client.get("/test")
        logs = log_stream.getvalue().strip().split("\n")
        # 응답 로그 찾기 (두 번째 로그)
        response_log = None
        for log in logs:
            parsed = json.loads(log)
            if "status_code" in parsed:
                response_log = parsed
                break
        assert response_log is not None
        assert response_log["status_code"] == 200

    def test_response_log_includes_process_time_ms(self, client, log_stream):
        """응답 로그에 process_time_ms가 포함된다."""
        client.get("/test")
        logs = log_stream.getvalue().strip().split("\n")
        response_log = None
        for log in logs:
            parsed = json.loads(log)
            if "process_time_ms" in parsed:
                response_log = parsed
                break
        assert response_log is not None
        assert "process_time_ms" in response_log
        assert isinstance(response_log["process_time_ms"], (int, float))

    def test_sensitive_data_is_masked_password(self, log_stream, logger):
        """password 필드가 마스킹된다."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.post("/login")
        async def login(request: Request):
            return {"status": "ok"}

        client = TestClient(app)
        client.post(
            "/login",
            json={"username": "test", "password": "secret123"},
        )

        logs = log_stream.getvalue()
        assert "secret123" not in logs
        assert "***MASKED***" in logs or "password" not in logs.lower()

    def test_sensitive_data_is_masked_token(self, log_stream, logger):
        """token 필드가 마스킹된다."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.post("/auth")
        async def auth(request: Request):
            return {"status": "ok"}

        client = TestClient(app)
        client.post(
            "/auth",
            json={"token": "abc123secret"},
        )

        logs = log_stream.getvalue()
        assert "abc123secret" not in logs

    def test_sensitive_data_is_masked_api_key(self, log_stream, logger):
        """api_key 필드가 마스킹된다."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)

        @app.post("/config")
        async def config(request: Request):
            return {"status": "ok"}

        client = TestClient(app)
        client.post(
            "/config",
            json={"api_key": "sk-secret-key-123"},
        )

        logs = log_stream.getvalue()
        assert "sk-secret-key-123" not in logs

    def test_post_method_is_logged(self, client, log_stream):
        """POST 메서드가 올바르게 로깅된다."""
        client.post("/submit")
        logs = log_stream.getvalue().strip().split("\n")
        parsed = json.loads(logs[0])
        assert parsed["method"] == "POST"

    def test_request_id_same_for_request_and_response(self, client, log_stream):
        """요청과 응답의 request_id가 동일하다."""
        client.get("/test")
        logs = log_stream.getvalue().strip().split("\n")
        request_ids = set()
        for log in logs:
            parsed = json.loads(log)
            if "request_id" in parsed:
                request_ids.add(parsed["request_id"])
        # 모든 로그의 request_id가 같아야 함
        assert len(request_ids) == 1
