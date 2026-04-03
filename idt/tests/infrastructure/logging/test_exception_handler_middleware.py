"""Tests for ExceptionHandlerMiddleware."""

import json
import logging
import pytest
from io import StringIO

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.infrastructure.logging.middleware import (
    ExceptionHandlerMiddleware,
    RequestLoggingMiddleware,
)
from src.infrastructure.logging import StructuredLogger
from src.infrastructure.logging.formatters import StructuredFormatter


class TestExceptionHandlerMiddleware:
    """ExceptionHandlerMiddleware 테스트."""

    @pytest.fixture
    def log_stream(self):
        """로그 출력 캡처 fixture."""
        return StringIO()

    @pytest.fixture
    def logger(self, log_stream):
        """테스트용 로거 fixture."""
        logger = StructuredLogger(
            name="test_exception_middleware", level=logging.DEBUG
        )
        logger._logger.handlers.clear()
        handler = logging.StreamHandler(log_stream)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(StructuredFormatter())
        logger._logger.addHandler(handler)
        return logger

    @pytest.fixture
    def app_debug_true(self, logger):
        """DEBUG=true인 테스트 앱 fixture."""
        app = FastAPI()
        # ExceptionHandler가 먼저 추가되어야 RequestLogging 이후 발생하는 에러를 잡음
        app.add_middleware(RequestLoggingMiddleware, logger=logger)
        app.add_middleware(ExceptionHandlerMiddleware, logger=logger, debug=True)

        @app.get("/success")
        async def success_endpoint():
            return {"status": "ok"}

        @app.get("/error")
        async def error_endpoint():
            raise ValueError("Test error message")

        @app.get("/runtime-error")
        async def runtime_error_endpoint():
            raise RuntimeError("Runtime failure")

        return app

    @pytest.fixture
    def app_debug_false(self, logger):
        """DEBUG=false인 테스트 앱 fixture."""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, logger=logger)
        app.add_middleware(ExceptionHandlerMiddleware, logger=logger, debug=False)

        @app.get("/error")
        async def error_endpoint():
            raise ValueError("Test error message")

        return app

    @pytest.fixture
    def client_debug_true(self, app_debug_true):
        """DEBUG=true 테스트 클라이언트 fixture."""
        return TestClient(app_debug_true, raise_server_exceptions=False)

    @pytest.fixture
    def client_debug_false(self, app_debug_false):
        """DEBUG=false 테스트 클라이언트 fixture."""
        return TestClient(app_debug_false, raise_server_exceptions=False)

    def test_exception_returns_500_status(self, client_debug_true):
        """예외 발생 시 500 상태 코드를 반환한다."""
        response = client_debug_true.get("/error")
        assert response.status_code == 500

    def test_exception_returns_json_response(self, client_debug_true):
        """예외 발생 시 JSON 응답을 반환한다."""
        response = client_debug_true.get("/error")
        data = response.json()
        assert "request_id" in data
        assert "error" in data

    def test_exception_response_includes_error_type(self, client_debug_true):
        """에러 응답에 error type이 포함된다."""
        response = client_debug_true.get("/error")
        data = response.json()
        assert data["error"]["type"] == "ValueError"

    def test_exception_response_includes_error_message(self, client_debug_true):
        """에러 응답에 error message가 포함된다."""
        response = client_debug_true.get("/error")
        data = response.json()
        assert data["error"]["message"] == "Test error message"

    def test_exception_logged_with_stacktrace(self, client_debug_true, log_stream):
        """예외가 스택 트레이스와 함께 로깅된다."""
        client_debug_true.get("/error")
        logs = log_stream.getvalue()
        assert "error" in logs.lower()
        assert "Traceback" in logs

    def test_debug_true_includes_stacktrace_in_response(self, client_debug_true):
        """DEBUG=true일 때 응답에 스택 트레이스가 포함된다."""
        response = client_debug_true.get("/error")
        data = response.json()
        assert "stacktrace" in data["error"]
        assert "Traceback" in data["error"]["stacktrace"]

    def test_debug_false_excludes_stacktrace_in_response(self, client_debug_false):
        """DEBUG=false일 때 응답에 스택 트레이스가 포함되지 않는다."""
        response = client_debug_false.get("/error")
        data = response.json()
        # stacktrace가 없거나 None이어야 함
        assert data["error"].get("stacktrace") is None

    def test_request_id_included_in_error_response(self, client_debug_true):
        """에러 응답에 request_id가 포함된다."""
        response = client_debug_true.get("/error")
        data = response.json()
        assert "request_id" in data
        assert data["request_id"] is not None

    def test_successful_request_not_affected(self, client_debug_true):
        """정상 요청은 영향 받지 않는다."""
        response = client_debug_true.get("/success")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_different_exception_types_handled(self, client_debug_true):
        """다양한 예외 타입이 처리된다."""
        response = client_debug_true.get("/runtime-error")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["type"] == "RuntimeError"
        assert data["error"]["message"] == "Runtime failure"

    def test_error_logged_at_error_level(self, client_debug_true, log_stream):
        """에러가 ERROR 레벨로 로깅된다."""
        client_debug_true.get("/error")
        logs = log_stream.getvalue()
        assert '"level": "ERROR"' in logs
